# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The learning library on the site; learning_library_rules.py has the rules
(scripts/verify_learning_library.py).

  Learning Content             a policy, SOP, manual, video, link,
                               presentation, toolbox talk or quiz, with its
                               version history; a new version asks everyone
                               who had it to read and acknowledge it again
  Learning Content Assignment  one per employee and content: Assigned, In
                               Progress, Completed, Passed or Failed; the
                               score, the attempts and when it was
                               acknowledged. Content tied to a training counts
                               for that training's requirement (learning.py)
  assign                       by a training rule's reach, by plant, section
                               or department, or by a list: in the background,
                               a hundred at a time, each person told once
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now, now_datetime, today

from hrms_addon.hrms_addon import learning_library_rules as rules

CONTENT, ASSIGNMENT, QUESTION, ATTEMPT, VERSION = ("Learning Content", "Learning Content Assignment",
                                                   "Learning Quiz Question", "Learning Content Attempt",
                                                   "Learning Content Version")
HR_ROLES = ("HR Manager", "HR User", "System Manager")
PART = 100
FIELDS = ["name", "learning_content", "employee", "status", "version", "attempts", "score", "acknowledged_on"]


def _is_hr():
    return bool(set(frappe.get_roles()) & set(HR_ROLES))


# ── The content ───────────────────────────────────────────────────────
def content_validate(doc):
    doc.title = (doc.title or "").strip()
    errors = rules.content_errors(dict(doc.as_dict(), questions=[row.as_dict() for row in doc.get("questions") or []]))
    errors += rules.quiz_errors([row.as_dict() for row in doc.get("questions") or []])
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(CONTENT))
    if doc.content_type == rules.QUIZ and not flt(doc.get("pass_mark")):
        doc.pass_mark = rules.PASS_MARK
    if doc.get("work_section") and not doc.get("branch"):
        doc.branch = frappe.db.get_value("Work Section", doc.work_section, "branch")
    before = doc.get_doc_before_save()
    if doc.is_new() or not cint(doc.get("version")):
        doc.version = cint(doc.get("version")) or 1
        if not doc.get("versions"):
            doc.append("versions", {"version": doc.version, "changed_on": now(), "changed_by": frappe.session.user,
                                    "notes": doc.get("version_notes") or _("First version")})
    elif rules.new_version(_facts(before), _facts(doc)):
        doc.version = cint(before.get("version")) + 1
        doc.append("versions", {"version": doc.version, "changed_on": now(), "changed_by": frappe.session.user,
                                "notes": doc.get("version_notes")})
        doc.flags.new_version = True
    doc.version_notes = None


def _facts(doc):
    return dict(doc.as_dict(), questions=[row.as_dict() for row in doc.get("questions") or []])


def content_on_update(doc):
    """A new version: everyone who had it reads it again, in the background."""
    if doc.flags.get("new_version"):
        frappe.enqueue("hrms_addon.hrms_addon.learning_library.reopen", queue="long", timeout=3600,
                       job_id="learning_content_version::%s" % doc.name, deduplicate=True, enqueue_after_commit=True,
                       content=doc.name, version=doc.version)


def reopen(content, version):
    """Those who completed, passed or acknowledged an older version asked to
    read the new one and acknowledge it again; each told once."""
    rows = frappe.get_all(ASSIGNMENT, filters={"learning_content": content, "status": ["!=", rules.WITHDRAWN],
                                               "version": ["<", cint(version)]},
                          fields=["name", "employee"], limit_page_length=0)
    for start in range(0, len(rows), PART):
        part = [row.name for row in rows[start:start + PART]]
        frappe.db.set_value(ASSIGNMENT, {"name": ["in", part]},
                            {"status": rules.ASSIGNED, "version": cint(version), "acknowledged_on": None,
                             "completed_on": None}, update_modified=False)
        frappe.db.commit()
    _tell([row.employee for row in rows], content, _("A new version of {0} is out: read it and acknowledge it."))
    _refresh([row.employee for row in rows], content)
    return len(rows)


