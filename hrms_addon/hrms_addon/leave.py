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
  _assign       the plan gives each employee with no leave for the year
                their leave: a Leave Policy Assignment drawn up as the plan
                is saved, with the days on their row, and submitted when the
                plan is approved, which is when Frappe HR allocates it.
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
  raise_advance step 7: the form's "Leave Advance Requested" raises the Leave
                Advance, its own document (leave_advances.py); on approval
                it is raised by itself.
  Leave earned  Part 2 shows what the employee has earned by the days
                worked and what can be taken, and a leave longer than that
                is refused (leave_accrual.py).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import attendance_rules, leave_follow, leave_rules as rules, people

PLAN = "Annual Leave Plan"
ROW = "Annual Leave Plan Employee"
ASSIGNMENT = "Leave Policy Assignment"
POLICY = "Leave Policy"
# a plan with more employees than this has their leave assignments seen to
# in the background, so a save does not wait on hundreds of them
INLINE = 40
CHANGE = "Leave Plan Change"
APPLICATION = "Leave Application"
HR_ROLES = {"HR User", "HR Manager", "System Manager"}


# ── 1. The Annual Leave Plan ──────────────────────────────────────────
def plan_validate(doc, method=None):
    # the year is picked from a list, and kept as the list writes it
    doc.year = str(cint(doc.get("year")) or rules.default_plan_year(getdate(today())))
    doc.title = _("Leave Plan %s") % (doc.get("year") or "")
    _fill_plan_policy(doc)
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
        if not row.leave_status:
            row.leave_status = rules.PLANNED
    if drawing_up:
        _fill_plan_days(doc, before)


def _fill_plan_days(doc, before=None):
    """Each employee's leave days for the plan year. One who already has
    their leave for the year (a leave policy assigned for it, or an
    allocation) keeps what it gives, which the plan does not change. For
    anybody else the plan gives it (_assign): the days HR entered on their
    row, else those of the leave policy they had before, the plan's Leave
    Policy, or Leave Management Settings' default. A leave split in parts
    shares one figure. What is written on a row by the form is put back
    here: the server decides."""
    rows = [row for row in doc.get("employees") or [] if row.employee]
    if not rows or not doc.get("year"):
        return
    employees = list(dict.fromkeys(row.employee for row in rows))
    held = _held(employees, doc.get("year"), _own_drafts(rows))
    stored = {line.name: line.get("entitlement_days") for line in (before.get("employees") if before else None) or []
              if line.get("name")}
    chosen = rules.employee_days([row.as_dict() for row in rows], stored)
    start, _end = rules.year_window(doc.get("year"))
    figures = {}
    for employee in employees:
        if employee in held:
            days, brought = _available(employee, doc.get("year"))
            figures[employee] = (days, brought, 1, held[employee], 0)
            continue
        policy = _base_policy(employee, doc.get("leave_policy"))
        typed, set_by_hr = chosen.get(employee, (0, False))
        kept = bool(set_by_hr and typed)
        days = typed if kept else (_annual_days(policy) or 0)
        figures[employee] = (days, _carried_into(employee, start), 0, policy, 1 if kept else 0)
    for row in rows:
        days, brought, on_record, policy, days_set = figures[row.employee]
        row.entitlement_days, row.brought_forward = flt(days), flt(brought)
        row.available_days = flt(days) + flt(brought)
        row.on_record, row.days_set = on_record, days_set
        # a row given its leave by the plan names the policy made for its days (_assign)
        if not (row.get("leave_policy") and not on_record and row.get("leave_policy_assignment")):
            row.leave_policy = policy


def _fill_plan_policy(doc):
    """The Leave Policy the plan gives employees with none before: Leave
    Management Settings' default until HR choose, where it gives annual
    leave (a plan is never refused for a policy nobody chose), and the
    Annual Leave days it gives shown beside it."""
    if doc.docstatus == 0 and not doc.get("leave_policy"):
        default = _default_policy()
        if default and rules.policy_days(_details(default), rules.ANNUAL) is not None:
            doc.leave_policy = default
    doc.policy_days = None
    if doc.get("leave_policy"):
        details = _details(doc.leave_policy)
        days = rules.policy_days(details, rules.ANNUAL)
        if days is None and doc.docstatus == 0:
            title = frappe.db.get_value(POLICY, doc.leave_policy, "title") or doc.leave_policy
            named = "%s (%s)" % (title, doc.leave_policy) if title != doc.leave_policy else doc.leave_policy
            if details:
                message = _("The Leave Policy {0} has no {1} line. It gives {2}. Add {1} to it, or choose another "
                            "policy.").format(named, _(rules.ANNUAL), rules.policy_summary(details))
            else:
                message = _("The Leave Policy {0} gives no leave at all. Add {1} to it, or choose another policy.").format(
                    named, _(rules.ANNUAL))
            frappe.throw(message, title=_(PLAN))
        doc.policy_days = days


