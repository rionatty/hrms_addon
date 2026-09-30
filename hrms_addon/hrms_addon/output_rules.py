# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Output pay: Per Meter, Per Piece, and the hourly casuals.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_output_pay.py exercises them without a bench.

WHERE THIS COMES FROM

The minutes of 16 and 20 July 2026 (Human Resource, Reward and
Compensation), §4.6 Gross Salary Processing, and Luuka's own sheet, PER
METER AUGUST 2026:

  Per Meter   the looms. Each size of material has its own rate, the Work
              Unit, in shillings a metre: 45CM-60CM 5.2, 74CM 6.5, 60CM
              6.9, 61CM-79CM 7.8, ABOVE 80CM 8.7 and ABOVE 39CM 8 on the
              August sheet. For each person, each day and each size the
              sheet has the Work Done in metres, and its TOTAL is Work Done
              x Work Unit; the day's six TOTALs are its BASIC, the day's
              LOOMS OT is typed in beside it, and TOTAL EARN is the two
              together. The month runs from the 26th to the 25th.
  Per Piece   the casuals at Matugga, the same way in pieces: each piece
              category has its own price.
  Hourly      the other casuals, at Namanve and Kawempe: hours worked x the
              standard hourly rate, "and then adding any overtime".

NO MACHINES

The machine a size was made on does not change what it pays: the rate is
the size's (Luuka, 30 Sep 2026). A size here is a Per Meter size or a Per
Piece category, each with its Work Unit.

EACH SIZE HAS ITS OWN WORK UNIT, FROM A DATE

A new Work Unit takes a start date, so a rate that changes in September
does not reprice August. Work with no Work Unit on its day is refused
rather than paid at nothing: it is a rate nobody has set, not work that
earned nothing.

THE LOOMS OT IS PAID HERE

Luuka's sheet added only the BASIC into each person's month, so the LOOMS
OT typed beside it never reached the month. It is paid here (Luuka, 30 Sep
2026): the month is every day's TOTAL EARN, metres and LOOMS OT together.
The hourly casuals' overtime is still the overtime module's, which prices
it from attendance, so only their standard hours are paid here.

ONE PLACE FOR A PERSON'S DAY

The metres come in by a supervisor's daily report or by the month's sheet
uploaded. A person's day is taken from one or the other, never both, so
nothing is paid twice. The sheet downloaded shows the supervisors' days
too; they come back as they were and stay the supervisors'.
"""

import datetime
import re

PER_METER, PER_PIECE, HOURLY = "Per Meter", "Per Piece", "Hourly"
OUTPUT_SECTIONS = (PER_METER, PER_PIECE)
SECTIONS = (PER_METER, PER_PIECE, HOURLY)
UNITS = {PER_METER: "Metres", PER_PIECE: "Pieces", HOURLY: "Hours"}
SIZE_WORD = {PER_METER: "size", PER_PIECE: "piece category"}
SHIFTS = ("Day", "Night")
ENTERED, UPLOADED = "Entered", "Uploaded"
SOURCES = (ENTERED, UPLOADED)

# the sizes on Luuka's PER METER AUGUST 2026 sheet, in its order, with
# their Work Units, from the first day of that month
SHEET_SIZES = (("45CM-60CM", 5.2), ("74CM", 6.5), ("60CM", 6.9), ("61CM-79CM", 7.8), ("ABOVE 80CM", 8.7),
               ("ABOVE 39CM", 8.0))
SHEET_FROM = "2026-07-26"

# a shift is twelve hours of which two are overtime (attendance_rules)
STANDARD_HOURS = 10.0


# ── The sizes and their Work Units ────────────────────────────────────
def size_key(label):
    """A size as written anywhere, for matching: " 45 cm - 60cm " and
    "45CM-60CM" are the same size."""
    return re.sub(r"\s+", "", str(label or "")).upper()


def size_errors(section, size, rows):
    """What is wrong with a size and its Work Units, as messages.

    rows: [{"work_unit", "valid_from"}]
    """
    if section not in OUTPUT_SECTIONS:
        return ["A size is for the Per Meter or the Per Piece section."]
    errors = []
    if not _text(size):
        errors.append("Name the %s." % SIZE_WORD[section])
    if not rows:
        errors.append("Give the %s its Work Unit, from the day it starts." % SIZE_WORD[section])
    seen = set()
    for number, row in enumerate(rows or [], 1):
        if _num(row.get("work_unit")) <= 0:
            errors.append("Work Unit row %d: the Work Unit is more than nothing." % number)
        start = _date(row.get("valid_from"))
        if not start:
            errors.append("Work Unit row %d: say the day it starts." % number)
        elif start in seen:
            errors.append("Work Unit row %d: another Work Unit starts the same day." % number)
        seen.add(start)
    return errors


def work_unit_on(rows, day):
    """The Work Unit in force on a day: the one with the latest start on or
    before it. None before the first one starts."""
    day = _date(day)
    fitting = [(_date(row.get("valid_from")), _num(row.get("work_unit"))) for row in rows or []
               if _date(row.get("valid_from")) and day and _date(row.get("valid_from")) <= day]
    return sorted(fitting)[-1][1] if fitting else None


def line_total(work_done, work_unit):
    """A line's TOTAL: Work Done x Work Unit."""
    return round(_num(work_done) * _num(work_unit), 2)


