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
  Weekly      the other casuals, at Namanve and Kawempe: hours worked x the
              standard hourly rate, "and then adding any overtime". They are
              not on a run: a weekly Payroll Entry pays them (weekly_pay.py).

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
import difflib
import re

PER_METER, PER_PIECE, HOURLY = "Per Meter", "Per Piece", "Hourly"
# everybody on a salary: Luuka's own word for it (5 Nov 2026)
REGULAR = "Regular"
# everybody on a salary: Luuka's own word for it (5 Nov 2026)
REGULAR = "Regular"
OUTPUT_SECTIONS = (PER_METER, PER_PIECE)
UNITS = {PER_METER: "Metres", PER_PIECE: "Pieces"}
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
                          % (number, who, employees[who] or REGULAR, section))
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
                          % (number, who, employees[who] or REGULAR))
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


def earnings(lines, overtime, components, default, overtime_component=None):
    """What each person is paid under each salary component, so that the
    payslip shows the sizes apart as Luuka's own does (PER METER 1 to 6):
    [{"employee", "salary_component", "amount"}], people in the order they
    first appear, each person's components in the order of their lines and
    their Looms OT last. Sizes that share a component are paid as one, and
    a component that comes to nothing is left out.

    lines: [{"employee", "size", "amount"}]; overtime: {employee: Looms OT};
    components: {size: the salary component it is paid under}; default: the
    section's own, for a size that names none; overtime_component: the
    Looms OT's own, else it is paid with the section's."""
    paid, order = {}, []

    def add(who, component, amount):
        if not who or not component:
            return
        key = (who, component)
        if key not in paid:
            paid[key] = 0.0
            order.append(key)
        paid[key] = round(paid[key] + _num(amount), 2)

    for row in lines or []:
        add(row.get("employee"), (components or {}).get(row.get("size")) or default, row.get("amount"))
    for who, amount in (overtime or {}).items():
        add(who, overtime_component or default, amount)
    people = []
    for who, _component in order:
        if who not in people:
            people.append(who)
    return [{"employee": who, "salary_component": component, "amount": paid[(who, component)]}
            for person in people for who, component in order if who == person and paid[(who, component)] > 0]


def component_errors(name, component):
    """Why a size cannot be paid under a salary component. component:
    {"type", "disabled"}, None when the site has none of that name."""
    if not component:
        return ["%s is not a salary component." % name]
    if (component.get("type") or "Earning") != "Earning":
        return ["%s is a deduction. Output is paid under an earning." % name]
    if int(_num(component.get("disabled"))):
        return ["%s is disabled." % name]
    return []


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
    is LPL12261, and so is the "LPL12261_x000D_" Excel leaves of a line
    break typed into the cell."""
    return re.sub(r"[\s.]+$", "", str(value or "").replace("_x000D_", "").strip()).upper()


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
                     % (called(employee), categories.get(employee) or REGULAR), problems)
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


def held_days(taken, holders, own_branch, branches):
    """The person-days on the sheet that other submitted reports hold, with
    the sheet's own figures for them, to be said: keep_reported_days takes
    them out of what the upload counts, and a total that falls short of the
    sheet's with no word was what Luuka saw (19 Oct 2026: 84,712,569 on the
    sheet, 84,215,144 said). Called before keep_reported_days.

    taken: take_sheet's result; holders: {(employee, day): {report}};
    own_branch: the run's plant; branches: {report: its plant}.

    Returns [{"own", "plant", "days", "metres", "amount", "reports"}], the
    run's own plant first. own: a report of the run's own plant holds the
    day (one entered by hand: the run pays it from there); otherwise only
    another plant's do, and this run does not pay it."""
    figures = {}
    for (employee, day, size), (done, unit, _row) in taken["work"].items():
        if (employee, day) in holders:
            metres, amount = figures.get((employee, day), (0.0, 0.0))
            figures[(employee, day)] = (metres + _num(done), amount + line_total(done, unit))
    for (employee, day), (extra, _row) in taken["overtime"].items():
        if (employee, day) in holders:
            metres, amount = figures.get((employee, day), (0.0, 0.0))
            figures[(employee, day)] = (metres, amount + _num(extra))
    groups = {}
    for key, (metres, amount) in figures.items():
        plants = sorted({branches.get(report) or "" for report in holders[key]})
        own = own_branch in plants
        plant = own_branch if own else plants[0]
        group = groups.setdefault((own, plant), {"own": own, "plant": plant, "days": 0, "metres": 0.0,
                                                 "amount": 0.0, "reports": set()})
        group["days"] += 1
        group["metres"] += metres
        group["amount"] += amount
        group["reports"] |= {report for report in holders[key] if (branches.get(report) or "") == plant}
    return [dict(group, metres=round(group["metres"], 3), amount=round(group["amount"], 2),
                 reports=sorted(group["reports"]))
            for _key, group in sorted(groups.items(), key=lambda item: (not item[0][0], item[0][1]))]


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


