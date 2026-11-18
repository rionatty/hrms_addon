# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent's bulk steps in the background, and the one digest each person
gets from them. The rules are in talent_jobs_rules.py
(scripts/verify_talent_jobs.py).

  start     a Talent Job Log made and the step queued on the long queue,
            one at a time for the same review or plan
  run       the step: each document in a savepoint of its own, committed in
            chunks, its progress on the log and on the page that asked
  tell      people.notify, or a line of the step's digest while one runs
  assign    people.assign, or a quiet ToDo while a step runs: the digest is
            the one message
  flush     the digest sent, one message a person
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from hrms_addon.hrms_addon import people, talent_jobs_rules as rules

LOG = "Talent Job Log"
RUNNER = "hrms_addon.hrms_addon.talent_jobs.run"
EVENT = "talent_job"
_DIGEST = "ha_talent_digest"


# ── Starting a step ───────────────────────────────────────────────────
def start(kind, reference_doctype, reference_name, method, **kwargs):
    """Queue `method` (a dotted path taking the log first) over the
    reference, and return the log's name. A step of the same kind still
    running for the same document is refused."""
    job_id = rules.job_id(kind, reference_name)
    running = frappe.db.get_value(LOG, {"job_id": job_id, "status": ["in", list(rules.LIVE)]}, "name")
    if running:
        frappe.throw(_("{0} is already under way for {1}: {2}. You will be told when it is done.").format(
            _(rules.KINDS.get(kind, kind)), reference_name, running), title=_("Talent"))
    log = frappe.get_doc({"doctype": LOG, "job": rules.KINDS.get(kind, kind), "job_id": job_id,
                          "reference_doctype": reference_doctype, "reference_name": reference_name,
                          "status": rules.QUEUED, "started_by": frappe.session.user, "started_on": now_datetime()})
    log.flags.ignore_permissions = True
    log.insert()
    frappe.enqueue(RUNNER, queue="long", timeout=4 * 3600, job_id=job_id, deduplicate=True,
                   enqueue_after_commit=True, log=log.name, kind=kind, method=method, kwargs=kwargs)
    return log.name


def run(log, kind, method, kwargs=None):
    """The queued step. `method(context, **kwargs)` does the work through the
    context (items, each, chunked commits); whatever it tells people is
    gathered and sent once a person at the end."""
    context = Context(log, kind)
    frappe.flags[_DIGEST] = []
    try:
        frappe.get_attr(method)(context, **(kwargs or {}))
        context.finish()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="HRMS Addon: talent job %s" % log)
        context.finish(failed=True)
    finally:
        flush(context)
        frappe.flags[_DIGEST] = None
        frappe.db.commit()
    return context.result()