# ── Assigning ─────────────────────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def assign(content, training_rule=None, employees=None, branch=None, department=None, work_section=None,
           due_date=None):
    """Content given to many people: everyone a training rule reaches, the
    active people of a plant, section or department, or a list. Done in the
    background; returns how many are asked of."""
    frappe.has_permission(ASSIGNMENT, "create", throw=True)
    doc = frappe.get_doc(CONTENT, content)
    if not cint(doc.is_active):
        frappe.throw(_("{0} is not active.").format(doc.title), title=_(CONTENT))
    people = _people(training_rule, employees, branch, department, work_section)
    if not people:
        frappe.throw(_("Nobody to assign it to."), title=_(CONTENT))
    frappe.enqueue("hrms_addon.hrms_addon.learning_library.assign_many", queue="long", timeout=3600,
                   job_id="learning_content_assign::%s::%s" % (content, frappe.session.user), deduplicate=True,
                   enqueue_after_commit=True, content=content, employees=people, due_date=due_date,
                   source=training_rule or _("List"), user=frappe.session.user)
    return {"employees": len(people)}


def _people(training_rule=None, employees=None, branch=None, department=None, work_section=None):
    if employees:
        employees = json.loads(employees) if isinstance(employees, str) else list(employees)
        return sorted({employee for employee in employees if employee})
    if training_rule:
        from hrms_addon.hrms_addon import learning, learning_rules

        rule = learning._rules([training_rule], enabled_only=False).get(training_rule)
        if not rule:
            return []
        facts = learning._employees(frappe.get_all("Employee", filters={"status": "Active"}, pluck="name",
                                                   limit_page_length=0))
        return sorted(name for name, person in facts.items() if learning_rules.in_scope(rule, person))
    filters = {"status": "Active"}
    for field, value in (("branch", branch), ("department", department), ("custom_work_section", work_section)):
        if value:
            filters[field] = value
    if len(filters) == 1:
        return []
    return frappe.get_list("Employee", filters=filters, pluck="name", limit_page_length=0)


def assign_many(content, employees, due_date=None, source=None, user=None):
    """The background job: an assignment for each employee who has none yet,
    written a hundred at a time; each newly asked told once."""
    doc = frappe.get_doc(CONTENT, content)
    have = set(frappe.get_all(ASSIGNMENT, filters={"learning_content": content}, pluck="employee",
                              limit_page_length=0))
    fresh = [employee for employee in employees if employee not in have]
    stamp = now()
    made = 0
    for start in range(0, len(fresh), PART):
        part = fresh[start:start + PART]
        facts = {row.name: row for row in frappe.get_all(
            "Employee", filters={"name": ["in", part]},
            fields=["name", "employee_name", "branch", "department"] + (
                ["custom_work_section"] if frappe.get_meta("Employee").has_field("custom_work_section") else []),
            limit_page_length=0)}
        for employee in part:
            person = facts.get(employee)
            if not person:
                continue
            row = frappe.new_doc(ASSIGNMENT)
            row.update({"learning_content": content, "content_title": doc.title, "content_type": doc.content_type,
                        "training_program": doc.get("training_program"), "version": doc.version,
                        "employee": employee, "employee_name": person.employee_name, "branch": person.branch,
                        "department": person.department, "work_section": person.get("custom_work_section"),
                        "due_date": due_date or (str(frappe.utils.add_days(today(), cint(doc.get("days_to_complete"))))
                                                 if cint(doc.get("days_to_complete")) else None),
                        "status": rules.ASSIGNED, "assigned_by": user or frappe.session.user, "source": source})
            row.set_new_name()
            row.owner = row.modified_by = user or frappe.session.user
            row.creation = row.modified = stamp
            try:
                row.db_insert()
                made += 1
            except Exception as error:
                twice = tuple(getattr(frappe, name) for name in ("UniqueValidationError", "DuplicateEntryError")
                              if hasattr(frappe, name))
                if not (twice and isinstance(error, twice)):
                    raise
                frappe.clear_last_message()
        frappe.db.commit()
    _tell(fresh, content, _("{0} is assigned to you: open My Learning."))
    return made