def _held(employees, year, own=()):
    """{employee: leave policy} for the employees who already have their
    leave for the plan year: a Leave Policy Assignment covering it (one
    being drawn up elsewhere too), or an annual Leave Allocation made for
    it. The plan's own draft assignments (own) are the plan's, not theirs."""
    if not employees or not year:
        return {}
    start, end = rules.year_window(year)
    out = {}
    for row in frappe.get_all(ASSIGNMENT, filters={"employee": ["in", list(employees)], "docstatus": ["<", 2],
                                                   "effective_from": ["<=", end]},
                              fields=["name", "employee", "leave_policy", "effective_to", "docstatus"],
                              order_by="docstatus desc", limit_page_length=0):
        if row.name in own or (row.effective_to and getdate(row.effective_to) < start):
            continue
        out.setdefault(row.employee, row.leave_policy)
    for row in frappe.get_all("Leave Allocation", filters={"employee": ["in", list(employees)], "docstatus": 1,
                                                           "leave_type": rules.ANNUAL, "from_date": ["<=", end],
                                                           "to_date": [">=", start]},
                              fields=["employee", "leave_policy"], limit_page_length=0):
        out.setdefault(row.employee, row.get("leave_policy"))
    return out


def _own_drafts(rows):
    """The plan's own leave assignments still being drawn up."""
    links = [row.get("leave_policy_assignment") for row in rows if row.get("leave_policy_assignment")]
    if not links:
        return set()
    return set(frappe.get_all(ASSIGNMENT, filters={"name": ["in", links], "docstatus": 0}, pluck="name"))


def _base_policy(employee, plan_policy=None):
    """The leave policy an employee with none for the year is given: the
    one they had before (as the yearly allocation does), else the plan's
    Leave Policy, else Leave Management Settings' default."""
    from hrms_addon.hrms_addon import leave_accrual

    return leave_accrual._last_policy(employee) or plan_policy or _default_policy()


def _default_policy():
    if frappe.db.exists("DocType", "Leave Management Settings"):
        return frappe.db.get_single_value("Leave Management Settings", "default_leave_policy") or None
    return None


def _details(policy):
    """A leave policy's rows: each leave type and its days a year."""
    if not policy:
        return []
    return frappe.get_all("Leave Policy Detail", filters={"parent": policy, "parenttype": POLICY},
                          fields=["leave_type", "annual_allocation"], order_by="idx asc")


def _policy_with_days(policy, days, cache=None):
    """The leave policy that is `policy` with `days` of Annual Leave a year:
    itself where it gives those days, else one already made that gives the
    same, else made now (submitted, titled after `policy`). Its other leave
    types stay as `policy` gives them."""
    cache = {} if cache is None else cache
    key = (policy, flt(days))
    if key in cache:
        return cache[key]
    details = _details(policy)
    if rules.policy_days(details, rules.ANNUAL) == flt(days):
        cache[key] = policy
        return policy
    wanted = rules.with_days(details, rules.ANNUAL, days)
    for name in frappe.get_all(POLICY, filters={"docstatus": 1}, pluck="name", order_by="creation asc"):
        if rules.same_details(_details(name), wanted):
            cache[key] = name
            return name
    title = frappe.db.get_value(POLICY, policy, "title") or policy
    made = frappe.get_doc({"doctype": POLICY, "title": rules.variant_title(title, rules.ANNUAL, days),
                           "leave_policy_details": wanted})
    made.flags.ignore_permissions = True
    made.insert()
    made.submit()
    cache[key] = made.name
    return made.name


