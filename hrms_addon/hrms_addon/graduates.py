# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The graduate pipeline in depth, on the site. The rules are in
graduate_rules.py (scripts/verify_graduates.py).

  cohort_validate      a Graduate Cohort: its milestones in order, one
                       deciding confirmation; its trainees counted by stage
  trainee_milestones   a trainee joining a cohort gets the cohort's 30, 60
                       and 90 day milestones, dated from their start
  rotation_assessment_* the rotation supervisor's assessment of a stint:
                       the stint read from the trainee, the criteria from
                       Talent Settings, a score and a recommendation;
                       submitted, it is written onto the stint
  session_*            a mentor's Mentoring Session: only the mentor writes
                       it; the programme counts its sessions
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import graduate_rules as rules, talent_jobs

COHORT, TRAINEE, ROTATION, ASSESSMENT, SESSION, PROGRAM = (
    "Graduate Cohort", "Graduate Trainee Program", "Trainee Rotation", "Rotation Assessment", "Mentoring Session",
    "Talent Program")
WHOLE = ("System Manager", "HR Manager", "HR User", "Talent Council")


# ── The cohort ────────────────────────────────────────────────────────
def cohort_validate(doc):
    if not doc.get("milestones"):
        doc.set("milestones", [{"milestone": name, "days_after_start": days, "final": final}
                               for name, days, final in rules.TEMPLATE])
    errors = rules.cohort_errors({"milestones": [row.as_dict() for row in doc.milestones],
                                  "start_date": doc.get("start_date"), "end_date": doc.get("end_date")})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(COHORT))
    if not doc.is_new():
        count_cohort(doc)


def count_cohort(doc):
    rows = frappe.db.sql("""select workflow_state as stage, count(*) as n from `tabGraduate Trainee Program`
                            where cohort = %(cohort)s and docstatus < 2 group by workflow_state""",
                         {"cohort": doc.name}, as_dict=True)
    stages = {row.stage or "Recruited": cint(row.n) for row in rows}
    doc.trainees = sum(stages.values())
    doc.confirmed = stages.get("Confirmed", 0)
    doc.exited = stages.get("Exited", 0)
    doc.in_programme = doc.trainees - doc.confirmed - doc.exited


def trainee_milestones(doc):
    """A trainee in a cohort gets its milestones, once, from their start."""
    if doc.get("milestones") or not doc.get("start_date") or doc.docstatus != 0:
        return
    template = []
    if doc.get("cohort") and frappe.db.exists(COHORT, doc.cohort):
        template = frappe.get_all("Cohort Milestone", filters={"parent": doc.cohort, "parenttype": COHORT},
                                  fields=["milestone", "days_after_start"], order_by="idx asc")
    for row in rules.milestones_from(template, doc.start_date):
        doc.append("milestones", row)


def cohort_of_text(name, company=None):
    """A cohort by name, made where none is kept yet (an applicant hired into
    a cohort typed on the way)."""
    if not name or frappe.db.exists(COHORT, name):
        return name
    doc = frappe.get_doc({"doctype": COHORT, "cohort_name": name, "company": company,
                          "intake_year": getdate(today()).year})
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


