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
  open_quarter raises the appraisals for a quarter and tells the supervisor
               and the employee (case 3)
  appraisal_*  the form itself: the scores, the signatures (case 4)
  sheet        the flowchart's other branch: export the sheet, the
               supervisor fills it away from the system, HR uploads it
  review_*     the report to top management and the decision (cases 5, 6,
               10); a promotion or an increase raises an Employee Position
               Change (cases 8, 9), a PIP a Performance Improvement Plan
               (case 7)
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import (
    appraisal_approval as approval,
    appraisal_rules as rules,
    bsc,
    bsc_rules,
    people,
    pip_rules,
    position_rules,
    workflows,
)

HOD_ROLE = "Head of Department"


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
        "kra_evaluation_method": "Manual Rating",
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
    appraisal = frappe.get_doc({
        "doctype": "Appraisal", "employee": employee.name, "employee_name": employee.employee_name,
        "appraisal_cycle": cycle.name, "company": plan.company, "department": employee.department,
        "designation": employee.designation, "start_date": row.from_date, "end_date": row.to_date,
        "rate_goals_manually": 1,
        "custom_plan": plan.name, "custom_quarter": row.quarter, "custom_supervisor": employee.reports_to,
        "custom_appraisal_status": approval.DRAFT, "workflow_state": approval.DRAFT,
    })
    # the role's scorecard decides which form: a graded role with an active
    # BSC template is appraised on it, everyone else on LPL/HR/18
    card = bsc.template_for(designation=employee.get("designation"), year=plan.get("year"))
    if card:
        appraisal.custom_form_type = approval.FORM_BSC
        appraisal.custom_bsc_template = card
        appraisal.custom_period = row.quarter if row.quarter in bsc_rules.QUARTERS else bsc_rules.ANNUAL
        bsc.fill(appraisal, card)
    else:
        appraisal.custom_form_type = approval.FORM_SUPERVISORY
        appraisal.set("custom_factors", [{"item": factor} for factor in _factors()])
        appraisal.set("custom_objectives", [{"item": objective} for objective in _objectives(employee)])
    appraisal.flags.ignore_permissions = True
    appraisal.flags.ignore_mandatory = True
    appraisal.insert()
    _tell_about(appraisal, employee)
    return appraisal


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
    """The supervisor and the employee are told the appraisal is open."""
    when = _("{0} {1}").format(appraisal.custom_quarter or "", appraisal.get("custom_plan") or "")
    supervisor = frappe.db.get_value("Employee", appraisal.custom_supervisor, "user_id") \
        if appraisal.get("custom_supervisor") else None
    message = _("Appraisal open for {0} ({1}). Rate them once they have assessed themselves.").format(
        employee.employee_name or employee.name, when)
    people.notify([supervisor], "Appraisal", appraisal.name, message)
    people.assign("Appraisal", appraisal.name, [supervisor], message,
                  date=appraisal.get("end_date"))
    if employee.get("user_id"):
        people.notify([employee.user_id], "Appraisal", appraisal.name,
                      _("Your appraisal for {0} is open. Complete the self-assessment.").format(when))


# ── 4. The form ───────────────────────────────────────────────────────
def appraisal_validate(doc, method=None):
    if not doc.get("custom_supervisor") and doc.get("employee"):
        doc.custom_supervisor = frappe.db.get_value("Employee", doc.employee, "reports_to")
    if not doc.get("custom_form_type"):
        doc.custom_form_type = approval.FORM_BSC if bsc.template_for(employee=doc.get("employee")) \
            else approval.FORM_SUPERVISORY
    if _is_bsc(doc):
        _attach_scorecard(doc)
        bsc.score(doc)
        _carry_scores(doc, doc.get("custom_bsc_overall"), doc.get("custom_bsc_band"))
    else:
        if not doc.get("custom_factors"):
            for factor in _factors():
                doc.append("custom_factors", {"item": factor})
        _score(doc)
    _check_step(doc)
    doc.custom_appraisal_status = doc.get("workflow_state") or doc.get("custom_appraisal_status") or approval.DRAFT


def _is_bsc(doc):
    return doc.get("custom_form_type") == approval.FORM_BSC