def _assign(doc, submit=False):
    """Each employee on the plan with no leave of their own for the year is
    given it: their Leave Policy Assignment for the year, drawn up as the
    plan is, changed when their days are, and submitted with submit (the
    plan approved), which is when Frappe HR allocates their leave. An
    employee who has their leave from elsewhere by then has the plan's draft
    taken back. Each employee in a savepoint of their own: one that is
    refused is named, and the rest go on.
    Returns {"made", "changed", "submitted", "failed": [(name, why)]}."""
    from hrms_addon.hrms_addon import leave_accrual

    done = {"made": 0, "changed": 0, "submitted": 0, "failed": []}
    rows = [row for row in doc.get("employees") or [] if row.employee]
    if not rows or not doc.get("year"):
        return done
    employees = list(dict.fromkeys(row.employee for row in rows))
    links = [row.get("leave_policy_assignment") for row in rows if row.get("leave_policy_assignment")]
    found = {row.name: row for row in frappe.get_all(ASSIGNMENT, filters={"name": ["in", links or [""]]},
                                                     fields=["name", "docstatus", "leave_policy"])}
    held = _held(employees, doc.get("year"), {name for name, row in found.items() if row.docstatus == 0})
    start, _end = rules.year_window(doc.get("year"))
    period, cache = None, {}
    for employee in employees:
        lines = [row for row in rows if row.employee == employee]
        name = next((row.get("leave_policy_assignment") for row in lines
                     if row.get("leave_policy_assignment") in found), None)
        current = found.get(name)
        who = lines[0].get("employee_name") or employee
        if employee in held:
            if current and current.docstatus == 0:
                _link(lines, None, held[employee])
                frappe.delete_doc(ASSIGNMENT, name, ignore_permissions=True, force=True)
            continue
        days = flt(lines[0].get("entitlement_days"))
        if not days:
            # nothing to give them now: a draft made when there was is taken back
            if current and current.docstatus == 0:
                _link(lines, None, lines[0].get("leave_policy"))
                frappe.delete_doc(ASSIGNMENT, name, ignore_permissions=True, force=True)
            continue
        frappe.db.savepoint("ha_leave_assignment")
        try:
            base = _base_policy(employee, doc.get("leave_policy"))
            if not base:
                frappe.throw(_("There is no leave policy to give {0} their leave: choose the plan's Leave Policy.")
                             .format(who))
            wanted = _policy_with_days(base, days, cache)
            if current and current.docstatus == 1:
                if current.leave_policy != wanted:
                    frappe.throw(_("{0} has their leave from {1} already. Cancel it to change their days.").format(
                        who, name))
                _link(lines, name, current.leave_policy)
                continue
            if current:
                if current.leave_policy != wanted:
                    assignment = frappe.get_doc(ASSIGNMENT, name)
                    assignment.leave_policy = wanted
                    assignment.flags.ignore_permissions = True
                    assignment.save()
                    done["changed"] += 1
            else:
                period = period or leave_accrual._leave_period(doc.get("company"), start)
                assignment = frappe.get_doc({"doctype": ASSIGNMENT, "employee": employee, "leave_policy": wanted,
                                             "assignment_based_on": "Leave Period", "leave_period": period.name,
                                             "effective_from": period.from_date, "effective_to": period.to_date,
                                             "carry_forward": 1})
                assignment.flags.ignore_permissions = True
                assignment.insert()
                name = assignment.name
                done["made"] += 1
            if submit:
                assignment = frappe.get_doc(ASSIGNMENT, name)
                assignment.flags.ignore_permissions = True
                assignment.submit()
                done["submitted"] += 1
            _link(lines, name, wanted)
        except Exception as error:
            frappe.db.rollback(save_point="ha_leave_assignment")
            done["failed"].append((who, frappe.utils.strip_html(str(error)) or _("refused")))
            frappe.log_error(title="HRMS Addon: leave assignment for %s on %s" % (employee, doc.name))
    return done


def _link(lines, assignment, policy):
    """A plan row names the leave assignment the plan made for its employee,
    and the leave policy it gives."""
    for row in lines:
        row.leave_policy_assignment, row.leave_policy = assignment, policy
        if row.get("name") and not row.is_new():
            row.db_set({"leave_policy_assignment": assignment, "leave_policy": policy}, update_modified=False)