# ── The day: the Daily Production Report ──────────────────────────────
def report_errors(section, rows, overtime=None, employees=None, sizes=None):
    """What is wrong with a Daily Production Report, as messages.

    rows: [{"employee", "size", "output", "rate"}], rate None where the
    size has no Work Unit that day; overtime: [{"employee", "amount"}];
    employees: {employee: pay category}; sizes: {size: section}, the sizes
    in use.
    """
    if section not in OUTPUT_SECTIONS:
        return ["A production report is for the Per Meter or the Per Piece section."]
    employees, sizes = employees or {}, sizes or {}
    word = SIZE_WORD[section]
    errors = []
    seen = set()
    for number, row in enumerate(rows or [], 1):
        who, size = row.get("employee"), row.get("size")
        if not who or not size:
            errors.append("Row %d: say who made which %s." % (number, word))
            continue
        if _num(row.get("output")) < 0:
            errors.append("Row %d: Work Done cannot be less than nothing." % number)
        if size not in sizes:
            errors.append("Row %d: %s is not a %s in use." % (number, size, word))
        elif sizes[size] != section:
            errors.append("Row %d: %s is a %s %s, not %s." % (number, size, sizes[size],
                                                            SIZE_WORD.get(sizes[size], "size"), section))
        elif row.get("rate") is None:
            errors.append("Row %d: %s has no Work Unit on this day. Give it one from this day or before."
                          % (number, size))
        if who in employees and employees[who] != section:
            errors.append("Row %d: %s is paid %s, so their work does not belong on a %s report."
                          % (number, who, employees[who] or "Monthly", section))
        if (who, size) in seen:
            errors.append("Row %d: %s on %s is already on this report." % (number, who, size))
        seen.add((who, size))
    errors += overtime_errors(section, overtime, employees)
    return errors


def overtime_errors(section, overtime, employees=None, where="report"):
    """What is wrong with the LOOMS OT typed on a report (or a run). A row
    is called by its own idx where it has one, so a run that checks only
    the rows typed in still names the row as the table shows it."""
    if not overtime:
        return []
    if section != PER_METER:
        return ["Looms OT belongs on a Per Meter %s." % where]
    employees = employees or {}
    errors = []
    seen = set()
    for position, row in enumerate(overtime, 1):
        number = row.get("idx") or position
        who = row.get("employee")
        if not who:
            errors.append("Looms OT row %d: say whose it is." % number)
            continue
        if _num(row.get("amount")) < 0:
            errors.append("Looms OT row %d: it cannot be less than nothing." % number)
        if who in employees and employees[who] != PER_METER:
            errors.append("Looms OT row %d: %s is paid %s, not Per Meter."
                          % (number, who, employees[who] or "Monthly"))
        if who in seen:
            errors.append("Looms OT row %d: %s already has Looms OT on this %s." % (number, who, where))
        seen.add(who)
    return errors


def day_clashes(rows, overtime, source, shift, others):
    """Messages for a person's day that another submitted report already
    carries. Their day comes from one place (a supervisor's reports or the
    uploaded sheet), and a size is entered once a shift.

    others: [{"report", "source", "shift", "employee", "size"}], the lines
    (and, with size None, the Looms OT) of the other submitted reports of
    the same section and day."""
    errors = []
    mine = [(row.get("employee"), row.get("size")) for row in rows or []] + \
        [(row.get("employee"), None) for row in overtime or []]
    for who, size in mine:
        for other in others or []:
            if other.get("employee") != who:
                continue
            if (other.get("source") or ENTERED) != (source or ENTERED):
                errors.append("%s's day is already on %s, from the %s. A day is taken from one or the other."
                              % (who, other.get("report"), "uploaded sheet" if other.get("source") == UPLOADED
                                 else "daily reports"))
                break
            if other.get("shift") == shift and other.get("size") == size:
                errors.append("%s on %s is already on %s for this shift."
                              % (who, size or "Looms OT", other.get("report")))
                break
    return list(dict.fromkeys(errors))


