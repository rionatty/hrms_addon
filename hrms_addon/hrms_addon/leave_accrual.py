# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave earned by the days worked, on the site.

The rules are in leave_accrual_rules.py, without a Frappe import
(scripts/verify_leave_accrual.py). This reads and writes the site.

  accrual            what an employee has earned of a leave type by a day,
                     and what they can still take: Frappe HR's own balance,
                     less what is allocated but not yet earned, less what
                     is waiting for approval
  application_*      the Leave Application shows it in Part 2 and refuses a
                     leave longer than what can be taken
  with_earned        the Earned columns on Frappe HR's three leave reports
                     (report_extensions.py puts them there)
  allocate           every active employee with no leave policy for the
                     leave period gets one: the policy they had the year
                     before, else the default; each year, and as people
                     join, when Leave Management Settings say so
  remove_unearned    when a leave year ends, what was allocated but never
                     earned comes off the allocation (a Leave Adjustment),
                     so only earned leave is carried forward

WHY FRAPPE HR'S BALANCE IS READ, NOT CALLED

Frappe HR's get_leave_balance_on refuses anyone but HR, the employee and
their leave approver (validate_leave_access), and the approval chain's
supervisors and heads of department save the form too. So its balance is
read here from the same functions it uses, without that check.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import leave_accrual_rules as rules, leave_advance_rules, people

SETTINGS = "Leave Management Settings"
EXCLUDED_TYPES = "Leave Advance Employment Type"
HR_ROLES = {"HR User", "HR Manager", "System Manager"}
ACCRUAL_DEFAULTS = {"absent_days_earn": 0, "count_up_to": rules.UP_TO_LEAVE_START, "remove_unearned": 1,
                    "auto_allocate": 0, "default_leave_policy": None, "leave_advance_account": None}
# the year-end adjustment's reason, so a second run finds the first
UNEARNED_REASON = "Leave not earned"
APPLICATION_FIELDS = ("custom_leave_earned", "custom_earned_by", "custom_days_worked", "custom_leave_brought_forward",
                      "custom_leave_available")
# Frappe HR's leave reports that gain the Earned columns (report_extensions.py)
REPORTS = ("Employee Leave Balance", "Employee Leave Balance Summary", "Leave Ledger")


# ── 0. The settings ───────────────────────────────────────────────────
def settings():
    """Leave Management Settings, what was never saved taking its default."""
    stored = {}
    if frappe.db.exists("DocType", SETTINGS):
        stored = dict(frappe.db.get_singles_dict(SETTINGS) or {})
        stored["not_regular_types"] = frappe.get_all(
            EXCLUDED_TYPES, filters={"parent": SETTINGS, "parenttype": SETTINGS}, pluck="employment_type",
            limit_page_length=0)
    merged = leave_advance_rules.settings_from(stored)
    for key, default in ACCRUAL_DEFAULTS.items():
        value = stored.get(key)
        merged[key] = default if value in (None, "") else value
    for key in ("absent_days_earn", "remove_unearned", "auto_allocate"):
        merged[key] = cint(merged[key])
    if merged["count_up_to"] not in rules.UP_TO:
        merged["count_up_to"] = rules.UP_TO_LEAVE_START
    return frappe._dict(merged)


def settings_validate(doc, method=None):
    values = {key: doc.get(key) for key in leave_advance_rules.DEFAULTS}
    values["not_regular_types"] = [row.employment_type for row in doc.get("not_regular_types") or []]
    errors = leave_advance_rules.settings_errors(leave_advance_rules.settings_from(values))
    account = doc.get("leave_advance_account")
    if account:
        found = frappe.db.get_value("Account", account, ["account_type", "root_type", "is_group"], as_dict=True)
        if found and (found.account_type in ("Receivable", "Payable") or found.root_type != "Asset" or found.is_group):
            errors.append("The Leave Advance Account is an asset account, not a group, a receivable or a payable: "
                          "the payroll takes each deduction back into it without naming the employee.")
    doc.recovery_component = leave_advance_rules.RECOVERY_COMPONENT
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SETTINGS))


