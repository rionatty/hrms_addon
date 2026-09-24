# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Management on the site (4.1).

The rules are in leave_rules.py, without a Frappe import
(scripts/verify_leave.py). This reads and writes the site.

  plan_*        the Annual Leave Plan: the HR Officer draws it up at the
                end of a year (Get Employees brings in the plant or
                department, with what each has available), the HODs approve
                it for their own people, the HR Officer tells everyone their
                dates. A leave may be split in parts; days are counted as the
                Leave Application counts them; too many of one department
                off together shows as a clash.
  change_*      the Leave Plan Change: one planned leave moved to new dates,
                approved by the supervisor and the HOD.
  apply_from_plan  step 5 from the plan: the Leave Application, filled in.
  application_* LPL/HR/15 on Frappe HR's own Leave Application: Part 1 the
                applicant's, Part 2 the HR Officer's balances, Part 3 the
                three signatures, Part 4 what Accounts advanced. Their
                `status` stays theirs; the chain's own state sits beside it.
  daily         step 4, the system monitoring: a planned leave falling due
                tells the employee and the immediate supervisor, one that
                has started with nothing applied for tells HR, each planned
                leave's status is brought up to date, and a leave whose last
                day has passed asks for the report back.
  raise_advance step 7: the form's "Salary Requested in Advance" raises the
                Leave Advance for the HR Officer (advances.py).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import leave_rules as rules, people

PLAN = "Annual Leave Plan"
ROW = "Annual Leave Plan Employee"
CHANGE = "Leave Plan Change"
APPLICATION = "Leave Application"
HR_ROLES = {"HR User", "HR Manager", "System Manager"}


# ── 1. The Annual Leave Plan ──────────────────────────────────────────
def plan_validate(doc, method=None):
    doc.title = _("Leave Plan %s") % (doc.get("year") or "")
    _fill_plan_rows(doc)
    rows = doc.get("employees") or []
    doc.total_employees = len({row.employee for row in rows if row.employee})
    doc.total_days = sum(flt(row.planned_days) for row in rows)
    found = rules.clashes([row.as_dict() for row in rows], doc.get("most_off"))
    doc.clashes = "\n".join(rules.clash_lines(found, doc.get("most_off"))) or None
    _check_plan_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or "Draft"


def _fill_plan_rows(doc):
    """Each row's leave days, counted as the Leave Application counts them;
    the last day, where only the days are given; and, while HR draw the plan
    up, what each employee has available for the year, the parts of a split
    leave sharing it. Frappe HR shows a balance only to HR, the employee and
    their leave approver, so the approvers' steps keep what HR saw."""
    from hrms_addon.hrms_addon import leave_plan_approval as approval

    include = annual_counts_holidays()
    before = doc.get_doc_before_save()
    drawing_up = (before.get("workflow_state") if before else None) in (None, "", approval.DRAFT)
    available = {}
    for row in doc.get("employees") or []:
        if not row.employee:
            continue
        if not (row.get("employee_name") and row.get("department")):
            found = frappe.db.get_value("Employee", row.employee, ["employee_name", "department", "designation"],
                                        as_dict=True) or {}
            for field in ("employee_name", "department", "designation"):
                if not row.get(field):
                    row.set(field, found.get(field))
        if row.planned_from and row.planned_days and not row.planned_to:
            row.planned_to = rules.end_after(row.planned_from, row.planned_days, holidays_between(
                row.employee, row.planned_from, add_days(row.planned_from, 400)), include)
        if row.planned_from and row.planned_to:
            row.planned_days = rules.leave_days(row.planned_from, row.planned_to, holidays_between(
                row.employee, row.planned_from, row.planned_to), include)
        if drawing_up:
            if row.employee not in available:
                available[row.employee] = _available(row.employee, doc.get("year"))
            row.entitlement_days, row.brought_forward = available[row.employee]
            row.available_days = flt(row.entitlement_days) + flt(row.brought_forward)
        if not row.leave_status:
            row.leave_status = rules.PLANNED


def annual_counts_holidays():
    """Whether annual leave counts the holidays inside it as leave: the
    Leave Type's own setting, as the Leave Application reads it."""
    return cint(frappe.db.get_value("Leave Type", rules.ANNUAL, "include_holiday"))