# ── The month: the Output Pay Run ─────────────────────────────────────
def merge_lines(rows):
    """Daily lines folded into one per person and size, in the order they
    first appear, the days counted and the Work Unit they came to.

    rows: [{"employee", "size", "output", "amount"}]"""
    merged = {}
    for row in rows or []:
        key = (row.get("employee"), row.get("size"))
        seat = merged.setdefault(key, {"employee": key[0], "size": key[1], "output": 0.0, "amount": 0.0,
                                       "shifts": 0})
        seat["output"] = round(seat["output"] + _num(row.get("output")), 3)
        seat["amount"] = round(seat["amount"] + _num(row.get("amount")), 2)
        seat["shifts"] += 1
    for seat in merged.values():
        seat["rate"] = round(seat["amount"] / seat["output"], 4) if seat["output"] else 0.0
    return list(merged.values())


def overtime_by_employee(rows):
    """Each person's Looms OT added up. rows: [{"employee", "amount"}]"""
    totals = {}
    for row in rows or []:
        if row.get("employee"):
            totals[row["employee"]] = round(totals.get(row["employee"], 0.0) + _num(row.get("amount")), 2)
    return totals


def per_employee(lines, overtime=None):
    """What each person is paid for the month, in the order they first
    appear: their work (every day's BASIC) and their Looms OT, together the
    month's TOTAL EARN.

    lines: [{"employee", "output", "amount", "shifts"}];
    overtime: {employee: amount}."""
    totals = {}
    for row in lines or []:
        who = row.get("employee")
        if not who:
            continue
        seat = totals.setdefault(who, _seat(who))
        seat["output"] = round(seat["output"] + _num(row.get("output")), 3)
        seat["output_amount"] = round(seat["output_amount"] + _num(row.get("amount")), 2)
        seat["shifts"] += int(_num(row.get("shifts")) or 0)
    for who, amount in (overtime or {}).items():
        if who:
            totals.setdefault(who, _seat(who))["looms_ot"] = round(_num(amount), 2)
    for seat in totals.values():
        seat["amount"] = round(seat["output_amount"] + seat["looms_ot"], 2)
    return list(totals.values())


def _seat(who):
    return {"employee": who, "output": 0.0, "output_amount": 0.0, "looms_ot": 0.0, "amount": 0.0, "shifts": 0}


# ── The month's sheet, uploaded ───────────────────────────────────────
def employee_key(value):
    """An Employee Id as written on the sheet, for matching: " lpl12261. "
    is LPL12261."""
    return re.sub(r"[\s.]+$", "", str(value or "").strip()).upper()


