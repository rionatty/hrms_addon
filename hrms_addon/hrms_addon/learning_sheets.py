# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The entry sheets on the site; learning_sheets_rules.py has the rules
(scripts/verify_learning_sheets.py).

Each sheet is a document per section, session or supervisor with a row per
employee. Submitted, it is worked through in the background on the long
queue, a hundred rows at a time, each part committed; the sheet shows how far
it is and each row what was done with it.

  Skills Assessment Sheet   Get Employees fills a section's people against
                            the skills picked; each level given becomes (or
                            updates) that employee's Competency Assessment.
                            Reassessments falling due are put on one sheet a
                            section, for its supervisors
  Application Review Sheet  raised for each supervisor and session when its
                            trainees' reviews fall due; submitted, it answers
                            each Training Application Review
  Training Results Sheet    Get Trainees fills those who attended; their pre
                            and post tests go to Frappe HR's Training Result,
                            the attempt that counts for each
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import learning_sheets_rules as rules

SKILLS_SHEET, SKILLS_ROW = "Skills Assessment Sheet", "Skills Assessment Sheet Row"
REVIEW_SHEET, REVIEW_ROW = "Application Review Sheet", "Application Review Sheet Row"
RESULTS_SHEET, RESULTS_ROW = "Training Results Sheet", "Training Results Sheet Row"
ASSESSMENT, REVIEW, RESULT, EVENT = ("Competency Assessment", "Training Application Review", "Training Result",
                                     "Training Event")
HR_ROLES = ("HR Manager", "HR User", "System Manager")
SEE_ALL = HR_ROLES + ("General Manager", "Executive Director", "Auditor")
ANSWERS = ("applied", "behaviour", "competency")
JOBS = {SKILLS_SHEET: "hrms_addon.hrms_addon.learning_sheets.process_skills_sheet",
        REVIEW_SHEET: "hrms_addon.hrms_addon.learning_sheets.process_review_sheet",
        RESULTS_SHEET: "hrms_addon.hrms_addon.learning_sheets.process_results_sheet"}


# ── Common ────────────────────────────────────────────────────────────
def sheet_on_submit(doc):
    """Worked through in the background, the sheet showing how far it is."""
    doc.db_set({"status": rules.QUEUED, "rows_done": 0, "created": 0, "updated": 0, "failed": 0,
                "result_log": None}, update_modified=False)
    frappe.enqueue(JOBS[doc.doctype], queue="long", timeout=3600, job_id="%s::%s" % (doc.doctype, doc.name),
                   deduplicate=True, enqueue_after_commit=True, name=doc.name)


def sheet_on_cancel(doc):
    doc.db_set("status", "Cancelled", update_modified=False)


@frappe.whitelist(methods=["POST"])
def run_again(doctype, name):
    """A sheet that failed, or finished with rows that failed, worked through
    again: what was done is updated, not made twice."""
    if doctype not in JOBS:
        frappe.throw(_("Not a sheet."))
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("submit")
    if doc.docstatus != 1:
        frappe.throw(_("Submit the sheet first."), title=_(doctype))
    sheet_on_submit(doc)
    return {"status": rules.QUEUED}


def _work(doctype, name, child, worker):
    """The job: the sheet's rows a part at a time, each part committed, each
    row's result written on it; Failed with the reason where it stops."""
    doc = frappe.get_doc(doctype, name)
    doc.db_set("status", rules.PROCESSING, update_modified=False, commit=True)
    results, problems = [], []
    try:
        context = {}
        for part in rules.parts(doc.get("rows") or []):
            for row in part:
                frappe.db.savepoint("learning_sheet_row")
                try:
                    result, message, link = worker(doc, row, context)
                except Exception as error:
                    # only this row is undone: the part's other rows stand
                    frappe.db.rollback(save_point="learning_sheet_row")
                    frappe.clear_last_message()
                    result, message, link = rules.ROW_FAILED, str(error)[:140], None
                    problems.append("%s: %s" % (row.get("employee_name") or row.get("employee"), message))
                values = {"result": result, "message": message}
                if link is not None:
                    values[_link_field(child)] = link
                frappe.db.set_value(child, row.name, values, update_modified=False)
                results.append(result)
            doc.db_set(dict(_counts(results), rows_done=len(results)), update_modified=False, commit=True)
        after = context.get("after")
        if after:
            after(doc, context)
        doc.db_set(dict(_counts(results), rows_done=len(results), status=rules.DONE,
                        result_log="\n".join(problems[:200]) or None), update_modified=False, commit=True)
    except Exception as error:
        frappe.db.rollback()
        frappe.log_error(title="%s %s stopped" % (doctype, name))
        doc.db_set({"status": rules.FAILED, "result_log": _("It stopped: {0}").format(str(error)[:500])},
                   update_modified=False, commit=True)
    return rules.tally(results)