def _forget(names):
    """The plan's own leave assignments still being drawn up, taken back:
    each row lets go of it first."""
    for name in frappe.get_all(ASSIGNMENT, filters={"name": ["in", list(names) or [""]], "docstatus": 0}, pluck="name"):
        for row in frappe.get_all(ROW, filters={"leave_policy_assignment": name, "parenttype": PLAN}, pluck="name"):
            frappe.db.set_value(ROW, row, "leave_policy_assignment", None, update_modified=False)
        frappe.delete_doc(ASSIGNMENT, name, ignore_permissions=True, force=True)


def _gone(doc):
    """The leave assignments the plan drew up for employees taken off it."""
    before = doc.get_doc_before_save()
    had = {row.get("leave_policy_assignment") for row in (before.get("employees") if before else None) or []}
    have = {row.get("leave_policy_assignment") for row in doc.get("employees") or []}
    return {name for name in had - have if name}


def plan_on_update(doc, method=None):
    """Drawn up, the plan's leave assignments follow it: made for those it
    gives leave to, changed with their days, taken back for those taken
    off. A big plan has it done in the background."""
    from hrms_addon.hrms_addon import leave_plan_approval as approval

    if doc.docstatus != 0 or (doc.get("workflow_state") or approval.DRAFT) != approval.DRAFT:
        return
    _forget(_gone(doc))
    _assign_now_or_later(doc, submit=False)


def _assign_now_or_later(doc, submit):
    employees = {row.employee for row in doc.get("employees") or [] if row.employee}
    if len(employees) > INLINE:
        frappe.enqueue("hrms_addon.hrms_addon.leave.assign_plan", queue="long", timeout=3000,
                       enqueue_after_commit=True, plan=doc.name, submit=1 if submit else 0,
                       user=frappe.session.user)
        frappe.msgprint(_("The leave assignments of the {0} employees are being made in the background. You will "
                          "be told when they are done.").format(len(employees)), alert=True)
        return
    _report(doc, _assign(doc, submit=submit), submit)


def assign_plan(plan, submit=0, user=None):
    """In the background: a big plan's leave assignments, and who saved or
    approved it told how it went."""
    doc = frappe.get_doc(PLAN, plan)
    done = _assign(doc, submit=cint(submit))
    frappe.db.commit()
    _report(doc, done, cint(submit), user=user)


def _report(doc, done, submit, user=None):
    """What the plan's leave assignments came to: a refusal is named,
    whoever it is for."""
    failed = done.get("failed") or []
    if not (failed or user):
        return
    lines = [_("{0}: {1}").format(who, why) for who, why in failed]
    summary = (_("{0} leave assignment(s) submitted for {1}.").format(done["submitted"], doc.get("year")) if submit
               else _("{0} leave assignment(s) made, {1} changed, for {2}.").format(done["made"], done["changed"],
                                                                                   doc.get("year")))
    if failed:
        summary += " " + _("Not given their leave: {0}.").format("; ".join(lines))
    if user:
        people.notify([user], PLAN, doc.name, summary)
    else:
        frappe.msgprint(summary, title=_("Leave Assignments"), indicator="orange")


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
    employee's leave policy and what their balance carries into the year.
    Earned leave grows through the year as it is earned, so its plan takes
    the year's days from the policy instead of what is credited so far."""
    if not (employee and year):
        return 0.0, 0.0
    start, end = rules.year_window(year)
    allocations = frappe.get_all("Leave Allocation",
                                 filters={"employee": employee, "leave_type": rules.ANNUAL, "docstatus": 1,
                                          "from_date": ["<=", end], "to_date": [">=", start]},
                                 fields=["new_leaves_allocated", "unused_leaves"])
    if allocations:
        days = flt(sum(flt(row.new_leaves_allocated) for row in allocations))
        # an earned type is credited as it is earned, and an allocation made
        # from a policy can still read nothing, so the year's days (30, 21)
        # come from the employee's policy then
        if not days or cint(frappe.db.get_value("Leave Type", rules.ANNUAL, "is_earned_leave")):
            days = _policy_days(employee, start, end) or days
        # unused_leaves is what was brought into the allocation; its
        # carry_forwarded_leaves_count is what it later passed on
        return days, flt(sum(flt(row.unused_leaves) for row in allocations))
    return _policy_days(employee, start, end), _carried_into(employee, start)