def take_sheet(lines, ids, categories, sizes, rates, period, names=None):
    """What the month's sheet gives, checked line by line.

    lines: [{"row", "block", "name", "employee_id", "date", "work_unit",
             "work_done", "size", "looms_ot"}] as output_sheet.read gives
             them: "block" counts the names down column A and "name" is
             the one heading the line's rows;
    ids: {employee_key: employee}; categories: {employee: pay category};
    sizes: {size_key: size}, the Per Meter sizes in use;
    rates: {size: [{"work_unit", "valid_from"}]}; period: (from, to);
    names: {employee: employee name}, for the messages.

    Returns {"work": {(employee, date, size): (work_done, work_unit, row)},
    "overtime": {(employee, date): (amount, row)}, "problems": [...],
    "notes": [...]}. A problem leaves a line out and says why; a note
    changes nothing and says what was seen.
    """
    names = names or {}
    start, end = _date(period[0]), _date(period[1])
    work, overtime = {}, {}
    problems, notes = [], []
    said = set()

    def once(kind, message, into):
        if kind not in said:
            said.add(kind)
            into.append(message)

    def called(employee):
        return "%s (%s)" % (names[employee], employee) if names.get(employee) else employee

    heading = {}  # block: the ID its rows start with
    heads = {}  # employee: {block: the block's first row}
    for line in lines or []:
        row, block = line.get("row"), line.get("block")
        raw = line.get("employee_id")
        key = employee_key(raw)
        done, extra = line.get("work_done"), line.get("looms_ot")
        has_work = _positive(done) or _positive(extra)
        if not key:
            if has_work:
                problems.append("Row %s: no Employee Id, so its work is left out." % row)
            continue
        employee = ids.get(key)
        if not employee:
            if has_work:
                once(("unknown", key), "%s is not an employee here: their work is left out (row %s)."
                     % (_text(raw), row), problems)
            continue
        if block is not None:
            first = heading.setdefault(block, key)
            if first == key:
                heads.setdefault(employee, {}).setdefault(block, row)
            else:
                owner = "%s's rows" % _text(line.get("name")) if _text(line.get("name")) else "the rows of %s" % first
                if has_work:
                    problems.append("Row %s: the ID %s is %s's, in %s. Left out: correct the ID and upload again."
                                    % (row, _text(raw), called(employee), owner))
                else:
                    once(("stray", key, block), "Rows of %s carry the ID %s, which is %s's (from row %s)."
                         % (_text(line.get("name")) or first, _text(raw), called(employee), row), notes)
                continue
        if raw is not None and _text(raw) != key:
            once(("spelt", key), "%s is written %r on the sheet, read as %s." % (called(employee), _text(raw), key),
                 notes)
        if categories.get(employee) != PER_METER:
            if has_work:
                once(("category", employee), "%s is paid %s, not Per Meter: their work is left out."
                     % (called(employee), categories.get(employee) or "Monthly"), problems)
            continue
        day = _date(line.get("date"))
        if not day or (start and day < start) or (end and day > end):
            if has_work:
                problems.append("Row %s: %s is not a day of this month (%s to %s)."
                                % (row, _text(line.get("date")) or "a line with no date", _day(start), _day(end)))
            continue
        if extra not in (None, ""):
            if not _is_number(extra) or _num(extra) < 0:
                problems.append("Row %s: Looms OT %r is not an amount." % (row, extra))
            elif _num(extra) > 0:
                if (employee, day) in overtime:
                    problems.append("Row %s: %s's Looms OT for %s is on the sheet twice (rows %s and %s); the "
                                    "second is left out." % (row, called(employee), _day(day),
                                                             overtime[(employee, day)][1], row))
                else:
                    overtime[(employee, day)] = (round(_num(extra), 2), row)
        if done in (None, ""):
            continue
        if not _is_number(done) or _num(done) < 0:
            problems.append("Row %s: Work Done %r is not a number of metres." % (row, done))
            continue
        if _num(done) == 0:
            continue
        size = sizes.get(size_key(line.get("size")))
        if not size:
            if _text(line.get("size")):
                problems.append("Row %s: %s is not a size in use, so its %s metres are left out."
                                % (row, _text(line.get("size")), _figure(done)))
            else:
                problems.append("Row %s: no size, so its %s metres are left out." % (row, _figure(done)))
            continue
        unit = work_unit_on(rates.get(size), day)
        if unit is None:
            problems.append("Row %s: %s has no Work Unit on %s." % (row, size, _day(day)))
            continue
        if _is_number(line.get("work_unit")) and abs(_num(line.get("work_unit")) - unit) > 0.0001:
            once(("rate", size, _num(line.get("work_unit")), unit),
                 "The sheet's Work Unit for %s is %s; the system's on those days is %s, which is what is paid."
                 % (size, _figure(line.get("work_unit")), _figure(unit)), notes)
        if (employee, day, size) in work:
            problems.append("Row %s: %s's %s for %s is on the sheet twice (rows %s and %s); the second is left out."
                            % (row, called(employee), size, _day(day), work[(employee, day, size)][2], row))
            continue
        work[(employee, day, size)] = (_num(done), unit, row)
    for employee, blocks in sorted(heads.items()):
        if len(blocks) > 1:
            notes.append("%s heads more than one set of rows (from rows %s): their work is taken once a day "
                         "and size." % (called(employee), _joined(sorted(blocks.values(), key=_num))))
    return {"work": work, "overtime": overtime, "problems": problems, "notes": notes}