def _counts(results):
    """What the sheet shows: made, updated and failed (a skipped row says so on itself)."""
    found = rules.tally(results)
    return {"created": found["created"], "updated": found["updated"], "failed": found["failed"]}


def _link_field(child):
    return {SKILLS_ROW: "assessment", REVIEW_ROW: "review", RESULTS_ROW: "result_row"}[child]


# ── Skills Assessment Sheet ───────────────────────────────────────────
def skills_validate(doc):
    if doc.docstatus == 0:
        doc.status = "Draft"
    if doc.get("assessor"):
        doc.assessor_name = frappe.db.get_value("Employee", doc.assessor, "employee_name")
    if doc.get("work_section") and not doc.get("branch"):
        doc.branch = frappe.db.get_value("Work Section", doc.work_section, "branch")
    names = dict(frappe.get_all("Employee", filters={"name": ["in", list({row.employee for row in doc.rows}) or [""]]},
                                fields=["name", "employee_name"], as_list=True, limit_page_length=0))
    for row in doc.get("rows") or []:
        row.employee_name = names.get(row.employee) or row.employee_name
    errors = rules.skills_errors([row.as_dict() for row in doc.get("rows") or []], doc.get("assessor"),
                                 submitting=doc.docstatus == 1)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SKILLS_SHEET))


@frappe.whitelist()
def skill_rows(company=None, branch=None, work_section=None, department=None, skills=None, have=None):
    """The rows a sheet gets: each active employee of the section, department
    or plant, through the user's permissions, against each skill picked,
    with the level that counts for them now."""
    frappe.has_permission(SKILLS_SHEET, "write", throw=True)
    skills = frappe.parse_json(skills) if isinstance(skills, str) else (skills or [])
    have = frappe.parse_json(have) if isinstance(have, str) else (have or [])
    filters = {"status": "Active"}
    for field, value in (("company", company), ("branch", branch), ("department", department),
                         ("custom_work_section", work_section)):
        if value:
            filters[field] = value
    employees = frappe.get_list("Employee", filters=filters, fields=["name", "employee_name"],
                                order_by="employee_name asc", limit_page_length=0)
    current = {}
    if employees and skills:
        for row in frappe.get_all(ASSESSMENT, filters={"employee": ["in", [e.name for e in employees]],
                                                       "skill": ["in", skills], "status": ["!=", "Superseded"]},
                                  fields=["employee", "skill", "level"], limit_page_length=0):
            current[(row.employee, row.skill)] = row.level
    return rules.skills_rows(employees, skills, current, [tuple(pair) for pair in have])


def process_skills_sheet(name):
    return _work(SKILLS_SHEET, name, SKILLS_ROW, _assess)


def _assess(doc, row, context):
    """A row's level as the employee's assessment in the skill: the one this
    row made before, or the one of that day, updated; else a new one."""
    if not row.get("level"):
        return rules.SKIPPED, _("No level given."), None
    existing = row.get("assessment") if row.get("assessment") and frappe.db.exists(ASSESSMENT, row.assessment) \
        else frappe.db.get_value(ASSESSMENT, {"employee": row.employee, "skill": row.skill,
                                              "assessed_on": str(getdate(doc.assessed_on))}, "name")
    if existing:
        assessment = frappe.get_doc(ASSESSMENT, existing)
        assessment.update({"level": row.level, "assessed_by": doc.get("assessor"),
                           "evidence": row.get("evidence") or assessment.get("evidence")})
        assessment.flags.ignore_permissions = True
        assessment.save()
        return rules.UPDATED, None, assessment.name
    assessment = frappe.get_doc({"doctype": ASSESSMENT, "employee": row.employee, "skill": row.skill,
                                 "level": row.level, "assessed_on": doc.assessed_on, "assessed_by": doc.get("assessor"),
                                 "evidence": row.get("evidence"), "assessment_sheet": doc.name})
    assessment.flags.ignore_permissions = True
    assessment.insert()
    return rules.CREATED, None, assessment.name


