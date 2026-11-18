# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The entry sheets: the rules, without a Frappe import
(scripts/verify_learning_sheets.py). learning_sheets.py reads and writes the
site.

Data entry for many people at once (18 Nov 2026): one sheet per section,
session or supervisor with a row per employee, which creates or updates each
employee's own record in the background, in parts, and says what it did on
each row.

  Skills Assessment Sheet   a section's people against its skills, a level 1
                            to 5 each (a grid of employees by skills): a
                            Competency Assessment per employee per skill
  Application Review Sheet  a supervisor's trainees from one session: how
                            each applies it, into each Training Application
                            Review (level 3)
  Training Results Sheet    a session's trainees: their pre and post test,
                            the gain, the attempt and the kind of test, into
                            Frappe HR's Training Result (level 2)
"""

QUEUED, PROCESSING, DONE, FAILED = "Queued", "Processing", "Done", "Failed"
SHEET_STATUSES = ("Draft", QUEUED, PROCESSING, DONE, FAILED, "Cancelled")
CREATED, UPDATED, SKIPPED, ROW_FAILED = "Created", "Updated", "Skipped", "Failed"
ROW_RESULTS = (CREATED, UPDATED, SKIPPED, ROW_FAILED)
PART = 100
ASSESSMENT, REASSESSMENT = "Assessment", "Reassessment"
PURPOSES = (ASSESSMENT, REASSESSMENT)


# ── Skills Assessment Sheet ───────────────────────────────────────────
def skills_rows(employees, skills, current=None, have=()):
    """The sheet's rows: each employee against each skill, in order, with the
    level that counts for them now; the pairs it already has left out.

    employees: [{"name", "employee_name"}]; skills: [skill]; current:
    {(employee, skill): level}; have: [(employee, skill)]."""
    current, have = current or {}, set(have or ())
    rows = []
    for person in employees or ():
        for skill in skills or ():
            if (person["name"], skill) in have:
                continue
            rows.append({"employee": person["name"], "employee_name": person.get("employee_name"), "skill": skill,
                         "current_level": current.get((person["name"], skill))})
    return rows


def skills_errors(rows, assessor=None, submitting=False):
    """Why a skills sheet cannot be saved or sent."""
    errors = []
    seen = set()
    for row in rows or ():
        key = (row.get("employee"), row.get("skill"))
        if key in seen:
            errors.append("%s is listed twice for %s." % (row.get("employee_name") or row.get("employee"),
                                                          row.get("skill")))
            break
        seen.add(key)
    if assessor and any(row.get("employee") == assessor for row in rows or () if row.get("level")):
        errors.append("Nobody assesses themselves.")
    if submitting and not any(row.get("level") for row in rows or ()):
        errors.append("Give a level on at least one row.")
    return errors


def grid(rows):
    """The rows as a grid: {"employees": [(employee, name)], "skills": [skill],
    "cells": {(employee, skill): row index}} for the form to draw."""
    employees, skills, cells = [], [], {}
    for index, row in enumerate(rows or ()):
        if row.get("employee") not in [employee for employee, _name in employees]:
            employees.append((row.get("employee"), row.get("employee_name")))
        if row.get("skill") not in skills:
            skills.append(row.get("skill"))
        cells[(row.get("employee"), row.get("skill"))] = index
    return {"employees": employees, "skills": skills, "cells": cells}


# ── Application Review Sheet ──────────────────────────────────────────
def review_groups(trainees):
    """The trainees of a session grouped by the supervisor who reviews them:
    {supervisor: [employee]}; those with none left out."""
    groups = {}
    for row in trainees or ():
        if row.get("supervisor") and row.get("employee"):
            groups.setdefault(row["supervisor"], []).append(row["employee"])
    return groups


def review_sheet_errors(rows, answers):
    """Every trainee answered, and a reason where it was not applied.
    answers: the review's answer fields ("applied", "behaviour", "competency")."""
    errors = []
    for row in rows or ():
        missing = [field for field in answers if not row.get(field)]
        if missing:
            errors.append("Answer every question for %s." % (row.get("employee_name") or row.get("employee")))
            break
    for row in rows or ():
        if row.get("applied") == "Not Applied" and not (row.get("comments") or "").strip():
            errors.append("Say why %s has not applied it." % (row.get("employee_name") or row.get("employee")))
            break
    return errors


