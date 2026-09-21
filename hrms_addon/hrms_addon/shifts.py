# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Shifts on the site: the rotation that comes round, and what a shift
is worth.

The rules are in shift_rules.py, without a Frappe import
(scripts/verify_shifts.py). This reads and writes the site.

  rotation_*   the cycle: which shift each member is on this period, and
               who is held off it until a promised date
  roll         the day's work — for every active rotation whose period has
               turned, a real Shift Assignment per member for the period
               ahead, so attendance is marked against the right shift
  allowance_*  what the shifts actually worked in a cycle come to, paid
               through a salary component as an Additional Salary
  draw_allowances  one per employee per attendance cycle, counted from the
               attendance rather than from the roster

The shifts themselves are Frappe HR's: a Shift Type with its hours and its
auto-attendance, a Shift Assignment putting somebody on one for a span, and
the Shift Assignment Tool for a whole plant at once. Nothing here rebuilds
them — the rotation writes their Shift Assignments, and that is all.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import attendance_rules, people, shift_rules as rules

ROTATION = "Shift Rotation"
ALLOWANCE = "Shift Allowance"
ASSIGNMENT = "Shift Assignment"
SHIFT_TYPE = "Shift Type"


# ── 1. The rotation ───────────────────────────────────────────────────
def rotation_validate(doc, method=None):
    errors = rules.rotation_errors({
        "rotation_name": doc.get("rotation_name"), "start_date": doc.get("start_date"),
        "period": doc.get("period"),
        "shifts": [row.as_dict() for row in doc.get("shifts") or []],
        "members": [row.as_dict() for row in doc.get("members") or []]})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(ROTATION))
    doc.cycle_length = rules.cycle_length([row.shift_type for row in doc.get("shifts") or []])
    if doc.get("start_date"):
        window = rules.period_window(doc.start_date, today(), doc.get("period") or rules.WEEKLY)
        doc.this_period_from, doc.this_period_to = window["from"], window["to"]
    _fill_current_shift(doc)


def _fill_current_shift(doc):
    """What each member is on this period, so the form is the roster."""
    shifts = [row.shift_type for row in doc.get("shifts") or []]
    if not (shifts and doc.get("start_date")):
        return
    rows = rules.schedule(doc.start_date, today(),
                          [row.as_dict() for row in doc.get("members") or []], shifts,
                          doc.get("period") or rules.WEEKLY)
    for member, planned in zip(doc.get("members") or [], rows):
        member.current_shift = planned["shift_type"]


@frappe.whitelist(methods=["POST"])
def roll(rotation=None, day=None):
    """Test case 4: the shifts come round on their own. For each active
    rotation, a Shift Assignment per member for the period ahead."""
    day = day or today()
    names = [rotation] if rotation else frappe.get_all(
        ROTATION, filters={"status": "Active", "start_date": ["<=", getdate(day)]}, pluck="name")
    made = 0
    for name in names:
        doc = frappe.get_doc(ROTATION, name)
        if rotation:
            doc.check_permission("write")
        made += _roll_one(doc, day)
    return made


def _roll_one(doc, day):
    shifts = [row.shift_type for row in doc.get("shifts") or []]
    if not shifts or not doc.get("members"):
        return 0
    planned = rules.schedule(doc.start_date, day,
                             [row.as_dict() for row in doc.get("members") or []], shifts,
                             doc.get("period") or rules.WEEKLY)
    made = 0
    for row in planned:
        if not (row["employee"] and row["shift_type"]):
            continue
        if frappe.db.exists(ASSIGNMENT, {
                "employee": row["employee"], "shift_type": row["shift_type"],
                "start_date": row["from"], "docstatus": ["<", 2]}):
            continue
        try:
            assignment = frappe.get_doc({
                "doctype": ASSIGNMENT, "employee": row["employee"],
                "shift_type": row["shift_type"], "company": doc.company,
                "department": doc.get("department"), "start_date": row["from"],
                "end_date": row["to"], "status": "Active"})
            assignment.flags.ignore_permissions = True
            assignment.flags.ignore_mandatory = True
            assignment.insert()
            assignment.submit()
        except Exception:
            frappe.log_error(title="HRMS Addon: rolling a shift rotation")
            continue
        made += 1
    doc.db_set({"last_rolled_on": getdate(day),
                "assignments_created": cint(doc.get("assignments_created")) + made},
               update_modified=False)
    _tell_rejoiners(doc, day)
    return made


