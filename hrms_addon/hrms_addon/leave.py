# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Management on the site (4.1).

The rules are in leave_rules.py, without a Frappe import
(scripts/verify_leave.py). This reads and writes the site.

  plan_*        the Annual Leave Plan: the HR Officer draws it up at the
                end of a year, the HODs approve it for their own people,
                the HR Officer tells everyone their dates.
  application_* LPL/HR/15 on Frappe HR's own Leave Application: Part 1 the
                applicant's, Part 2 the HR Officer's balances, Part 3 the
                three signatures, Part 4 what Accounts advanced. Their
                `status` stays theirs; the chain's own state sits beside it.
  daily         step 4, the system monitoring: a planned leave falling due
                tells the employee and the immediate supervisor, and a
                leave whose last day has passed asks for the report back.
  raise_advance step 7: the form's "Salary Requested in Advance" raises the
                Leave Advance for the HR Officer (advances.py).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import leave_rules as rules, people

PLAN = "Annual Leave Plan"
APPLICATION = "Leave Application"


# ── 1. The Annual Leave Plan ──────────────────────────────────────────
def plan_validate(doc, method=None):
    doc.title = _("Leave Plan %s") % (doc.get("year") or "")
    _fill_plan_rows(doc)
    doc.total_employees = len(doc.get("employees") or [])
    doc.total_days = sum(flt(row.planned_days) for row in doc.get("employees") or [])
    _check_plan_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or "Draft"


def _fill_plan_rows(doc):
    """Days from the dates, and what each employee is entitled to, so the
    plan is drawn up against real balances rather than guesses."""
    for row in doc.get("employees") or []:
        if row.planned_from and row.planned_to:
            counted = rules.days_between(row.planned_from, row.planned_to)
            if not row.planned_days:
                row.planned_days = counted
        elif row.planned_from and row.planned_days and not row.planned_to:
            row.planned_to = rules.end_for(row.planned_from, row.planned_days)
        if row.employee and not row.entitlement_days:
            row.entitlement_days = _entitlement(row.employee, doc.get("year"))


def _entitlement(employee, year):
    """Annual leave allocated to this employee for the plan year."""
    if not (employee and year):
        return 0
    start, end = rules.year_window(year)
    rows = frappe.get_all("Leave Allocation",
                          filters={"employee": employee, "leave_type": rules.ANNUAL, "docstatus": 1,
                                   "from_date": ["<=", end], "to_date": [">=", start]},
                          pluck="total_leaves_allocated")
    return flt(sum(flt(value) for value in rows))


def _check_plan_step(doc):
    from hrms_addon.hrms_addon import leave_plan_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {"return_remarks": doc.get("return_remarks")})
        if new_state == approval.PENDING_HOD and old_state in (None, approval.DRAFT):
            errors = rules.plan_errors(_plan_facts(doc)) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Annual Leave Plan"))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_plan(doc, new_state)


def _plan_facts(doc):
    return {
        "year": doc.get("year"),
        "rows": [row.as_dict() for row in doc.get("employees") or []],
    }


def _tell_plan(doc, state):
    from hrms_addon.hrms_addon import leave_plan_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"), doc.get("department"))
    message = _("Annual Leave Plan for {0}: {1} employee(s) to approve.").format(
        doc.get("year"), doc.get("total_employees") or 0)
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def plan_on_submit(doc, method=None):
    """Approved. Step 3 follows: the HR Officer tells the employees."""
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    message = _("Leave Plan {0} is approved. Tell the {1} employee(s) their dates.").format(
        doc.get("year"), doc.get("total_employees") or 0)
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def plan_on_cancel(doc, method=None):
    doc.status = "Cancelled"


@frappe.whitelist(methods=["POST"])
def inform_employees(plan):
    """Step 3: tell every employee on an approved plan their dates."""
    doc = frappe.get_doc(PLAN, plan)
    doc.check_permission("write")
    if doc.docstatus != 1:
        frappe.throw(_("The plan is told to the employees once it is approved."))
    told = 0
    for row in doc.employees:
        user = frappe.db.get_value("Employee", row.employee, "user_id")
        if user:
            people.notify([user], PLAN, doc.name, _("Your {0} leave is planned for {1} to {2} ({3} day(s)).")
                          .format(doc.year, frappe.utils.format_date(row.planned_from),
                                  frappe.utils.format_date(row.planned_to), flt(row.planned_days)))
        row.db_set("informed", 1, update_modified=False)
        row.db_set("informed_on", today(), update_modified=False)
        told += 1
    doc.db_set("informed_count", told)
    doc.db_set("informed_on", today())
    return told


