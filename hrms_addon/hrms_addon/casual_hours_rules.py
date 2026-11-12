# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Casuals' hours by the week, one sheet a plant.

Luuka, 12 Nov 2026: "the team captures total number of hours worked and
overtime how can we make it easy for them"; "working hour is 10, and per day
2hrs per day and no maximum overtime hours for casuals"; then "build it".

No Frappe import, like the other *_rules.py modules, so
scripts/verify_casual_hours.py exercises it without a bench.

A sheet is one plant's week: each casual paid by the hour, with the week's
hours and overtime as totals rather than a row a day. Once the plant's
General Manager approves it, the weekly payroll pays it (weekly_pay.py):

  the hours        at the person's own Hourly Rate on the week's last day
  the overtime     at that rate times their Overtime Type's multiplier, with
                   no cap: a casual's overtime has no maximum
  the days         none of the days a sheet covers is paid again from the
                   attendance, so the week is paid once

  read_rows        the team's sheet, whatever row its headings are on
  number           a cell as hours: "1,5" is refused, never read as 15
  row_errors       a row's hours: none below nothing, no more ordinary hours
                   than the week has standard days
  sheet_errors     the week: From and To, at most seven days, none to come
  pay              what a row comes to
  overlap          whether two weeks share a day
  slip_rows        what a weekly slip ending on a day pays from the sheets
"""

import datetime

# a casual's standard day where Output Pay Settings give none (Luuka, 12 Nov 2026: "working hour is 10")
STANDARD_DAY = 10.0
# a sheet is one week
MOST_DAYS = 7

# what the headings may say: the template's own first, then the team's casual master payroll's
EMPLOYEE_HEADS = ("PAYROLL NO", "PAYROLL NUMBER", "EMP ID", "EMPLOYEE ID", "EMPLOYEE", "ID")
NAME_HEADS = ("NAME", "EMPLOYEE NAME", "COUNT OF EMPLOYEE")
HOURS_HEADS = ("HOURS WORKED", "WORKING HOURS", "TOTAL HOURS", "HOURS")
OVERTIME_HEADS = ("OVERTIME HOURS", "OT HOURS", "OT1-HOURS", "OVERTIME", "OT")
DAYS_HEADS = ("DAYS WORKED", "DAYS")
TEMPLATE_HEADS = ("PAYROLL NO", "NAME", "HOURS WORKED", "OVERTIME HOURS", "DAYS WORKED")
# a row the team's own sheet adds up on, not a person
TOTALS = ("TOTAL", "TOTALS", "GRAND TOTAL", "SUB TOTAL", "SUBTOTAL")


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    try:
        return datetime.date(*(int(part) for part in str(value)[:10].split("-")))
    except (ValueError, TypeError):
        return None


def shown(value):
    day = _date(value)
    return "%d %s %d" % (day.day, day.strftime("%b"), day.year) if day else ""


def _head(value):
    return " ".join(str(value or "").replace("\n", " ").split()).upper()


def number(value):
    """(hours, None), or (None, why) for a cell that is not hours. An empty cell is nothing. A comma is never read
    as a point: "1,5" would otherwise become fifteen hours."""
    if value is None or value == "":
        return 0.0, None
    if isinstance(value, bool):
        return None, "%s is not a number of hours" % value
    if isinstance(value, (int, float)):
        return float(value), None
    text = str(value).strip()
    if not text:
        return 0.0, None
    if "," in text:
        return None, "write %s with a point, not a comma" % text
    try:
        return float(text), None
    except ValueError:
        return None, "%s is not a number of hours" % text


def _find(heads, wanted):
    """The column whose heading is the first of `wanted` the headings have."""
    for name in wanted:
        if name in heads:
            return heads.index(name)
    return None


def read_rows(table):
    """{"rows": [{"line", "employee", "name", "hours", "overtime", "days"}], "problems": [text]} from a sheet's
    cells, a list of rows of values, whatever row the headings are on and whatever else it carries. A person with
    nothing on the row is left out; a total line is not a person. Raises ValueError with no headings to read."""
    rows = [list(row or ()) for row in table or ()]
    start = None
    for at, row in enumerate(rows):
        heads = [_head(cell) for cell in row]
        if _find(heads, EMPLOYEE_HEADS) is not None and _find(heads, HOURS_HEADS) is not None:
            start = at
            break
    if start is None:
        raise ValueError("The sheet has no PAYROLL NO and HOURS WORKED headings: download the template and fill "
                         "that in.")
    heads = [_head(cell) for cell in rows[start]]
    columns = {"employee": _find(heads, EMPLOYEE_HEADS), "name": _find(heads, NAME_HEADS),
               "hours": _find(heads, HOURS_HEADS), "overtime": _find(heads, OVERTIME_HEADS),
               "days": _find(heads, DAYS_HEADS)}
    found, problems = [], []
    for at in range(start + 1, len(rows)):
        row = rows[at]

        def cell(key):
            index = columns[key]
            return row[index] if index is not None and index < len(row) else None

        employee = " ".join(str(cell("employee") or "").split())
        if not employee or employee.upper() in TOTALS:
            continue
        line, values, wrong = at + 1, {}, []
        for key in ("hours", "overtime", "days"):
            value, why = number(cell(key))
            values[key] = value
            if why:
                wrong.append(why)
        if wrong:
            problems.append("Row %d, %s: %s." % (line, employee, "; ".join(wrong)))
            continue
        if not (values["hours"] or values["overtime"] or values["days"]):
            continue
        found.append({"line": line, "employee": employee, "name": " ".join(str(cell("name") or "").split()),
                      "hours": values["hours"], "overtime": values["overtime"], "days": values["days"]})
    return {"rows": found, "problems": problems}


def week_days(from_date, to_date):
    first, last = _date(from_date), _date(to_date)
    return (last - first).days + 1 if first and last and last >= first else 0


def sheet_errors(from_date, to_date, today=None):
    """Why a sheet's week will not do, as messages."""
    first, last, now = _date(from_date), _date(to_date), _date(today)
    if not first or not last:
        return ["Say the week: its From and To."]
    if last < first:
        return ["To is before From."]
    errors = []
    if week_days(first, last) > MOST_DAYS:
        errors.append("A sheet is one week: at most %d days." % MOST_DAYS)
    if now and last > now:
        errors.append("The week ends on %s: hours are entered once they are worked." % shown(last))
    return errors


