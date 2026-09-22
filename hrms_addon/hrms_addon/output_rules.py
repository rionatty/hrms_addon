# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Output pay: Per Meter, Per Piece, and the hourly casuals.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_output_pay.py exercises them without a bench.

WHERE THIS COMES FROM

The minutes of 16 and 20 July 2026 (Human Resource, Reward and
Compensation), §4.6 Gross Salary Processing:

  Per Meter   the looms. Output-based pay "depends on the machine
              category, the rate of the machine, and the pieces or metres
              produced in a shift". Two machines run faster and share a
              rate; the other two run slower and pay more; and the rate
              changes with the width of the material — 45 cm pays less
              than 74 cm on the same machine. The shift supervisor fills
              in the Daily Loom Production Report; the Per Meter Template
              multiplies the machine's rate by the metres each person made
              on each shift, sums the month — 26th to 25th — and adds it to
              the operator's basic salary.
  Per Piece   the casuals at Matugga. The same thing in pieces: three
              piece categories, each with its own price, pieces x rate a
              day, summed for the month. That sum is their gross.
  Hourly      the other casuals, at Namanve and Kawempe: hours worked x the
              standard hourly rate, "and then adding any overtime".

A target output a day is set per employee and per machine. The minutes do
not say that missing it changes the pay, so nothing here does: the target
is recorded and the achievement reported, and that is all.

EACH MACHINE HAS ITS OWN RATE

A machine carries a rate for every width it runs (Per Meter) or every
piece category it makes (Per Piece), each from a date, so a rate that
changes in March does not reprice February. Two machines that share a
rate simply carry the same figure.

THE OVERTIME IS NOT COUNTED HERE

An hourly casual's overtime is priced by the overtime module — the
Overtime Slip Frappe HR draws for each cycle — so only the standard hours
of each day are paid here. Counting all twelve would pay two of them
twice.
"""

import datetime

PER_METER, PER_PIECE, HOURLY = "Per Meter", "Per Piece", "Hourly"
OUTPUT_SECTIONS = (PER_METER, PER_PIECE)
SECTIONS = (PER_METER, PER_PIECE, HOURLY)
UNITS = {PER_METER: "Metres", PER_PIECE: "Pieces", HOURLY: "Hours"}
SHIFTS = ("Day", "Night")

# a shift is twelve hours of which two are overtime (attendance_rules)
STANDARD_HOURS = 10.0


# ── The machine's rates ───────────────────────────────────────────────
def rate_errors(section, rows):
    """What is wrong with a machine's rates, as messages.

    rows: [{"width_cm", "piece_category", "rate", "valid_from"}]
    """
    errors = []
    if section not in OUTPUT_SECTIONS:
        errors.append("A machine is in the Per Meter or the Per Piece section.")
        return errors
    if not rows:
        errors.append("Give the machine at least one rate, or nothing it makes can be paid.")
    seen = set()
    for number, row in enumerate(rows or [], 1):
        width = _num(row.get("width_cm"))
        category = _text(row.get("piece_category"))
        if section == PER_METER:
            if width <= 0:
                errors.append("Rate row %d: a Per Meter rate is for a width of material, in cm." % number)
            if category:
                errors.append("Rate row %d: a piece category belongs to a Per Piece machine." % number)
        else:
            if not category:
                errors.append("Rate row %d: a Per Piece rate is for a piece category." % number)
            if width:
                errors.append("Rate row %d: a width belongs to a Per Meter machine." % number)
        if _num(row.get("rate")) <= 0:
            errors.append("Rate row %d: the rate is more than nothing." % number)
        if not _date(row.get("valid_from")):
            errors.append("Rate row %d: say the day the rate starts." % number)
        key = (width if section == PER_METER else category.lower(), _date(row.get("valid_from")))
        if key in seen:
            errors.append("Rate row %d: the same %s from the same day is already there."
                          % (number, "width" if section == PER_METER else "category"))
        seen.add(key)
    return errors


def rate_for(rows, on, width=None, category=None, section=PER_METER):
    """The rate row that applies to a day's output, or None.

    The machine's row for that width (Per Meter) or piece category (Per
    Piece), with the latest start on or before the day. None is refused
    by the report rather than paid at nought: output with no rate is a
    rate nobody has set, not work that earned nothing.
    """
    on = _date(on)
    fitting = []
    for row in rows or []:
        start = _date(row.get("valid_from"))
        if not start or (on and start > on):
            continue
        if section == PER_METER:
            if _num(row.get("width_cm")) != _num(width):
                continue
        elif _text(row.get("piece_category")).lower() != _text(category).lower():
            continue
        fitting.append((start, row))
    if not fitting:
        return None
    return sorted(fitting, key=lambda pair: pair[0])[-1][1]


# ── One shift's line ──────────────────────────────────────────────────
def line(output, rate, target=None):
    """What a shift's output earned, and how it measured against target."""
    output, rate = _num(output), _num(rate)
    target = _num(target)
    return {"amount": round(output * rate, 2),
            "achieved": round(output / target * 100.0, 1) if target > 0 else None}