def _tell_rejoiners(doc, day):
    """Somebody held on one shift whose promised date has passed rejoins
    the rotation. That is a change to their week, so it is said."""
    rejoining = rules.due_to_rejoin([row.as_dict() for row in doc.get("members") or []], day)
    if not rejoining:
        return
    for row in doc.get("members") or []:
        if row.employee in rejoining:
            row.db_set({"hold_until": None, "held_shift": None}, update_modified=False)
    users = [frappe.db.get_value("Employee", employee, "user_id") for employee in rejoining]
    users += list(people.people_for("Supervisor", doc.get("branch"), doc.get("department")))
    users = [user for user in dict.fromkeys(users) if user]
    if users:
        people.notify(users, doc.doctype, doc.name,
                      _("{0} rejoin the shift rotation on {1}.").format(
                          len(rejoining), frappe.utils.format_date(day)))


# ── 2. What a shift is worth ──────────────────────────────────────────
def allowance_validate(doc, method=None):
    _fill_lines(doc)
    errors = rules.allowance_errors({
        "employee": doc.get("employee"), "from_date": doc.get("from_date"),
        "to_date": doc.get("to_date"),
        "lines": [row.as_dict() for row in doc.get("lines") or []],
        "salary_component": doc.get("salary_component")})
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(ALLOWANCE))
    if doc.docstatus == 0:
        doc.status = "Draft"


def _fill_lines(doc):
    """Counted from the attendance, not from the roster: a shift planned
    and not worked is not paid."""
    if not (doc.get("employee") and doc.get("from_date") and doc.get("to_date")):
        return
    if not doc.get("lines"):
        for shift_type, count in sorted(_shifts_worked(doc).items()):
            rate = flt(frappe.db.get_value(SHIFT_TYPE, shift_type, "custom_shift_allowance"))
            if not rate:
                continue
            doc.append("lines", {"shift_type": shift_type, "shifts": count, "rate": rate})
    worked = {row.shift_type: cint(row.shifts) for row in doc.get("lines") or []}
    rates = {row.shift_type: flt(row.rate) for row in doc.get("lines") or []}
    due = rules.allowance_due(worked, rates)
    for row, line in zip(doc.get("lines") or [], due["lines"]):
        row.amount = line["amount"]
    doc.total = due["total"]
    doc.shifts_worked = sum(worked.values())
    if not doc.get("salary_component") and doc.get("lines"):
        doc.salary_component = frappe.db.get_value(
            SHIFT_TYPE, doc.lines[0].shift_type, "custom_allowance_component")


def _shifts_worked(doc):
    """{shift type: shifts} from the employee's own attendance."""
    rows = frappe.get_all(
        "Attendance",
        filters={"employee": doc.employee, "docstatus": 1, "status": ["in", ("Present",
                                                                             "Half Day")],
                 "attendance_date": ["between", [getdate(doc.from_date), getdate(doc.to_date)]]},
        fields=["shift"], limit=200)
    counted = {}
    for row in rows:
        if not row.shift:
            continue
        counted[row.shift] = counted.get(row.shift, 0) + 1
    return counted


def allowance_on_submit(doc, method=None):
    """Approved. The allowance is paid through the salary component as an
    Additional Salary, the way every other recovery and payment in this
    app reaches the payroll."""
    _pay(doc)