# ── 1. What has been earned ───────────────────────────────────────────
def leave_type_rule(leave_type):
    """The Leave Type's standard earned leave settings, read once a request."""
    if not leave_type:
        return None
    memo = frappe.flags.setdefault("hrms_addon_leave_types", {})
    if leave_type not in memo:
        memo[leave_type] = frappe.db.get_value(
            "Leave Type", leave_type, ["name", "is_earned_leave", "is_lwp", "earned_leave_frequency", "allocate_on_day",
                                       "rounding", "include_holiday", "allow_negative"], as_dict=True)
    return memo[leave_type]


def earning_types():
    """The leave types that are earned."""
    return [row.name for row in frappe.get_all("Leave Type", filters={"is_earned_leave": 1},
                                              fields=["name", "is_earned_leave", "is_lwp"], order_by="name asc")
            if rules.earns(row)]


def accrual(employee, leave_type, on, until=None, exclude=None, s=None):
    """What `employee` has earned of `leave_type` by `on`, and what they can
    take; None when the type is not earned. until: the last day of the leave
    being checked, for when brought-forward leave expires; exclude: the
    application being checked, which is not "waiting for approval"."""
    rule = leave_type_rule(leave_type)
    if not (employee and rules.earns(rule)):
        return None
    s = s or settings()
    on = getdate(on or today())
    person = _employee(employee)
    allocation = _allocation(employee, leave_type, on)
    start, end = _window(person.company, on, allocation)
    rate = rules.per_year(_policy_days(employee, leave_type, on, allocation, s),
                          allocation.new_leaves_allocated if allocation else None, start, end,
                          person.date_of_joining, person.relieving_date)
    earned = rules.earned({"per_year": rate, "window_start": start, "window_end": end,
                           "frequency": rule.earned_leave_frequency, "allocate_on_day": rule.allocate_on_day,
                           "rounding": rule.rounding, "as_of": on, "joining": person.date_of_joining,
                           "relieving": person.relieving_date, "off": _off_days(employee, start, end, s)})
    figures = _hrms_figures(employee, leave_type, on, until)
    pending = _pending(employee, leave_type, start, end, exclude)
    return frappe._dict(
        leave_type=leave_type, as_of=on, window_start=start, window_end=end, per_year=rate,
        earned=earned["earned"], days_worked=earned["days_worked"], days_off=earned["days_off"],
        carried=figures.carried, credited=figures.credited, taken=figures.taken, pending=pending,
        balance=figures.balance, available=rules.available(figures.balance, figures.credited, earned["earned"], pending),
        unearned=rules.unearned(figures.credited, earned["earned"]))


def _employee(employee):
    memo = frappe.flags.setdefault("hrms_addon_accrual_people", {})
    if employee not in memo:
        memo[employee] = frappe.db.get_value("Employee", employee, ["company", "date_of_joining", "relieving_date"],
                                             as_dict=True) or frappe._dict()
    return memo[employee]


def _allocation(employee, leave_type, on):
    rows = frappe.get_all("Leave Allocation",
                          filters={"employee": employee, "leave_type": leave_type, "docstatus": 1,
                                   "from_date": ["<=", on], "to_date": [">=", on]},
                          fields=["name", "from_date", "to_date", "new_leaves_allocated", "leave_policy"],
                          order_by="from_date desc", limit=1)
    return rows[0] if rows else None


def _window(company, on, allocation):
    """The leave year a day falls in: its allocation's, else the company's
    Leave Period, else the calendar year."""
    if allocation:
        return getdate(allocation.from_date), getdate(allocation.to_date)
    if company:
        period = frappe.get_all("Leave Period", filters={"company": company, "from_date": ["<=", on],
                                                         "to_date": [">=", on]},
                                fields=["from_date", "to_date"], order_by="from_date desc", limit=1)
        if period:
            return getdate(period[0].from_date), getdate(period[0].to_date)
    return getdate("%d-01-01" % on.year), getdate("%d-12-31" % on.year)


def _policy_days(employee, leave_type, on, allocation, s):
    """The year's days on the employee's leave policy: the allocation's own,
    else the assignment in force, else (with no allocation at all) the
    default policy."""
    policy = allocation.leave_policy if allocation and allocation.get("leave_policy") else None
    if not policy:
        found = frappe.get_all("Leave Policy Assignment",
                               filters={"employee": employee, "docstatus": 1, "effective_from": ["<=", on],
                                        "effective_to": [">=", on]}, pluck="leave_policy", limit=1)
        policy = found[0] if found else None
    if not policy and not allocation:
        policy = s.get("default_leave_policy")
    if not policy:
        return None
    days = frappe.get_all("Leave Policy Detail", filters={"parent": policy, "parenttype": "Leave Policy",
                                                          "leave_type": leave_type},
                          pluck="annual_allocation", limit=1)
    return flt(days[0]) if days else None


