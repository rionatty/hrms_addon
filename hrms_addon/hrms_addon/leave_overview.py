# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Leave Overview (page/leave_overview): the queries.

What each figure means is leave_overview_rules.py; this is the part that
asks the site, and that decides whose leave the person asking may see.
Everything here reads. Nothing is written, so the page can be opened as
often as it is wanted.

  overview()   rows 1, 2 and 4: who is away and the cover, what is stuck,
               the year by month. One call, for the first paint.
  year_end()   row 3: what the leave earned and not taken is worth. Asked
               for separately, by those who may see it: it prices every
               employee from their salary structure, which takes longer
               than the rest of the page together.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import leave_follow, leave_overview_rules as rules, leave_rules

APPLICATION = "Leave Application"
CHANGE = "Leave Plan Change"
PLAN = "Annual Leave Plan"
PLAN_ROW = "Annual Leave Plan Employee"
# a list on the page is a glance, not a report: its count is always whole
LIST_SHOWN = 15
LEAVE_FIELDS = ["name", "employee", "employee_name", "department", "custom_branch", "leave_type", "from_date",
                "to_date", "total_leave_days", "custom_reliever"]


def _reach():
    """What the person asking may see, or a refusal: the page lists who is
    away, which being able to read a Leave Application (one's own) does
    not entitle anybody to."""
    seen = rules.reach(frappe.get_roles())
    if not seen:
        frappe.throw(_("The Leave Overview is for HR, management, heads of department and supervisors."),
                     frappe.PermissionError)
    return seen


def _people(seen, branch=None, department=None):
    """{employee: row} whose leave the person asking sees, within the plant
    and department asked for: everybody for HR and management, their own
    people for a head of department or a supervisor."""
    rows = frappe.get_all("Employee", filters={"status": "Active"}, limit_page_length=0,
                          fields=["name", "employee_name", "department", "branch", "reports_to"])
    if not seen["all"]:
        user = frappe.session.user
        held = frappe.get_all("User Permission", filters={"user": user, "allow": ["in", ["Branch", "Department"]]},
                              fields=["allow", "for_value"], limit_page_length=0)
        own = rules.own_people(
            rows, frappe.db.get_value("Employee", {"user_id": user}, "name"),
            {row.for_value for row in held if row.allow == "Department"},
            {row.for_value for row in held if row.allow == "Branch"}, head=seen["head"])
        rows = [row for row in rows if row.name in own]
    return {row.name: row for row in rows
            if (not branch or row.branch == branch) and (not department or row.department == department)}


def _approved_between(names, start, end):
    """Approved leave of these people touching the days from start to end."""
    if not names:
        return []
    return frappe.get_all(APPLICATION, limit_page_length=0, fields=LEAVE_FIELDS, filters={
        "employee": ["in", names], "docstatus": 1, "status": "Approved",
        "from_date": ["<=", end], "to_date": [">=", start]})


def _shown(rows, seen, people):
    """A list as the page shows it: capped, with the reliever's name, the
    plant from the employee, and the leave type only for HR."""
    out = []
    for row in rows[:LIST_SHOWN]:
        line = dict(row)
        if not seen["why"]:
            line.pop("leave_type", None)
        reliever = line.pop("custom_reliever", None)
        line["reliever"] = frappe.db.get_value("Employee", reliever, "employee_name") if reliever else None
        line["branch"] = (people.get(line.get("employee")) or {}).get("branch")
        out.append(line)
    return out