# ── 2. LPL/HR/15 ──────────────────────────────────────────────────────
def application_validate(doc, method=None):
    from hrms_addon.hrms_addon import leave_approval as approval

    _fill_balances(doc)
    _check_application_step(doc)
    state = doc.get("workflow_state")
    doc.custom_leave_status = state or doc.get("custom_leave_status") or approval.DRAFT
    # Frappe HR's own status is what their controller and their ledger read
    if state:
        doc.status = approval.upstream_status(state)
    if doc.get("custom_reported_back") and not doc.get("custom_reported_back_on"):
        doc.custom_reported_back_on = today()


def _fill_balances(doc):
    """Part 2 of the form: what was left before the leave and what is left
    after it. The HR Officer types the balance before; the rest follows."""
    if doc.get("custom_balance_before") in (None, 0) and doc.get("leave_balance"):
        doc.custom_balance_before = flt(doc.leave_balance)
    if doc.get("custom_balance_before"):
        doc.custom_balance_after = rules.balance_after(doc.custom_balance_before, doc.get("total_leave_days"))
    if doc.get("custom_sick_balance_before"):
        taken = flt(doc.total_leave_days) if doc.get("leave_type") == rules.SICK else 0
        doc.custom_sick_balance_after = rules.balance_after(doc.custom_sick_balance_before, taken)
    if not doc.get("custom_last_leave_type") and doc.get("employee"):
        _fill_last_leave(doc)


def _fill_last_leave(doc):
    last = frappe.get_all(APPLICATION,
                          filters={"employee": doc.employee, "docstatus": 1, "status": "Approved",
                                   "name": ["!=", doc.name or ""]},
                          fields=["leave_type", "from_date", "to_date", "total_leave_days"],
                          order_by="to_date desc", limit=1)
    if last:
        doc.custom_last_leave_type = last[0].leave_type
        doc.custom_last_leave_from = last[0].from_date
        doc.custom_last_leave_to = last[0].to_date
        doc.custom_last_leave_days = last[0].total_leave_days


def _check_application_step(doc):
    from hrms_addon.hrms_addon import leave_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            "custom_balance_before": doc.get("custom_balance_before"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_SUPERVISOR and old_state in (None, approval.DRAFT):
            errors = rules.application_errors(_application_facts(doc)) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Leave Application"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state == approval.PENDING_HR:
        doc.custom_hro_by = doc.custom_hro_by or frappe.session.user
        doc.custom_hro_on = doc.custom_hro_on or today()
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_application(doc, new_state)


def _application_facts(doc):
    return {
        "leave_type": doc.get("leave_type"), "from_date": doc.get("from_date"), "to_date": doc.get("to_date"),
        "total_leave_days": doc.get("total_leave_days"),
        "certificate": doc.get("custom_medical_certificate"),
        "reason": doc.get("description"),
        "balance_before": doc.get("custom_balance_before") or doc.get("leave_balance"),
    }


def _tell_application(doc, state):
    from hrms_addon.hrms_addon import leave_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("custom_branch"), doc.get("department"))
    message = _("Leave application from {0}: {1} to {2}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.format_date(doc.get("from_date")),
        frappe.utils.format_date(doc.get("to_date")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message, date=doc.get("from_date"))


def application_on_submit(doc, method=None):
    """Approved. Step 7: an advance was asked for, so the HR Officer is told
    to start the Leave Advance process."""
    if doc.get("status") != "Approved":
        return
    _mark_plan_row(doc)
    if not rules.advance_wanted({"salary_requested_in_advance": doc.get("custom_salary_requested_in_advance")}):
        return
    users = people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    message = _("{0} asked for salary in advance on their leave. Raise the Leave Advance.").format(
        doc.get("employee_name") or doc.employee)
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message, date=doc.get("from_date"))


def application_on_cancel(doc, method=None):
    doc.custom_leave_status = "Cancelled"


