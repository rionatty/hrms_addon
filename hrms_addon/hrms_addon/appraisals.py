# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance management on the site: the appraisal round from the plan to
the decision.

The rules are in appraisal_rules.py and the signatures in
appraisal_approval.py, both without a Frappe import
(scripts/verify_performance.py). This reads and writes the site.

WHY FRAPPE HR'S APPRAISAL AND NOT ANOTHER FORM

Frappe HR already carries an appraisal round: an Appraisal Cycle with its
appraisees, an Appraisal per employee, and the Appraisal Overview chart on
the Performance page. Luuka's Supervisory Skills Evaluation Form (LPL/HR/18)
is added to that Appraisal as custom fields rather than replacing it, so the
round keeps all of it and the chart fills up as appraisals are scored.

  plan_*       the Annual Appraisal Plan (case 1), whose submission opens
               an Appraisal Cycle per quarter
  daily        watches the plan: the HR Officer is told when a quarter is
               due (case 2), and everyone appraising is reminded a week, a
               day and on the day before the hard deadline, and on the soft
               one (the recommendation)
  open_quarter raises the appraisals for a quarter from each employee's
               Appraisal Template and sends them on: to the employee for
               their self-appraisal, or straight to the supervisor, as
               Appraisal Settings say (case 3)
  appraisal_*  the form itself: the template it is filled from, the
               scores, the signatures (case 4)
  sheet        the flowchart's other branch: Luuka's own form downloaded
               (appraisal_sheet.py), filled in away from the system, and
               uploaded again
  results      the Appraisal Results report: every appraisal with what is
               to become of the employee and how far that has got; what it
               shows goes on a Performance Review for management
  review_*     the report to top management, approved by the General
               Manager and then the Executive Director, and the decisions
               (cases 5, 6, 10); a promotion or an increase raises an
               Employee Position Change (cases 8, 9), a PIP a Performance
               Improvement Plan (case 7)
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import (
    appraisal_approval as approval,
    appraisal_rules as rules,
    appraisal_sheet as sheet,
    bsc,
    bsc_rules,
    people,
    performance_review_approval as review_approval,
    pip_rules,
    pips,
    position_rules,
    workflows,
)

HOD_ROLE = "Head of Department"
SETTINGS = "Appraisal Settings"
TEMPLATE = "Appraisal Template"
# who writes which comment block, on either form
REMARKS = {"supervisor": "custom_supervisor_remarks", "employee": "custom_employee_remarks",
           "hod": "custom_hod_remarks", "hrm": "custom_hrm_remarks", "ed": "custom_ed_remarks",
           "production": "custom_production_remarks", "gm": "custom_gm_remarks"}
# the sections a template fills, on either form
SECTIONS = ("custom_factors", "custom_objectives", "custom_bsc_perspectives", "custom_bsc_kpis",
            "custom_bsc_competencies")


def settings():
    """Appraisal Settings, with their defaults where nothing is saved yet.
    Read as stored: Frappe reads a Check never saved as 0, not as its
    default of 1."""
    stored = frappe.db.get_singles_dict(SETTINGS) if frappe.db.exists("DocType", SETTINGS) else {}
    return frappe._dict(rules.settings_values(stored))


def settings_on_update(doc, method=None):
    """Appraisal Settings saved: the appraisals the supervisor does not have
    yet follow them now."""
    moved = follow_settings()
    if moved:
        frappe.msgprint(_("Appraisals sent on to the supervisor: {0}").format(len(moved)), alert=True)


def follow_settings():
    """Every open appraisal the supervisor does not have yet takes the
    self-appraisal as Appraisal Settings say now, and one waiting on a
    self-appraisal no longer asked for goes on to the supervisor
    (approval.follow_setting). Returns the ones sent on."""
    own = settings().self_appraisal
    moved = []
    for row in frappe.get_all("Appraisal", filters={"docstatus": 0},
                              fields=["name", approval.STATE_FIELD, approval.SELF_FIELD]):
        wanted = approval.follow_setting(row.get(approval.STATE_FIELD), own)
        if not wanted:
            continue
        flag, state = wanted
        if state != (row.get(approval.STATE_FIELD) or approval.DRAFT):
            _skip_self_appraisal(row.name, state)
            moved.append(row.name)
        elif int(row.get(approval.SELF_FIELD) or 0) != flag:
            # modified moves on, so a form opened before the change is reloaded
            # before it is sent on the old way
            frappe.db.set_value("Appraisal", row.name, approval.SELF_FIELD, flag)
    return moved


def _skip_self_appraisal(name, state):
    """The self-appraisal no longer asked for: the employee's task is
    withdrawn and the supervisor has the appraisal, as if HR had sent it
    straight to them."""
    frappe.db.set_value("Appraisal", name, {approval.SELF_FIELD: 0, approval.STATE_FIELD: state,
                                            approval.STATUS_FIELD: state})
    doc = frappe.get_doc("Appraisal", name)
    if doc.get("employee"):
        people.withdraw("Appraisal", name, [frappe.db.get_value("Employee", doc.employee, "user_id")])
    doc.add_comment("Info", _("Sent to the supervisor: self-appraisal is off in Appraisal Settings."))
    _tell_next(doc, state)


# the employee's own ratings, where each form keeps them: a rating on the
# supervisory form, a figure on the scorecard (each KPI's own percentage
# since October 2026, each competency's score)
SELF_RATINGS = (("Appraisal Factor Rating", "employee_rating"), ("Appraisal Objective Rating", "employee_rating"),
                ("BSC Appraisal KPI", "self_percent"), ("BSC Appraisal Competency", "self_score"))
SELF_FIGURES = ("self_percent", "self_score")


def gave_self_appraisal(names):
    """The appraisals among `names` in which the employee rated themselves."""
    names = list(names or ())
    ratings, scores = {}, {}
    for doctype, field in SELF_RATINGS if names else ():
        kept = scores if field in SELF_FIGURES else ratings
        for row in frappe.get_all(doctype, filters={"parenttype": "Appraisal", "parent": ["in", names]},
                                  fields=["parent", field]):
            kept.setdefault(row.parent, []).append(row.get(field))
    return {name for name in names if rules.gave_self_appraisal(ratings.get(name), scores.get(name))}


# ── 1. The annual plan ────────────────────────────────────────────────
def plan_validate(doc, method=None):
    doc.title = " ".join(str(part) for part in (doc.get("year"), doc.get("branch") or doc.get("company")) if part)
    for row in doc.get("quarters") or []:
        if row.quarter and not (row.from_date and row.to_date):
            first, last = rules.quarter_window(int(doc.year), row.quarter)
            row.from_date, row.to_date = row.from_date or first, row.to_date or last
        if row.quarter and not row.hard_deadline:
            soft, hard = rules.deadlines(int(doc.year), row.quarter)
            row.soft_deadline, row.hard_deadline = row.soft_deadline or soft, hard
    if doc.docstatus == 0:
        doc.status = "Draft"
    errors = rules.plan_errors({
        "year": doc.get("year"), "company": doc.get("company"),
        "quarters": [row.as_dict() for row in doc.get("quarters") or []],
    })
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Appraisal Plan"))


def plan_on_submit(doc, method=None):
    doc.db_set("status", "Active", update_modified=False)
    officers = people.hr_officers(doc.get("branch"), doc.get("department"))
    people.notify(officers, doc.doctype, doc.name,
                  _("The {0} appraisal plan is active: {1} quarters to appraise.").format(
                      doc.year, len(doc.get("quarters") or [])))


def plan_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)


@frappe.whitelist()
def fill_year(year, soft_day=None):
    """The four quarters of `year` with their windows and deadlines, for the
    plan's Fill the Year button."""
    year = int(year)
    day = int(soft_day or rules.SOFT_DEADLINE_DAY)
    rows = []
    for quarter in rules.QUARTERS:
        first, last = rules.quarter_window(year, quarter)
        soft, hard = rules.deadlines(year, quarter, day)
        rows.append({"quarter": quarter, "from_date": str(first), "to_date": str(last),
                     "soft_deadline": str(soft), "hard_deadline": str(hard)})
    return rows


# ── 2, 3. The quarter opens ───────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def open_quarter(plan, quarter):
    """The quarter's Appraisal Cycle and an Appraisal for each employee in
    scope; the supervisor and the employee are told. Returns how many."""
    doc = frappe.get_doc("Appraisal Plan", plan)
    doc.check_permission("submit")
    if doc.docstatus != 1:
        frappe.throw(_("Submit the appraisal plan first."))
    row = next((row for row in doc.quarters if row.quarter == quarter), None)
    if not row:
        frappe.throw(_("{0} is not on this plan.").format(quarter))
    cycle = _cycle_for(doc, row)
    made = 0
    for employee in _employees_for(doc):
        if frappe.db.exists("Appraisal", {"employee": employee.name, "appraisal_cycle": cycle.name,
                                          "docstatus": ["!=", 2]}):
            continue
        _raise_appraisal(doc, row, cycle, employee)
        made += 1
    row.db_set("appraisal_cycle", cycle.name, update_modified=False)
    row.db_set("appraisals", (row.appraisals or 0) + made, update_modified=False)
    row.db_set("notified_on", row.notified_on or today(), update_modified=False)
    return made