# ── Luuka's Per Piece workbook (piece_sheet.py) ───────────────────────
def piece_key(name):
    """A name as written on the workbook, for matching: case, spaces, dots
    and the order of its words aside, "Jane  Doe" and "DOE JANE." are
    one name."""
    return " ".join(sorted(re.findall(r"[A-Z0-9]+", str(name or "").upper())))


def piece_pay_day(first, last, joined=None, left=None, status=None):
    """The day a person's week of piece pay is dated, or why it cannot be paid on this run: (day, None) or
    (None, why). Frappe HR takes no Additional Salary dated before someone joined or after they left, nor any for
    one who is Inactive. first: the first day of the days this run pays; last: the week's last day. One who
    left during the week is paid on their last day, which the slip still holds."""
    first, last, joined, left = _date(first), _date(last), _date(joined), _date(left)
    if status == "Inactive":
        return None, "they are Inactive"
    if joined and last and joined > last:
        return None, "they joined on %s, after the week" % _day(joined)
    if left and first and left < first:
        return None, "they left on %s, before the days this run pays" % _day(left)
    return (left if left and last and left < last else last), None


def take_pieces(weeks, people, sizes, rates, period, branch, unread=None):
    """What Luuka's Per Piece workbook gives for a payroll's days, checked row by row.

    weeks: piece_sheet.read's weeks [{"sheet", "start", "end", "prices",
    "rows"}]; people: [{"employee", "employee_name", "employee_number",
    "category", "branch"}], every employee; sizes: the Per Piece categories
    in use; rates: {category: [{"work_unit", "valid_from"}]}; period:
    (from, to); branch: the payroll's plant; unread: the sheets dated by nothing.

    A week is the payroll's when its last day is in it, so each week is
    paid once. A bag column's price names its category: the one whose Work
    Unit that week is that price. A person is found by the Employee Id
    where the sheet has one, else by name, its words in any order; a name
    that is nobody's, or more than one person's, is said and left out, never
    guessed. The ARREARS beside a person are paid with their week (Luuka's
    casual payroll adds them to the gross).

    Returns {"work": {(employee, the week's last day, category): (bags,
    price, where)}, "arrears": {(employee, the week's last day): (amount,
    where)}, "overtime": {}, "weeks": [the weeks taken], "problems",
    "notes"}, as take_sheet does, so the same reports are made of it."""
    start, end = _date(period[0]), _date(period[1])
    work, problems, notes, taken = {}, [], [], []
    by_name, by_id, called, piece_names = {}, {}, {}, {}
    for person in people or []:
        employee = person["employee"]
        called[employee] = person.get("employee_name") or employee
        by_name.setdefault(piece_key(person.get("employee_name")), []).append(person)
        if (person.get("category") or REGULAR) == PER_PIECE:
            piece_names.setdefault(piece_key(person.get("employee_name")), []).append(person)
        for value in (employee, person.get("employee_number")):
            if value:
                by_id.setdefault(employee_key(value), person)

    def who(employee):
        return "%s (%s)" % (called[employee], employee)

    weeks_in = {}
    for week in weeks or []:
        last = _date(week.get("end"))
        if last and start and end and start <= last <= end:
            weeks_in.setdefault((_date(week.get("start")), last), []).append(week)
    if not weeks_in:
        problems.append("No weekly sheet ends between %s and %s: there is nothing to pay."
                        % (_day(start), _day(end)))
    arrears = {}
    for (first, last), copies in sorted(weeks_in.items()):
        if len(copies) > 1:
            problems.append("%s to %s is on %d sheets (%s): none of them is taken. Keep one and upload again."
                            % (_day(first), _day(last), len(copies), _joined("'%s'" % week["sheet"] for week in copies)))
            continue
        week = copies[0]
        sheet = "'%s'" % week["sheet"]
        categories = {}
        for price in week.get("prices") or []:
            fitting = sorted(size for size in sizes or ()
                             if work_unit_on(rates.get(size), last) is not None
                             and abs(work_unit_on(rates.get(size), last) - _num(price)) < 0.005)
            if len(fitting) == 1:
                categories[price] = fitting[0]
            elif fitting:
                problems.append("On %s, %s are all priced %s, so the bags at %s are left out: give each category "
                                "its own Work Unit." % (_day(last), _joined(fitting), _figure(price), _figure(price)))
            else:
                problems.append("No Per Piece category is priced %s on %s, so the bags at %s on %s are left out: "
                                "set it in Sizes and Work Units." % (_figure(price), _day(last), _figure(price), sheet))
        found = {}
        for row in week.get("rows") or []:
            bags = {price: value for price, value in (row.get("bags") or {}).items() if _text(value)}
            owed = _num(row.get("arrears")) if _positive(row.get("arrears")) else 0.0
            # bags that are no number or less than nothing, and arrears less than nothing, are said, never passed over
            odd = [value for value in bags.values() if not _is_number(value) or _num(value) < 0]
            owes_back = _is_number(row.get("arrears")) and _num(row.get("arrears")) < 0
            if not owed and not odd and not owes_back and not any(_positive(value) for value in bags.values()):
                continue
            worth = sum(_num(value) * _num(price) for price, value in bags.items() if _positive(value))
            what = "bags and arrears" if owed and worth else "arrears" if owed else "bags"
            due = _amount(worth + owed)
            if row.get("employee_id"):
                person = by_id.get(employee_key(row["employee_id"]))
                if not person:
                    problems.append("%s, row %s: the Employee Id %s is nobody here, so %s's %s, worth %s, are "
                                    "left out." % (sheet, row["row"], _text(row["employee_id"]),
                                                   row.get("name") or "the row", what, due))
                    continue
            else:
                matches = by_name.get(piece_key(row.get("name")), [])
                if len(matches) > 1:
                    problems.append("%s, row %s: %s is the name of %s, so the %s, worth %s, are left out: add an "
                                    "Employee Id column." % (sheet, row["row"], row.get("name"),
                                                             _joined(who(p["employee"]) for p in matches), what, due))
                    continue
                if not matches:
                    # the nearest Per Piece casual's name is said, never taken: the spelling is put right first
                    near = difflib.get_close_matches(piece_key(row.get("name")), list(piece_names), n=1, cutoff=0.8)
                    problems.append("%s, row %s: no employee is called %s, so the %s, worth %s, are left out: "
                                    "correct the name on the sheet or on the employee.%s"
                                    % (sheet, row["row"], row.get("name"), what, due,
                                       " Closest: %s." % _joined(who(p["employee"]) for p in piece_names[near[0]])
                                       if near else ""))
                    continue
                person = matches[0]
            found.setdefault(person["employee"], []).append((row, bags, worth, person, owed))
        for employee, rows in found.items():
            if len(rows) > 1:
                problems.append("%s is on %s twice (rows %s), so neither is taken: keep one row."
                                % (who(employee), sheet, _joined(str(row[0]["row"]) for row in rows)))
                continue
            row, bags, worth, person, owed = rows[0]
            if (person.get("category") or REGULAR) != PER_PIECE:
                problems.append("%s is paid %s, not Per Piece, so their bags on %s are left out."
                                % (who(employee), person.get("category") or REGULAR, sheet))
                continue
            if branch and person.get("branch") != branch:
                problems.append("%s works at %s, not %s, so their bags on %s are left out."
                                % (who(employee), person.get("branch") or "no plant", branch, sheet))
                continue
            if _is_number(row.get("arrears")) and _num(row.get("arrears")) < 0:
                problems.append("%s, row %s: arrears of %s are less than nothing, so they are left out."
                                % (sheet, row["row"], _amount(row["arrears"])))
            if owed:
                arrears[(employee, last)] = (round(owed, 2), "%s, row %s" % (sheet, row["row"]))
            for price, value in bags.items():
                if not _is_number(value) or _num(value) < 0:
                    problems.append("%s, row %s: %r bags at %s is not a number of bags, so it is left out."
                                    % (sheet, row["row"], value, _figure(price)))
                    continue
                if _num(value) and price in categories:
                    work[(employee, last, categories[price])] = (round(_num(value), 3), _num(price),
                                                                 "%s, row %s" % (sheet, row["row"]))
            if row.get("total") is not None and abs(_num(row["total"]) - worth) > 0.5:
                notes.append("%s, row %s: %s's total is %s, but the bags at their prices come to %s, which is "
                             "what is paid." % (sheet, row["row"], row.get("name") or called[employee],
                                                _amount(row["total"]), _amount(worth)))
        taken.append(week)
    if taken:
        notes.insert(0, "Weeks taken: %s." % _joined("%s to %s" % (_day(week["start"]), _day(week["end"]))
                                                      for week in taken))
    if arrears:
        owed_by = len({employee for employee, _week in arrears})
        notes.append("Arrears paid with their week: %d %s, %s in all."
                     % (owed_by, "person" if owed_by == 1 else "people",
                        _amount(sum(amount for amount, _where in arrears.values()))))
    if unread:
        notes.append("Sheets with no week in their name or title, not read: %s." % _joined(unread))
    return {"work": work, "arrears": arrears, "overtime": {}, "weeks": taken, "problems": problems, "notes": notes}


def _amount(value):
    value = round(_num(value), 2)
    return "{:,.0f}".format(value) if value == int(value) else "{:,.2f}".format(value)


def run_errors(section, employees):
    """What stops a month's run being paid, as messages."""
    errors = []
    if section not in OUTPUT_SECTIONS:
        return ["A run is for Per Meter or Per Piece pay."]
    if not employees:
        errors.append("There is nothing in this run to pay.")
    for row in employees or []:
        if _num(row.get("amount")) < 0:
            errors.append("%s cannot be paid less than nothing." % row.get("employee"))
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