def _mark_plan_row(doc):
    """The plan row this leave was foreseen in keeps the application, so the
    plan shows what has actually been taken."""
    if not doc.get("custom_plan"):
        return
    row = frappe.db.get_value("Annual Leave Plan Employee",
                              {"parent": doc.custom_plan, "employee": doc.employee}, "name")
    if row:
        frappe.db.set_value("Annual Leave Plan Employee", row, "leave_application", doc.name,
                            update_modified=False)


@frappe.whitelist(methods=["POST"])
def raise_advance(leave_application):
    """Step 7: the Leave Advance, raised from the leave form (advances.py)."""
    from hrms_addon.hrms_addon import advances

    return advances.from_leave(leave_application)


# ── 3. Step 4: the system watching ────────────────────────────────────
def daily():
    """A planned leave coming due, and a leave nobody has reported back from."""
    _tell_due()
    _ask_report_back()


def _tell_due():
    """The employee and the immediate supervisor, told as a planned leave
    comes near: a month, a fortnight and a week before (leave_rules)."""
    now = getdate(today())
    rows = frappe.get_all(
        "Annual Leave Plan Employee",
        filters={"parenttype": PLAN, "planned_from": ["between", [now, add_days(now, max(rules.DUE_HORIZONS))]]},
        fields=["name", "parent", "employee", "employee_name", "planned_from", "planned_to", "planned_days",
                "alerts_sent", "leave_application"])
    for row in rows:
        if row.leave_application:
            continue  # already applied for
        if frappe.db.get_value(PLAN, row.parent, "docstatus") != 1:
            continue
        horizons = rules.due_alerts(row.planned_from, now, sent=row.alerts_sent)
        if not horizons:
            continue
        _tell_employee_due(row, horizons[0])
        frappe.db.set_value("Annual Leave Plan Employee", row.name, "alerts_sent",
                            rules.record_alerts(row.alerts_sent, horizons), update_modified=False)
    frappe.db.commit()


def _tell_employee_due(row, days):
    employee = frappe.db.get_value("Employee", row.employee,
                                   ["user_id", "reports_to", "branch", "department"], as_dict=True)
    if not employee:
        return
    message = _("{0}'s leave is due in {1} day(s): {2} to {3}.").format(
        row.employee_name or row.employee, days, frappe.utils.format_date(row.planned_from),
        frappe.utils.format_date(row.planned_to))
    users = []
    if employee.user_id:
        users.append(employee.user_id)
    supervisor = frappe.db.get_value("Employee", employee.reports_to, "user_id") if employee.reports_to else None
    if supervisor:
        users.append(supervisor)
    users.extend(people.people_for("Supervisor", employee.branch, employee.department))
    if users:
        people.notify(list(dict.fromkeys(users)), PLAN, row.parent, message)


def _ask_report_back():
    """Step 8: a leave whose last day has passed and nobody has said the
    employee is back."""
    rows = frappe.get_all(APPLICATION,
                          filters={"docstatus": 1, "status": "Approved", "custom_reported_back": 0,
                                   "to_date": ["<", today()]},
                          fields=["name", "employee", "employee_name", "to_date", "custom_branch", "department"],
                          limit=200)
    for row in rows:
        users = people.hr_officers(row.custom_branch, row.department)
        if not users:
            continue
        message = _("{0}'s leave ended on {1}. Mark them as reported back.").format(
            row.employee_name or row.employee, frappe.utils.format_date(row.to_date))
        people.assign(APPLICATION, row.name, users, message)
    frappe.db.commit()


# ── 4. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the plan's two approvals and the form's three."""
    from hrms_addon.hrms_addon import leave_approval, leave_plan_approval, workflows

    workflows.setup_on_migrate(leave_plan_approval, "Annual Leave Plan workflow")
    workflows.setup_on_migrate(leave_approval, "Leave Application workflow")


def seed_leave_types():
    """The five kinds LPL/HR/15 offers, as Leave Types on the site. An
    existing one is left exactly as Luuka has set it up."""
    made = []
    for name in rules.LEAVE_TYPES:
        if frappe.db.exists("Leave Type", name):
            continue
        doc = frappe.new_doc("Leave Type")
        doc.leave_type_name = name
        doc.max_leaves_allowed = rules.STATUTORY_DAYS.get(name, 0)
        if name == rules.UNPAID:
            doc.is_lwp = 1
        if name == rules.ANNUAL:
            doc.is_carry_forward = 1
            doc.allow_encashment = 1
        doc.insert(ignore_permissions=True)
        made.append(name)
    return made