def _cycle_for(plan, row):
    """The quarter's Appraisal Cycle, made once."""
    if row.appraisal_cycle and frappe.db.exists("Appraisal Cycle", row.appraisal_cycle):
        return frappe.get_doc("Appraisal Cycle", row.appraisal_cycle)
    name = " ".join(str(part) for part in (plan.year, row.quarter, plan.get("branch")) if part)
    existing = frappe.db.get_value("Appraisal Cycle", {"cycle_name": name}, "name")
    if existing:
        return frappe.get_doc("Appraisal Cycle", existing)
    cycle = frappe.get_doc({
        "doctype": "Appraisal Cycle", "cycle_name": name, "company": plan.company,
        "start_date": row.from_date, "end_date": row.to_date, "status": "In Progress",
        "branch": plan.get("branch"), "department": plan.get("department"),
        "kra_evaluation_method": settings().kra_evaluation_method,
        "custom_plan": plan.name, "custom_quarter": row.quarter,
        "custom_soft_deadline": row.soft_deadline, "custom_hard_deadline": row.hard_deadline,
    })
    cycle.flags.ignore_permissions = True
    cycle.flags.ignore_mandatory = True
    cycle.insert()
    return cycle


def _employees_for(plan):
    if not plan.get("appraise_all"):
        named = [row.employee for row in plan.get("employees") or []]
        if not named:
            return []
        filters = {"name": ["in", named], "status": "Active"}
    else:
        filters = {"status": "Active"}
        if plan.get("branch"):
            filters["branch"] = plan.branch
        if plan.get("department"):
            filters["department"] = plan.department
        if plan.get("company"):
            filters["company"] = plan.company
    return frappe.get_all("Employee", filters=filters,
                          fields=["name", "employee_name", "reports_to", "designation", "user_id", "branch",
                                  "department"], order_by="name asc")


def _raise_appraisal(plan, row, cycle, employee):
    """The employee's appraisal for the quarter, filled from their Appraisal
    Template, then sent on: to them for their self-appraisal, or to their
    supervisor."""
    appraisal = frappe.get_doc({
        "doctype": "Appraisal", "employee": employee.name, "employee_name": employee.employee_name,
        "appraisal_cycle": cycle.name, "company": plan.company, "department": employee.department,
        "designation": employee.designation, "start_date": row.from_date, "end_date": row.to_date,
        "rate_goals_manually": rules.rates_goals_manually(cycle.get("kra_evaluation_method")),
        "custom_plan": plan.name, "custom_quarter": row.quarter, "custom_supervisor": employee.reports_to,
        "custom_self_appraisal": settings().self_appraisal,
        "custom_appraisal_status": approval.DRAFT, "workflow_state": approval.DRAFT,
    })
    template = template_for(employee.name, employee.get("designation"), cycle.name, plan.get("year"))
    _take_template(appraisal, template, employee)
    appraisal.flags.ignore_permissions = True
    appraisal.flags.ignore_mandatory = True
    appraisal.insert()
    appraisal = _send_on(appraisal)
    _tell_about(appraisal, employee)
    return appraisal


def _send_on(appraisal):
    """A raised appraisal leaves Draft by the workflow's own step (to the
    employee, or to the supervisor, as Appraisal Settings say now), so it is
    routed, signed and told like any other."""
    own = settings().self_appraisal
    _action, state = approval.opening(own)
    appraisal = frappe.get_doc("Appraisal", appraisal.name)
    appraisal.set(approval.SELF_FIELD, own)
    appraisal.workflow_state = state
    appraisal.flags.ignore_permissions = True
    appraisal.save()
    return appraisal


# ── The template each appraisal is filled from ────────────────────────
def template_for(employee, designation=None, cycle=None, year=None):
    """The Appraisal Template an employee is appraised on: the one the cycle
    names for them, else their Job Title's (which every Job Title must
    have), else an active scorecard made for the role."""
    if cycle:
        named = frappe.db.get_value("Appraisee", {"parent": cycle, "parenttype": "Appraisal Cycle",
                                                  "employee": employee}, "appraisal_template")
        if named and frappe.db.exists(TEMPLATE, named):
            return named
    designation = designation or (frappe.db.get_value("Employee", employee, "designation") if employee else None)
    if designation:
        assigned = frappe.db.get_value("Designation", designation, "appraisal_template")
        if assigned and frappe.db.exists(TEMPLATE, assigned):
            return assigned
    return bsc.template_for(designation=designation, year=year)


def form_of(template):
    """Which of the two forms a template carries. A scorecard with no KPIs on
    it cannot be scored, so it counts as the supervisory form."""
    if not template:
        return approval.FORM_SUPERVISORY
    form = frappe.db.get_value(TEMPLATE, template, "custom_form_type")
    if form == approval.FORM_SUPERVISORY:
        return form
    has_kpis = frappe.db.exists("BSC Template KPI", {"parent": template, "parenttype": TEMPLATE})
    return approval.FORM_BSC if has_kpis else approval.FORM_SUPERVISORY


def _take_template(doc, template, employee=None):
    """The form and its sections from the template. Rows already there are
    kept, so taking the template again never wipes a rating."""
    doc.appraisal_template = template or None
    doc.custom_form_type = form_of(template)
    if doc.custom_form_type == approval.FORM_BSC:
        bsc.fill(doc, template)
        return
    card = frappe.get_doc(TEMPLATE, template) if template else None
    if not doc.get("custom_factors"):
        factors = [row.factor for row in (card.get("custom_factors") or []) if row.factor] if card else []
        doc.set("custom_factors", [{"item": factor} for factor in factors or _factors()])
    if not doc.get("custom_objectives"):
        objectives = [row.objective for row in (card.get("custom_objectives") or []) if row.objective] \
            if card else []
        objectives = rules.objectives_from_kras(objectives) or _objectives(
            employee or frappe._dict(designation=doc.get("designation")))
        doc.set("custom_objectives", [{"item": objective} for objective in objectives])


@frappe.whitelist(methods=["POST"])
def apply_template(appraisal, template=None):
    """The form's Get from Template: the appraisal takes its template again
    (the one given, else the one it names, else the employee's), and a
    template of the other form changes the form. Only before the supervisor
    has rated: after that the form stays as it was rated."""
    doc = frappe.get_doc("Appraisal", appraisal)
    doc.check_permission("write")
    if doc.docstatus != 0 or (doc.get("workflow_state") or approval.DRAFT) not in (approval.DRAFT,
                                                                                   approval.PENDING_SELF):
        frappe.throw(_("The template can be taken again only before the supervisor rates the appraisal."))
    template = template or doc.get("appraisal_template") or template_for(
        doc.employee, doc.get("designation"), doc.get("appraisal_cycle"),
        getdate(doc.start_date).year if doc.get("start_date") else None)
    if not template:
        frappe.throw(_("{0} has no Appraisal Template: set one on the Job Title.").format(
            doc.get("designation") or doc.employee))
    if template != doc.get("appraisal_template") or form_of(template) != doc.get("custom_form_type"):
        # another template: its own sections, nothing of the last one's
        for table in SECTIONS:
            doc.set(table, [])
    _take_template(doc, template)
    # taken now, so the save does not take it a second time
    doc.flags.template_taken = True
    doc.flags.ignore_permissions = True
    doc.save()
    return {"template": doc.appraisal_template, "form_type": doc.custom_form_type}


def _factors():
    listed = frappe.get_all("Appraisal Factor", pluck="name", order_by="creation asc")
    return listed or list(rules.FACTORS)


def _objectives(employee):
    """The employee's objectives: their Job Title's Key Result Areas, which
    the form says should be in line with the department's."""
    if not employee.get("designation"):
        return []
    kras = frappe.get_all("Designation KRA", filters={"parent": employee.designation, "parenttype": "Designation"},
                          fields=["key_outputs", "kra"], order_by="idx asc") \
        if frappe.db.exists("DocType", "Designation KRA") else []
    lines = [(row.get("key_outputs") or row.get("kra") or "").split("\n")[0] for row in kras]
    return rules.objectives_from_kras(lines)


def _tell_about(appraisal, employee):
    """While the employee appraises themselves, the supervisor knows it is
    coming; told when it reaches them (_tell_next), as is the employee."""
    if not appraisal.get("custom_self_appraisal") or not appraisal.get("custom_supervisor"):
        return
    supervisor = frappe.db.get_value("Employee", appraisal.custom_supervisor, "user_id")
    when = " ".join(part for part in (appraisal.get("custom_quarter"), appraisal.get("custom_plan")) if part)
    people.notify([supervisor], "Appraisal", appraisal.name,
                  _("Appraisal open for {0} ({1}): you rate them once they have appraised themselves.").format(
                      employee.employee_name or employee.name, when))


# ── 4. The form ───────────────────────────────────────────────────────
def appraisal_validate(doc, method=None):
    if doc.is_new() or (doc.get(approval.STATE_FIELD) or approval.DRAFT) == approval.DRAFT:
        # one HR has not sent on yet follows Appraisal Settings as they are now
        doc.custom_self_appraisal = settings().self_appraisal
    if not doc.get("custom_supervisor") and doc.get("employee"):
        doc.custom_supervisor = frappe.db.get_value("Employee", doc.employee, "reports_to")
    doc.custom_supervisor_name = frappe.db.get_value("Employee", doc.custom_supervisor, "employee_name") \
        if doc.get("custom_supervisor") else None
    _settle_quarter(doc)
    _mark_pip(doc)
    _attach_template(doc)
    if _is_bsc(doc):
        _carry_earlier_quarters(doc)
        _check_figures(doc)
        bsc.score(doc)
        _carry_scores(doc, doc.get("custom_bsc_overall"), doc.get("custom_bsc_band"))
    else:
        if not doc.get("custom_factors"):
            for factor in _factors():
                doc.append("custom_factors", {"item": factor})
        _score(doc)
    _year_so_far(doc)
    _check_remarks(doc)
    _check_step(doc)
    doc.custom_appraisal_status = doc.get("workflow_state") or doc.get("custom_appraisal_status") or approval.DRAFT


def appraisal_onload(doc, method=None):
    """What the form needs to know beyond the record: the step each
    signatory's remarks are written at, on this appraisal's form, and the
    improvement plan the employee is on."""
    doc.set_onload("remark_steps", approval.remark_steps(doc.get("custom_form_type")))
    if doc.get("custom_improvement_plan"):
        doc.set_onload("improvement_plan", frappe.db.get_value(
            "Performance Improvement Plan", doc.custom_improvement_plan, ["name", "status", "end_date"], as_dict=True))