def report_errors(section, rows, employees=None, machines=None):
    """What is wrong with a Daily Production Report, as messages.

    rows: [{"employee", "machine", "width_cm", "piece_category", "output",
           "rate"}]
    employees: {employee: pay category}; machines: {machine: section}
    """
    errors = []
    if section not in OUTPUT_SECTIONS:
        return ["A production report is for the Per Meter or the Per Piece section."]
    employees, machines = employees or {}, machines or {}
    seen = set()
    for number, row in enumerate(rows or [], 1):
        who, machine = row.get("employee"), row.get("machine")
        if not who or not machine:
            errors.append("Row %d: say who worked which machine." % number)
            continue
        if _num(row.get("output")) < 0:
            errors.append("Row %d: output cannot be less than nothing." % number)
        if machines.get(machine) and machines[machine] != section:
            errors.append("Row %d: %s is a %s machine, not %s." % (number, machine, machines[machine], section))
        if who in employees and employees[who] != section:
            errors.append("Row %d: %s is paid %s, so their output does not belong on a %s report."
                          % (number, who, employees[who] or "Monthly", section))
        if section == PER_METER and _num(row.get("width_cm")) <= 0:
            errors.append("Row %d: say the width of the material, which decides the rate." % number)
        if section == PER_PIECE and not _text(row.get("piece_category")):
            errors.append("Row %d: say the piece category, which decides the price." % number)
        if row.get("rate") is None:
            errors.append("Row %d: %s has no rate for %s on this day. Set one on the machine."
                          % (number, machine, _what(section, row)))
        key = (who, machine, _num(row.get("width_cm")), _text(row.get("piece_category")).lower())
        if key in seen:
            errors.append("Row %d: %s on %s is already on this report." % (number, who, machine))
        seen.add(key)
    return errors


# ── The month ─────────────────────────────────────────────────────────
def per_employee(lines):
    """The month's lines added up for each person, in the order they
    first appear. lines: [{"employee", "output", "amount", "shifts"}]"""
    totals = {}
    for row in lines or []:
        who = row.get("employee")
        if not who:
            continue
        seat = totals.setdefault(who, {"employee": who, "output": 0.0, "amount": 0.0, "shifts": 0})
        seat["output"] = round(seat["output"] + _num(row.get("output")), 3)
        seat["amount"] = round(seat["amount"] + _num(row.get("amount")), 2)
        seat["shifts"] += int(_num(row.get("shifts")) or 0)
    return list(totals.values())


def merge_lines(rows):
    """Daily lines folded into one per person, machine and width or piece
    category — the Per Meter Template's own shape — with the shifts counted
    and the targets added up so the month's achievement can be read."""
    merged = {}
    for row in rows or []:
        key = (row.get("employee"), row.get("machine"), _num(row.get("width_cm")) or None,
               _text(row.get("piece_category")) or None)
        seat = merged.setdefault(key, {
            "employee": key[0], "machine": key[1], "width_cm": key[2], "piece_category": key[3],
            "output": 0.0, "amount": 0.0, "target": 0.0, "shifts": 0})
        seat["output"] = round(seat["output"] + _num(row.get("output")), 3)
        seat["amount"] = round(seat["amount"] + _num(row.get("amount")), 2)
        seat["target"] = round(seat["target"] + _num(row.get("target")), 3)
        seat["shifts"] += 1
    for seat in merged.values():
        seat["achieved"] = line(seat["output"], 0, seat["target"])["achieved"]
    return list(merged.values())


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


def _what(section, row):
    if section == PER_METER:
        return "%g cm" % _num(row.get("width_cm"))
    return "the %s category" % (_text(row.get("piece_category")) or "?")


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


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return str(value or "").strip()