def holidays_between(employee, start, end):
    """The holidays on the employee's list between two days, as Frappe HR
    reads them for a leave."""
    from hrms.utils.holiday_list import get_holiday_dates_between_range

    return [getdate(day) for day in get_holiday_dates_between_range(
        employee, start, end, raise_exception_for_holiday_list=False) or []]


def _available(employee, year):
    """(days for the year, days brought forward): the year's annual Leave
    Allocation where there is one; before it is made, the days on the
    employee's leave policy and what their balance carries into the year."""
    if not (employee and year):
        return 0.0, 0.0
    start, end = rules.year_window(year)
    allocations = frappe.get_all("Leave Allocation",
                                 filters={"employee": employee, "leave_type": rules.ANNUAL, "docstatus": 1,
                                          "from_date": ["<=", end], "to_date": [">=", start]},
                                 fields=["new_leaves_allocated", "carry_forwarded_leaves_count"])
    if allocations:
        return (flt(sum(flt(row.new_leaves_allocated) for row in allocations)),
                flt(sum(flt(row.carry_forwarded_leaves_count) for row in allocations)))
    return _policy_days(employee, start, end), _carried_into(employee, start)


def _policy_days(employee, start, end):
    """The annual days on the leave policy the employee has in the year,
    else what their last annual allocation gave them."""
    for assignment in frappe.get_all("Leave Policy Assignment",
                                     filters={"employee": employee, "docstatus": 1, "effective_from": ["<=", end]},
                                     fields=["leave_policy", "effective_to"], order_by="effective_from desc"):
        if assignment.effective_to and getdate(assignment.effective_to) < start:
            continue
        days = frappe.get_all("Leave Policy Detail",
                              filters={"parent": assignment.leave_policy, "parenttype": "Leave Policy",
                                       "leave_type": rules.ANNUAL}, pluck="annual_allocation")
        if days:
            return flt(days[0])
    last = frappe.get_all("Leave Allocation",
                          filters={"employee": employee, "leave_type": rules.ANNUAL, "docstatus": 1,
                                   "to_date": ["<", start]},
                          fields=["new_leaves_allocated"], order_by="to_date desc", limit=1)
    return flt(last[0].new_leaves_allocated) if last else 0.0


def _carried_into(employee, start):
    """What the employee's annual leave balance carries into the year, when
    annual leave carries forward, up to the most it allows."""
    carries = frappe.db.get_value("Leave Type", rules.ANNUAL, ["is_carry_forward", "maximum_carry_forwarded_leaves"],
                                  as_dict=True)
    if not carries or not cint(carries.is_carry_forward):
        return 0.0
    from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

    balance = max(flt(get_leave_balance_on(employee, rules.ANNUAL, add_days(start, -1),
                                           consider_all_leaves_in_the_allocation_period=True)), 0.0)
    return min(balance, flt(carries.maximum_carry_forwarded_leaves)) if flt(carries.maximum_carry_forwarded_leaves) \
        else balance


@frappe.whitelist(methods=["POST"])
def get_employees(plan):
    """Step 1: every active employee of the plan's company, plant and
    department not on it yet, with what each has available."""
    doc = frappe.get_doc(PLAN, plan)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Employees are added while the plan is being drawn up."))
    filters = {"status": "Active", "company": doc.company}
    if doc.get("branch"):
        filters["branch"] = doc.branch
    if doc.get("department"):
        filters["department"] = doc.department
    have = {row.employee for row in doc.get("employees") or []}
    added = 0
    for employee in frappe.get_all("Employee", filters=filters,
                                   fields=["name", "employee_name", "department", "designation"],
                                   order_by="employee_name asc"):
        if employee.name in have:
            continue
        doc.append("employees", {"employee": employee.name, "employee_name": employee.employee_name,
                                 "department": employee.department, "designation": employee.designation})
        added += 1
    doc.save()
    return added


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
    """Step 3: tell every employee on an approved plan their dates, the
    parts of a split leave in one message."""
    doc = frappe.get_doc(PLAN, plan)
    doc.check_permission("write")
    if doc.docstatus != 1:
        frappe.throw(_("The plan is told to the employees once it is approved."))
    parts = {}
    for row in doc.employees:
        parts.setdefault(row.employee, []).append(row)
    for employee, rows in parts.items():
        user = frappe.db.get_value("Employee", employee, "user_id")
        if user:
            dates = "; ".join(_("{0} ({1} day(s))").format(_range(row.planned_from, row.planned_to),
                                                         "%g" % flt(row.planned_days)) for row in rows)
            people.notify([user], PLAN, doc.name, _("Your {0} leave is planned: {1}.").format(doc.year, dates))
        for row in rows:
            row.db_set("informed", 1, update_modified=False)
            row.db_set("informed_on", today(), update_modified=False)
    doc.db_set("informed_count", len(parts))
    doc.db_set("informed_on", today())
    return len(parts)