def appraisal_on_change(doc, method=None):
    """A quarter changed (saved, signed, submitted or cancelled): the
    employee's later quarters still open carry it as it is now, their
    earlier quarters and their year to date. Written straight in, so their
    own checks and signatures are not run again."""
    quarter = doc.get("custom_quarter")
    if quarter not in bsc_rules.QUARTERS or not doc.get("employee"):
        return
    later = bsc_rules.QUARTERS[bsc_rules.QUARTERS.index(quarter) + 1:]
    for each, row in _year_appraisals(doc).items():
        if each not in later or row.docstatus != 0:
            continue
        other = frappe.get_doc("Appraisal", row.name)
        if _is_bsc(other):
            _carry_earlier_quarters(other)
            bsc.score(other)
            _carry_scores(other, other.get("custom_bsc_overall"), other.get("custom_bsc_band"))
        _year_so_far(other)
        other.db_update()
        for table in ("custom_bsc_kpis", "custom_bsc_perspectives", "custom_quarter_results"):
            other.update_child_table(table)


def _is_bsc(doc):
    return doc.get("custom_form_type") == approval.FORM_BSC


def _settle_quarter(doc):
    """The quarter the appraisal is for: the plan's, or the one HR gave an
    appraisal made by hand, else its cycle's, else the one its period starts
    in. Once it is being rated the quarter stays: the scores are recorded
    against it."""
    before = doc.get_doc_before_save()
    started = before is not None and (before.get(approval.STATE_FIELD) or approval.DRAFT) \
        not in approval.BEFORE_SUPERVISOR
    if started and before.get("custom_quarter") and doc.get("custom_quarter") != before.get("custom_quarter"):
        doc.custom_quarter = before.custom_quarter
        frappe.msgprint(_("The appraisal keeps the quarter it is being rated for."), indicator="orange", alert=True)
    if doc.get("custom_quarter") in bsc_rules.QUARTERS:
        return
    cycle = frappe.db.get_value("Appraisal Cycle", doc.appraisal_cycle, ["custom_quarter", "start_date"],
                                as_dict=True) if doc.get("appraisal_cycle") else None
    if cycle and cycle.custom_quarter in bsc_rules.QUARTERS:
        doc.custom_quarter = cycle.custom_quarter
        return
    start = doc.get("start_date") or (cycle.start_date if cycle else None)
    doc.custom_quarter = bsc_rules.quarter_of(getdate(start).month) if start else None


def _mark_pip(doc):
    """An employee on an improvement plan still open is marked, and their
    appraisals show it (pips.mark_appraisals keeps them right as plans open
    and close)."""
    plan = pips.open_plan(doc.get("employee")) if doc.get("employee") else None
    doc.custom_improvement_plan = plan
    doc.custom_on_pip = 1 if plan else 0


def _year_appraisals(doc):
    """{quarter: row} of the employee's other appraisals of the year this
    one is in: the same plan's, or, for one made by hand, those of the same
    calendar year. One a quarter: a submitted one before an open one, the
    last changed before an earlier."""
    if not doc.get("employee"):
        return {}
    filters = {"employee": doc.employee, "docstatus": ["!=", 2], "name": ["!=", doc.name or ""],
               "custom_quarter": ["in", list(bsc_rules.QUARTERS)]}
    if doc.get("custom_plan"):
        filters["custom_plan"] = doc.custom_plan
    elif doc.get("start_date"):
        year = getdate(doc.start_date).year
        filters["start_date"] = ["between", ["%s-01-01" % year, "%s-12-31" % year]]
    else:
        return {}
    found = {}
    for row in frappe.get_all("Appraisal", filters=filters, order_by="docstatus asc, modified asc", fields=[
            "name", "docstatus", "custom_quarter", "custom_form_type", approval.STATE_FIELD, "custom_total_score",
            "custom_band", "custom_bsc_section_a_score", "custom_bsc_section_b_score", "custom_factors_score",
            "custom_objectives_score"]):
        found[row.custom_quarter] = row
    return found


def _earlier_quarters(doc):
    """{quarter: {(perspective, kpi): {"percent", "comments"}}} for the
    quarters before this one, as their own appraisals on the scorecard
    recorded them."""
    quarter = doc.get("custom_quarter")
    if quarter not in bsc_rules.QUARTERS:
        return {}
    before = bsc_rules.QUARTERS[:bsc_rules.QUARTERS.index(quarter)]
    found = {}
    for each, row in _year_appraisals(doc).items():
        if each not in before or row.custom_form_type != approval.FORM_BSC:
            continue
        percent, comments = bsc_rules.percent_field(each), bsc_rules.comments_field(each)
        found[each] = {(kpi.perspective, bsc._plain(kpi.kpi)): {"percent": kpi.get(percent),
                                                                "comments": kpi.get(comments)}
                       for kpi in frappe.get_all("BSC Appraisal KPI", fields=["perspective", "kpi", percent, comments],
                                                 filters={"parent": row.name, "parenttype": "Appraisal",
                                                          "parentfield": "custom_bsc_kpis"})}
    return found


def _carry_earlier_quarters(doc):
    """The quarters before this one, each KPI's percentage and comments as
    their own appraisals recorded them, and the quarters after it blank:
    only the quarter appraised is filled in here (Luuka, 4 Oct 2026)."""
    quarter = doc.get("custom_quarter")
    if quarter not in bsc_rules.QUARTERS:
        return
    # only the quarters before this one are found, so the ones after it
    # come out blank: they are recorded on their own appraisals
    earlier = _earlier_quarters(doc)
    rows = doc.get("custom_bsc_kpis") or []
    for row in rows:
        key = (row.perspective, bsc._plain(row.kpi))
        for each in bsc_rules.QUARTERS:
            if each == quarter:
                continue
            found = (earlier.get(each) or {}).get(key) or {}
            row.set(bsc_rules.percent_field(each), found.get("percent"))
            row.set(bsc_rules.comments_field(each), found.get("comments"))
    _blank_unrecorded(rows)


def _blank_unrecorded(rows):
    """Frappe keeps a figure left blank as 0: a column of the KPIs never
    filled in is blank again, so it is neither scored nor shown as 0%."""
    for field in [bsc_rules.percent_field(each) for each in bsc_rules.QUARTERS] + ["self_percent"]:
        if not bsc_rules.recorded(rows, field):
            for row in rows:
                row.set(field, None)


def _year_so_far(doc):
    """Results This Year, on either form: each quarter up to this one as its
    own appraisal recorded it, this one as it stands, and the year to date,
    the average of the quarters appraised (Luuka, 4 Oct 2026). A quarter
    counts once it is scored, which its rating says: a score not given is
    kept as 0."""
    quarter = doc.get("custom_quarter")
    rows = []
    if quarter in bsc_rules.QUARTERS:
        others = _year_appraisals(doc)
        for each in bsc_rules.QUARTERS[:bsc_rules.QUARTERS.index(quarter) + 1]:
            source = doc if each == quarter else others.get(each)
            if source is not None and source.get("custom_band"):
                rows.append(_quarter_result(each, source))
    doc.set("custom_quarter_results", rows)
    doc.custom_annual_score = bsc_rules.year_to_date([row["total"] for row in rows])
    doc.custom_year_band = (bsc_rules.band if _is_bsc(doc) else rules.band)(doc.custom_annual_score)


def _quarter_result(quarter, source):
    """One quarter's line of Results This Year, from its appraisal (the
    record itself, or a row of it)."""
    on_card = source.get("custom_form_type") == approval.FORM_BSC
    return {"quarter": quarter, "appraisal": source.get("name"),
            "section_a": source.get("custom_bsc_section_a_score" if on_card else "custom_factors_score"),
            "section_b": source.get("custom_bsc_section_b_score" if on_card else "custom_objectives_score"),
            "total": source.get("custom_total_score"), "band": source.get("custom_band"),
            "status": source.get(approval.STATE_FIELD) or approval.DRAFT}


def _check_figures(doc):
    """A percentage achieved over 100, or a competency scored over 10, is
    refused at every save, whoever saves it (Luuka, 5 Oct 2026: 400% was
    kept and scored 28 of a weight of 7)."""
    errors = _figure_errors(doc)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Appraisal"))


def _figure_errors(doc):
    return bsc_rules.figure_errors([row.as_dict() for row in doc.get("custom_bsc_kpis") or []],
                                   [row.as_dict() for row in doc.get("custom_bsc_competencies") or []],
                                   doc.get("custom_quarter"))


def _check_remarks(doc):
    """Each signatory's remarks are theirs, written when the appraisal is
    with them (Luuka, 4 Oct 2026); the form opens only those. An uploaded
    sheet brings the employee's and the supervisor's while their parts are
    open (_apply_sheet)."""
    before = doc.get_doc_before_save()
    if before is None or doc.flags.get("from_sheet"):
        return
    changed = [field for field in approval.ALL_REMARK_FIELDS
               if _plain(doc.get(field)) != _plain(before.get(field))]
    errors = approval.remark_errors(doc.get("custom_form_type"), before.get(approval.STATE_FIELD) or approval.DRAFT,
                                    changed)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Appraisal"))