def allowance_on_cancel(doc, method=None):
    doc.status = "Cancelled"
    if doc.get("additional_salary"):
        try:
            extra = frappe.get_doc("Additional Salary", doc.additional_salary)
            if extra.docstatus == 1:
                extra.flags.ignore_permissions = True
                extra.cancel()
        except Exception:
            frappe.log_error(title="HRMS Addon: cancelling a shift allowance")


def _pay(doc):
    if doc.get("additional_salary") or not doc.get("total"):
        return None
    try:
        extra = frappe.get_doc({
            "doctype": "Additional Salary", "employee": doc.employee, "company": doc.company,
            "salary_component": doc.salary_component, "amount": flt(doc.total),
            "payroll_date": getdate(doc.to_date), "overwrite_salary_structure_amount": 0,
            "ref_doctype": doc.doctype, "ref_docname": doc.name})
        extra.flags.ignore_permissions = True
        extra.flags.ignore_mandatory = True
        extra.insert()
        extra.submit()
    except Exception:
        frappe.log_error(title="HRMS Addon: paying a shift allowance")
        return None
    doc.db_set({"additional_salary": extra.name, "status": "Sent to Payroll",
                "sent_to_payroll_on": today()}, update_modified=False)
    return extra.name


@frappe.whitelist(methods=["POST"])
def draw_allowances(year=None, month=None, company=None):
    """One draft allowance per employee per attendance cycle, for everyone
    who worked a shift that carries one."""
    cycle = attendance_rules.cycle_of(today()) if not (year and month) else (int(year), int(month))
    start, end = attendance_rules.cycle_window(*cycle)
    paying = frappe.get_all(SHIFT_TYPE, filters={"custom_shift_allowance": [">", 0]},
                            pluck="name")
    if not paying:
        return 0
    rows = frappe.get_all(
        "Attendance",
        filters={"docstatus": 1, "shift": ["in", paying],
                 "attendance_date": ["between", [start, end]]},
        fields=["employee", "company"], limit=20000)
    made = 0
    for employee in dict.fromkeys(row.employee for row in rows):
        if frappe.db.exists(ALLOWANCE, {"employee": employee, "from_date": start,
                                        "docstatus": ["<", 2]}):
            continue
        company_of = company or frappe.db.get_value("Employee", employee, "company")
        try:
            doc = frappe.get_doc({
                "doctype": ALLOWANCE, "employee": employee, "company": company_of,
                "from_date": start, "to_date": end})
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: drawing a shift allowance")
            continue
        made += 1
    return made


# ── 3. What the clock does ────────────────────────────────────────────
def daily():
    try:
        roll()
    except Exception:
        frappe.log_error(title="HRMS Addon: rolling the shift rotations")
    frappe.db.commit()


def monthly():
    """On the day the attendance cycle closes, the allowances are drawn
    for the cycle that has just ended."""
    if getdate(today()).day != attendance_rules.CYCLE_END_DAY:
        return
    try:
        draw_allowances()
    except Exception:
        frappe.log_error(title="HRMS Addon: drawing the shift allowances")
    frappe.db.commit()


# ── 4. The three shifts, as masters ───────────────────────────────────
def seed_shift_types():
    """Luuka's own three, made once: the office day, and the twelve-hour
    day and night the register's M and N stand for."""
    for name, (hours, start, end) in rules.SHIFT_HOURS.items():
        if frappe.db.exists(SHIFT_TYPE, name):
            continue
        try:
            doc = frappe.get_doc({
                "doctype": SHIFT_TYPE, "__newname": name, "start_time": start, "end_time": end,
                "enable_auto_attendance": 1,
                "working_hours_threshold_for_half_day": hours / 2.0,
                "working_hours_threshold_for_absent": 1.0,
                "determine_check_in_and_check_out":
                    "Alternating entries as IN and OUT during the same shift",
                "working_hours_calculation_based_on": "First Check-in and Last Check-out",
            })
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: seeding the shift types")


def setup_on_migrate():
    seed_shift_types()