# ── Who sees which plan ───────────────────────────────────────────────
SEES_EVERY_PLAN = HR_ROLES | {"Head of Department", "Supervisor"}


def own_place(user):
    """None for those who see every plan; else the plant and department on
    the user's employee record, empty when they have none."""
    if SEES_EVERY_PLAN & set(frappe.get_roles(user)):
        return None
    return frappe.db.get_value("Employee", {"user_id": user}, ["branch", "department"], as_dict=True) or frappe._dict()


def plan_query_conditions(user=None, doctype=None):
    """An employee is shown the plans of their own plant and department, and
    those drawn up for the whole plant or company."""
    own = own_place(user or frappe.session.user)
    if own is None:
        return ""
    if not own:
        return "1=0"
    return ("(ifnull(`tabAnnual Leave Plan`.`branch`, '') in ('', {0}) "
            "and ifnull(`tabAnnual Leave Plan`.`department`, '') in ('', {1}))").format(
        frappe.db.escape(own.branch or ""), frappe.db.escape(own.department or ""))


def plan_has_permission(doc, ptype=None, user=None):
    """The same, for a plan opened."""
    own = own_place(user or frappe.session.user)
    if own is None:
        return True
    if not own:
        return False
    return (doc.get("branch") or "") in ("", own.branch or "") and (doc.get("department") or "") in (
        "", own.department or "")


def _range(start, end):
    return _("{0} to {1}").format(frappe.utils.format_date(start), frappe.utils.format_date(end))


def _row(name):
    """A planned leave on an approved plan."""
    row = frappe.db.get_value(ROW, name, ["name", "parent", "employee", "employee_name", "department",
                                          "planned_from", "planned_to", "planned_days", "available_days",
                                          "leave_application"], as_dict=True) if name else None
    if not row or frappe.db.get_value(PLAN, row.parent, "docstatus") != 1:
        frappe.throw(_("Choose a planned leave on an approved plan."))
    return row


def _still_applied(application):
    found = frappe.db.get_value(APPLICATION, application, ["status", "docstatus"], as_dict=True)
    return bool(found) and found.docstatus in (0, 1) and found.status not in ("Rejected", "Cancelled")