# ── The rotation supervisor's assessment ──────────────────────────────
def rotation_assessment_validate(doc):
    trainee = frappe.get_doc(TRAINEE, doc.trainee_program)
    stint = _stint(trainee, doc)
    if stint:
        doc.rotation = stint.name
        for field in ("department", "branch", "from_date", "to_date"):
            doc.set(field, stint.get(field))
    if not doc.get("criteria"):
        names = [row.criterion for row in masters_criteria()] or list(rules.CRITERIA)
        doc.set("criteria", [{"criterion": name} for name in names])
    doc.overall_score = rules.rotation_score([row.as_dict() for row in doc.criteria])
    if doc.docstatus == 1:
        errors = rules.rotation_assessment_errors({
            "trainee_program": doc.trainee_program, "rotation": doc.get("rotation"), "supervisor": doc.supervisor,
            "rotation_supervisor": stint.supervisor if stint else None,
            "criteria": [row.as_dict() for row in doc.criteria], "recommendation": doc.get("recommendation")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(ASSESSMENT))
    me = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not set(frappe.get_roles()) & {"System Manager", "HR Manager", "HR User"} and me != doc.supervisor:
        frappe.throw(_("A stint is assessed by its own rotation supervisor."), frappe.PermissionError)


def masters_criteria():
    try:
        return frappe.get_single("Talent Settings").get("rotation_criteria") or []
    except Exception:
        return []


def _stint(trainee, doc):
    """The stint assessed: the one named, else the supervisor's current one,
    else their latest begun."""
    rows = trainee.get("rotations") or []
    if doc.get("rotation"):
        return next((row for row in rows if row.name == doc.rotation), None)
    day = getdate(doc.get("assessed_on") or today())
    theirs = [row for row in rows if row.get("supervisor") == doc.get("supervisor") and row.get("from_date")
              and getdate(row.from_date) <= day]
    current = [row for row in theirs if not row.get("to_date") or getdate(row.to_date) >= day]
    unassessed = [row for row in (current or theirs) if not row.get("assessment")]
    found = unassessed or current or theirs
    return found[-1] if found else None


def rotation_assessment_on_submit(doc):
    outcome = rules.rotation_outcome(doc.recommendation, doc.get("strengths"), doc.get("development_areas"))
    frappe.db.set_value(ROTATION, doc.rotation, {"score": doc.overall_score, "outcome": outcome, "completed": 1,
                                                 "assessment": doc.name, "recommendation": doc.recommendation},
                        update_modified=False)
    _count_rotations(doc.trainee_program)
    trainee = frappe.db.get_value(TRAINEE, doc.trainee_program, ["trainee_name", "mentor", "home_branch",
                                                                 "home_department"], as_dict=True) or {}
    from hrms_addon.hrms_addon import people

    users = list(people.hr_officers(trainee.get("home_branch"), trainee.get("home_department")))
    mentor = frappe.db.get_value("Employee", trainee.get("mentor"), "user_id") if trainee.get("mentor") else None
    talent_jobs.tell(users + [mentor], TRAINEE, doc.trainee_program,
                     _("{0}'s stint in {1} is assessed: {2} out of 100, {3}.").format(
                         trainee.get("trainee_name"), doc.get("department") or _("the rotation"),
                         doc.overall_score, doc.recommendation))


def rotation_assessment_on_cancel(doc):
    if doc.get("rotation") and frappe.db.get_value(ROTATION, doc.rotation, "assessment") == doc.name:
        frappe.db.set_value(ROTATION, doc.rotation, {"score": None, "outcome": None, "completed": 0,
                                                     "assessment": None, "recommendation": None},
                            update_modified=False)
    _count_rotations(doc.trainee_program)


def _count_rotations(trainee):
    count = frappe.db.count(ASSESSMENT, {"trainee_program": trainee, "docstatus": 1})
    frappe.db.set_value(TRAINEE, trainee, "rotation_assessments", count, update_modified=False)


# ── The mentor's sessions ─────────────────────────────────────────────
def session_validate(doc):
    if doc.get("trainee_program"):
        found = frappe.db.get_value(TRAINEE, doc.trainee_program, ["employee", "trainee_name", "mentor"],
                                    as_dict=True) or {}
        doc.mentee, doc.mentee_name = found.get("employee"), found.get("trainee_name")
        doc.mentor = doc.get("mentor") or found.get("mentor")
    elif doc.get("talent_program"):
        found = frappe.db.get_value(PROGRAM, doc.talent_program, ["employee", "employee_name", "mentor"],
                                    as_dict=True) or {}
        doc.mentee, doc.mentee_name = found.get("employee"), found.get("employee_name")
        doc.mentor = doc.get("mentor") or found.get("mentor")
    errors = rules.mentoring_errors({"mentor": doc.get("mentor"), "mentee": doc.get("mentee"),
                                     "trainee_program": doc.get("trainee_program"),
                                     "talent_program": doc.get("talent_program"), "session_date": doc.session_date,
                                     "topics": doc.get("topics"), "mode": doc.get("mode"), "today": today()})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SESSION))
    if not rules.may_edit_session(_me(), doc.mentor, frappe.get_roles()):
        frappe.throw(_("Only the mentor writes their mentoring sessions."), frappe.PermissionError)


def session_on_update(doc):
    _count_sessions(doc)


def session_on_trash(doc):
    if not rules.may_edit_session(_me(), doc.mentor, frappe.get_roles()):
        frappe.throw(_("Only the mentor writes their mentoring sessions."), frappe.PermissionError)
    _count_sessions(doc, leaving=doc.name)


def _count_sessions(doc, leaving=None):
    for field, doctype in (("trainee_program", TRAINEE), ("talent_program", PROGRAM)):
        if doc.get(field):
            filters = {field: doc.get(field)}
            if leaving:
                filters["name"] = ["!=", leaving]
            frappe.db.set_value(doctype, doc.get(field), "mentoring_sessions", frappe.db.count(SESSION, filters),
                                update_modified=False)


def _me(user=None):
    return frappe.db.get_value("Employee", {"user_id": user or frappe.session.user}, "name")


def session_has_permission(doc, ptype=None, user=None):
    """The mentor writes their sessions; HR and the council read them all;
    the mentee reads their own."""
    user = user or frappe.session.user
    roles = frappe.get_roles(user)
    me = _me(user)
    if ptype in (None, "read", "print", "email", "report", "export", "share"):
        return bool(set(roles) & set(WHOLE)) or bool(me and me in (doc.get("mentor"), doc.get("mentee")))
    return bool(rules.may_edit_session(me, doc.get("mentor"), roles)) or (ptype == "create" and not doc.get("mentor"))


def session_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & set(WHOLE):
        return ""
    me = _me(user)
    if not me:
        return "1=0"
    quoted = frappe.db.escape(me)
    return "(`tabMentoring Session`.`mentor` = {0} or `tabMentoring Session`.`mentee` = {0})".format(quoted)


def rotation_has_permission(doc, ptype=None, user=None):
    """A rotation supervisor opens the assessments that are theirs; HR, the
    council and the trainee's mentor read every one."""
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles & set(WHOLE):
        return True
    me = _me(user)
    if not me:
        return False
    if doc.get("supervisor") == me:
        return True
    mentor = frappe.db.get_value(TRAINEE, doc.get("trainee_program"), "mentor") if doc.get("trainee_program") else None
    return ptype in (None, "read", "print") and mentor == me


def rotation_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & set(WHOLE):
        return ""
    me = _me(user)
    if not me:
        return "1=0"
    quoted = frappe.db.escape(me)
    return ("(`tabRotation Assessment`.`supervisor` = {0} or exists (select 1 from `tabGraduate Trainee Program` "
            "ha_trainee where ha_trainee.name = `tabRotation Assessment`.`trainee_program` and ha_trainee.mentor = {0}))"
            ).format(quoted)


def funnel(company=None):
    """Trainees by cohort and stage, as the page draws them."""
    condition, values = "", {}
    if company:
        condition, values = " and company = %(company)s", {"company": company}
    rows = frappe.db.sql("""select cohort, workflow_state as stage, count(*) as n
                            from `tabGraduate Trainee Program` where docstatus < 2 {0}
                            group by cohort, workflow_state""".format(condition), values, as_dict=True)
    return rules.funnel(rows)