def sheet_days(work, overtime):
    """The sheet's work and Looms OT gathered by day, for one report a day:
    {date: {"lines": [{"employee", "size", "output", "rate"}],
    "overtime": [{"employee", "amount"}]}}, days and rows in order."""
    days = {}
    for (employee, day, size), (done, unit, _row) in sorted(work.items(), key=lambda item: (item[0][1], item[1][2])):
        days.setdefault(day, {"lines": [], "overtime": []})["lines"].append(
            {"employee": employee, "size": size, "output": done, "rate": unit})
    for (employee, day), (amount, _row) in sorted(overtime.items(), key=lambda item: (item[0][1], item[1][1])):
        days.setdefault(day, {"lines": [], "overtime": []})["overtime"].append(
            {"employee": employee, "amount": amount})
    return dict(sorted(days.items()))


def keep_reported_days(taken, work, overtime, shown=None):
    """Takes out of take_sheet's result every person's day that another
    submitted report already has: that report stands. The downloaded sheet
    shows those days, so they come back as they were and need no word; the
    days the sheet changed are returned, to be said.

    work: {(employee, day): {size: metres}} and overtime: {(employee, day):
    amount}, on the other reports; shown: the sizes the sheet has rows for,
    the only ones it can be compared on."""
    reported = set(work) | set(overtime)
    sheet_work, sheet_overtime = {}, {}
    for (employee, day, size), (done, _unit, _row) in list(taken["work"].items()):
        if (employee, day) in reported:
            sheet_work.setdefault((employee, day), {})[size] = done
            del taken["work"][(employee, day, size)]
    for key, (amount, _row) in list(taken["overtime"].items()):
        if key in reported:
            sheet_overtime[key] = amount
            del taken["overtime"][key]

    def figures(sizes):
        return {size: round(_num(done), 3) for size, done in (sizes or {}).items()
                if _num(done) and (shown is None or size in shown)}

    changed = [key for key in set(sheet_work) | set(sheet_overtime)
               if figures(sheet_work.get(key)) != figures(work.get(key))
               or round(_num(sheet_overtime.get(key)), 2) != round(_num(overtime.get(key)), 2)]
    return sorted(changed, key=lambda key: (key[1], str(key[0])))


# ── The hourly casuals ────────────────────────────────────────────────
def standard_hours(hours, standard=STANDARD_HOURS):
    return round(min(max(_num(hours), 0.0), _num(standard) or STANDARD_HOURS), 2)


def overtime_hours(hours, standard=STANDARD_HOURS):
    return round(max(_num(hours) - (_num(standard) or STANDARD_HOURS), 0.0), 2)


def hourly_pay(daily_hours, rate, standard=STANDARD_HOURS):
    """An hourly casual's month: the standard hours of each day at the
    rate. The overtime is counted, to be seen, and not paid here."""
    days = [hours for hours in daily_hours or [] if _num(hours) > 0]
    paid = round(sum(standard_hours(hours, standard) for hours in days), 2)
    return {"days": len(days), "hours": paid,
            "overtime": round(sum(overtime_hours(hours, standard) for hours in days), 2),
            "amount": round(paid * _num(rate), 2)}


def run_errors(section, employees, hourly_rates=None):
    """What stops a month's run being paid, as messages."""
    errors = []
    if section not in SECTIONS:
        return ["A run is for Per Meter, Per Piece or Hourly pay."]
    if not employees:
        errors.append("There is nothing in this run to pay.")
    for row in employees or []:
        if _num(row.get("amount")) < 0:
            errors.append("%s cannot be paid less than nothing." % row.get("employee"))
        if section == HOURLY and _num((hourly_rates or {}).get(row.get("employee"))) <= 0 \
                and _num(row.get("hours")) > 0:
            errors.append("%s has hours but no hourly rate: set one on the employee or the standard "
                          "rate on Output Pay Settings." % row.get("employee"))
    return errors


def _day(value):
    day = _date(value)
    return day.strftime("%d-%b-%Y") if day else ""


def _figure(value):
    return "%g" % _num(value)


def _joined(items):
    items = [str(item) for item in items]
    return " and ".join(items) if len(items) < 3 else "%s and %s" % (", ".join(items[:-1]), items[-1])


def _positive(value):
    return _is_number(value) and _num(value) > 0


def _is_number(value):
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value).replace(",", "").strip())
        return True
    except (TypeError, ValueError):
        return False


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for pattern, width in (("%Y-%m-%d", 10), ("%d-%b-%Y", 11), ("%d/%m/%Y", 10), ("%d-%B-%Y", 20)):
        try:
            return datetime.datetime.strptime(text[:width], pattern).date()
        except ValueError:
            continue
    return None


def _num(value):
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return str(value or "").strip()