def _attach_template(doc):
    """The employee's Appraisal Template, attached and filled in without
    being asked for.

    Luuka: "these templates will be already attached to the
    employee/designation and will automatically populate the information."
    The plan does this when it raises an appraisal and Frappe HR's cycle
    names the template when it creates one; an appraisal made by hand gets
    it here. Nothing already rated is touched, and an appraisal that has
    left the employee's hands keeps the form it was rated on.
    """
    if doc.docstatus != 0 or not doc.get("employee") or doc.flags.get("template_taken"):
        return
    before = doc.get_doc_before_save()
    started = (before.get(approval.STATE_FIELD) if before else None) not in (None, approval.DRAFT,
                                                                           approval.PENDING_SELF)
    if started and doc.get("custom_form_type"):
        # it is being rated on its template: another one picked now is not taken
        if before.get("appraisal_template") != doc.get("appraisal_template"):
            doc.appraisal_template = before.get("appraisal_template")
            frappe.msgprint(_("The appraisal keeps the template it is being rated on."), indicator="orange",
                            alert=True)
        return
    # HR picked another template: the form is filled from it afresh
    if before and doc.get("appraisal_template") and before.get("appraisal_template") != doc.appraisal_template:
        for table in SECTIONS:
            doc.set(table, [])
    empty = not (doc.get("custom_bsc_perspectives") or doc.get("custom_factors"))
    if not empty and doc.get("custom_form_type"):
        return
    if not doc.get("appraisal_template"):
        doc.appraisal_template = template_for(
            doc.employee, doc.get("designation"), doc.get("appraisal_cycle"),
            getdate(doc.start_date).year if doc.get("start_date") else None)
    _take_template(doc, doc.get("appraisal_template"))


def _carry_scores(doc, total, band):
    """The scorecard's overall is the appraisal's score, so one review, one
    report and one chart read both forms the same way."""
    doc.custom_total_score = total
    doc.custom_band = band
    doc.final_score = flt(total or 0)


def _score(doc):
    """Section C, from the supervisor's ratings, and Frappe HR's own score
    fields with it so the Appraisal Overview chart shows the round."""
    found = rules.scores([row.supervisor_rating for row in doc.get("custom_factors") or []],
                         [row.supervisor_rating for row in doc.get("custom_objectives") or []])
    doc.custom_factors_score = found["factors"]
    doc.custom_objectives_score = found["objectives"]
    doc.custom_total_score = found["total"]
    doc.custom_band = rules.band(found["total"])
    self_found = rules.scores([row.employee_rating for row in doc.get("custom_factors") or []],
                              [row.employee_rating for row in doc.get("custom_objectives") or []]) \
        if doc.get("custom_self_appraisal") else {"total": None}
    # Frappe HR's fields, so its chart and its list views read the round
    doc.final_score = flt(found["total"] or 0)
    doc.total_score = flt(found["objectives"] or 0)
    doc.self_score = flt(self_found["total"] or 0)


def _facts(doc, step=None):
    return {
        "step": step, "form_type": doc.get("custom_form_type"),
        "factors": [row.as_dict() for row in doc.get("custom_factors") or []],
        "objectives": [row.as_dict() for row in doc.get("custom_objectives") or []],
        "roles": doc.get("custom_roles"), "skills": doc.get("custom_skills"),
        "achievements": doc.get("custom_achievements"), "challenges": doc.get("custom_challenges"),
        "return_remarks": doc.get("custom_return_remarks"),
        **{field: doc.get(field) for field in approval.ALL_REMARK_FIELDS},
    }


def _check_step(doc):
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    form_type = doc.get("custom_form_type")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, _facts(doc))
        forward = new_state != approval.DRAFT
        if forward and old_state == approval.PENDING_SELF:
            # the employee's own ratings, on whichever form they are on
            errors = _rating_errors(doc, "self") + errors
        if forward and old_state == approval.PENDING_SUPERVISOR:
            errors = _rating_errors(doc, "supervisor") + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Appraisal"))
        if forward:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current,
                                                form_type).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_next(doc, new_state)


def _rating_errors(doc, step):
    """What the employee (step "self") or the supervisor ("supervisor")
    must fill in before passing the form on."""
    if _is_bsc(doc):
        return bsc_rules.appraisal_errors(bsc.facts(doc, "self" if step == "self" else "appraiser"))
    return rules.appraisal_errors(_facts(doc, step))


def _tell_next(doc, state):
    role = approval.ROLE_WAITING[state]
    name = doc.get("employee_name") or doc.get("employee")
    if state == approval.PENDING_SUPERVISOR and doc.get("custom_supervisor"):
        users = [frappe.db.get_value("Employee", doc.custom_supervisor, "user_id")]
    elif state in (approval.PENDING_SELF, approval.PENDING_EMPLOYEE):
        users = [frappe.db.get_value("Employee", doc.employee, "user_id")]
    else:
        users = people.people_for(role, doc.get("custom_branch"), doc.get("department"))
    if state == approval.PENDING_SELF:
        message = _("Your appraisal is open: rate yourself and submit your self-appraisal.")
    elif state == approval.PENDING_EMPLOYEE:
        message = _("Your appraisal has been rated: read it, comment and sign.")
    else:
        message = _("Appraisal of {0}: your rating and signature are needed.").format(name)
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def appraisal_on_cancel(doc, method=None):
    doc.db_set("custom_appraisal_status", approval.CANCELLED, update_modified=False)


# ── The sheet, for appraising away from the system ────────────────────
# what an uploaded sheet may still change, by where the appraisal stands:
# the employee's part until they have submitted it (or, on the scorecard,
# until they have signed the appraiser's scores), the supervisor's until
# they have passed the form on
EMPLOYEE_STATES = (approval.DRAFT, approval.PENDING_SELF)
SUPERVISOR_STATES = (approval.DRAFT, approval.PENDING_SELF, approval.PENDING_SUPERVISOR)


@frappe.whitelist()
def download_sheet(appraisal_cycle=None, appraisal=None, supervisor=None):
    """The flowchart's other branch: Luuka's own form, one sheet per
    appraisal still open, filled in with what the system knows. From a
    cycle, a supervisor's own people only, when one is named.

    Opened as a download, so a refusal shows as Frappe's bare error page:
    the cycle's button asks sheet_count first and explains an empty sheet
    on the form instead."""
    if not (appraisal or appraisal_cycle):
        frappe.throw(_("Name the appraisal cycle or the appraisal to download."))
    names = [appraisal] if appraisal else _sheet_names(appraisal_cycle, supervisor)
    docs = [frappe.get_doc("Appraisal", name) for name in names]
    docs = [doc for doc in docs if doc.has_permission("read")]
    if not docs:
        frappe.throw(_("No open appraisals to download here.") if appraisal
                     else _(_no_sheet(appraisal_cycle, supervisor, names, docs)))
    content = sheet.build([_sheet_data(doc) for doc in docs], logo=_logo(docs[0].company))
    title = docs[0].employee_name if appraisal else (appraisal_cycle or "Appraisals")
    frappe.response["type"] = "binary"
    frappe.response["filecontent"] = content
    frappe.response["filename"] = "%s %s.xlsx" % (_("Appraisal Sheet"), title)


@frappe.whitelist()
def sheet_count(appraisal_cycle: str, supervisor: str | None = None) -> dict:
    """What the cycle's Download Sheet would give, asked before the download
    so an empty sheet is explained on the form: {"count", "reason"}."""
    names = _sheet_names(appraisal_cycle, supervisor)
    readable = [name for name in names if frappe.has_permission("Appraisal", "read", name)]
    return {"count": len(readable),
            "reason": None if readable else _(_no_sheet(appraisal_cycle, supervisor, names, readable))}


def _sheet_names(appraisal_cycle, supervisor=None):
    """The cycle's appraisals still open, by the employee's name: with a
    supervisor named, those whose appraisal names them, or that names nobody
    yet and whose employee reports to them now."""
    rows = frappe.get_all("Appraisal", filters={"appraisal_cycle": appraisal_cycle, "docstatus": 0},
                          fields=["name", "employee", "custom_supervisor"], order_by="employee_name asc")
    if supervisor:
        unnamed = [row.employee for row in rows if not row.custom_supervisor]
        theirs = set(frappe.get_all("Employee", filters={"name": ["in", unnamed], "reports_to": supervisor},
                                    pluck="name")) if unnamed else set()
        rows = [row for row in rows if row.custom_supervisor == supervisor
                or (not row.custom_supervisor and row.employee in theirs)]
    return [row.name for row in rows]


def _no_sheet(appraisal_cycle, supervisor, names, readable):
    """Why the cycle's sheet is empty (rules.no_sheet_reason)."""
    every = frappe.get_all("Appraisal", filters={"appraisal_cycle": appraisal_cycle, "docstatus": ["!=", 2]},
                           pluck="docstatus")
    return rules.no_sheet_reason({
        "cycle": appraisal_cycle, "appraisals": len(every), "open": sum(1 for docstatus in every if not docstatus),
        "theirs": len(names), "readable": len(readable),
        "supervisor": (frappe.db.get_value("Employee", supervisor, "employee_name") or supervisor) if supervisor else None,
    })


def _sheet_data(doc):
    """Everything the sheet shows for one appraisal, as appraisal_sheet.build
    takes it."""
    template = frappe.get_doc(TEMPLATE, doc.appraisal_template) \
        if doc.get("appraisal_template") and frappe.db.exists(TEMPLATE, doc.appraisal_template) else None
    person = frappe.db.get_value("Employee", doc.employee, ["branch", "grade", "designation"], as_dict=True) \
        or frappe._dict()
    boss = frappe.db.get_value("Employee", doc.custom_supervisor, ["employee_name", "designation"], as_dict=True) \
        if doc.get("custom_supervisor") else None
    year = getdate(doc.start_date).year if doc.get("start_date") else (template.get("custom_review_year")
                                                                       if template else None)
    data = {
        "name": doc.name, "form_type": doc.custom_form_type, "period": doc.get("custom_quarter"),
        "self_appraisal": doc.get("custom_self_appraisal"), "company": doc.company, "year": year,
        "currency": frappe.db.get_value("Company", doc.company, "default_currency") if doc.get("company") else None,
        "employee_name": doc.employee_name, "designation": doc.get("designation") or person.designation,
        "department": doc.get("department"), "branch": doc.get("custom_branch") or person.branch,
        "grade": person.grade or (template.get("custom_grade") if template else None),
        "supervisor": ", ".join(part for part in (boss.employee_name, boss.designation) if part) if boss else None,
        "review_period": _review_period(doc, template, year),
        "form_reference": template.get("custom_form_reference") if template else None,
        "revision": template.get("custom_revision") if template else None,
        "remarks": {key: doc.get(field) for key, field in REMARKS.items()},
        "names": {"supervisor": boss.employee_name if boss else None, "employee": doc.employee_name},
    }
    if _is_bsc(doc):
        data.update(_scorecard_data(doc))
    else:
        data.update({
            "factors": [row.as_dict() for row in doc.get("custom_factors") or []],
            "objectives": [row.as_dict() for row in doc.get("custom_objectives") or []],
            "answers": {key: doc.get("custom_%s" % key) for key, _question in rules.QUESTIONS},
        })
    return data