def _off_days(employee, start, end, s):
    """{date: part of the day not worked}: leave without pay, and days marked
    Absent unless the settings say those earn too."""
    key = (employee, str(start), str(end), cint(s.get("absent_days_earn")))
    memo = frappe.flags.setdefault("hrms_addon_accrual_off", {})
    if key in memo:
        return memo[key]
    unpaid = {row.name: row for row in frappe.get_all("Leave Type", filters={"is_lwp": 1},
                                                      fields=["name", "include_holiday"])}
    spans = []
    if unpaid:
        for row in frappe.get_all("Leave Application",
                                  filters={"employee": employee, "docstatus": 1, "status": "Approved",
                                           "leave_type": ["in", list(unpaid)], "from_date": ["<=", end],
                                           "to_date": [">=", start]},
                                  fields=["leave_type", "from_date", "to_date", "half_day", "half_day_date"]):
            spans.append(dict(row, include_holiday=unpaid[row.leave_type].include_holiday))
    off = {}
    if spans:
        from hrms_addon.hrms_addon import leave

        off = rules.unpaid_days(spans, leave.holidays_between(employee, start, end))
    if not cint(s.get("absent_days_earn")):
        off = rules.merge_off(off, {getdate(day): 1.0 for day in frappe.get_all(
            "Attendance", filters={"employee": employee, "docstatus": 1, "status": rules.ABSENT,
                                   "attendance_date": ["between", [start, end]]},
            pluck="attendance_date", limit_page_length=0)})
    memo[key] = off
    return off


def _hrms_figures(employee, leave_type, on, until=None):
    """Frappe HR's balance for consumption on a day, the new leave credited
    and the leave brought forward, as its own balance check reads them."""
    from hrms.hr.doctype.leave_application.leave_application import (
        get_allocation_expiry_for_cf_leaves, get_leave_allocation_records, get_leaves_for_period,
        get_manually_expired_leaves, get_remaining_leaves)

    allocation = get_leave_allocation_records(employee, on, leave_type).get(leave_type)
    if not allocation:
        return frappe._dict(balance=0.0, credited=0.0, carried=0.0, taken=0.0)
    expiry = get_allocation_expiry_for_cf_leaves(employee, leave_type, until or on, allocation.from_date)
    taken = get_leaves_for_period(employee, leave_type, allocation.from_date, allocation.to_date)
    expired = get_manually_expired_leaves(employee, leave_type, allocation.from_date, allocation.to_date)
    remaining = get_remaining_leaves(allocation, taken, on, expiry, expired)
    return frappe._dict(balance=flt(remaining.get("leave_balance_for_consumption")),
                        credited=flt(allocation.new_leaves_allocated), carried=flt(allocation.unused_leaves),
                        taken=round(-flt(taken), 2))


def _pending(employee, leave_type, start, end, exclude=None):
    """Leave of this type sent for approval and not yet decided, other than
    the application being checked."""
    from hrms_addon.hrms_addon import leave_approval as approval

    rows = frappe.get_all("Leave Application",
                          filters={"employee": employee, "leave_type": leave_type, "docstatus": 0, "status": "Open",
                                   "name": ["!=", exclude or ""], "from_date": ["<=", end], "to_date": [">=", start]},
                          fields=["total_leave_days", "workflow_state"])
    return round(sum(flt(row.total_leave_days) for row in rows if row.workflow_state in approval.PENDING_STATES), 2)


# ── 2. The Leave Application ──────────────────────────────────────────
def application_accrual(doc):
    """Part 2 of the form: what the employee has earned by the day the leave
    starts (or by the day of applying) and what can be taken. None, and the
    figures cleared, when the leave is not an earned type."""
    rule = leave_type_rule(doc.get("leave_type"))
    if not (doc.get("employee") and doc.get("from_date") and rules.earns(rule)):
        for field in APPLICATION_FIELDS:
            doc.set(field, None)
        return None
    s = settings()
    on = rules.count_up_to(s.count_up_to, doc.from_date, doc.get("posting_date") or today())
    found = accrual(doc.employee, doc.leave_type, on, until=doc.get("to_date"), exclude=doc.name, s=s)
    doc.custom_leave_earned = found.earned
    doc.custom_earned_by = on
    doc.custom_days_worked = found.days_worked
    doc.custom_leave_brought_forward = found.carried
    doc.custom_leave_available = found.available
    return found


