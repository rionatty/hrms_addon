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

from hrms_addon.hrms_addon import attendance_rules, overtime_rules as rules, pay, people

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
         "maximum_overtime_hours_allowed", "overtime_salary_component", "custom_gross_above"], as_dict=True)


def _types_for(kind):
    """The Overtime Types a day of this kind can price under: its own and,
    on a weekday, each type with a gross line (minutes §4.12)."""
    names = {rules.type_name_for(kind)}
    if kind == rules.WEEKDAY:
        names |= set(frappe.get_all(TYPE, filters={"custom_gross_above": [">", 0]}, pluck="name"))
    return {name: _type_row(name) for name in names if frappe.db.exists(TYPE, name)}


def _monthly_gross(employees, day):
    """Each employee's monthly gross on the day, as their salary structure
    works it out: what the line on the Overtime Type is compared with."""
    return {employee: pay.monthly_gross(employee, day) for employee in employees}


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
    people_on_it = [row.get("employee") for row in rows if row.get("employee")]
    bases = _monthly_bases(people_on_it)
    costed = rules.priced(rows, bases, kind, overtime_type, _types_for(kind),
                          _monthly_gross(people_on_it, doc.overtime_date))
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
    grosses = _monthly_gross([row["employee"] for row in rows], doc.overtime_date)
    lines = rules.gross_lines(_types_for(kind))
    marked = 0
    for row in rows:
        values = rules.attendance_update(row, kind, attendance_rules.STANDARD_HOURS,
                                         gross=grosses.get(row["employee"]), lines=lines)
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
    """The Employment Act's floor, made once. An hour is worked out of the
    earnings the salary structures work out from the base (Frappe HR asks
    for them on an Overtime Type), and each type pays through the company's
    own overtime earning for its rate. Luuka amend them after; this never
    writes over a type that is already there."""
    kinds = [kind for kind in (rules.WEEKDAY, rules.REST_DAY, rules.PUBLIC_HOLIDAY)
             if not frappe.db.exists(TYPE, rules.type_name_for(kind))]
    higher = not frappe.db.exists(TYPE, rules.HIGHER_EARNERS)
    if not kinds and not higher:
        return
    hourly = _hourly_components()
    if not hourly:
        message = ("HRMS Addon: the overtime types are not made yet. No submitted salary structure works "
                   "an earning out from the base for an hour of overtime to be priced from.")
        frappe.log_error(title=message)
        print(message)
        return
    earnings = frappe.get_all("Salary Component", filters={"type": "Earning"},
                              fields=["name", "salary_component_abbr"])
    weekday_component = rules.component_for_rate(rules.ACT_MULTIPLIERS[rules.WEEKDAY], earnings)
    for kind in kinds:
        _make_type(rules.type_name_for(kind),
                   rules.component_for_rate(rules.ACT_MULTIPLIERS[kind], earnings) or _overtime_component(),
                   hourly, rules.ACT_MULTIPLIERS[kind])
    # a weekday for those whose gross is above the line pays 1x (§4.12)
    if higher:
        _make_type(rules.HIGHER_EARNERS,
                   rules.component_for_rate(rules.HIGHER_EARNER_MULTIPLIER, earnings) or weekday_component
                   or _overtime_component(),
                   hourly, rules.HIGHER_EARNER_MULTIPLIER, gross_above=rules.GROSS_THRESHOLD)


def _hourly_components():
    """The earnings the active salary structures work out from the base."""
    structures = set(frappe.get_all("Salary Structure", filters={"docstatus": 1, "is_active": "Yes"},
                                    pluck="name"))
    found = []
    for row in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure", "parentfield": "earnings"},
                              fields=["parent", "salary_component", "formula", "amount_based_on_formula",
                                      "statistical_component", "do_not_include_in_total"], order_by="idx asc"):
        if row.parent in structures and rules.works_from_base(row) and row.salary_component not in found:
            found.append(row.salary_component)
    return found


def _make_type(name, component, hourly, standard, gross_above=None):
    values = {
        "doctype": TYPE, "__newname": name, "overtime_salary_component": component,
        "overtime_calculation_method": "Salary Component Based",
        "applicable_salary_component": [{"salary_component": earning} for earning in hourly],
        "standard_multiplier": standard,
        "applicable_for_weekend": 1, "weekend_multiplier": rules.ACT_MULTIPLIERS[rules.REST_DAY],
        "applicable_for_public_holiday": 1,
        "public_holiday_multiplier": rules.ACT_MULTIPLIERS[rules.PUBLIC_HOLIDAY],
    }
    if gross_above:
        values["custom_gross_above"] = gross_above
    try:
        doc = frappe.get_doc(values)
        doc.flags.ignore_permissions = True
        doc.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: making the %s overtime type" % name)
        print("HRMS Addon: the %s overtime type could not be made. See the Error Log." % name)


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
            "description": "Overtime, paid through the Overtime Slip."})
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


def fill_gross_line():
    """The higher earners' type made before it carried its line gets the
    minutes' UGX 500,000. A line HR have set is theirs."""
    if frappe.db.exists(TYPE, rules.HIGHER_EARNERS) and \
            not flt(frappe.db.get_value(TYPE, rules.HIGHER_EARNERS, "custom_gross_above")):
        frappe.db.set_value(TYPE, rules.HIGHER_EARNERS, "custom_gross_above", rules.GROSS_THRESHOLD,
                            update_modified=False)


def setup_on_migrate():
    seed_overtime_types()
    fill_gross_line()
    warn_below_the_act()