def _policy_days(employee, start, end):
    """The annual days on the leave policy the employee has in the year: the
    one assigned to them, else what their last annual allocation gave them,
    else the default policy in Leave Management Settings, which the yearly
    allocation gives anyone without one."""
    for assignment in frappe.get_all("Leave Policy Assignment",
                                     filters={"employee": employee, "docstatus": 1, "effective_from": ["<=", end]},
                                     fields=["leave_policy", "effective_to"], order_by="effective_from desc"):
        if assignment.effective_to and getdate(assignment.effective_to) < start:
            continue
        days = _annual_days(assignment.leave_policy)
        if days:
            return days
    last = frappe.get_all("Leave Allocation",
                          filters={"employee": employee, "leave_type": rules.ANNUAL, "docstatus": 1,
                                   "to_date": ["<", start]},
                          fields=["new_leaves_allocated", "leave_policy"], order_by="to_date desc", limit=1)
    if last:
        days = _annual_days(last[0].get("leave_policy")) or flt(last[0].new_leaves_allocated)
        if days:
            return days
    if frappe.db.exists("DocType", "Leave Management Settings"):
        return _annual_days(frappe.db.get_single_value("Leave Management Settings", "default_leave_policy")) or 0.0
    return 0.0


def _years(first, last):
    """Plan years as the Plan Year list keeps them, from `first` to `last`."""
    return [str(year) for year in range(first, last + 1)]


def _annual_days(policy):
    """The annual leave days a Leave Policy gives; None without one. Its
    annual line is found as the plan finds it (leave_rules.policy_line)."""
    if not policy:
        return None
    return rules.policy_days(_details(policy), rules.ANNUAL)


@frappe.whitelist()
def plan_row(employee, year, leave_policy=None, plan=None):
    """A row of the plan as the employee is picked: their name, department
    and their leave for the year: what they already have, else what the
    plan gives them (leave_policy, the plan's own)."""
    if not frappe.has_permission(PLAN, "write"):
        frappe.throw(_("You may not draw up a leave plan."), frappe.PermissionError)
    return plan_figures(employee, year, leave_policy, plan)


def plan_figures(employee, year, leave_policy=None, plan=None):
    """An employee's leave for the plan year, as plan_row gives it, without
    asking who wants it: the callers check that."""
    found = frappe.db.get_value("Employee", employee, ["employee_name", "department", "designation"],
                                as_dict=True) or frappe._dict()
    year = cint(year)
    out = {"employee_name": found.employee_name, "department": found.department, "designation": found.designation,
           "entitlement_days": 0.0, "brought_forward": 0.0, "available_days": 0.0, "on_record": 0,
           "leave_policy": None}
    if not year:
        return out
    own = set()
    if plan and frappe.db.exists(PLAN, plan):
        own = _own_drafts(frappe.get_all(ROW, filters={"parent": plan, "parenttype": PLAN, "employee": employee},
                                         fields=["leave_policy_assignment"]))
    held = _held([employee], year, own)
    if employee in held:
        entitled, brought = _available(employee, year)
        out.update(on_record=1, leave_policy=held[employee])
    else:
        policy = _base_policy(employee, leave_policy)
        entitled, brought = (_annual_days(policy) or 0.0), _carried_into(employee, rules.year_window(year)[0])
        out["leave_policy"] = policy
    out.update(entitlement_days=flt(entitled), brought_forward=flt(brought),
               available_days=flt(entitled) + flt(brought))
    return out


@frappe.whitelist()
def plan_years(year=None):
    """The Plan Year list: last year to two years ahead, the plan's own year,
    and the year a new plan is for."""
    day = getdate(today())
    return {"years": rules.plan_years(day, year), "default": str(rules.default_plan_year(day))}


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
    """Approved: each employee given their leave by the plan has their
    leave assignment submitted, and Frappe HR allocates their leave. Step 3
    follows: the HR Officer tells the employees."""
    _assign_now_or_later(doc, submit=True)
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    message = _("Leave Plan {0} is approved. Tell the {1} employee(s) their dates.").format(
        doc.get("year"), doc.get("total_employees") or 0)
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def plan_on_cancel(doc, method=None):
    """Cancelled. Leave already allocated stands (cancel its Leave Policy
    Assignment to take it back); an assignment still being drawn up goes."""
    doc.status = "Cancelled"
    _forget({row.get("leave_policy_assignment") for row in doc.get("employees") or []} - {None})


