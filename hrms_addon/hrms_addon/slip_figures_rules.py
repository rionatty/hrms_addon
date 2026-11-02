# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a payroll's slips will show, before they are made, for its Employees
tab (Luuka, 1 Nov 2026: "this information doesnt populate after fetching
employee", "we have over 2000 employees").

No Frappe import, like the other *_rules.py modules, so
scripts/verify_slip_figures.py runs it without a bench. slip_figures.py reads
the whole payroll's attendance, assignments and Additional Salaries at once and
hands each person's here.

Frappe HR works a slip out one person at a time, with a dozen queries each. For
2,000 people that is minutes, and these figures are wanted as the form opens.
So this comes to what it comes to, from rows already read:

  days_of       the days, as SalarySlip.get_working_days_details counts them on
                attendance: who is on the payroll when, leave without pay,
                absences, half days, and unmarked days if Payroll Settings call
                them absent. pay_days_rules then puts them on Luuka's month, as
                it does for a slip
  month_lines   what a structure's lines come to for a whole month, as the
                assignment works them out
  earning_rows  those, and the Additional Salaries, as a slip's earning rows
  paid_rows     and what each of them is paid for the days

Once the slips are made the Employees tab reads them instead
(payroll_register.py).
"""

import ast
import datetime

ATTENDANCE = "Attendance"
ABSENT, HALF_DAY, ON_LEAVE = "Absent", "Half Day", "On Leave"
# the attendance that takes days off; Frappe HR reads only these
TAKES_DAYS = (ABSENT, HALF_DAY, ON_LEAVE)
DEFAULT_HALF_DAY = 0.5


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _flag(value):
    return int(_num(value))


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10]) if value else None


def days_of(start_date, end_date, joining, relieving, holidays, attendance, settings, leave_types, marked=()):
    """What Frappe HR's slip counts for one person, on Attendance:
    {"working", "on_payroll", "counted_from", "paid", "without_pay", "absent"}.

    holidays     the dates of the period on their holiday list
    attendance   their submitted rows of the period with a status in TAKES_DAYS
    settings     Payroll Settings
    leave_types  {name: row} of the leave types without pay or part paid
    marked       the dates of all their submitted attendance in the period, read
                 only if Payroll Settings count an unmarked day as absent
    """
    start, end = _date(start_date), _date(end_date)
    joining, relieving = _date(joining), _date(relieving)
    holidays = set(holidays or ())
    first = joining if joining and start < joining <= end else start
    last = relieving if relieving and start <= relieving < end else end
    counts_holidays = _flag(settings.get("include_holidays_in_total_working_days"))
    marked_on_holidays = counts_holidays and _flag(settings.get("consider_marked_attendance_on_holidays"))
    half_day = _num(settings.get("daily_wages_fraction_for_half_day")) or DEFAULT_HALF_DAY

    without_pay, absent, half_absent = 0.0, 0.0, 0
    for row in attendance or []:
        day, status, leave_type = _date(row.get("attendance_date")), row.get("status"), row.get("leave_type")
        if status == HALF_DAY and row.get("half_day_status") == ABSENT and first <= day <= last and (
                marked_on_holidays or day not in holidays):
            half_absent += 1
        if not start <= day <= last:
            continue
        leave = leave_types.get(leave_type) if leave_type else None
        if not marked_on_holidays and day in holidays and (
                status in (ABSENT, HALF_DAY) or (leave and not _flag(leave.get("include_holiday")))):
            continue
        if status == HALF_DAY and leave:
            without_pay += (1 - half_day) * _leave_share(leave)
        elif status == ON_LEAVE and leave:
            without_pay += _leave_share(leave)
        elif status == ABSENT:
            absent += 1

    holidays_on_payroll = sum(1 for day in holidays if first <= day <= last)
    working = (end - start).days + 1 - (0 if counts_holidays else len(holidays))
    on_payroll = (last - first).days + 1
    counted_from = 0 if joining and joining > end else on_payroll - (0 if counts_holidays else holidays_on_payroll)

    paid = 0.0
    if counted_from > without_pay:
        paid = counted_from - without_pay - absent
        if settings.get("consider_unmarked_attendance_as") == ABSENT:
            outside = _days_outside(start, first, last, end, holidays, counts_holidays)
            marks = sum(1 for day in marked or () if first <= day <= last and day not in holidays)
            unmarked = working - outside - marks - (holidays_on_payroll if counts_holidays else 0)
            absent += unmarked
            paid -= unmarked
        absent += half_absent * half_day
        paid -= half_absent * half_day
    return {"working": working, "on_payroll": on_payroll, "counted_from": counted_from, "paid": paid,
            "without_pay": without_pay, "absent": absent}


def _leave_share(leave):
    """The share of a day a day of this leave takes off: all of it, or what a part paid leave does not pay."""
    return (_num(leave.get("fraction_of_daily_salary_per_leave")) or 1) if _flag(leave.get("is_ppl")) else 1


def _days_outside(start, first, last, end, holidays, counts_holidays):
    """The days of the period before they joined or after they left."""
    before = [start + datetime.timedelta(days=offset) for offset in range((first - start).days)]
    after = [last + datetime.timedelta(days=offset) for offset in range(1, (end - last).days + 1)]
    return sum(1 for day in before + after if counts_holidays or day not in holidays)


def names_in(code):
    """The names a formula or condition reads: what it needs in hand to be worked out."""
    try:
        return {node.id for node in ast.walk(ast.parse(code or "", mode="eval")) if isinstance(node, ast.Name)}
    except (SyntaxError, ValueError):
        return set()


def month_lines(lines, data, evaluate):
    """What a structure's earning lines come to for a whole month, as a slip's
    rows; statistical lines and lines of nought have no row. lines: in the
    structure's order; data: what formulas may read, and is added to as each line
    is worked out, so a later line can read an earlier; evaluate(code, data): as
    Frappe HR evaluates a formula. A line that cannot be worked out comes to
    nought: the slip itself will say why."""
    rows = []
    for line in lines or []:
        condition, formula = line.get("condition"), line.get("formula")
        try:
            if condition and not evaluate(condition, data):
                continue
            formula_says = _flag(line.get("amount_based_on_formula")) and formula
            amount = round(_num(evaluate(formula, data)), 2) if formula_says else _num(line.get("amount"))
        except Exception:
            amount = 0.0
        data[line.get("abbr")] = amount
        if amount and not _flag(line.get("statistical_component")):
            rows.append({"salary_component": line.get("salary_component"), "default_amount": amount,
                         "additional_amount": 0.0, "depends_on_payment_days": line.get("depends_on_payment_days"),
                         "do_not_include_in_total": line.get("do_not_include_in_total")})
    return rows


def earning_rows(lines, additional):
    """A slip's earning rows: the structure's, and the Additional Salaries'. A row
    that overwrites a structure's amount takes its place and is paid whole; any
    other is a row of its own, and follows the days as its component says.
    additional: rows with salary_component, amount and overwrite_salary_structure_amount,
    joined to their component's flags."""
    rows = [dict(line) for line in lines or []]
    for pay in additional or []:
        amount = _num(pay.get("amount"))
        overwritten = None
        if _flag(pay.get("overwrite_salary_structure_amount")):
            overwritten = next((row for row in rows if row["salary_component"] == pay.get("salary_component")
                                and row["default_amount"]), None)
        if overwritten:
            overwritten["additional_amount"] = amount - overwritten["default_amount"]
            overwritten["whole"] = 1
            continue
        rows.append({"salary_component": pay.get("salary_component"), "default_amount": 0.0, "additional_amount": amount,
                     "depends_on_payment_days": pay.get("depends_on_payment_days"),
                     "statistical_component": pay.get("statistical_component"),
                     "do_not_include_in_total": pay.get("do_not_include_in_total")})
    return rows


def paid_rows(rows, payment_days, working_days, rounded=()):
    """The rows with what each is paid (`amount`): by the days, where it follows them,
    each of its two amounts to the cent; otherwise whole. rounded: the components
    paid to the nearest shilling."""
    paid = []
    for row in rows or []:
        default, additional = _num(row.get("default_amount")), _num(row.get("additional_amount"))
        amount = default + additional
        if _flag(row.get("depends_on_payment_days")) and not row.get("whole") and _num(working_days) > 0:
            share = _num(payment_days) / _num(working_days)
            amount = round(default * share, 2) + round(additional * share, 2)
        if row.get("salary_component") in rounded:
            amount = round(amount)
        paid.append(dict(row, amount=amount))
    return paid