def check_application(doc):
    """A leave of an earned type is no longer than what has been earned and
    can still be taken. Where the Leave Type allows a negative balance
    (Frappe HR's own setting), it is said rather than refused."""
    found = application_accrual(doc)
    if not found or doc.get("status") == "Rejected" or doc.docstatus == 2:
        return found
    errors = rules.accrual_errors({"leave_type": doc.leave_type, "days": doc.get("total_leave_days"),
                                   "available": found.available, "earned": found.earned,
                                   "days_worked": found.days_worked, "carried": found.carried, "as_of": found.as_of})
    if errors:
        if cint((leave_type_rule(doc.leave_type) or {}).get("allow_negative")):
            frappe.msgprint(_(errors[0]), indicator="orange", alert=True)
        else:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Leave Earned"))
    return found


@frappe.whitelist()
def get_application_accrual(employee, leave_type, from_date, to_date=None, posting_date=None, name=None):
    """The form's Part 2 figures, as they are typed in."""
    _may_see(employee)
    rule = leave_type_rule(leave_type)
    if not (employee and from_date and rules.earns(rule)):
        return None
    s = settings()
    on = rules.count_up_to(s.count_up_to, from_date, posting_date or today())
    found = accrual(employee, leave_type, on, until=to_date, exclude=name, s=s)
    return {"earned": found.earned, "earned_by": str(on), "days_worked": found.days_worked,
            "brought_forward": found.carried, "available": found.available, "pending": found.pending,
            "taken": found.taken}


def _may_see(employee):
    """HR, the employee themself, or anyone allowed to read the employee."""
    if HR_ROLES & set(frappe.get_roles()):
        return
    if frappe.db.get_value("Employee", employee, "user_id") == frappe.session.user:
        return
    if frappe.has_permission("Employee", "read", employee):
        return
    frappe.throw(_("Only HR, the employee or their approvers can see this."), frappe.PermissionError)


# ── 3. The Earned columns on the leave reports ────────────────────────
def with_earned(report, result, filters):
    """Frappe HR's leave report `report`, with the leave earned beside the
    balances (report_extensions.LeaveReportColumns calls this)."""
    filters = frappe._dict(filters or {})
    if not isinstance(result, (list, tuple)) or len(result) < 2:
        return result
    columns, data = list(result[0] or []), list(result[1] or [])
    types = set(earning_types())
    if not types:
        return result
    s = settings()
    if report == "Employee Leave Balance":
        columns, data = _balance_columns(columns, data, filters, types, s)
    elif report == "Employee Leave Balance Summary":
        columns, data = _summary_columns(columns, data, filters, types, s)
    elif report == "Leave Ledger":
        columns, data = _ledger_columns(columns, data, types, s)
    return (columns, data, *result[2:])


def _balance_columns(columns, data, filters, types, s):
    at = next((i for i, column in enumerate(columns)
               if isinstance(column, dict) and column.get("fieldname") == "closing_balance"), len(columns) - 1)
    columns[at + 1:at + 1] = [
        {"label": _("Leave(s) Earned"), "fieldtype": "Float", "fieldname": "leaves_earned", "width": 140},
        {"label": _("Can Be Taken"), "fieldtype": "Float", "fieldname": "leaves_available", "width": 130},
    ]
    on = getdate(filters.get("to_date") or today())
    for row in data:
        if isinstance(row, dict) and row.get("employee") and row.get("leave_type") in types:
            found = accrual(row["employee"], row["leave_type"], on, s=s)
            if found:
                row["leaves_earned"], row["leaves_available"] = found.earned, found.available
    return columns, data