def plan_on_trash(doc, method=None):
    """A plan deleted before it is approved takes its draft assignments with it."""
    _forget({row.get("leave_policy_assignment") for row in doc.get("employees") or []} - {None})


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
                # a row from a plan approved before entitlements were checked carries no figure
                "available": flt(target.available_days) or sum(_available(target.employee, plan.year)),
                "reason": doc.get("reason"),
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
    from hrms_addon.hrms_addon import leave_accrual, leave_approval as approval, suspension_rules

    if doc.get("leave_type") in suspension_rules.LEAVE_TYPES:
        frappe.throw(_("Suspension days are marked by an Employee Suspension, not applied for."),
                     title=_("Leave Application"))
    if doc.get("leave_type") == attendance_rules.OFF_DUTY_LEAVE_TYPE:
        frappe.throw(_("A paid day off is given by an Off Duty Request, not applied for."),
                     title=_("Leave Application"))
    earned = leave_accrual.check_application(doc)
    _fill_balances(doc, earned)
    if doc.docstatus == 0:
        # who else of the department is off the same days, for each desk to see
        leave_follow.check_cover(doc)
    _check_application_step(doc)
    state = doc.get("workflow_state")
    doc.custom_leave_status = state or doc.get("custom_leave_status") or approval.DRAFT
    # Frappe HR's own status is what their controller and their ledger read
    if state:
        doc.status = approval.upstream_status(state)
    if doc.get("custom_reported_back") and not doc.get("custom_reported_back_on"):
        doc.custom_reported_back_on = today()