def _attach_scorecard(doc):
    """The role's scorecard, attached and filled in without being asked for.

    Luuka: "these templates will be already attached to the
    employee/designation and will automatically populate the information."
    The plan already did this when it raised an appraisal; an appraisal made
    by hand gets it here too. Nothing already scored is touched, and a
    submitted appraisal is left exactly as it was approved.
    """
    if doc.docstatus != 0 or not doc.get("employee"):
        return
    if not doc.get("custom_bsc_template"):
        year = None
        if doc.get("start_date"):
            year = getdate(doc.start_date).year
        doc.custom_bsc_template = bsc.template_for(employee=doc.employee, year=year)
    if doc.get("custom_bsc_template") and not doc.get("custom_bsc_perspectives"):
        bsc.fill(doc, doc.custom_bsc_template)


def _carry_scores(doc, total, band):
    """The scorecard's overall is the appraisal's score, so one review, one
    report and one chart read both forms the same way."""
    doc.custom_total_score = total
    doc.custom_band = band
    doc.final_score = flt(total or 0)
    doc.custom_annual_score = _annual(doc)


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
                              [row.employee_rating for row in doc.get("custom_objectives") or []])
    # Frappe HR's fields, so its chart and its list views read the round
    doc.final_score = flt(found["total"] or 0)
    doc.total_score = flt(found["objectives"] or 0)
    doc.self_score = flt(self_found["total"] or 0)
    doc.custom_annual_score = _annual(doc)


def _annual(doc):
    """The year to date: the average of this employee's scored quarters, as
    the recommendation asks."""
    if not (doc.get("employee") and doc.get("custom_plan")):
        return None
    others = frappe.get_all("Appraisal", filters={"employee": doc.employee, "custom_plan": doc.custom_plan,
                                                  "docstatus": ["!=", 2], "name": ["!=", doc.name or ""]},
                            pluck="custom_total_score")
    return rules.annual_average(list(others) + [doc.get("custom_total_score")])


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
        if new_state != approval.DRAFT and old_state in (None, approval.DRAFT, approval.PENDING_SUPERVISOR):
            if _is_bsc(doc):
                # the scorecard is scored by the appraiser, not self-assessed
                if old_state == approval.PENDING_SUPERVISOR:
                    errors = bsc_rules.appraisal_errors(bsc.facts(doc, "appraiser")) + errors
            else:
                step = {approval.PENDING_SUPERVISOR: "self", approval.PENDING_HRM: "supervisor"}.get(new_state)
                if step:
                    errors = rules.appraisal_errors(_facts(doc, step)) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Appraisal"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current,
                                                form_type).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_next(doc, new_state)


def _tell_next(doc, state):
    role = approval.ROLE_WAITING[state]
    if state == approval.PENDING_SUPERVISOR and doc.get("custom_supervisor"):
        users = [frappe.db.get_value("Employee", doc.custom_supervisor, "user_id")]
    elif state == approval.PENDING_EMPLOYEE:
        users = [frappe.db.get_value("Employee", doc.employee, "user_id")]
    else:
        users = people.people_for(role, doc.get("custom_branch"), doc.get("department"))
    message = _("Appraisal of {0}: your rating and signature are needed.").format(
        doc.get("employee_name") or doc.get("employee"))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def appraisal_on_cancel(doc, method=None):
    doc.db_set("custom_appraisal_status", approval.CANCELLED, update_modified=False)


# ── The sheet, for appraising away from the system ────────────────────
@frappe.whitelist()
def download_sheet(appraisal_cycle=None, appraisal=None):
    """The flowchart's other branch: the quarter's appraisals as one sheet
    the supervisor fills in, then HR uploads."""
    names = [appraisal] if appraisal else frappe.get_all(
        "Appraisal", filters={"appraisal_cycle": appraisal_cycle, "docstatus": 0}, pluck="name", order_by="name asc")
    if not names:
        frappe.throw(_("No appraisals to export for this cycle."))
    rows = []
    for name in names:
        doc = frappe.get_doc("Appraisal", name)
        doc.check_permission("read")
        rows.extend(rules.sheet_rows(doc.name, doc.employee, doc.employee_name,
                                     [row.as_dict() for row in doc.get("custom_factors") or []],
                                     [row.as_dict() for row in doc.get("custom_objectives") or []]))
    from frappe.utils.xlsxutils import build_xlsx_response

    build_xlsx_response([list(rules.SHEET_COLUMNS)] + rows, "Appraisal Sheet")