def _may_act_for(employee):
    """The employee themself, or HR."""
    if frappe.db.get_value("Employee", employee, "user_id") == frappe.session.user:
        return
    if HR_ROLES & set(frappe.get_roles()):
        return
    frappe.throw(_("Only the employee or HR can do this."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def apply_from_plan(row):
    """Step 5 from the plan: a Leave Application for a planned leave, filled
    in with its dates, for the employee to check and send."""
    target = _row(row)
    _may_act_for(target.employee)
    if target.leave_application and _still_applied(target.leave_application):
        return target.leave_application
    doc = frappe.get_doc({
        "doctype": APPLICATION, "employee": target.employee, "leave_type": rules.ANNUAL,
        "from_date": target.planned_from, "to_date": target.planned_to,
        "company": frappe.db.get_value("Employee", target.employee, "company"),
        "custom_plan": target.parent, "custom_plan_row": target.name,
    })
    doc.insert()
    frappe.db.set_value(ROW, target.name, {"leave_application": doc.name, "leave_status": rules.APPLIED},
                        update_modified=False)
    return doc.name


# ── Moving one planned leave ──────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def request_change(row, new_from, new_to, reason):
    """A Leave Plan Change for one planned leave, raised from the plan by the
    employee or by HR for them. It is sent for approval from its own form."""
    target = _row(row)
    _may_act_for(target.employee)
    doc = frappe.get_doc({"doctype": CHANGE, "plan": target.parent, "plan_row": target.name,
                          "employee": target.employee, "new_from": new_from, "new_to": new_to, "reason": reason})
    doc.insert()
    return doc.name


def change_validate(doc, method=None):
    from hrms_addon.hrms_addon import leave_plan_change_approval as approval

    target = frappe.db.get_value(ROW, doc.get("plan_row"), ["name", "parent", "employee", "employee_name",
                                                            "department", "planned_from", "planned_to",
                                                            "planned_days", "available_days", "leave_application"],
                                 as_dict=True) if doc.get("plan_row") else None
    if not target or target.parent != doc.get("plan"):
        frappe.throw(_("Choose the planned leave to move."), title=_(CHANGE))
    plan = frappe.db.get_value(PLAN, doc.plan, ["year", "branch", "company", "most_off", "docstatus"], as_dict=True)
    doc.employee, doc.employee_name, doc.department = target.employee, target.employee_name, target.department
    doc.branch = frappe.db.get_value("Employee", target.employee, "branch") or plan.branch
    doc.company, doc.year = plan.company, plan.year
    if doc.docstatus == 0:
        doc.current_from, doc.current_to, doc.current_days = target.planned_from, target.planned_to, target.planned_days
    doc.new_days = rules.leave_days(doc.new_from, doc.new_to, holidays_between(doc.employee, doc.new_from, doc.new_to),
                                    annual_counts_holidays()) if doc.get("new_from") and doc.get("new_to") else 0
    rows = frappe.get_all(ROW, filters={"parent": doc.plan, "parenttype": PLAN},
                          fields=["name", "employee", "employee_name", "department", "planned_from", "planned_to",
                                  "planned_days"])
    moved = [dict(row, planned_from=doc.new_from, planned_to=doc.new_to) if row.name == target.name else row
             for row in rows]
    doc.clashes = "\n".join(rules.clash_lines(rules.clashes(moved, plan.most_off), plan.most_off)) or None
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {"supervisor_remarks": doc.get("supervisor_remarks"),
                                                             "hod_remarks": doc.get("hod_remarks")})
        if new_state == approval.PENDING_SUPERVISOR:
            if plan.docstatus != 1:
                errors.insert(0, "Only a planned leave on an approved plan is moved.")
            errors = rules.change_errors({
                "year": plan.year, "new_from": doc.new_from, "new_to": doc.new_to, "new_days": doc.new_days,
                "available": target.available_days, "reason": doc.get("reason"),
                "others": [(row.planned_from, row.planned_to, row.planned_days) for row in rows
                           if row.employee == target.employee and row.name != target.name],
                "applied": bool(target.leave_application and _still_applied(target.leave_application)),
            }) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(CHANGE))
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    doc.approval_status = new_state or doc.get("approval_status") or approval.DRAFT
    if old_state != new_state and new_state in approval.PENDING_STATES:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.branch, doc.department)
        message = _("{0} asks to move their leave from {1} to {2}.").format(
            doc.employee_name or doc.employee, _range(doc.current_from, doc.current_to),
            _range(doc.new_from, doc.new_to))
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)


def change_on_submit(doc, method=None):
    """Approved: the planned leave takes the new dates, keeping the first
    ones; its reminders start again, and the employee and HR are told."""
    target = frappe.db.get_value(ROW, doc.plan_row, ["original_from", "planned_from", "planned_to",
                                                     "leave_application"], as_dict=True)
    if target.leave_application and _still_applied(target.leave_application):
        frappe.throw(_("A leave is already applied for on these dates. Cancel that application first."),
                     title=_(CHANGE))
    values = {"planned_from": doc.new_from, "planned_to": doc.new_to, "planned_days": doc.new_days,
              "alerts_sent": "", "not_applied_told": 0, "leave_status": rules.plan_row_status(doc.new_from, today()),
              "last_change": doc.name}
    if not target.original_from:
        values.update(original_from=target.planned_from, original_to=target.planned_to)
    frappe.db.set_value(ROW, doc.plan_row, values, update_modified=False)
    _retotal(doc.plan)
    users = [frappe.db.get_value("Employee", doc.employee, "user_id")]
    users += people.hr_officers(doc.get("branch"), doc.get("department"))
    people.notify([user for user in dict.fromkeys(users) if user], PLAN, doc.plan,
                  _("{0}'s leave is moved to {1}.").format(doc.employee_name or doc.employee,
                                                          _range(doc.new_from, doc.new_to)))