def reassessment_sheets(due):
    """The reassessments newly due, one draft sheet a section (or department)
    and plant, added to an open one where there is one, put on the section's
    supervisors' lists. due: the assessments (employee, skill, branch,
    work_section, department, employee_name)."""
    from hrms_addon.hrms_addon import people

    groups = {}
    for row in due:
        key = (row.get("branch") or "", row.get("work_section") or "", "" if row.get("work_section")
               else (row.get("department") or ""))
        groups.setdefault(key, []).append(row)
    made = []
    for (branch, section, department), rows in sorted(groups.items()):
        filters = {"docstatus": 0, "purpose": rules.REASSESSMENT, "branch": branch or ["is", "not set"]}
        if section:
            filters["work_section"] = section
        else:
            filters["department"] = department or ["is", "not set"]
        name = frappe.db.get_value(SKILLS_SHEET, filters, "name")
        doc = frappe.get_doc(SKILLS_SHEET, name) if name else frappe.get_doc({
            "doctype": SKILLS_SHEET, "purpose": rules.REASSESSMENT, "branch": branch or None,
            "work_section": section or None, "department": department or None, "assessed_on": today(),
            "company": frappe.db.get_value("Employee", rows[0].employee, "company")})
        have = {(row.employee, row.skill) for row in doc.get("rows") or []}
        for row in rows:
            if (row.employee, row.skill) in have:
                continue
            doc.append("rows", {"employee": row.employee, "employee_name": row.get("employee_name"), "skill": row.skill,
                                "current_level": row.get("level")})
            if row.skill not in [item.skill for item in doc.get("skills") or []]:
                doc.append("skills", {"skill": row.skill})
        doc.flags.ignore_permissions = True
        doc.save()
        users = _section_supervisors(section) or _supervisors_of([row.employee for row in rows])
        if users:
            people.assign(SKILLS_SHEET, doc.name, users,
                          _("Reassess {0} skill(s) in {1}").format(len(rows), section or department or branch))
        made.append(doc.name)
    return made


def _section_supervisors(section):
    if not section:
        return []
    employees = frappe.get_all("Work Section Supervisor", filters={"parenttype": "Work Section", "parent": section,
                                                                  "active": 1}, pluck="employee")
    return [user for user in frappe.get_all("Employee", filters={"name": ["in", employees or [""]]}, pluck="user_id")
            if user]


def _supervisors_of(employees):
    bosses = [boss for boss in frappe.get_all("Employee", filters={"name": ["in", employees or [""]]},
                                              pluck="reports_to") if boss]
    return list(dict.fromkeys(user for user in frappe.get_all("Employee", filters={"name": ["in", bosses or [""]]},
                                                               pluck="user_id") if user))


# ── Application Review Sheet ──────────────────────────────────────────
def review_sheet_for(event, supervisor, reviews, due_on):
    """The supervisor's sheet for a session: a row per review raised for
    their trainees, on their list once. Returns the sheet's name."""
    from hrms_addon.hrms_addon import people

    name = frappe.db.get_value(REVIEW_SHEET, {"training_event": event.name, "supervisor": supervisor,
                                              "docstatus": 0}, "name")
    doc = frappe.get_doc(REVIEW_SHEET, name) if name else frappe.get_doc({
        "doctype": REVIEW_SHEET, "training_event": event.name, "training_program": event.training_program,
        "supervisor": supervisor, "due_on": due_on})
    have = {row.review for row in doc.get("rows") or []}
    for review in reviews:
        if review.name not in have:
            doc.append("rows", {"review": review.name, "employee": review.employee,
                                "employee_name": review.employee_name})
    doc.flags.ignore_permissions = True
    doc.save()
    if doc.get("reviewer"):
        people.assign(REVIEW_SHEET, doc.name, [doc.reviewer],
                      _("How your team applies {0}: {1} trainee(s)").format(event.training_program or event.name,
                                                                           len(doc.rows)), date=due_on)
    return doc.name


def review_sheet_validate(doc):
    if doc.docstatus == 0:
        doc.status = "Draft"
    if doc.get("supervisor"):
        facts = frappe.db.get_value("Employee", doc.supervisor, ["employee_name", "user_id"], as_dict=True) or {}
        doc.supervisor_name, doc.reviewer = facts.get("employee_name"), facts.get("user_id")
    if doc.docstatus == 1:
        errors = rules.review_sheet_errors([row.as_dict() for row in doc.get("rows") or []], ANSWERS)
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(REVIEW_SHEET))


def process_review_sheet(name):
    return _work(REVIEW_SHEET, name, REVIEW_ROW, _answer)


def _answer(doc, row, context):
    if not row.get("review") or not frappe.db.exists(REVIEW, row.review):
        return rules.ROW_FAILED, _("Its review is gone."), None
    review = frappe.get_doc(REVIEW, row.review)
    review.update({field: row.get(field) for field in ANSWERS})
    review.update({"comments": row.get("comments"), "evidence": row.get("evidence")})
    review.flags.ignore_permissions = True
    review.save()
    frappe.db.set_value(REVIEW_ROW, row.name, "score", review.score, update_modified=False)
    return rules.UPDATED, None, review.name