def _scorecard_data(doc):
    """The scorecard as the sheet lays it out: each KPI with its weight and
    every quarter's percentage and comments, the earlier ones as their own
    appraisals recorded them; the earlier quarters' results; and the rest
    of the form."""
    if doc.docstatus == 0:
        _carry_earlier_quarters(doc)
    else:
        _blank_unrecorded(doc.get("custom_bsc_kpis") or [])
    quarter = doc.get("custom_quarter")
    earlier = bsc_rules.QUARTERS[:bsc_rules.QUARTERS.index(quarter)] if quarter in bsc_rules.QUARTERS else ()
    return {
        "kpis": [row.as_dict() for row in doc.get("custom_bsc_kpis") or []],
        "results": {row.quarter: row.total for row in doc.get("custom_quarter_results") or []
                    if row.quarter in earlier},
        "assignments": [row.as_dict() for row in doc.get("custom_assignments") or []],
        "competencies": [row.as_dict() for row in doc.get("custom_bsc_competencies") or []],
        "plan": {"continue": doc.get("custom_continue"), "stop": doc.get("custom_stop"),
                 "start": doc.get("custom_start")},
        "actions": [row.as_dict() for row in doc.get("custom_development_actions") or []],
    }


def _review_period(doc, template, year):
    """What the sheet says is being reviewed: the quarter and its months, or
    the year."""
    quarter = doc.get("custom_quarter")
    if quarter in rules.QUARTERS:
        if doc.get("start_date") and doc.get("end_date"):
            return "%s %s (%s to %s)" % (quarter, year or "", getdate(doc.start_date).strftime("%B"),
                                         getdate(doc.end_date).strftime("%B"))
        return "%s %s" % (quarter, year or "")
    if template and template.get("custom_review_period"):
        return template.custom_review_period
    return "January to December %s" % (year or "")


def _plain(text):
    """Text compared the way a sheet gives it back: spaces and line breaks
    count as one space."""
    return " ".join(str(text or "").split())


def _logo(company):
    """The company's logo for the sheet's header: the company's own, else
    the site's. None when there is none to read."""
    urls = [frappe.db.get_value("Company", company, "company_logo") if company else None]
    if frappe.db.exists("DocType", "HRMS Addon Branding"):
        urls.append(frappe.db.get_single_value("HRMS Addon Branding", "company_logo"))
    urls.append(frappe.db.get_single_value("Navbar Settings", "app_logo")
                if frappe.db.exists("DocType", "Navbar Settings") else None)
    for url in urls:
        if not url:
            continue
        try:
            return _file_bytes(url)
        except Exception:  # noqa: BLE001 - a missing picture never stops the download
            continue
    return None


def _file_bytes(file_url):
    """A file's content as it is kept on the site."""
    if frappe.db.exists("File", {"file_url": file_url}):
        path = frappe.get_doc("File", {"file_url": file_url}).get_full_path()
    else:
        path = frappe.get_site_path("public", str(file_url).lstrip("/"))
    with open(path, "rb") as handle:
        return handle.read()


@frappe.whitelist(methods=["POST"])
def upload_sheet(file_url, appraisal_cycle=None, appraisal=None):
    """The filled sheet back in: each sheet is written onto its appraisal.

    What each appraisal accepts depends on where it stands: the employee's
    ratings and answers until their self-appraisal is submitted, the
    supervisor's ratings, comments and plan until the supervisor has passed
    it on. Returns what was updated and what was not, and why."""
    found = sheet.read(_file_bytes(file_url))
    if not found:
        frappe.throw(_("This is not an appraisal sheet from here: download the sheet again and fill that one in."))
    updated, skipped, problems = [], [], []
    for name, values in found.items():
        where = values.get("sheet") or name
        reason = _not_taken(name, values, appraisal_cycle, appraisal)
        if reason:
            skipped.append({"sheet": where, "appraisal": name, "reason": reason})
            continue
        doc = frappe.get_doc("Appraisal", name)
        taken, left = _apply_sheet(doc, values)
        problems.extend({"sheet": where, "appraisal": name, "problem": text} for text in values.get("problems") or [])
        problems.extend({"sheet": where, "appraisal": name, "problem": text} for text in left)
        if not taken:
            skipped.append({"sheet": where, "appraisal": name, "reason": _("Nothing on the sheet to take.")})
            continue
        # one saved before figures were held to their range, the sheet not
        # putting it right: that appraisal is left, the others still taken
        wrong = _figure_errors(doc) if _is_bsc(doc) else []
        if wrong:
            skipped.append({"sheet": where, "appraisal": name, "reason": " ".join(_(text) for text in wrong)})
            continue
        doc.flags.ignore_permissions = True
        doc.save()
        updated.append({"sheet": where, "appraisal": name, "employee_name": doc.employee_name, "fields": taken})
    return {"updated": updated, "skipped": skipped, "problems": problems}


def _not_taken(name, values, appraisal_cycle=None, appraisal=None):
    """Why a sheet is not written onto its appraisal; None when it is."""
    if appraisal and name != appraisal:
        return _("The sheet is for another appraisal ({0}).").format(name)
    if not frappe.db.exists("Appraisal", name):
        return _("No appraisal {0} on the system.").format(name)
    doc = frappe.db.get_value("Appraisal", name, ["appraisal_cycle", "docstatus", "workflow_state",
                                                  "custom_form_type", "custom_quarter"], as_dict=True)
    if appraisal_cycle and doc.appraisal_cycle != appraisal_cycle:
        return _("The appraisal belongs to another cycle ({0}).").format(doc.appraisal_cycle)
    if not frappe.has_permission("Appraisal", "write", name):
        return _("You may not change this appraisal.")
    if doc.docstatus != 0:
        return _("The appraisal is already {0}.").format(_("completed") if doc.docstatus == 1 else _("cancelled"))
    if (doc.custom_form_type or approval.FORM_SUPERVISORY) != (values.get("form_type") or approval.FORM_SUPERVISORY):
        return _("The sheet is for the {0} form, the appraisal is on the {1}.").format(
            values.get("form_type"), doc.custom_form_type)
    if values.get("outdated"):
        return _("The sheet was downloaded before each KPI was scored on its own weight: download it again and fill "
                 "that one in.")
    if doc.custom_form_type == approval.FORM_BSC and (values.get("period") or None) != (doc.custom_quarter or None):
        return _("The sheet is for {0}, the appraisal for {1}.").format(values.get("period"), doc.custom_quarter)
    state = doc.workflow_state or approval.DRAFT
    if state not in SUPERVISOR_STATES + (approval.PENDING_EMPLOYEE,):
        return _("The appraisal has moved on to {0}: it is changed on the system from here.").format(_(state))
    return None


def _apply_sheet(doc, values):
    """Write what the sheet says onto the appraisal, where the appraisal
    still takes it; a blank cell leaves what the system has. Returns (the
    parts taken, what could not be taken)."""
    state = doc.get("workflow_state") or approval.DRAFT
    employee = state in EMPLOYEE_STATES or (state == approval.PENDING_EMPLOYEE and _is_bsc(doc))
    supervisor = state in SUPERVISOR_STATES
    # the sheet's own rules say whose remarks it brings, not the form's
    doc.flags.from_sheet = True
    taken, left = [], []
    remarks = values.get("remarks") or {}
    if employee and remarks.get("employee") and remarks["employee"] != doc.get("custom_employee_remarks"):
        doc.custom_employee_remarks = remarks["employee"]
        taken.append(_("employee's comments"))
    if supervisor and remarks.get("supervisor") and remarks["supervisor"] != doc.get("custom_supervisor_remarks"):
        doc.custom_supervisor_remarks = remarks["supervisor"]
        taken.append(_("supervisor's comments"))
    others = [key for key in remarks if key not in ("employee", "supervisor")
              and remarks[key] != doc.get(REMARKS.get(key) or "")]
    if others:
        left.append(_("Comments by {0} are written on the system at their own step.").format(
            ", ".join(_(key.upper() if len(key) <= 3 else key.title()) for key in others)))
    if _is_bsc(doc):
        taken += _apply_scorecard(doc, values, employee, supervisor)
    else:
        taken += _apply_supervisory(doc, values, employee, supervisor, left)
    return taken, left