def _summary_columns(columns, data, filters, types, s):
    """Columns are "Label:Float:160" strings and rows lists, one balance per
    leave type in name order; each earned type gains its Earned column."""
    names = frappe.get_all("Leave Type", pluck="name", order_by="name asc")
    first = len(columns) - len(names)
    if first < 0:
        return columns, data
    on = getdate(filters.get("date") or today())
    earned_at = [first + i for i, name in enumerate(names) if name in types]
    new_columns = []
    for i, column in enumerate(columns):
        new_columns.append(column)
        if i in earned_at:
            new_columns.append(_("{0} Earned").format(_(names[i - first])) + ":Float:130")
    new_data = []
    for row in data:
        if not isinstance(row, (list, tuple)):
            new_data.append(row)
            continue
        out = []
        for i, value in enumerate(row):
            out.append(value)
            if i in earned_at:
                found = accrual(row[0], names[i - first], on, s=s) if row and row[0] else None
                out.append(found.earned if found else None)
        new_data.append(out)
    return new_columns, new_data


def _ledger_columns(columns, data, types, s):
    columns.append({"label": _("Earned to Date"), "fieldtype": "Float", "fieldname": "earned_to_date", "width": 130})
    memo = {}
    for row in data:
        if not (isinstance(row, dict) and row.get("employee") and row.get("leave_type") in types):
            continue
        on = getdate(row.get("from_date") or row.get("date") or today())
        key = (row["employee"], row["leave_type"], on)
        if key not in memo:
            found = accrual(row["employee"], row["leave_type"], on, s=s)
            memo[key] = found.earned if found else None
        row["earned_to_date"] = memo[key]
    return columns, data


def earned_for(employees, leave_type, on):
    """{employee: accrual} for this app's own leave reports."""
    s = settings()
    if not rules.earns(leave_type_rule(leave_type)):
        return {}
    return {employee: accrual(employee, leave_type, on, s=s) for employee in dict.fromkeys(employees) if employee}


# ── 4. Allocating a year's leave to everyone ──────────────────────────
@frappe.whitelist(methods=["POST"])
def allocate_now():
    """Leave Management Settings' Allocate Now: the run, in the background."""
    frappe.only_for(("HR Manager", "System Manager"))
    frappe.enqueue("hrms_addon.hrms_addon.leave_accrual.allocate", queue="long", timeout=3000,
                   notify_user=frappe.session.user)
    return _("Allocating in the background. You will be told when it is done.")


def allocate(company=None, on=None, notify_user=None):
    """Every active employee with no leave policy for the leave period gets
    one: the policy they had before, else the default. Nobody who already
    has an allocation for the period is touched. Returns the counts."""
    s = settings()
    on = getdate(on or today())
    counts = {"assigned": 0, "already": 0, "no_policy": 0, "failed": 0}
    for name in ([company] if company else frappe.get_all("Company", pluck="name")):
        period = _leave_period(name, on)
        people_here = frappe.get_all("Employee", filters={"company": name, "status": "Active"},
                                     fields=["name", "date_of_joining"], limit_page_length=0)
        if not people_here:
            continue
        covered = set(frappe.get_all(
            "Leave Policy Assignment",
            filters={"docstatus": 1, "employee": ["in", [row.name for row in people_here]],
                     "effective_from": ["<=", period.to_date], "effective_to": [">=", period.from_date]},
            pluck="employee", limit_page_length=0))
        for person in people_here:
            if person.name in covered or (person.date_of_joining and getdate(person.date_of_joining) > getdate(
                    period.to_date)):
                counts["already"] += 1
                continue
            policy = _last_policy(person.name) or s.default_leave_policy
            if not policy:
                counts["no_policy"] += 1
                continue
            if _allocated_in(person.name, policy, period):
                counts["already"] += 1
                continue
            frappe.db.savepoint("hrms_addon_leave_policy")
            try:
                assignment = frappe.get_doc({"doctype": "Leave Policy Assignment", "employee": person.name,
                                             "leave_policy": policy, "assignment_based_on": "Leave Period",
                                             "leave_period": period.name, "effective_from": period.from_date,
                                             "effective_to": period.to_date, "carry_forward": 1})
                assignment.flags.ignore_permissions = True
                assignment.insert()
                assignment.submit()
                counts["assigned"] += 1
            except Exception:
                frappe.db.rollback(save_point="hrms_addon_leave_policy")
                frappe.log_error(title="HRMS Addon: leave policy for %s" % person.name)
                counts["failed"] += 1
    summary = _("{0} given their leave policy, {1} already had one, {2} with no policy to give, {3} failed "
                "(see the Error Log).").format(counts["assigned"], counts["already"], counts["no_policy"],
                                               counts["failed"])
    if frappe.db.exists("DocType", SETTINGS):
        frappe.db.set_single_value(SETTINGS, {"last_allocated_on": frappe.utils.now_datetime(),
                                                "last_allocation": summary})
    users = [notify_user] if notify_user else [row["user"] for row in people.holders("HR Manager")]
    if users and (counts["assigned"] or counts["failed"] or notify_user):
        people.notify(list(dict.fromkeys(users)), SETTINGS, SETTINGS, _("Leave allocation: {0}").format(summary))
    frappe.db.commit()
    return counts