def _tell(employees, content, text):
    title = frappe.db.get_value(CONTENT, content, "title") or content
    users = [user for user in frappe.get_all("Employee", filters={"name": ["in", list(employees) or [""]]},
                                             pluck="user_id", limit_page_length=0) if user]
    if users:
        from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

        from hrms_addon.hrms_addon import people

        enqueue_create_notification(users, {"type": people.alert_type(), "subject": text.format(title),
                                            "email_content": text.format(title),
                                            "link": "/app/learning-command-centre"})


def _refresh(employees, content):
    if frappe.db.get_value(CONTENT, content, "training_program"):
        from hrms_addon.hrms_addon import learning

        learning.refresh_later(employees)


# ── The employee's own ────────────────────────────────────────────────
def _mine(assignment):
    doc = frappe.get_doc(ASSIGNMENT, assignment)
    own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if doc.employee != own and not _is_hr():
        frappe.throw(_("This is not yours."), frappe.PermissionError)
    return doc


@frappe.whitelist(methods=["POST"])
def start(assignment):
    """Opened: In Progress; where to read it, or the quiz to take."""
    doc = _mine(assignment)
    if doc.status == rules.ASSIGNED:
        doc.db_set({"status": rules.IN_PROGRESS, "started_on": now_datetime()}, update_modified=False)
    content = frappe.db.get_value(CONTENT, doc.learning_content, ["file", "url", "body", "content_type",
                                                                   "needs_acknowledgement", "title"], as_dict=True)
    return dict(content, status=doc.status)


@frappe.whitelist(methods=["POST"])
def acknowledge(assignment):
    """Read and acknowledged: done, unless it is a quiz, which is done by passing it."""
    doc = _mine(assignment)
    content = frappe.db.get_value(CONTENT, doc.learning_content, ["content_type", "needs_acknowledgement"], as_dict=True)
    values = {"acknowledged_on": now_datetime()}
    if rules.completes(content.content_type, content.needs_acknowledgement, True):
        values.update(status=rules.COMPLETED, completed_on=today())
    doc.db_set(values, update_modified=False)
    _refresh([doc.employee], doc.learning_content)
    return {"status": values.get("status", doc.status)}


@frappe.whitelist()
def quiz(assignment):
    """The quiz's questions and options, never its answers."""
    doc = _mine(assignment)
    rows = frappe.get_all(QUESTION, filters={"parenttype": CONTENT, "parent": doc.learning_content},
                          fields=["name", "question", "options", "marks"], order_by="idx asc", limit_page_length=0)
    return {"title": doc.content_title, "pass_mark": frappe.db.get_value(CONTENT, doc.learning_content, "pass_mark"),
            "questions": [dict(row, options=rules.options_of(row.options)) for row in rows],
            "attempts": doc.attempts}


@frappe.whitelist(methods=["POST"])
def submit_quiz(assignment, answers):
    """An attempt scored: Passed at the pass mark, else Failed to try again;
    every attempt kept."""
    doc = _mine(assignment)
    answers = json.loads(answers) if isinstance(answers, str) else (answers or {})
    content = frappe.get_doc(CONTENT, doc.learning_content)
    if content.content_type != rules.QUIZ and not content.get("questions"):
        frappe.throw(_("{0} has no quiz.").format(content.title), title=_(CONTENT))
    percent, got, possible, wrong = rules.score([row.as_dict() for row in content.questions], answers)
    status = rules.after_attempt(percent, content.pass_mark)
    doc.append("attempt_log", {"attempted_on": now_datetime(), "score": percent, "passed": int(status == rules.PASSED),
                               "answers": json.dumps(answers)[:2000]})
    doc.attempts = cint(doc.attempts) + 1
    doc.score = percent
    doc.best_score = max(flt(doc.get("best_score")), percent)
    doc.status = rules.PASSED if status == rules.PASSED or doc.status == rules.PASSED else rules.FAILED
    if doc.status == rules.PASSED and not doc.get("completed_on"):
        doc.completed_on = today()
        doc.acknowledged_on = doc.get("acknowledged_on") or now_datetime()
    doc.flags.ignore_permissions = True
    doc.save()
    _refresh([doc.employee], doc.learning_content)
    return {"score": percent, "marks": got, "out_of": possible, "status": status, "wrong": len(wrong),
            "pass_mark": content.pass_mark}


