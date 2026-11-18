# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A shift's crew from the clock (Manufacturing Excellence, 18 Nov 2026).

The people a section's shift planned on are its employees (their Section)
whose shift that day is the shift's: their Shift Assignment (made by the
Shift Rotations), else their default shift, else the shift their attendance
was marked on, else Day. For each, from what the site already holds:

  Attendance           present or not, on leave, late and early (the
                       minutes the clock gave), overtime written onto the day
  Overtime Request     the overtime approved for the day and what it cost
  Safety Incident      their incidents and near misses on the shift
  salary structure     their day: the month's pay without overtime over the
                       paid days (pay.monthly_gross), kept for the month

So planned, on shift, unauthorised absence, lateness, early departures,
overtime and incidents are sums with the names behind them, and the shift's
labour costs what its people are paid. PPE stays observed: tick Without PPE
on the people seen without it.
"""

import datetime

import frappe
from frappe.utils import add_days, cint, flt, getdate, now_datetime

from hrms_addon.hrms_addon import excellence_rules as rules

ATTENDANCE, ASSIGNMENT, OT_REQUEST, OT_LINE = "Attendance", "Shift Assignment", "Overtime Request", "Overtime Request Employee"
INCIDENT, EMPLOYEE_SECTION = "Safety Incident", "custom_work_section"
OT_LIVE = ("Requested", "Authorised", "Costed", "Sent to Payroll")
RATE_KEY = "hrms_addon:me_day_rates:%s"
RATE_SECONDS = 40 * 24 * 3600


def crew(section, day, shift, s, standard=None):
    """The crew of a section's shift on a day, as Shift Crew rows."""
    day = getdate(day)
    employees = _section_people(section, day)
    if not employees:
        return []
    names = [row.name for row in employees]
    shifts = _shifts(names, day)
    marked = _attendance(names, day)
    on_shift = []
    for row in employees:
        kind = shifts.get(row.name)
        if kind is None and marked.get(row.name) and marked[row.name].get("shift"):
            kind = rules.shift_of(marked[row.name]["shift"], _start_times().get(marked[row.name]["shift"]))
        if (kind or rules.DAY) == shift:
            on_shift.append(row)
    names = [row.name for row in on_shift]
    if not names:
        return []
    overtime = _overtime(names, day)
    incidents = _incidents(names, day, shift)
    rates = day_rates(names, day, s)
    fallback = flt((standard or {}).get("labour_rate"))
    lwp = _unpaid_leave_types()
    found = []
    for row in on_shift:
        mark = marked.get(row.name) or {}
        ot = overtime.get(row.name)
        facts = {"status": mark.get("status"), "leave_type": mark.get("leave_type"),
                 "paid_leave": mark.get("leave_type") not in lwp if mark.get("leave_type") else None,
                 "late": mark.get("late_entry"), "early": mark.get("early_exit"),
                 "late_minutes": mark.get("custom_late_minutes"), "early_minutes": mark.get("custom_early_minutes"),
                 "attendance_ot_hours": mark.get("actual_overtime_duration"),
                 "ot_hours": ot["hours"] if ot else None, "ot_amount": ot["amount"] if ot else 0}
        line = rules.crew_line(facts, rates.get(row.name) or fallback, s)
        hit = incidents.get(row.name) or {}
        found.append({
            "employee": row.name, "employee_name": row.employee_name,
            "employment": rules.CASUAL if "casual" in (row.employment_type or "").lower() else rules.PERMANENT,
            "rostered_shift": shifts.get(row.name + ":type") or mark.get("shift"),
            "status": line["status"], "unauthorised": line["unauthorised"], "late_minutes": line["late_minutes"],
            "early_minutes": line["early_minutes"], "ot_hours": line["ot_hours"], "ot_cost": line["ot_cost"],
            "day_rate": line["day_rate"], "day_cost": line["day_cost"], "absence_cost": line["absence_cost"],
            "incidents": hit.get("incidents", 0), "near_misses": hit.get("near_misses", 0),
            "attendance": mark.get("name"),
        })
    return found


def fill(doc):
    """The Shift Report's crew from the clock, keeping who was ticked Without
    PPE."""
    from hrms_addon.hrms_addon import excellence

    s = excellence.settings()
    section = frappe.get_cached_doc(excellence.SECTION, doc.work_section)
    standard = excellence.section_standard(section, doc.report_date)
    ticked = {row.employee for row in doc.get("crew") or [] if cint(row.get("no_ppe"))}
    rows = crew(doc.work_section, doc.report_date, doc.shift, s, standard)
    doc.set("crew", [])
    for row in rows:
        row["no_ppe"] = int(row["employee"] in ticked)
        doc.append("crew", row)
    doc.clock_fetched_on = now_datetime()
    return rows


