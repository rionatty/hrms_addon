# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Overtime on the site: what the day is, what it costs, and how it is paid.

The rules are in overtime_rules.py, without a Frappe import
(scripts/verify_overtime.py). This reads and writes the site.

LPL/HR/14 is raised before the work and authorised by the officer who
carries the section (attendance.py). This adds the two steps after that:

  cost_check      HR read what the overtime comes to — the day's rate
                  against each person's own hourly pay — and sign for it
  send_to_payroll the authorised hours are written onto the employees'
                  Attendance rows with the Overtime Type they fall under,
                  and an Overtime Slip is drawn for the cycle

The slip is Frappe HR's own: it prices the attendance it finds, holds the
multipliers on the Overtime Type, and writes the Additional Salary the
payroll run reads. Nothing here re-prices it, and nothing here writes a
salary component.

  seed_overtime_types   the three kinds of day, at the Employment Act's
                        floor, made once and then Luuka's to amend
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import attendance_rules, overtime_rules as rules, people

REQUEST = "Overtime Request"
TYPE = "Overtime Type"
SLIP = "Overtime Slip"


# ── 1. What sort of day it is ─────────────────────────────────────────
def day_kind(employee, day):
    """Read the day rather than ask for it: a holiday on the employee's
    own list, their weekly off, a day they are on leave, or a weekday."""
    return rules.kind_of_day({
        "on_holiday_list": _is_holiday(employee, day, weekly_off=False),
        "is_weekly_off": _is_holiday(employee, day, weekly_off=True),
        "on_leave": _on_leave(employee, day),
    })


def _holiday_list(employee):
    found = frappe.db.get_value("Employee", employee, ["holiday_list", "company"], as_dict=True)
    if not found:
        return None
    if found.holiday_list:
        return found.holiday_list
    return frappe.db.get_value("Company", found.company, "default_holiday_list")


def _is_holiday(employee, day, weekly_off):
    name = _holiday_list(employee)
    if not name:
        return False
    return bool(frappe.db.exists("Holiday", {"parent": name, "holiday_date": getdate(day),
                                             "weekly_off": 1 if weekly_off else 0}))


def _on_leave(employee, day):
    return bool(frappe.db.exists("Leave Application", {
        "employee": employee, "docstatus": 1, "status": "Approved",
        "from_date": ["<=", getdate(day)], "to_date": [">=", getdate(day)]}))


def type_for(kind, company=None):
    """The Overtime Type the day falls under. Named, not guessed: the
    types are seeded under the names in overtime_rules."""
    name = rules.type_name_for(kind)
    if frappe.db.exists(TYPE, name):
        return name
    return None


# ── 2. What it costs ──────────────────────────────────────────────────
def fill_day_and_rate(doc):
    """Called from attendance.overtime_validate: the day, its type and its
    multiplier, so the form shows the rate before anybody signs."""
    if not doc.get("overtime_date") or not (doc.get("employees") or []):
        return
    first = next((row.employee for row in doc.employees if row.employee), None)
    if not first:
        return
    kind = day_kind(first, doc.overtime_date)
    doc.day_kind = kind
    doc.overtime_type = type_for(kind, doc.get("company"))
    doc.multiplier = rules.multiplier_for(kind, _type_row(doc.overtime_type))


def _type_row(name):
    if not name:
        return None
    return frappe.db.get_value(
        TYPE, name,
        ["standard_multiplier", "weekend_multiplier", "public_holiday_multiplier",
         "applicable_for_weekend", "applicable_for_public_holiday",
         "maximum_overtime_hours_allowed", "overtime_salary_component"], as_dict=True)


def _types_for(kind):
    """The Overtime Types a day of this kind can price under: its own and,
    on a weekday, the higher earners' (minutes §4.12)."""
    names = {rules.type_name_for(kind), rules.type_name_for(kind, rules.GROSS_THRESHOLD + 1)}
    return {name: _type_row(name) for name in names if frappe.db.exists(TYPE, name)}


def _monthly_bases(employees):
    """Each employee's monthly base, from their Salary Structure
    Assignment. The one in force, not the newest ever written."""
    out = {}
    for employee in employees:
        found = frappe.get_all(
            "Salary Structure Assignment",
            filters={"employee": employee, "docstatus": 1,
                     "from_date": ["<=", today()]},
            fields=["base"], order_by="from_date desc", limit=1)
        out[employee] = flt(found[0].base) if found else 0.0
    return out