def _apply_scorecard(doc, values, employee, supervisor):
    taken = []
    if supervisor:
        quarter = doc.get("custom_quarter")
        percent, said = bsc_rules.percent_field(quarter), bsc_rules.comments_field(quarter)
        found = {(perspective, _plain(kpi)): entry for (perspective, kpi), entry in (values.get("kpis") or {}).items()}
        changed = 0
        for row in doc.get("custom_bsc_kpis") or []:
            got = found.get((row.perspective, _plain(row.kpi))) or {}
            if got.get("percent") is not None and got["percent"] != row.get(percent):
                row.set(percent, got["percent"])
                changed += 1
            if got.get("comments") and got["comments"] != row.get(said):
                row.set(said, got["comments"])
                changed += 1
        competencies = values.get("competencies") or {}
        for row in doc.get("custom_bsc_competencies") or []:
            if row.competency in competencies and competencies[row.competency] != row.get("score"):
                row.score = competencies[row.competency]
                changed += 1
        if changed:
            taken.append(_("Section A and B scores"))
        for table, key, label, fields in (
                ("custom_assignments", "assignments", _("assignments"),
                 ("task", "assignment_given", "expected_outcome", "employee_comments", "supervisor_comments")),
                ("custom_development_actions", "actions", _("development actions"),
                 ("action", "duration", "by_when", "by_whom", "estimated_cost"))):
            rows = values.get(key) or []
            if _table_of(doc, table, fields) != _table_of(None, rows, fields):
                doc.set(table, rows)
                taken.append(label)
        plan = values.get("plan") or {}
        if any(plan.get(key) and plan[key] != doc.get("custom_%s" % key) for key in ("continue", "stop", "start")):
            for key in ("continue", "stop", "start"):
                if plan.get(key):
                    doc.set("custom_%s" % key, plan[key])
            taken.append(_("development plan"))
    elif employee:
        # the employee comments on their assignments at their own step
        found = values.get("assignments") or []
        changed = 0
        for index, row in enumerate(doc.get("custom_assignments") or []):
            match = next((one for one in found if _plain(one.get("task")) == _plain(row.get("task"))), None) \
                or (found[index] if index < len(found) else None)
            if match and match.get("employee_comments") and match["employee_comments"] != row.get("employee_comments"):
                row.employee_comments = match["employee_comments"]
                changed += 1
        if changed:
            taken.append(_("assignments"))
    return taken


def _table_of(doc, rows, fields):
    """A table's rows as plain values, to see whether a sheet changes it:
    the document's table when `doc` is given, else the sheet's rows."""
    rows = (doc.get(rows) or []) if doc is not None else rows

    def plain(value):
        if isinstance(value, (int, float)):
            return "%g" % value if value else ""
        return _plain(value)

    return [tuple(plain(row.get(field)) for field in fields) for row in rows]


def _apply_supervisory(doc, values, employee, supervisor, left):
    taken = []
    for table, key, label in (("custom_factors", "factors", _("factors")),
                              ("custom_objectives", "objectives", _("objectives"))):
        rows = {_plain(row.item): row for row in doc.get(table) or []}
        changed = 0
        for found in values.get(key) or []:
            row = rows.get(_plain(found["item"]))
            if row is None:
                if key == "objectives" and supervisor and len(doc.get(table) or []) < rules.MAX_OBJECTIVES:
                    row = doc.append(table, {"item": found["item"]})
                    rows[_plain(found["item"])] = row
                    changed += 1
                else:
                    left.append(_("{0} is not on the appraisal and was not added.").format(found["item"]))
                    continue
            if employee and found.get("employee_rating") and found["employee_rating"] != row.get("employee_rating"):
                row.employee_rating = found["employee_rating"]
                changed += 1
            if supervisor and found.get("supervisor_rating") and \
                    found["supervisor_rating"] != row.get("supervisor_rating"):
                row.supervisor_rating = found["supervisor_rating"]
                changed += 1
            if supervisor and found.get("supervisor_comment") and \
                    found["supervisor_comment"] != row.get("supervisor_comment"):
                row.supervisor_comment = found["supervisor_comment"]
                changed += 1
        if changed:
            taken.append(label)
    if employee:
        answers = values.get("answers") or {}
        for key, _question in rules.QUESTIONS:
            if answers.get(key) and answers[key] != doc.get("custom_%s" % key):
                doc.set("custom_%s" % key, answers[key])
                if _("answers") not in taken:
                    taken.append(_("answers"))
    return taken


@frappe.whitelist(methods=["POST"])
def send_drafts(appraisal_cycle):
    """The cycle's Send Drafts On: every appraisal still in Draft goes on as
    the plan's would, to the employee or to the supervisor. Returns how many."""
    frappe.only_for(approval.PREPARERS)
    sent = 0
    for name in frappe.get_all("Appraisal", filters={"appraisal_cycle": appraisal_cycle, "docstatus": 0,
                                                     "workflow_state": approval.DRAFT}, pluck="name"):
        _send_on(frappe.get_doc("Appraisal", name))
        sent += 1
    return sent


@frappe.whitelist()
def get_appraisal_cycle_summary(cycle_name):
    """Frappe HR's summary on the Appraisal Cycle, its Self Appraisal Pending
    being the appraisals waiting on the employee's self-appraisal (none
    while employees do not appraise themselves), not every open one with no
    self score."""
    from hrms.hr.doctype.appraisal_cycle.appraisal_cycle import (
        get_appraisal_cycle_summary as frappe_hr_summary,
    )

    summary = frappe_hr_summary(cycle_name)
    summary["self_appraisal_pending"] = frappe.db.count(
        "Appraisal", {"appraisal_cycle": cycle_name, "docstatus": 0, approval.STATE_FIELD: approval.PENDING_SELF})
    return summary


# ── 5, 6, 10. The results, the report to management and the decision ──
# The Appraisal Results report reads the round as it stands. HR put what it
# shows on a Performance Review, which the General Manager and then the
# Executive Director approve (performance_review_approval.py); the approval
# carries each decision out.
REVIEW = "Performance Review"
REVIEW_ROW = "Performance Review Employee"
RATES = "Appraisal Increase Rate"
# what the results read of each appraisal
RESULT_FIELDS = ["name", "employee", "employee_name", "designation", "department", "custom_branch", "company",
                 "appraisal_cycle", "custom_quarter", "custom_form_type", "custom_total_score", "custom_band",
                 "custom_annual_score", "custom_year_band", "custom_outcome", "custom_performance_review",
                 "custom_on_pip", "custom_improvement_plan", "custom_appraisal_status", "docstatus"]
# the report's filters that are the appraisal's own fields
RESULT_FILTERS = (("company", "company"), ("appraisal_cycle", "appraisal_cycle"), ("branch", "custom_branch"),
                  ("department", "department"), ("employee", "employee"), ("form_type", "custom_form_type"))
FORM_NAMES = {approval.FORM_SUPERVISORY: "LPL/HR/18", approval.FORM_BSC: "BSC"}


def increase_rates():
    """The salary increase rates on Appraisal Settings: [{"score_from", "increase"}]."""
    return frappe.get_all(RATES, filters={"parent": SETTINGS, "parenttype": SETTINGS},
                          fields=["score_from", "increase"], order_by="score_from desc")


def settings_validate(doc, method=None):
    errors = rules.rate_errors([row.as_dict() for row in doc.get("increase_rates") or []])
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_("Salary Increase by Score"))


def results(filters):
    """The Appraisal Results report's rows: each appraisal the user may
    read, with what is to become of the employee and how far that has got
    (appraisal_rules.result_outcome), the best outcome and score first."""
    filters = frappe._dict(filters or {})
    conditions = {"docstatus": ["!=", 2]}
    for key, field in RESULT_FILTERS:
        if filters.get(key):
            conditions[field] = filters.get(key)
    year = cint(filters.get("year"))
    if year:
        conditions["start_date"] = ["between", ["%d-01-01" % year, "%d-12-31" % year]]
    appraisals = frappe.get_list("Appraisal", filters=conditions, fields=RESULT_FIELDS, limit_page_length=0)
    reviews = _reviews_of([appraisal.name for appraisal in appraisals])
    rates = increase_rates()
    unrated = filters.get("include_unrated") or filters.get("stage") == rules.NOT_RATED
    out = []
    for appraisal in appraisals:
        row = _result(appraisal, reviews.get(appraisal.name) or {}, rates)
        if row["stage"] == rules.NOT_RATED and not unrated:
            continue
        if rules.result_matches(row, filters):
            out.append(row)
    out.sort(key=rules.result_order)
    return out


def _result(appraisal, review, rates):
    """A row of the results: the appraisal, the review it is on, if any, and
    what that comes to."""
    rated = bool(appraisal.custom_band)
    score = flt(appraisal.custom_total_score) if rated else None
    open_review = review if review.get("docstatus") == 0 else {}
    outcome, stage = rules.result_outcome(
        score=score, rated=rated, review_state=open_review.get("state"), decision=open_review.get("decision"),
        decided=appraisal.custom_outcome, rates=rates)
    increase = None
    if outcome == rules.INCREASE:
        increase = flt(review.get("increase_percent")) or rules.increase_for(score, rates)
    return {
        "appraisal": appraisal.name, "employee": appraisal.employee, "employee_name": appraisal.employee_name,
        "designation": appraisal.designation, "department": appraisal.department,
        "branch": appraisal.custom_branch, "company": appraisal.company,
        "appraisal_cycle": appraisal.appraisal_cycle, "quarter": appraisal.custom_quarter,
        "form": FORM_NAMES.get(appraisal.custom_form_type, appraisal.custom_form_type),
        "score": score, "band": appraisal.custom_band,
        "year_score": flt(appraisal.custom_annual_score) if appraisal.custom_year_band else None,
        "year_band": appraisal.custom_year_band,
        "outcome": outcome, "increase": increase, "stage": stage,
        "review": review.get("review") or appraisal.custom_performance_review,
        "position_change": review.get("position_change"),
        "improvement_plan": review.get("improvement_plan") or appraisal.custom_improvement_plan,
        "on_pip": cint(appraisal.custom_on_pip),
        "appraisal_status": appraisal.custom_appraisal_status, "docstatus": appraisal.docstatus,
        "remarks": review.get("remarks"),
    }