def _section_people(section, day):
    """The section's employees who were employed on the day."""
    rows = frappe.get_all("Employee", filters={EMPLOYEE_SECTION: section, "date_of_joining": ["<=", str(day)]},
                          fields=["name", "employee_name", "employment_type", "status", "relieving_date",
                                  "default_shift"], order_by="employee_name asc", limit_page_length=0)
    return [row for row in rows if row.status in ("Active", "Suspended")
            or (row.relieving_date and getdate(row.relieving_date) >= day)]


def _start_times():
    found = getattr(frappe.local, "ha_me_shift_starts", None)
    if found is None:
        found = {row.name: row.start_time for row in frappe.get_all("Shift Type", fields=["name", "start_time"],
                                                                    limit_page_length=0)}
        frappe.local.ha_me_shift_starts = found
    return found


def _shifts(names, day):
    """{employee: Day or Night} on the day, from the Shift Assignment in force,
    else the default shift; "<employee>:type" holds the Shift Type itself."""
    starts = _start_times()
    found = {}
    for row in frappe.get_all(ASSIGNMENT, filters={"employee": ["in", names], "docstatus": 1, "status": "Active",
                                                   "start_date": ["<=", str(day)]},
                              fields=["employee", "shift_type", "start_date", "end_date"], order_by="start_date asc",
                              limit_page_length=0):
        if row.end_date and getdate(row.end_date) < day:
            continue
        found[row.employee] = rules.shift_of(row.shift_type, starts.get(row.shift_type))
        found[row.employee + ":type"] = row.shift_type
    for row in frappe.get_all("Employee", filters={"name": ["in", names], "default_shift": ["is", "set"]},
                              fields=["name", "default_shift"], limit_page_length=0):
        if row.name not in found:
            found[row.name] = rules.shift_of(row.default_shift, starts.get(row.default_shift))
            found[row.name + ":type"] = row.default_shift
    return found


def _attendance(names, day):
    fields = ["name", "employee", "status", "leave_type", "late_entry", "early_exit", "shift"]
    meta = frappe.get_meta(ATTENDANCE)
    for field in ("custom_late_minutes", "custom_early_minutes", "actual_overtime_duration"):
        if meta.has_field(field):
            fields.append(field)
    return {row.employee: row for row in frappe.get_all(
        ATTENDANCE, filters={"employee": ["in", names], "attendance_date": str(day), "docstatus": 1},
        fields=fields, limit_page_length=0)}


def _overtime(names, day):
    """{employee: {"hours", "amount"}} approved or waiting for the day."""
    requests = frappe.get_all(OT_REQUEST, filters={"overtime_date": str(day), "docstatus": ["<", 2],
                                                   "status": ["in", list(OT_LIVE)]}, pluck="name",
                              limit_page_length=0)
    if not requests:
        return {}
    found = {}
    for row in frappe.get_all(OT_LINE, filters={"parenttype": OT_REQUEST, "parent": ["in", requests],
                                                "employee": ["in", names]},
                              fields=["employee", "hours", "payable_hours", "amount"], limit_page_length=0):
        mine = found.setdefault(row.employee, {"hours": 0.0, "amount": 0.0})
        mine["hours"] += flt(row.payable_hours) or flt(row.hours)
        mine["amount"] += flt(row.amount)
    return found


def _incidents(names, day, shift):
    """{employee: {"incidents", "near_misses"}} logged on the shift."""
    found = {}
    start = datetime.datetime.combine(day, datetime.time(0, 0))
    end = datetime.datetime.combine(add_days(day, 1), datetime.time(7, 0))
    for row in frappe.get_all(INCIDENT, filters={"employee": ["in", names], "docstatus": ["<", 2],
                                                 "incident_on": ["between", [str(start), str(end)]]},
                              fields=["employee", "incident_on", "severity"], limit_page_length=0):
        if rules.incident_shift(row.incident_on, day) != shift:
            continue
        mine = found.setdefault(row.employee, {"incidents": 0, "near_misses": 0})
        mine["near_misses" if row.severity == "Near Miss" else "incidents"] += 1
    return found


def _unpaid_leave_types():
    return set(frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name"))


def day_rates(employees, day, s):
    """{employee: day rate}: the month's pay of their salary structure (without
    overtime) over the paid days. Worked out once a month for each person and
    kept: the crews of a plant's day read them all."""
    from hrms_addon.hrms_addon import pay

    month = str(getdate(day))[:7]
    key = RATE_KEY % month
    kept = frappe.cache.get_value(key) or {}
    missing = [employee for employee in employees if employee not in kept]
    for employee in missing:
        try:
            kept[employee] = rules.day_rate_of(pay.monthly_gross(employee, day), s)
        except Exception:
            kept[employee] = 0.0
    if missing:
        frappe.cache.set_value(key, kept, expires_in_sec=RATE_SECONDS)
    return {employee: kept.get(employee) or 0.0 for employee in employees}
