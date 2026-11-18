# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent's bulk steps, run in the background (Luuka have more than 2,000
people in three plants: a step over a whole review is too long for a
request, and one notification a document is a flood).

No Frappe import (scripts/verify_talent_jobs.py); talent_jobs.py runs them.

  a job      one bulk step over many documents (placements drafted, sent to
             the council, finalised or returned; a succession plan's roles
             sent on or confirmed; a calibration session applied), on the
             long queue, one at a time for the same review or plan, each
             document in a savepoint of its own and committed in chunks
  its log    a Talent Job Log: how far it has got, what was done, and each
             document it left with the reason
  a digest   what the step would have told people one document at a time,
             gathered and sent once to each person when the step ends
"""

CHUNK = 150
DIGEST_LINES = 15
QUEUED, RUNNING, DONE, PROBLEMS, FAILED = "Queued", "Running", "Done", "Done with Problems", "Failed"
STATUSES = (QUEUED, RUNNING, DONE, PROBLEMS, FAILED)
LIVE = (QUEUED, RUNNING)
# what each kind of job is called, for its log and its digest
KINDS = {
    "draft": "Draft Placements",
    "advance": "Placements Moved On",
    "plan_send": "Succession Plan Sent to the Council",
    "plan_finalise": "Succession Plan Finalised",
    "calibration": "Calibration Session Applied",
    "milestones": "Trainee Milestones Raised",
}


def job_id(kind, reference):
    """One job of a kind for the same document at a time."""
    return "hrms_addon_talent::%s::%s" % (kind, reference)


def chunks(items, size=CHUNK):
    """The items in runs of `size`, committed run by run."""
    items = list(items or [])
    size = max(1, int(size or CHUNK))
    return [items[start:start + size] for start in range(0, len(items), size)]


def progress(done, total):
    """How far a job has got, out of a hundred."""
    return round(100.0 * done / total, 1) if total else 100.0


def status(done, left, failed=False):
    if failed:
        return FAILED
    return PROBLEMS if left else DONE


def summary(kind, done, left, total):
    """The log's one line."""
    name = KINDS.get(kind, kind)
    if not total:
        return "%s: nothing to do." % name
    text = "%s: %d of %d done" % (name, done, total)
    return text + (", %d left with a reason." % left if left else ".")


def digest(entries, limit=DIGEST_LINES):
    """Everything a step would have told, one entry per person per
    document, as one message per person.

    entries: [(user, line, doctype, name)]. Returns {user: {"count",
    "lines": [(line, doctype, name)], "more"}}: the first `limit` lines, and
    how many more there were. The same line about the same document is told
    once."""
    out = {}
    for user, line, doctype, name in entries or []:
        if not user:
            continue
        entry = out.setdefault(user, {"count": 0, "lines": [], "seen": set()})
        key = (line, doctype, name)
        if key in entry["seen"]:
            continue
        entry["seen"].add(key)
        entry["count"] += 1
        if len(entry["lines"]) < limit:
            entry["lines"].append(key)
    for entry in out.values():
        entry["more"] = entry["count"] - len(entry["lines"])
        del entry["seen"]
    return out


def digest_subject(kind, reference_title, count):
    """The digest's subject: the step, what it ran over, and how much it
    has for the reader."""
    return "%s, %s: %d item%s for you" % (KINDS.get(kind, kind), reference_title or "", count,
                                          "" if count == 1 else "s")