def row_errors(row, days, standard=STANDARD_DAY):
    """Why a row's figures will not do, as messages. row: "hours", "overtime", "days"; days: the sheet's days;
    standard: a casual's standard day. Overtime has no cap: a casual's overtime has no maximum."""
    errors = []
    hours, overtime, worked = _num(row.get("hours")), _num(row.get("overtime")), _num(row.get("days"))
    if hours < 0 or overtime < 0 or worked < 0:
        errors.append("hours and days cannot be less than nothing")
    most = round(int(days or 0) * _num(standard or STANDARD_DAY), 2)
    if most and hours > most:
        errors.append("%g hours is more than %d days of %g hours: put the rest under Overtime Hours"
                      % (hours, int(days), _num(standard or STANDARD_DAY)))
    if days and worked > int(days):
        errors.append("%g days worked in a week of %d days" % (worked, int(days)))
    return errors


def pay(hours, overtime, rate, multiplier):
    """{"hours_pay", "overtime_pay", "total_pay"}: the hours at the rate, the overtime at the rate times the
    multiplier."""
    hours_pay = round(_num(hours) * _num(rate), 2)
    overtime_pay = round(_num(overtime) * _num(rate) * _num(multiplier), 2)
    return {"hours_pay": hours_pay, "overtime_pay": overtime_pay, "total_pay": round(hours_pay + overtime_pay, 2)}


def overlap(first_from, first_to, second_from, second_to):
    """Whether two weeks share a day."""
    a, b, c, d = (_date(day) for day in (first_from, first_to, second_from, second_to))
    return bool(a and b and c and d and a <= d and c <= b)


def in_spans(day, spans):
    day = _date(day)
    return bool(day) and any(_date(first) <= day <= _date(last) for first, last in spans or ())


def default_week(last_to, today):
    """The week a new sheet is for: the day after the plant's last sheet, seven days, never past yesterday; with
    no sheet yet, the seven days to yesterday."""
    now = _date(today)
    yesterday = now - datetime.timedelta(days=1) if now else None
    last = _date(last_to)
    if last:
        start = last + datetime.timedelta(days=1)
        end = start + datetime.timedelta(days=MOST_DAYS - 1)
        return start, min(end, yesterday) if yesterday and yesterday >= start else end
    if not yesterday:
        return None, None
    return yesterday - datetime.timedelta(days=MOST_DAYS - 1), yesterday


def slip_rows(rows, paid, end):
    """What a weekly slip ending on `end` pays from the sheets, earliest first: the approved rows of weeks that
    end on or before it that no submitted slip has paid. rows: [{"sheet", "to_date", "hours", "overtime",
    "days", "overtime_type"}], one person's; paid: the sheets a submitted slip paid this person for."""
    last = _date(end)
    done = set(paid or ())
    out = []
    for row in rows or []:
        to_date = _date(row.get("to_date"))
        if not last or not to_date or to_date > last or row.get("sheet") in done:
            continue
        if not (_num(row.get("hours")) or _num(row.get("overtime"))):
            continue
        out.append(dict(row, to_date=to_date))
    return sorted(out, key=lambda row: (row["to_date"], row.get("sheet") or ""))


def day_rows(rows):
    """A sheet's rows as the weekly slip's days (weekly_pay.slip_before_validate): ([day], [overtime]), each
    dated the week's last day; the day carries the sheet, the days worked and the week's hours, which a standard
    day does not cap (they are a week's), and the overtime its Overtime Type."""
    days, overtime = [], []
    for row in rows or []:
        days.append({"attendance_date": _date(row["to_date"]), "status": "Present", "hours": round(_num(row.get("hours")), 2),
                     "hours_sheet": row.get("sheet"), "days_worked": round(_num(row.get("days")), 2)})
        if _num(row.get("overtime")) > 0:
            overtime.append({"attendance_date": _date(row["to_date"]), "status": "Present",
                             "hours": round(_num(row.get("overtime")), 2), "overtime_type": row.get("overtime_type")})
    return days, overtime