def change_on_cancel(doc, method=None):
    """A change cancelled puts back the dates it replaced, when the plan
    still has its dates."""
    target = frappe.db.get_value(ROW, doc.plan_row, ["last_change", "original_from", "original_to",
                                                     "leave_application"], as_dict=True)
    if not target or target.last_change != doc.name:
        return
    if target.leave_application and _still_applied(target.leave_application):
        frappe.throw(_("A leave is already applied for on the new dates. Cancel that application first."),
                     title=_(CHANGE))
    earlier = frappe.get_all(CHANGE, filters={"plan_row": doc.plan_row, "docstatus": 1, "name": ["!=", doc.name]},
                             pluck="name", order_by="modified desc", limit=1)
    values = {"planned_from": doc.current_from, "planned_to": doc.current_to, "planned_days": doc.current_days,
              "alerts_sent": "", "not_applied_told": 0, "leave_status": rules.plan_row_status(doc.current_from, today()),
              "last_change": earlier[0] if earlier else None}
    if not earlier:
        values.update(original_from=None, original_to=None)
    frappe.db.set_value(ROW, doc.plan_row, values, update_modified=False)
    _retotal(doc.plan)


def _retotal(plan):
    frappe.db.set_value(PLAN, plan, "total_days", sum(flt(row.planned_days) for row in frappe.get_all(
        ROW, filters={"parent": plan, "parenttype": PLAN}, fields=["planned_days"])), update_modified=False)


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
        _unmark_plan_row(doc)
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
    _unmark_plan_row(doc)


def _mark_plan_row(doc):
    """The planned leave this approved application takes keeps it: the row
    it was applied from, else the employee's planned leave its dates fall
    in, so the plan shows what has actually been taken."""
    row = doc.get("custom_plan_row")
    if not (row and frappe.db.exists(ROW, row)):
        row = _planned_row_for(doc.employee, doc.from_date, doc.to_date, doc.get("custom_plan"), doc.name)
    if not row:
        return
    frappe.db.set_value(ROW, row, {"leave_application": doc.name, "leave_status": rules.APPLIED},
                        update_modified=False)
    if not doc.get("custom_plan"):
        doc.db_set("custom_plan", frappe.db.get_value(ROW, row, "parent"), update_modified=False)


def _unmark_plan_row(doc):
    """A leave cancelled or refused leaves its planned leave to be applied
    for again."""
    for row in frappe.get_all(ROW, filters={"leave_application": doc.name}, fields=["name", "planned_from"]):
        frappe.db.set_value(ROW, row.name, {"leave_application": None,
                                            "leave_status": rules.plan_row_status(row.planned_from, today())},
                            update_modified=False)


def _planned_row_for(employee, from_date, to_date, plan=None, application=None):
    """The employee's planned leave, on an approved plan, that these dates
    overlap the most, unless another live application has it."""
    plans = [plan] if plan else frappe.get_all(PLAN, filters={"docstatus": 1}, pluck="name")
    if not plans or not (from_date and to_date):
        return None
    best, most = None, 0
    for row in frappe.get_all(ROW, filters={"parent": ["in", plans], "parenttype": PLAN, "employee": employee,
                                            "planned_from": ["<=", to_date], "planned_to": [">=", from_date]},
                              fields=["name", "planned_from", "planned_to", "leave_application"]):
        if row.leave_application and row.leave_application != application and _still_applied(row.leave_application):
            continue
        overlap = (min(getdate(row.planned_to), getdate(to_date)) - max(getdate(row.planned_from),
                                                                       getdate(from_date))).days + 1
        if overlap > most:
            best, most = row.name, overlap
    return best


@frappe.whitelist(methods=["POST"])
def raise_advance(leave_application):
    """Step 7: the Leave Advance, raised from the leave form (advances.py)."""
    from hrms_addon.hrms_addon import advances

    return advances.from_leave(leave_application)


# ── 3. Step 4: the system watching ────────────────────────────────────
def daily():
    """A planned leave coming due or started with nothing applied for, each
    planned leave's status, and a leave nobody has reported back from."""
    _tell_due()
    _tell_not_applied()
    _refresh_plan_statuses()
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