def review_sheet_query(user=None):
    """A supervisor lists their own sheets; HR and management all."""
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & set(SEE_ALL):
        return ""
    return "`tab{0}`.`reviewer` = {1}".format(REVIEW_SHEET, frappe.db.escape(user))


def review_sheet_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & set(HR_ROLES):
        return True
    if set(frappe.get_roles(user)) & set(SEE_ALL):
        return ptype in (None, "read", "print", "email", "report", "export")
    return doc.get("reviewer") == user


# ── Training Results Sheet ────────────────────────────────────────────
@frappe.whitelist()
def trainees(training_event):
    """Those who attended the session, for the sheet's rows; and its pass mark."""
    frappe.has_permission(RESULTS_SHEET, "write", throw=True)
    event = frappe.db.get_value(EVENT, training_event, ["training_program"], as_dict=True) or {}
    rows = frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "parent": training_event,
                                                              "attendance": "Present"},
                          fields=["employee", "employee_name"], order_by="idx asc", limit_page_length=0)
    return {"rows": rows, "pass_mark": _pass_mark(event.get("training_program"))}


def _pass_mark(programme):
    from hrms_addon.hrms_addon import training_rules

    mark = flt(frappe.db.get_value("Training Program", programme, "custom_pass_mark")) if programme else 0
    return mark or training_rules.PASS_MARK


def results_validate(doc):
    if doc.docstatus == 0:
        doc.status = "Draft"
    doc.training_program = frappe.db.get_value(EVENT, doc.training_event, "training_program")
    doc.pass_mark = _pass_mark(doc.training_program)
    present = set(frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "parent": doc.training_event,
                                                                     "attendance": "Present"}, pluck="employee"))
    errors = rules.results_errors([row.as_dict() for row in doc.get("rows") or []], present, doc.get("out_of"))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(RESULTS_SHEET))
    for row in doc.get("rows") or []:
        row.attempt = cint(row.get("attempt")) or 1
        row.assessment_type = row.get("assessment_type") or doc.get("assessment_type")
        found = rules.result_row(row.as_dict(), doc.get("out_of"), doc.pass_mark)
        row.gain, row.passed = found["gain"] or 0, found["passed"] or 0


def process_results_sheet(name):
    return _work(RESULTS_SHEET, name, RESULTS_ROW, _result)


def _result(doc, row, context):
    """Each trainee's attempt that counts goes on the session's Training
    Result, made where there is none, submitted once filled."""
    if "latest" not in context:
        context["latest"] = rules.latest_attempts([item.as_dict() for item in doc.rows])
        context["result"] = _the_result(doc)
        context["after"] = _close_result
    if context["latest"].get(row.employee, {}).get("name") != row.name:
        return rules.SKIPPED, _("A later attempt counts."), None
    result = context["result"]
    found = rules.result_row(row.as_dict(), doc.get("out_of"), doc.pass_mark)
    values = {"custom_marks": found["post_percent"], "custom_pre_test": found["pre_percent"],
              "custom_gain": found["gain"], "custom_attempt": cint(row.attempt) or 1,
              "custom_assessment_type": row.get("assessment_type") or doc.get("assessment_type")}
    line = next((item for item in result.employees if item.employee == row.employee), None)
    if line is None:
        if result.docstatus == 1:
            return rules.ROW_FAILED, _("Not on the submitted result: add them to it first."), None
        line = result.append("employees", {"employee": row.employee, "employee_name": row.employee_name})
        outcome = rules.CREATED
    else:
        outcome = rules.UPDATED
    line.update(values)
    context["changed"] = True
    return outcome, None, result.name


def _the_result(doc):
    name = frappe.db.get_value(RESULT, {"training_event": doc.training_event, "docstatus": ["<", 2]}, "name")
    if name:
        return frappe.get_doc(RESULT, name)
    return frappe.get_doc({"doctype": RESULT, "training_event": doc.training_event, "employees": []})


def _close_result(doc, context):
    """The result saved once with every trainee, and submitted when new."""
    result = context.get("result")
    if not result or not context.get("changed"):
        return
    result.flags.ignore_permissions = True
    if result.is_new():
        result.insert()
    if result.docstatus == 0:
        result.save()
        result.submit()
    else:
        result.save()
    doc.db_set("training_result", result.name, update_modified=False)