# ── Training Results Sheet ────────────────────────────────────────────
def percent_of(marks, out_of):
    """Marks as a percentage of what they were out of (100 by default)."""
    if marks in (None, ""):
        return None
    whole = _num(out_of) or 100.0
    return round(100.0 * _num(marks) / whole, 1)


def result_row(row, out_of, pass_mark):
    """A trainee's row worked out: the pre and post test as percentages, the
    gain, and whether the post test reaches the pass mark."""
    pre, post = percent_of(row.get("pre_test"), out_of), percent_of(row.get("post_test"), out_of)
    gain = round(post - pre, 1) if pre is not None and post is not None else None
    passed = None if post is None else int(post >= (_num(pass_mark) or 50))
    return {"pre_percent": pre, "post_percent": post, "gain": gain, "passed": passed}


def latest_attempts(rows):
    """The attempt that counts for each trainee: the highest number, then the
    later row. Returns {employee: row}."""
    found = {}
    for index, row in enumerate(rows or ()):
        employee = row.get("employee")
        if not employee:
            continue
        key = (int(_num(row.get("attempt")) or 1), index)
        if employee not in found or key > found[employee][0]:
            found[employee] = (key, row)
    return {employee: row for employee, (_key, row) in found.items()}


def results_errors(rows, present, out_of):
    """Why a results sheet cannot be saved: a trainee who did not attend, the
    same attempt twice, marks outside 0 and what they are out of."""
    errors = []
    whole = _num(out_of) or 100.0
    seen = set()
    for row in rows or ():
        name = row.get("employee_name") or row.get("employee")
        if row.get("employee") and present is not None and row.get("employee") not in present:
            errors.append("%s did not attend this training." % name)
            break
        key = (row.get("employee"), int(_num(row.get("attempt")) or 1))
        if key in seen:
            errors.append("%s's attempt %d is listed twice." % (name, key[1]))
            break
        seen.add(key)
        for field in ("pre_test", "post_test"):
            if row.get(field) not in (None, "") and not 0 <= _num(row.get(field)) <= whole:
                errors.append("%s's marks must be between 0 and %g." % (name, whole))
                return errors
    return errors


def learning_figures(rows):
    """Level 2 over a set of results: the average pre and post test, the
    average gain and the pass rate. rows: [{"pre", "post", "passed"}]."""
    pres = [_num(row["pre"]) for row in rows or () if row.get("pre") is not None]
    posts = [_num(row["post"]) for row in rows or () if row.get("post") is not None]
    gains = [_num(row["post"]) - _num(row["pre"]) for row in rows or ()
             if row.get("pre") is not None and row.get("post") is not None]
    judged = [row for row in rows or () if row.get("passed") is not None]
    return {"pre_test": _mean(pres), "post_test": _mean(posts), "gain": _mean(gains),
            "pass_rate": round(100.0 * sum(1 for row in judged if row["passed"]) / len(judged), 1) if judged else None}


# ── The background job ────────────────────────────────────────────────
def parts(rows, size=PART):
    rows = list(rows or ())
    return [rows[start:start + size] for start in range(0, len(rows), size)]


def tally(results):
    """{"created", "updated", "skipped", "failed"} from the rows' results."""
    out = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    for result in results or ():
        key = {CREATED: "created", UPDATED: "updated", SKIPPED: "skipped", ROW_FAILED: "failed"}.get(result)
        if key:
            out[key] += 1
    return out


def _mean(values):
    return round(sum(values) / len(values), 1) if values else None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