@frappe.whitelist(methods=["POST"])
def cost_check(name, cost_centre=None, remarks=None):
    """Test case 3's third step: HR see what the overtime costs before it
    goes anywhere near the payroll."""
    doc = frappe.get_doc(REQUEST, name)
    doc.check_permission("write")
    kind = doc.get("day_kind") or day_kind(doc.employees[0].employee, doc.overtime_date)
    overtime_type = _type_row(doc.get("overtime_type") or type_for(kind, doc.get("company")))
    rows = [row.as_dict() for row in doc.get("employees") or []]
    bases = _monthly_bases([row.get("employee") for row in rows if row.get("employee")])
    costed = rules.priced(rows, bases, kind, overtime_type, _types_for(kind))
    errors = rules.cost_check_errors({
        "status": doc.get("status"), "rows": costed["rows"], "unpriced": costed["unpriced"],
        "cost_centre": cost_centre or doc.get("cost_centre")})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Cost Check"))
    for row, priced_row in zip(doc.employees, costed["rows"]):
        row.db_set({"hourly_rate": priced_row["hourly_rate"], "multiplier": priced_row["multiplier"],
                    "amount": priced_row["amount"]}, update_modified=False)
    doc.db_set({
        "day_kind": kind, "overtime_type": doc.get("overtime_type") or type_for(kind),
        "multiplier": costed["multiplier"], "total_cost": costed["total"],
        "cost_centre": cost_centre or doc.get("cost_centre"),
        "cost_remarks": remarks or doc.get("cost_remarks"),
        "over_the_cap": 1 if rules.over_the_cap(
            doc.get("total_hours"), (overtime_type or {}).get("maximum_overtime_hours_allowed"))
        else 0,
        "costed_by": frappe.session.user, "costed_on": today(), "status": "Costed",
    }, update_modified=False)
    if doc.get("over_the_cap"):
        frappe.msgprint(_("This is over the ceiling on {0}. It may still be paid, but say so in "
                          "the HR remarks.").format(doc.overtime_type), indicator="orange")
    return {"total": costed["total"], "multiplier": costed["multiplier"], "kind": kind}


# ── 3. How it is paid ─────────────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def send_to_payroll(name):
    """Test cases 2, 4 and 5: the authorised hours are written onto the
    employees' own Attendance rows under the Overtime Type the day falls
    under, and Frappe HR's Overtime Slip is drawn for the cycle. The slip
    prices them and writes the Additional Salary payroll reads — none of
    that is done here."""
    doc = frappe.get_doc(REQUEST, name)
    doc.check_permission("submit")
    rows = []
    for row in doc.get("employees") or []:
        attendance = frappe.db.get_value("Attendance", {
            "employee": row.employee, "attendance_date": getdate(doc.overtime_date),
            "docstatus": 1}, "name")
        if attendance and not row.attendance:
            row.db_set("attendance", attendance, update_modified=False)
        rows.append(dict(row.as_dict(), attendance=attendance))
    errors = rules.payroll_errors({"status": doc.get("status"), "rows": rows})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Payroll"))
    kind = doc.get("day_kind") or rules.WEEKDAY
    bases = _monthly_bases([row["employee"] for row in rows])
    marked = 0
    for row in rows:
        values = rules.attendance_update(row, kind, attendance_rules.STANDARD_HOURS,
                                         gross=bases.get(row["employee"]))
        if not frappe.db.exists(TYPE, values["overtime_type"]):
            values.pop("overtime_type")
        frappe.db.set_value("Attendance", row["attendance"], values, update_modified=False)
        marked += 1
    slips = _draw_slips(doc)
    doc.db_set({"status": "Sent to Payroll", "sent_to_payroll_on": today()},
               update_modified=False)
    officers = people.people_for("Payroll Officer", doc.get("branch"), doc.get("department")) \
        or people.hr_officers(doc.get("branch"), doc.get("department"))
    if officers:
        people.notify(list(officers), doc.doctype, doc.name,
                      _("Overtime of {0} for {1} is checked and ready for payroll.").format(
                          frappe.utils.fmt_money(doc.get("total_cost") or 0),
                          frappe.utils.format_date(doc.overtime_date)))
    return {"attendance_marked": marked, "slips": slips}