@frappe.whitelist()
def overview(year=None, branch=None, department=None):
    """Rows 1, 2 and 4, in one answer."""
    from hrms_addon.hrms_addon import leave_approval as approval, leave_plan_change_approval as change_approval

    seen = _reach()
    now = getdate(today())
    year = cint(year) or now.year
    people = _people(seen, branch, department)
    names = list(people)

    # 1. who is away, and are we covered
    near = _approved_between(names, now, add_days(now, rules.COVER_DAYS))
    found = rules.away(near, now)
    headcount = {}
    for row in people.values():
        headcount[row.department or ""] = headcount.get(row.department or "", 0) + 1
    limit = leave_follow.most_off(frappe._dict(from_date=now, custom_branch=branch))

    # 2. what is stuck
    pending = frappe.get_all(APPLICATION, limit_page_length=0, filters={
        "employee": ["in", names], "docstatus": 0, "workflow_state": ["in", list(approval.PENDING_STATES)]},
        fields=["name", "employee", "employee_name", "department", "from_date", "to_date", "workflow_state",
                "custom_at_desk_since", "custom_chased", "modified"]) if names else []
    waiting = rules.waiting([dict(row, state=row.workflow_state, desk=_(approval.REMARK_FIELDS[row.workflow_state][1]),
                                  since=row.custom_at_desk_since or getdate(row.modified),
                                  from_date=str(row.from_date), to_date=str(row.to_date), modified=None)
                             for row in pending], now)
    changes = frappe.get_all(CHANGE, limit_page_length=0, filters={
        "employee": ["in", names], "docstatus": 0, "workflow_state": ["in", list(change_approval.PENDING_STATES)]},
        fields=["name", "employee", "employee_name", "department", "workflow_state", "modified"]) if names else []
    moving = rules.waiting([dict(row, state=row.workflow_state, since=getdate(row.modified), modified=None)
                            for row in changes], now)
    not_back = frappe.get_all(APPLICATION, limit_page_length=0, order_by="to_date asc", filters={
        "employee": ["in", names], "docstatus": 1, "status": "Approved", "custom_reported_back": ["!=", 1],
        "to_date": ["<", now]},
        fields=["name", "employee", "employee_name", "department", "to_date", "custom_overstay_days"]) if names else []

    # 4. is there a pattern
    start, end = leave_rules.year_window(year)
    yearly = _approved_between(names, start, end)
    months = rules.by_month([dict(row, days=row.total_leave_days) for row in yearly], year, by_type=seen["why"])
    sick = rules.sick_patterns([dict(row, days=row.total_leave_days) for row in yearly
                                if "sick" in (row.leave_type or "").lower()]) if seen["why"] else None

    return {
        "year": year, "today": str(now), "people": len(names), "sees": seen,
        "away": {"today": _shown(found["today"], seen, people), "today_count": len(found["today"]),
                 "soon": _shown(found["soon"], seen, people), "soon_count": len(found["soon"]),
                 "soon_days": rules.SOON_DAYS},
        "cover": {"departments": rules.cover(headcount, near, now, limit), "limit": limit, "days": rules.COVER_DAYS},
        "stuck": {
            "waiting": waiting[:LIST_SHOWN], "waiting_count": len(waiting), "longest": rules.longest(waiting),
            "changes": moving[:LIST_SHOWN], "changes_count": len(moving),
            "not_back": [dict(row, to_date=str(row.to_date), overdue=cint(row.custom_overstay_days))
                         for row in not_back[:LIST_SHOWN]],
            "not_back_count": len(not_back),
            "overdue_count": len([row for row in not_back if cint(row.custom_overstay_days)]),
        },
        "months": months, "sick": sick, "plan_kept": _plan_kept(names, year),
    }


def _plan_kept(names, year):
    """How far the year's approved plans were kept to, for these people."""
    plans = [row.name for row in frappe.get_all(PLAN, filters={"docstatus": 1}, fields=["name", "year"],
                                                limit_page_length=0) if str(row.year) == str(year)]
    if not plans or not names:
        return None
    counts = {}
    for row in frappe.get_all(PLAN_ROW, limit_page_length=0, fields=["leave_status"], filters={
            "parent": ["in", plans], "parenttype": PLAN, "employee": ["in", names]}):
        status = row.leave_status or leave_rules.PLANNED
        counts[status] = counts.get(status, 0) + 1
    return rules.plan_kept(counts)


@frappe.whitelist()
def year_end(year=None, branch=None, department=None):
    """Row 3: the annual leave earned and not taken, what it is worth at a
    day's pay, and the days the year end would lose. Management's, and
    asked for apart from the rest: every employee is priced from their own
    salary structure."""
    from hrms_addon.hrms_addon import leave, leave_accrual, pay

    seen = _reach()
    if not seen["money"]:
        frappe.throw(_("What leave is worth is for the HR Manager and management."), frappe.PermissionError)
    now = getdate(today())
    year = cint(year) or now.year
    # this year as it stands today; an earlier one as it closed
    on = now if year == now.year else leave_rules.year_window(year)[1]
    names = list(_people(seen, branch, department))
    annual = leave.annual_type()
    kind = frappe.db.get_value("Leave Type", annual, ["is_carry_forward", "maximum_carry_forwarded_leaves"],
                               as_dict=True) or frappe._dict()
    earned = leave_accrual.earned_for(names, annual, on)
    rows = []
    for name in names:
        found = earned.get(name)
        if found:
            days, balance = flt(found.available), flt(found.balance)
        else:
            # leave given at the start of the year, not earned by the days worked
            days = balance = flt(leave_accrual._hrms_figures(name, annual, on).balance)
        if days <= 0 and balance <= 0:
            continue
        rows.append({"earned": days, "balance": balance, "gross": pay.monthly_gross(name, on),
                     "carries_forward": cint(kind.is_carry_forward),
                     "most_carried": flt(kind.maximum_carry_forwarded_leaves)})
    return dict(rules.year_end(rows), year=year, as_of=str(on), leave_type=annual,
                working_days=rules.WORKING_DAYS_A_MONTH)