def _reviews_of(appraisals):
    """{appraisal: the review it is on}, never a cancelled one, a filed one
    before one still open: the review's name, state and docstatus, with the
    row's decision, increase, remarks and what it raised."""
    if not appraisals:
        return {}
    rows = frappe.get_all(REVIEW_ROW, filters={"parenttype": REVIEW, "appraisal": ["in", appraisals]},
                          fields=["parent", "appraisal", "decision", "increase_percent", "remarks",
                                  "position_change", "improvement_plan"])
    if not rows:
        return {}
    reviews = {review.name: review for review in frappe.get_all(
        REVIEW, filters={"name": ["in", sorted({row.parent for row in rows})], "docstatus": ["!=", 2]},
        fields=["name", "docstatus", "status", review_approval.STATE_FIELD])}
    out = {}
    for row in rows:
        review = reviews.get(row.parent)
        if review is None or (row.appraisal in out and out[row.appraisal]["docstatus"] >= review.docstatus):
            continue
        out[row.appraisal] = dict(row, review=review.name, docstatus=review.docstatus,
                                  state=review.get(review_approval.STATE_FIELD) or review.status)
    return out


@frappe.whitelist(methods=["POST"])
def review_from_results(filters, appraisals=None):
    """Prepare Report for Management, on the Appraisal Results: the
    completed appraisals shown, or those ticked, that are on no review yet,
    put on the plant's review of the quarter that HR are still preparing,
    or on a new one, each with the outcome suggested as its decision. HR
    check it and send it on."""
    filters = frappe._dict(frappe.parse_json(filters) or {})
    picked = set(frappe.parse_json(appraisals) or []) if appraisals else set()
    frappe.has_permission(REVIEW, "create", throw=True)
    if not filters.get("appraisal_cycle"):
        frappe.throw(_("Choose the Appraisal Cycle first: a report covers one quarter."), title=_(REVIEW))
    rows = [row for row in results(dict(filters, include_unrated=1)) if not picked or row["appraisal"] in picked]
    ready = [row for row in rows if row["stage"] == rules.RECOMMENDED and row["docstatus"] == 1]
    unfinished = [row for row in rows if row["docstatus"] != 1 and row["stage"] in (rules.NOT_RATED,
                                                                                    rules.RECOMMENDED)]
    if not ready:
        frappe.throw(_("Nothing to add: the appraisals shown are on a review already, or not completed yet."),
                     title=_(REVIEW))
    plants = {row["branch"] for row in ready}
    if not filters.get("branch") and len(plants) > 1:
        frappe.throw(_("Choose the Plant: each plant's General Manager approves its own results."),
                     title=_(REVIEW))
    branch = filters.get("branch") or next(iter(plants))
    review = _review_in_preparation(filters.appraisal_cycle, branch) or frappe.new_doc(REVIEW)
    if review.is_new():
        review.update({"appraisal_cycle": filters.appraisal_cycle, "branch": branch, "review_date": today(),
                       "company": filters.get("company") or ready[0].get("company")})
    for row in ready:
        review.append("employees", _review_row(row))
    review.save()
    return {"name": review.name, "added": len(ready), "unfinished": len(unfinished)}


def _review_in_preparation(cycle, branch):
    """The plant's review of the quarter that HR are still preparing."""
    name = frappe.db.get_value(REVIEW, {"appraisal_cycle": cycle, "branch": branch or ["is", "not set"],
                                        "docstatus": 0, "status": review_approval.DRAFT}, "name")
    return frappe.get_doc(REVIEW, name) if name else None


def _review_row(row):
    """A row of the review from a row of the results, decided as suggested."""
    return {"employee": row["employee"], "employee_name": row["employee_name"], "designation": row["designation"],
            "appraisal": row["appraisal"], "department": row["department"], "total_score": row["score"],
            "band": row["band"], "decision": row["outcome"], "increase_percent": row["increase"] or 0}


@frappe.whitelist()
def get_appraisals(appraisal_cycle, branch=None):
    """The form's Get Appraisals: the cycle's completed appraisals on no
    review yet, of the review's plant where it names one, each with the
    outcome the score suggests as its decision."""
    return [dict(_review_row(row), recommended=row["outcome"])
            for row in results({"appraisal_cycle": appraisal_cycle, "branch": branch})
            if row["stage"] == rules.RECOMMENDED and row["docstatus"] == 1]


def review_validate(doc, method=None):
    doc.title = " ".join(str(part) for part in (doc.get("appraisal_cycle"), doc.get("branch")) if part)
    if not doc.get("review_date"):
        doc.review_date = today()
    rates = increase_rates()
    for row in doc.get("employees") or []:
        row.recommended = rules.recommended(flt(row.total_score), rates) if row.get("band") else None
        if row.get("decision") != rules.INCREASE:
            row.increase_percent = 0
        elif not flt(row.get("increase_percent")):
            row.increase_percent = rules.increase_for(flt(row.total_score), rates) or 0
    _sum_up(doc)
    _check_on_one_review(doc)
    _check_review_step(doc)
    doc.status = doc.get(review_approval.STATE_FIELD) or (
        review_approval.APPROVED if doc.docstatus == 1 else review_approval.DRAFT)
    if doc.docstatus == 1:
        undecided = [row.employee_name or row.employee for row in doc.get("employees") or [] if not row.decision]
        if undecided:
            frappe.throw(_("Management must decide on every employee before the review is filed: {0}").format(
                ", ".join(undecided[:5])), title=_(REVIEW))


def _sum_up(doc):
    """The figures on top of the review, and of its print."""
    rows = doc.get("employees") or []
    totals = [flt(row.total_score) for row in rows if row.get("band")]
    doc.appraised = len(rows)
    doc.average_score = round(sum(totals) / len(totals), 1) if totals else 0
    doc.below_pass = len([total for total in totals if total < rules.PIP_BELOW])
    doc.completion = _completion(doc)
    counts = rules.decision_counts(rows)
    doc.promotions, doc.increases = counts[rules.PROMOTION], counts[rules.INCREASE]
    doc.improvement_plans, doc.closed = counts[rules.PIP], counts[rules.CLOSE]


def _completion(doc):
    """How much of the quarter's appraising is done at the plant: the
    appraisals completed, of all those raised."""
    if not doc.get("appraisal_cycle"):
        return 0
    filters = {"appraisal_cycle": doc.appraisal_cycle, "docstatus": ["!=", 2]}
    if doc.get("branch"):
        filters["custom_branch"] = doc.branch
    raised = frappe.db.count("Appraisal", filters)
    done = frappe.db.count("Appraisal", dict(filters, docstatus=1))
    return round(100.0 * done / raised, 1) if raised else 0


def _check_on_one_review(doc):
    """An appraisal goes before management once: on one review that
    stands, and once on it."""
    names, twice = set(), []
    for row in doc.get("employees") or []:
        if not row.get("appraisal"):
            continue
        if row.appraisal in names:
            twice.append(row.employee_name or row.employee)
        names.add(row.appraisal)
    if twice:
        frappe.throw(_("Listed twice: {0}").format(", ".join(twice[:5])), title=_(REVIEW))
    if not names:
        return
    others = [row for row in frappe.get_all(REVIEW_ROW, filters={"parenttype": REVIEW, "appraisal": ["in", sorted(names)]},
                                            fields=["parent", "employee", "employee_name"])
              if row.parent != doc.name]
    standing = set(frappe.get_all(REVIEW, filters={"name": ["in", sorted({row.parent for row in others})],
                                                   "docstatus": ["!=", 2]}, pluck="name")) if others else set()
    clashes = ["%s (%s)" % (row.employee_name or row.employee, row.parent) for row in others if row.parent in standing]
    if clashes:
        frappe.throw(_("Already on another Performance Review: {0}").format(", ".join(clashes[:5])), title=_(REVIEW))


def _check_review_step(doc):
    """A step of the review's workflow: what it needs, the signature it
    leaves, what HR proposed kept as it goes to management, and who is
    told."""
    before = doc.get_doc_before_save()
    old_state = before.get(review_approval.STATE_FIELD) if before else None
    new_state = doc.get(review_approval.STATE_FIELD)
    if old_state != new_state:
        errors = review_approval.step_errors(old_state, new_state, {
            "rows": [row.as_dict() for row in doc.get("employees") or []],
            "return_remarks": doc.get("return_remarks"), "unfinished": _unfinished(doc)})
        if errors:
            frappe.throw("<br>".join(_(error) for error in errors), title=_(REVIEW))
        if new_state != review_approval.DRAFT:
            doc.return_remarks = None
        if old_state == review_approval.DRAFT and new_state in review_approval.PENDING_STATES:
            for row in doc.get("employees") or []:
                row.proposed_decision = row.decision
    current = {field: before.get(field) for field in review_approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in review_approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                      current).items():
        doc.set(field, value)
    if old_state != new_state:
        _tell_review_step(doc, old_state, new_state, before)


def _unfinished(doc):
    """Who on the review has an appraisal not completed yet."""
    names = sorted({row.appraisal for row in doc.get("employees") or [] if row.get("appraisal")})
    done = set(frappe.get_all("Appraisal", filters={"name": ["in", names], "docstatus": 1}, pluck="name")) \
        if names else set()
    return [row.employee_name or row.employee for row in doc.get("employees") or []
            if row.get("appraisal") and row.appraisal not in done]


def _tell_review_step(doc, old_state, new_state, before):
    """Whoever the review now waits on is told and given it to do, and it
    is off the list of whoever had it; HR are told of a return."""
    branch = doc.get("branch")
    if old_state in review_approval.ROLE_WAITING:
        people.withdraw(doc.doctype, doc.name, people.people_for(review_approval.ROLE_WAITING[old_state], branch))
    what = _("The appraisal results for {0}").format(doc.title or doc.appraisal_cycle)
    if new_state in review_approval.ROLE_WAITING:
        role = review_approval.ROLE_WAITING[new_state]
        users = people.people_for(role, branch)
        if not users:
            frappe.msgprint(_("Nobody holds the {0} role for {1}, so nobody has been told. Give the role to the "
                              "right person.").format(_(role), branch or _("every plant")), title=_(REVIEW),
                            indicator="orange")
        message = _("{0} wait for your approval: {1}.").format(what, _decisions_line(doc))
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)
    elif new_state == review_approval.DRAFT and old_state in review_approval.PENDING_STATES:
        hr = {before.get("sent_by")} | set(people.hr_officers(branch))
        people.notify(sorted(user for user in hr if user), doc.doctype, doc.name,
                      _("{0} came back from management: {1}").format(what, doc.get("return_remarks") or ""))