def _fill_balances(doc, earned=None):
    """Part 2 of the form: what was left before the leave and what is left
    after it. For earned leave, what can be taken by the days worked
    (leave_accrual.py); else Frappe HR's balance, unless the HR Officer typed
    one."""
    if doc.get("custom_balance_before") in (None, 0):
        if earned is not None:
            doc.custom_balance_before = flt(earned.available)
        elif doc.get("leave_balance"):
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
            "off_duty_request": doc.get("custom_off_duty_request"),
            "amended_from": doc.get("amended_from"), "change_kind": doc.get("custom_change_kind"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_SUPERVISOR and old_state in (None, approval.DRAFT):
            errors = rules.application_errors(_application_facts(doc)) + leave_follow.sending_errors(doc) + errors
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
    if old_state == approval.DRAFT and new_state == approval.APPROVED and doc.get("custom_off_duty_request"):
        # signed as LPL/HR/25 was signed
        request = frappe.db.get_value("Off Duty Request", doc.custom_off_duty_request,
                                      ["supervisor_by", "supervisor_on", "manager_by", "manager_on", "hr_by",
                                       "hr_on"], as_dict=True) or {}
        for field, value in approval.off_duty_stamps(request).items():
            doc.set(field, value)
        doc.custom_hr_by = doc.custom_hr_by or frappe.session.user
        doc.custom_hr_on = doc.custom_hr_on or today()
        doc.custom_hro_by, doc.custom_hro_on = doc.custom_hro_by or frappe.session.user, doc.custom_hro_on or today()
    if old_state == approval.DRAFT and new_state == approval.APPROVED and doc.get("amended_from") \
            and doc.get("custom_change_kind") in approval.ENDED_EARLY:
        # signed as the leave first approved was
        leave_follow.signed_as(doc)
    if old_state != new_state:
        # the desk it reaches is told, and the day kept for how long it waits there
        if new_state in approval.PENDING_STATES:
            leave_follow.arrived(doc, new_state)
        else:
            leave_follow.left_the_desk(doc)


def _application_facts(doc):
    return {
        "leave_type": doc.get("leave_type"), "from_date": doc.get("from_date"), "to_date": doc.get("to_date"),
        "total_leave_days": doc.get("total_leave_days"),
        "certificate": doc.get("custom_medical_certificate"),
        "reason": doc.get("description"),
        "balance_before": doc.get("custom_balance_before") or doc.get("leave_balance"),
    }


def application_on_submit(doc, method=None):
    """Approved. Step 7: an advance was asked for, so the Leave Advance is
    raised and goes to the Accounts Manager (leave_advances.py)."""
    from hrms_addon.hrms_addon import leave_advances

    if doc.get("status") != "Approved":
        _unmark_plan_row(doc)
        return
    _mark_plan_row(doc)
    if doc.get("amended_from") and doc.get("custom_change_kind") in leave_follow.rules.ENDED_EARLY:
        # a leave ended early keeps the advance and the reliever of the one first approved
        return
    leave_follow.tell_reliever(doc)
    if not rules.advance_wanted({"salary_requested_in_advance": doc.get("custom_salary_requested_in_advance")}):
        return
    leave_advances.on_leave_approved(doc)


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


def approve_for_off_duty(request, leave_type):
    """LPL/HR/25 gives a day off as the employee's own leave (Annual Leave,
    Compassionate): the Leave Application for the day is raised and approved
    with the form, which already carries its three signatures, so the day
    comes off the balance as any leave does and Frappe HR marks it on the
    attendance. A leave the employee has not the balance for is refused
    here, and so the form is: HR give the day another way. Returns the
    Leave Application."""
    from frappe.model.workflow import apply_workflow

    from hrms_addon.hrms_addon import leave_approval as approval

    existing = frappe.db.get_value(APPLICATION, {"custom_off_duty_request": request.name, "docstatus": ["!=", 2]},
                                   ["name", "docstatus"], as_dict=True)
    if existing and existing.docstatus == 1:
        return existing.name
    if not frappe.db.exists("Leave Type", leave_type):
        frappe.throw(_("There is no Leave Type {0} to give the day as.").format(leave_type),
                     title=_("Off Duty Request"))
    if existing:
        # raised and never approved: it is approved now, not raised again
        doc = frappe.get_doc(APPLICATION, existing.name)
    else:
        doc = frappe.get_doc({
            "doctype": APPLICATION, "employee": request.employee, "leave_type": leave_type,
            "from_date": request.off_date, "to_date": request.off_date, "total_leave_days": 1,
            "posting_date": today(), "description": request.get("reason"),
            "leave_approver": frappe.session.user, "follow_via_email": 0,
            "company": frappe.db.get_value("Employee", request.employee, "company"),
            "custom_off_duty_request": request.name,
        })
        doc.flags.ignore_permissions = True
        doc.insert()
    return apply_workflow(doc, approval.APPROVE_OFF_DUTY).name


@frappe.whitelist(methods=["POST"])
def raise_advance(leave_application):
    """Step 7: the Leave Advance, raised from the leave form (leave_advances.py)."""
    from hrms_addon.hrms_addon import leave_advances

    return leave_advances.raise_advance(leave_application)


# ── 3. Step 4: the system watching ────────────────────────────────────
def daily():
    """A planned leave coming due or started with nothing applied for, each
    planned leave's status, a leave waiting too long on a desk, and one
    nobody has come back from (leave_follow.py)."""
    _tell_due()
    _tell_not_applied()
    _refresh_plan_statuses()
    # a leave on a desk too long, and one nobody has come back from
    for watch in (leave_follow.chase_approvals, leave_follow.watch_returns):
        try:
            watch()
        except Exception:  # noqa: BLE001 - one watch failing must not stop the other
            frappe.db.rollback()
            frappe.log_error(title="HRMS Addon: %s failed" % watch.__name__)


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
    plans = frappe.get_all(PLAN, filters={"docstatus": 1, "year": ["in", _years(now.year - 1, now.year)]},
                           pluck="name")
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
    plans = frappe.get_all(PLAN, filters={"docstatus": 1, "year": ["in", _years(now.year - 1, now.year + 1)]},
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
        # earned month by month, by the days worked (leave_accrual.py)
        values.update({"is_carry_forward": 1, "allow_encashment": 1,
                       "maximum_carry_forwarded_leaves": 0, "is_earned_leave": 1,
                       "earned_leave_frequency": "Monthly", "allocate_on_day": "Last Day", "rounding": ""})
    if name == rules.SICK_HALF_PAY:
        values.update({"is_ppl": 1, "fraction_of_daily_salary_per_leave": rules.HALF_PAY_FRACTION})
    return values