def _tell_not_applied():
    """A planned leave whose first day has passed with nothing applied for:
    the HR Officer and the immediate supervisor are told once, in its first
    week."""
    now = getdate(today())
    plans = frappe.get_all(PLAN, filters={"docstatus": 1, "year": ["in", [now.year - 1, now.year]]}, pluck="name")
    if not plans:
        return
    for row in frappe.get_all(ROW, filters={"parent": ["in", plans], "parenttype": PLAN,
                                            "planned_from": ["<", now], "not_applied_told": ["!=", 1]},
                              fields=["name", "parent", "employee", "employee_name", "planned_from", "planned_to",
                                      "leave_application"]):
        if row.leave_application and _still_applied(row.leave_application):
            continue
        if getdate(row.planned_from) >= getdate(add_days(now, -7)):
            employee = frappe.db.get_value("Employee", row.employee, ["reports_to", "branch", "department"],
                                           as_dict=True) or frappe._dict()
            users = list(people.hr_officers(employee.branch, employee.department))
            supervisor = frappe.db.get_value("Employee", employee.reports_to, "user_id") if employee.reports_to else None
            if supervisor:
                users.append(supervisor)
            if users:
                people.notify(list(dict.fromkeys(users)), PLAN, row.parent,
                              _("{0}'s planned leave, {1}, has started with no leave applied for.").format(
                                  row.employee_name or row.employee, _range(row.planned_from, row.planned_to)))
        frappe.db.set_value(ROW, row.name, {"not_applied_told": 1, "leave_status": rules.NOT_APPLIED},
                            update_modified=False)
    frappe.db.commit()


def _refresh_plan_statuses():
    """Each planned leave's status, as it stands today."""
    now = getdate(today())
    plans = frappe.get_all(PLAN, filters={"docstatus": 1, "year": ["in", [now.year - 1, now.year, now.year + 1]]},
                           pluck="name")
    if not plans:
        return
    rows = frappe.get_all(ROW, filters={"parent": ["in", plans], "parenttype": PLAN},
                          fields=["name", "planned_from", "leave_application", "leave_status"])
    applications = {row.name: row for row in frappe.get_all(
        APPLICATION, filters={"name": ["in", [row.leave_application for row in rows if row.leave_application] or [""]]},
        fields=["name", "docstatus", "status", "to_date"])}
    for row in rows:
        status = rules.plan_row_status(row.planned_from, now, applications.get(row.leave_application))
        if status != row.leave_status:
            frappe.db.set_value(ROW, row.name, "leave_status", status, update_modified=False)
    frappe.db.commit()


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
    from hrms_addon.hrms_addon import leave_approval, leave_plan_approval, leave_plan_change_approval, workflows

    workflows.setup_on_migrate(leave_plan_approval, "Annual Leave Plan workflow")
    workflows.setup_on_migrate(leave_approval, "Leave Application workflow")
    workflows.setup_on_migrate(leave_plan_change_approval, "Leave Plan Change workflow")


def seed_leave_types():
    """The kinds LPL/HR/15 offers, and the half-pay sick leave the minutes
    add, as Leave Types on the site (minutes §4.3). An existing one is
    left exactly as Luuka has set it up."""
    made = []
    for name in rules.LEAVE_TYPES + rules.EXTRA_TYPES:
        if frappe.db.exists("Leave Type", name):
            continue
        doc = frappe.new_doc("Leave Type")
        doc.leave_type_name = name
        for field, value in leave_type_values(name).items():
            doc.set(field, value)
        doc.insert(ignore_permissions=True)
        made.append(name)
    return made


def leave_type_values(name):
    """What a Leave Type is set up with, from the minutes.

    Without pay is limited by the length of one leave rather than by an
    allocation, since nobody is allocated unpaid leave.
    """
    days = rules.LEAVE_DAYS.get(name, 0)
    if name == rules.UNPAID:
        return {"is_lwp": 1, "max_leaves_allowed": 0, "max_continuous_days_allowed": days}
    values = {"max_leaves_allowed": days}
    if name == rules.ANNUAL:
        values.update({"is_carry_forward": 1, "allow_encashment": 1,
                       "maximum_carry_forwarded_leaves": 0})
    if name == rules.SICK_HALF_PAY:
        values.update({"is_ppl": 1, "fraction_of_daily_salary_per_leave": rules.HALF_PAY_FRACTION})
    return values