@frappe.whitelist(methods=["POST"])
def upload_sheet(file_url, appraisal_cycle=None):
    """The filled sheet back in: each appraisal's supervisor ratings and
    comments are written onto it. Returns how many were updated."""
    from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

    found = rules.read_sheet(read_xlsx_file_from_attached_file(file_url=file_url))
    if not found:
        frappe.throw(_("Nothing on that sheet: keep the columns it was downloaded with."))
    updated = 0
    for name, sections in found.items():
        if not frappe.db.exists("Appraisal", name):
            continue
        doc = frappe.get_doc("Appraisal", name)
        if appraisal_cycle and doc.appraisal_cycle != appraisal_cycle:
            continue
        doc.check_permission("write")
        if doc.docstatus != 0:
            continue
        for table, key in (("custom_factors", "A"), ("custom_objectives", "B")):
            for row in doc.get(table) or []:
                rating, comment = sections.get(key, {}).get((row.item or "").strip(), (None, None))
                if rating:
                    row.supervisor_rating = rating
                if comment:
                    row.supervisor_comment = comment
        doc.flags.ignore_permissions = True
        doc.save()
        updated += 1
    return updated


# ── 5, 6, 10. The report and the decision ─────────────────────────────
def review_validate(doc, method=None):
    doc.title = " ".join(str(part) for part in (doc.get("appraisal_cycle"), doc.get("branch")) if part)
    if not doc.get("review_date"):
        doc.review_date = today()
    totals = [flt(row.total_score) for row in doc.get("employees") or [] if row.total_score is not None]
    doc.appraised = len(doc.get("employees") or [])
    doc.average_score = round(sum(totals) / len(totals), 1) if totals else 0
    doc.below_pass = len([total for total in totals if total < rules.PIP_BELOW])
    doc.completion = round(100.0 * len(totals) / doc.appraised, 1) if doc.appraised else 0
    for row in doc.get("employees") or []:
        row.recommended = rules.recommended(row.total_score)
    if doc.docstatus == 0:
        doc.status = "Shared" if doc.get("shared_on") else "Draft"
    if doc.docstatus == 1:
        undecided = [row.employee_name or row.employee for row in doc.get("employees") or [] if not row.decision]
        if undecided:
            frappe.throw(_("Management must decide on every employee before the review is filed: {0}").format(
                ", ".join(undecided[:5])), title=_("Performance Review"))


@frappe.whitelist()
def get_appraisals(appraisal_cycle):
    """The cycle's completed appraisals, for the report's Get Appraisals."""
    rows = frappe.get_all(
        "Appraisal", filters={"appraisal_cycle": appraisal_cycle, "docstatus": ["!=", 2]},
        fields=["name", "employee", "employee_name", "department", "custom_total_score", "custom_band"],
        order_by="custom_total_score desc")
    return [{"employee": row.employee, "employee_name": row.employee_name, "appraisal": row.name,
             "department": row.department, "total_score": row.custom_total_score, "band": row.custom_band,
             "recommended": rules.recommended(row.custom_total_score)} for row in rows]


@frappe.whitelist(methods=["POST"])
def share_with_management(name, shared_with):
    """Case 5: the report goes to the top management team."""
    doc = frappe.get_doc("Performance Review", name)
    doc.check_permission("write")
    doc.db_set({"shared_with": shared_with, "shared_on": today(), "status": "Shared"}, update_modified=False)
    users = [part.strip() for part in (shared_with or "").replace(";", ",").split(",") if part.strip()]
    people.notify(users, doc.doctype, doc.name,
                  _("The appraisal report for {0} is ready for review.").format(doc.appraisal_cycle))
    return doc.status


def review_on_submit(doc, method=None):
    """Case 6: each decision is carried out — a promotion or an increase as
    an Employee Position Change, a PIP as its own plan, anything else
    closed."""
    doc.db_set({"status": "Decided", "decided_by": frappe.session.user, "decided_on": today()},
               update_modified=False)
    for row in doc.get("employees") or []:
        if row.decision in position_rules.CHANGE_TYPES or row.decision in rules.POSITION_CHANGE_FOR:
            _raise_position_change(doc, row)
        elif row.decision == rules.PIP:
            _raise_pip(doc, row)
        if row.appraisal and frappe.db.exists("Appraisal", row.appraisal):
            frappe.db.set_value("Appraisal", row.appraisal,
                                {"custom_outcome": row.decision, "custom_performance_review": doc.name},
                                update_modified=False)


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
    people.notify(people.hr_officers(review.get("branch")), "Employee Position Change", change.name,
                  _("{0} for {1}: fill in the new designation and pay, then send it for approval.").format(
                      change.change_type, row.employee_name or row.employee))


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
                                 fields=["name", "custom_supervisor"])
        users = {frappe.db.get_value("Employee", row.custom_supervisor, "user_id")
                 for row in waiting if row.custom_supervisor}
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