def _decisions_line(doc):
    counts = rules.decision_counts(doc.get("employees") or [])
    return "; ".join("%s %d" % (_(decision), counts[decision]) for decision in rules.DECISIONS if counts[decision])


@frappe.whitelist(methods=["POST"])
def share_with_management(name, shared_with):
    """Share a Copy: the review for anyone else in management to read (the
    General Manager and the Executive Director have it by its own steps).
    Each user named is told and may open it."""
    doc = frappe.get_doc(REVIEW, name)
    doc.check_permission("share")
    named = [part.strip() for part in (shared_with or "").replace(";", ",").replace("\n", ",").split(",")
             if part.strip()]
    users, unknown = [], []
    for entry in named:
        user = entry if frappe.db.exists("User", entry) else frappe.db.get_value("User", {"email": entry}, "name")
        if user:
            users.append(user)
        else:
            unknown.append(entry)
    if unknown:
        frappe.throw(_("Not users of the system: {0}").format(", ".join(unknown)), title=_("Share a Copy"))
    from frappe.share import add_docshare

    for user in users:
        add_docshare(REVIEW, name, user, read=1, flags={"ignore_share_permission": True})
    copies = [part.strip() for part in (doc.get("shared_with") or "").split(",") if part.strip()]
    doc.db_set("shared_with", ", ".join(dict.fromkeys(copies + users)), update_modified=False)
    people.notify(users, REVIEW, name, _("A copy of the appraisal results for {0}.").format(
        doc.title or doc.appraisal_cycle))
    return doc.shared_with


def review_on_submit(doc, method=None):
    """Cases 6 to 10, once management approve: each decision carried out (a
    promotion or an increase as an Employee Position Change, a PIP as its
    own plan, anything else closed), the appraisal told what was decided,
    and HR told."""
    if not doc.get("decided_by"):
        # filed without the workflow's last step: whoever filed it decided
        doc.db_set({"decided_by": frappe.session.user, "decided_on": today()}, update_modified=False)
    doc.db_set("status", review_approval.APPROVED, update_modified=False)
    for row in doc.get("employees") or []:
        if row.decision in position_rules.CHANGE_TYPES or row.decision in rules.POSITION_CHANGE_FOR:
            _raise_position_change(doc, row)
        elif row.decision == rules.PIP:
            _raise_pip(doc, row)
        if row.appraisal and frappe.db.exists("Appraisal", row.appraisal):
            frappe.db.set_value("Appraisal", row.appraisal,
                                {"custom_outcome": row.decision, "custom_performance_review": doc.name},
                                update_modified=False)
    hr = {doc.get("sent_by")} | set(people.hr_officers(doc.get("branch")))
    people.notify(sorted(user for user in hr if user), doc.doctype, doc.name,
                  _("The appraisal results for {0} are approved: {1}.").format(doc.title or doc.appraisal_cycle,
                                                                               _decisions_line(doc)))


def _raise_position_change(review, row):
    if row.position_change and frappe.db.exists("Employee Position Change", row.position_change):
        return
    change = frappe.new_doc("Employee Position Change")
    change.update({
        "change_type": rules.POSITION_CHANGE_FOR.get(row.decision, row.decision),
        "employee": row.employee, "effective_date": review.review_date,
        "contract_action": position_rules.DEFAULT_CONTRACT_ACTION,
        "appraisal_score": row.total_score,
    })
    change.flags.ignore_permissions = True
    change.flags.ignore_mandatory = True
    change.insert()
    row.db_set("position_change", change.name, update_modified=False)
    message = _("{0} for {1}: fill in the new designation and pay, then send it for approval.").format(
        change.change_type, row.employee_name or row.employee)
    if row.decision == rules.INCREASE and flt(row.get("increase_percent")) and flt(change.get("current_salary")):
        # the increase management approved, worked out on the pay the change starts from
        pay = rules.increased(change.current_salary, row.increase_percent)
        change.db_set({"new_salary": pay, "new_salary_in_words": position_rules.in_words(pay)},
                      update_modified=False)
        message = _("{0} for {1}: {2}% approved, from {3} to {4}. Check it, then send it for approval.").format(
            change.change_type, row.employee_name or row.employee, "%g" % flt(row.increase_percent),
            "{:,.0f}".format(flt(change.current_salary)), "{:,}".format(pay))
    people.notify(people.hr_officers(review.get("branch")), "Employee Position Change", change.name, message)


def _raise_pip(review, row):
    if row.improvement_plan and frappe.db.exists("Performance Improvement Plan", row.improvement_plan):
        return
    start = getdate(review.review_date)
    plan = frappe.new_doc("Performance Improvement Plan")
    plan.update({
        "employee": row.employee, "appraisal": row.appraisal, "appraisal_score": row.total_score,
        "performance_review": review.name, "start_date": start, "months": pip_rules.DEFAULT_MONTHS,
        "end_date": pip_rules.end_date(start, pip_rules.DEFAULT_MONTHS),
        "supervisor": frappe.db.get_value("Employee", row.employee, "reports_to"),
        "reason": _("Scored {0}% at the {1} appraisal, below the pass mark of {2}%.").format(
            row.total_score, review.appraisal_cycle, rules.PIP_BELOW),
    })
    plan.flags.ignore_permissions = True
    plan.flags.ignore_mandatory = True
    plan.insert()
    row.db_set("improvement_plan", plan.name, update_modified=False)
    told = [frappe.db.get_value("Employee", plan.supervisor, "user_id")] if plan.supervisor else []
    told += people.hr_officers(review.get("branch"))
    people.notify(told, "Performance Improvement Plan", plan.name,
                  _("A Performance Improvement Plan is recommended for {0}. Agree what must improve with them.").format(
                      row.employee_name or row.employee))


def review_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)
    for row in doc.get("employees") or []:
        if row.appraisal and frappe.db.exists("Appraisal", row.appraisal):
            frappe.db.set_value("Appraisal", row.appraisal,
                                {"custom_outcome": None, "custom_performance_review": None}, update_modified=False)


# ── 2. Watching the plan ──────────────────────────────────────────────
def daily():
    """The HR Officer is told when a quarter is due; everyone appraising is
    reminded before the deadlines."""
    day = today()
    _tell_due(day)
    _remind_of_deadlines(day)
    frappe.db.commit()


def _tell_due(day):
    rows = frappe.get_all(
        "Appraisal Plan Quarter",
        filters={"parenttype": "Appraisal Plan", "appraisal_cycle": ["is", "not set"],
                 "notified_on": ["is", "not set"]},
        fields=["name", "parent", "quarter", "to_date"])
    plans = {row.parent for row in rows}
    live = set(frappe.get_all("Appraisal Plan", filters={"name": ["in", list(plans)], "docstatus": 1},
                              pluck="name")) if plans else set()
    for row in rules.due_quarters([row for row in rows if row.parent in live], day):
        plan = frappe.get_doc("Appraisal Plan", row["parent"])
        officers = people.hr_officers(plan.get("branch"), plan.get("department"))
        message = _("{0} has closed: raise the appraisals for it.").format(row["quarter"])
        people.notify(officers, "Appraisal Plan", plan.name, message)
        people.assign("Appraisal Plan", plan.name, officers, message)
        frappe.db.set_value("Appraisal Plan Quarter", row["name"], "notified_on", day, update_modified=False)


def _remind_of_deadlines(day):
    for cycle in frappe.get_all(
            "Appraisal Cycle", filters={"status": "In Progress", "custom_hard_deadline": [">=", day]},
            fields=["name", "cycle_name", "custom_hard_deadline", "custom_soft_deadline", "custom_reminders_sent",
                    "branch", "department"]):
        due = rules.reminders_due(cycle.custom_hard_deadline, day, cycle.custom_reminders_sent,
                                  cycle.custom_soft_deadline)
        if not due:
            continue
        waiting = frappe.get_all("Appraisal", filters={"appraisal_cycle": cycle.name, "docstatus": 0},
                                 fields=["name", "custom_supervisor", "employee", "workflow_state"])
        users = {frappe.db.get_value("Employee", row.custom_supervisor, "user_id")
                 for row in waiting if row.custom_supervisor}
        # and whoever has still to appraise themselves
        users |= {frappe.db.get_value("Employee", row.employee, "user_id")
                  for row in waiting if row.workflow_state == approval.PENDING_SELF}
        users |= set(people.hr_officers(cycle.get("branch"), cycle.get("department")))
        message = _("{0} appraisals are due by {1}: {2} still to be completed.").format(
            cycle.cycle_name, frappe.utils.format_date(cycle.custom_hard_deadline), len(waiting))
        people.notify([user for user in users if user], "Appraisal Cycle", cycle.name, message)
        frappe.db.set_value("Appraisal Cycle", cycle.name, "custom_reminders_sent",
                            rules.record_reminders(cycle.custom_reminders_sent, due), update_modified=False)


def setup_workflows_on_migrate():
    """after_migrate: the appraisal's workflow and the rights its signatories
    need on Frappe HR's Appraisal (workflows.py)."""
    workflows.setup_on_migrate(approval, "Performance Appraisal workflow")
    # and the review that takes the results to management (cases 5, 6, 10)
    workflows.setup_on_migrate(review_approval, "Performance Review workflow")