def assignment_validate(doc):
    if doc.is_new():
        content = frappe.db.get_value(CONTENT, doc.learning_content, ["title", "content_type", "training_program",
                                                                      "version"], as_dict=True) or {}
        doc.content_title, doc.content_type = content.get("title"), content.get("content_type")
        doc.training_program, doc.version = content.get("training_program"), content.get("version") or 1
        facts = frappe.db.get_value("Employee", doc.employee, ["employee_name", "branch", "department"],
                                    as_dict=True) or {}
        doc.employee_name, doc.branch, doc.department = facts.get("employee_name"), facts.get("branch"), \
            facts.get("department")
        doc.assigned_by = doc.get("assigned_by") or frappe.session.user
        if frappe.db.exists(ASSIGNMENT, {"learning_content": doc.learning_content, "employee": doc.employee}):
            frappe.throw(_("{0} already has {1}.").format(doc.employee_name, doc.content_title), title=_(ASSIGNMENT))
    if doc.status not in rules.STATUSES:
        frappe.throw(_("Status is one of: {0}.").format(", ".join(rules.STATUSES)), title=_(ASSIGNMENT))


def assignment_query(user=None):
    """An employee lists their own; HR and managers what their roles reach."""
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if user == "Administrator" or roles & set(HR_ROLES + ("General Manager", "Head of Department", "Supervisor",
                                                           "Auditor")):
        return ""
    own = frappe.db.get_value("Employee", {"user_id": user}, "name")
    return "`tab{0}`.`employee` = {1}".format(ASSIGNMENT, frappe.db.escape(own or ""))


def my_assignments(employee):
    return frappe.get_all(ASSIGNMENT, filters={"employee": employee, "status": ["!=", rules.WITHDRAWN]},
                          fields=["name", "learning_content", "content_title", "content_type", "version", "status",
                                  "due_date", "score", "attempts", "acknowledged_on", "completed_on"],
                          order_by="due_date asc", limit_page_length=100)


def acknowledgement(filters):
    """For the SOP Acknowledgement report: each plant, section or content's
    assigned, done, pending, overdue and share done, counted by the database."""
    from hrms_addon.hrms_addon import queries

    filters = frappe._dict(filters or {})
    by = {"Plant": "branch", "Section": "work_section", "Content": "learning_content"}.get(filters.get("group_by")
                                                                                          or "Plant", "branch")
    conditions = {"status": ["!=", rules.WITHDRAWN]}
    if filters.get("content_type"):
        conditions["content_type"] = filters.content_type
    for field in ("learning_content", "branch", "work_section", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    rows = frappe.get_list(ASSIGNMENT, filters=conditions,
                           fields=[by, "status", queries.aggregate("COUNT", "*", "n")], group_by="%s, status" % by,
                           limit_page_length=0)
    late = frappe.get_list(ASSIGNMENT, filters=dict(conditions, status=["in", list(rules.OPEN)],
                                                    due_date=["between", ["2000-01-01", str(today())]]),
                           fields=[by, queries.aggregate("COUNT", "*", "n")], group_by=by, limit_page_length=0)
    overdue = {row.get(by) or "": row.n for row in late}
    groups = {}
    for row in rows:
        group = groups.setdefault(row.get(by) or "", {"group": row.get(by) or "", "assigned": 0, "done": 0})
        group["assigned"] += row.n
        if row.status in rules.DONE:
            group["done"] += row.n
    out = []
    for name, group in groups.items():
        group["pending"] = group["assigned"] - group["done"]
        group["overdue"] = overdue.get(name, 0)
        group["share"] = round(100.0 * group["done"] / group["assigned"], 1) if group["assigned"] else None
        out.append(group)
    return sorted(out, key=lambda row: (row["share"] if row["share"] is not None else 101, row["group"]))