def _leave_period(company, on):
    """The company's Leave Period for the day, made for the calendar year
    when there is none."""
    found = frappe.get_all("Leave Period", filters={"company": company, "from_date": ["<=", on], "to_date": [">=", on]},
                           fields=["name", "from_date", "to_date"], order_by="from_date desc", limit=1)
    if found:
        return found[0]
    period = frappe.get_doc({"doctype": "Leave Period", "company": company, "is_active": 1,
                             "from_date": "%d-01-01" % on.year, "to_date": "%d-12-31" % on.year})
    period.flags.ignore_permissions = True
    period.insert()
    return frappe._dict(name=period.name, from_date=period.from_date, to_date=period.to_date)


def _last_policy(employee):
    found = frappe.get_all("Leave Policy Assignment", filters={"employee": employee, "docstatus": 1},
                           pluck="leave_policy", order_by="effective_to desc", limit=1)
    return found[0] if found else None


def _allocated_in(employee, policy, period):
    """An allocation already covering the period for any of the policy's
    types: Frappe HR refuses a second one."""
    types = frappe.get_all("Leave Policy Detail", filters={"parent": policy, "parenttype": "Leave Policy"},
                           pluck="leave_type")
    return bool(types) and bool(frappe.get_all(
        "Leave Allocation", filters={"employee": employee, "docstatus": 1, "leave_type": ["in", types],
                                     "from_date": ["<=", period.to_date], "to_date": [">=", period.from_date]},
        pluck="name", limit=1))


# ── 5. When a leave year ends ─────────────────────────────────────────
def remove_unearned(on=None):
    """An allocation of an earned type that ended in the last two months
    gives up what was allocated but never earned, so that only earned leave
    is carried forward. Frappe HR allows one Leave Adjustment an allocation:
    one already there is left alone."""
    s = settings()
    if not s.remove_unearned:
        return 0
    on = getdate(on or today())
    types = earning_types()
    if not types:
        return 0
    made = 0
    for allocation in frappe.get_all("Leave Allocation",
                                     filters={"docstatus": 1, "leave_type": ["in", types],
                                              "to_date": ["between", [add_days(on, -60), add_days(on, -1)]]},
                                     fields=["name", "employee", "employee_name", "leave_type", "to_date"],
                                     limit_page_length=0):
        if frappe.db.exists("Leave Adjustment", {"leave_allocation": allocation.name, "docstatus": 1}):
            continue
        found = accrual(allocation.employee, allocation.leave_type, allocation.to_date, s=s)
        cut = round(min(found.unearned, max(found.balance, 0.0)), 2) if found else 0
        if cut <= 0:
            continue
        frappe.db.savepoint("hrms_addon_unearned")
        try:
            adjustment = frappe.get_doc({
                "doctype": "Leave Adjustment", "employee": allocation.employee, "leave_type": allocation.leave_type,
                "leave_allocation": allocation.name, "posting_date": allocation.to_date, "adjustment_type": "Reduce",
                "leaves_to_adjust": cut,
                "reason_for_adjustment": _("{0}: {1} day(s) allocated for the year were not earned by the days "
                                           "worked.").format(UNEARNED_REASON, cut)})
            adjustment.flags.ignore_permissions = True
            adjustment.insert()
            adjustment.submit()
            made += 1
        except Exception:
            frappe.db.rollback(save_point="hrms_addon_unearned")
            frappe.log_error(title="HRMS Addon: unearned leave for %s" % allocation.name)
    return made


# ── 6. Every day ──────────────────────────────────────────────────────
def daily():
    """The year's unearned leave taken off, then the year's (and new
    joiners') leave allocated when the settings say so."""
    remove_unearned()
    frappe.db.commit()
    if settings().auto_allocate:
        allocate()