class Context:
    """What a step reports through: the documents it works on, one by one."""

    def __init__(self, log, kind):
        self.log, self.kind = log, kind
        self.total = self.done = 0
        self.left = []
        self.title = None
        frappe.db.set_value(LOG, log, "status", rules.RUNNING, update_modified=False)
        frappe.db.commit()

    def each(self, names, work, label=None):
        """Run work(name) over the names in chunks, each in a savepoint of its
        own: one that is refused takes back only what it wrote, and is left
        with its reason. label(name) says who the line is about."""
        names = list(names or [])
        self.total += len(names)
        number = 0
        for chunk in rules.chunks(names):
            for name in chunk:
                number += 1
                savepoint = "ha_talent_job_%d" % number
                frappe.db.savepoint(savepoint)
                try:
                    work(name)
                    self.done += 1
                except Exception as error:  # noqa: BLE001 - each document stands alone
                    frappe.db.rollback(save_point=savepoint)
                    frappe.clear_last_message()
                    self.left.append((name, label(name) if label else name, plain(error)))
            frappe.db.commit()
            self.progress()

    def progress(self):
        share = rules.progress(self.done + len(self.left), self.total)
        frappe.db.set_value(LOG, self.log, {"total": self.total, "done": self.done, "left_count": len(self.left),
                                            "progress": share}, update_modified=False)
        frappe.db.commit()
        user = frappe.db.get_value(LOG, self.log, "started_by")
        if user:
            frappe.publish_realtime(EVENT, {"log": self.log, "progress": share, "done": self.done,
                                            "left": len(self.left), "total": self.total}, user=user)

    def finish(self, failed=False):
        state = rules.status(self.done, len(self.left), failed)
        doc = frappe.get_doc(LOG, self.log)
        doc.update({"status": state, "finished_on": now_datetime(), "total": self.total, "done": self.done,
                    "left_count": len(self.left), "progress": 100 if not failed else doc.progress,
                    "summary": rules.summary(self.kind, self.done, len(self.left), self.total)})
        doctype = self.doctype or doc.reference_doctype
        doc.set("lines", [{"document_type": doctype, "document": name, "employee_name": who, "outcome": "Left",
                           "reason": why[:1000]} for name, who, why in self.left[:2000]])
        doc.flags.ignore_permissions = True
        doc.save()
        frappe.db.commit()
        if doc.started_by:
            frappe.publish_realtime(EVENT, {"log": self.log, "progress": 100, "done": self.done,
                                            "left": len(self.left), "total": self.total, "finished": 1,
                                            "status": state}, user=doc.started_by)

    doctype = None

    def result(self):
        return {"log": self.log, "done": self.done, "left": [[who, why] for _name, who, why in self.left]}


def plain(error):
    """A refusal as the user reads it: the message, without the markup."""
    text = str(error.args[0]) if getattr(error, "args", None) else str(error)
    return frappe.utils.strip_html(text).strip() or type(error).__name__


# ── Telling people ────────────────────────────────────────────────────
def collecting():
    return frappe.flags.get(_DIGEST) is not None


def tell(users, doctype, name, message):
    """people.notify, or a line of the running step's digest."""
    users = [user for user in dict.fromkeys(users or []) if user]
    if not users:
        return
    entries = frappe.flags.get(_DIGEST)
    if entries is None:
        people.notify(users, doctype, name, message)
        return
    entries.extend((user, message, doctype, name) for user in users)


def assign(doctype, name, users, description):
    """people.assign, or a ToDo put quietly while a step runs."""
    users = [user for user in dict.fromkeys(users or []) if user]
    if not collecting():
        people.assign(doctype, name, users, description)
        return
    for user in users:
        if frappe.db.exists("ToDo", {"reference_type": doctype, "reference_name": name, "allocated_to": user,
                                     "status": "Open"}):
            continue
        frappe.get_doc({"doctype": "ToDo", "allocated_to": user, "reference_type": doctype, "reference_name": name,
                        "description": description, "status": "Open", "priority": "Medium",
                        "assigned_by": frappe.session.user}).insert(ignore_permissions=True)


def flush(context):
    """The step's digest: one message a person, naming what is theirs."""
    entries = frappe.flags.get(_DIGEST) or []
    if not entries:
        return
    reference = frappe.db.get_value(LOG, context.log, ["reference_doctype", "reference_name"], as_dict=True) or {}
    for user, found in rules.digest(entries).items():
        lines = "".join("<li>%s</li>" % frappe.utils.escape_html(line) for line, _doctype, _name in found["lines"])
        if found["more"]:
            lines += "<li>%s</li>" % _("and {0} more").format(found["more"])
        subject = rules.digest_subject(context.kind, reference.get("reference_name"), found["count"])
        people.notify([user], LOG, context.log, subject, "<p>%s</p><ul>%s</ul>" % (subject, lines))
    frappe.flags[_DIGEST] = []


@frappe.whitelist()
def get_log(log):
    """A step's log, for the page that started it."""
    doc = frappe.get_doc(LOG, log)
    doc.check_permission("read")
    return {"name": doc.name, "status": doc.status, "progress": doc.progress, "done": doc.done,
            "left": doc.left_count, "total": doc.total, "summary": doc.summary,
            "lines": [[row.employee_name or row.document, row.reason] for row in doc.lines[:50]]}