def _draw_slips(doc):
    """One Overtime Slip per employee per attendance cycle. An open slip
    that already covers the day is left alone — it will pick the hours up
    on its own, because it reads the attendance, not this request."""
    start, end = attendance_rules.cycle_window(*attendance_rules.cycle_of(doc.overtime_date))
    window = rules.slip_window(start, end)
    made = []
    for row in doc.get("employees") or []:
        existing = frappe.db.get_value(SLIP, {
            "employee": row.employee, "docstatus": ["<", 2],
            "start_date": ["<=", getdate(doc.overtime_date)],
            "end_date": [">=", getdate(doc.overtime_date)]}, "name")
        if existing:
            made.append(existing)
            continue
        try:
            slip = frappe.get_doc({
                "doctype": SLIP, "employee": row.employee, "company": doc.get("company"),
                "department": doc.get("department"), "posting_date": today(),
                "start_date": window["start_date"], "end_date": window["end_date"]})
            slip.flags.ignore_permissions = True
            slip.flags.ignore_mandatory = True
            slip.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: overtime slip for an authorised request")
            continue
        made.append(slip.name)
    return made


# ── 4. The three kinds of day, as masters ─────────────────────────────
def seed_overtime_types():
    """The Employment Act's floor, made once. Luuka amend the multipliers
    and name the salary component; this never writes over a type that is
    already there."""
    component = _overtime_component()
    for kind in (rules.WEEKDAY, rules.REST_DAY, rules.PUBLIC_HOLIDAY):
        name = rules.type_name_for(kind)
        if frappe.db.exists(TYPE, name):
            continue
        try:
            doc = frappe.get_doc({
                "doctype": TYPE, "__newname": name,
                "overtime_salary_component": component,
                "standard_multiplier": rules.ACT_MULTIPLIERS[rules.WEEKDAY],
                "applicable_for_weekend": 1,
                "weekend_multiplier": rules.ACT_MULTIPLIERS[rules.REST_DAY],
                "applicable_for_public_holiday": 1,
                "public_holiday_multiplier": rules.ACT_MULTIPLIERS[rules.PUBLIC_HOLIDAY],
                "overtime_calculation_method": "Salary Component Based",
            })
            doc.flags.ignore_permissions = True
            doc.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: seeding the overtime types")
    # a weekday for those whose gross is above the line pays 1x (§4.12)
    if not frappe.db.exists(TYPE, rules.HIGHER_EARNERS):
        try:
            doc = frappe.get_doc({
                "doctype": TYPE, "__newname": rules.HIGHER_EARNERS,
                "overtime_salary_component": component,
                "standard_multiplier": rules.HIGHER_EARNER_MULTIPLIER,
                "applicable_for_weekend": 1,
                "weekend_multiplier": rules.ACT_MULTIPLIERS[rules.REST_DAY],
                "applicable_for_public_holiday": 1,
                "public_holiday_multiplier": rules.ACT_MULTIPLIERS[rules.PUBLIC_HOLIDAY],
                "overtime_calculation_method": "Salary Component Based",
            })
            doc.flags.ignore_permissions = True
            doc.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: seeding the higher earners' overtime type")


def _overtime_component():
    """An Overtime Type cannot be saved without the salary component it
    pays through, so the component is made once if Luuka have none. It is
    an earning and nothing more: how it is taxed and where it posts is
    theirs to set."""
    for name in ("Overtime", "Overtime Allowance"):
        if frappe.db.exists("Salary Component", name):
            return name
    try:
        doc = frappe.get_doc({
            "doctype": "Salary Component", "salary_component": "Overtime",
            "salary_component_abbr": "OT", "type": "Earning",
            "description": "Overtime, paid through Frappe HR's Overtime Slip."})
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: the overtime salary component")
        return None
    return doc.name


def warn_below_the_act():
    """after_migrate: a multiplier somebody has edited under the statutory
    floor is said out loud on the deploy rather than found in a payslip."""
    for kind in (rules.WEEKDAY, rules.REST_DAY, rules.PUBLIC_HOLIDAY):
        name = rules.type_name_for(kind)
        row = _type_row(name) if frappe.db.exists(TYPE, name) else None
        if not row:
            continue
        multiplier = rules.multiplier_for(kind, row)
        if rules.below_the_act(kind, multiplier):
            message = ("HRMS Addon: %s pays %sx on a %s, under the Employment Act's %sx"
                       % (name, multiplier, kind.lower(), rules.ACT_MULTIPLIERS[kind]))
            frappe.log_error(title=message)
            print(message)


def setup_on_migrate():
    seed_overtime_types()
    warn_below_the_act()
