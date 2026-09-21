# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Grades, their salary bands and steps, and the per-diem scale.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_grades.py exercises them without a bench.

THE GRADAR STRUCTURE

Luuka's roles were evaluated onto a Gradar structure: nineteen active
grades, G2 to G20, each a band from a minimum to a maximum and each cut
into ten steps. A step is where a person sits inside their grade, and
moving up one is what an increment means. The steps are evenly spaced
across the band unless somebody sets them otherwise, which is what the
generator here is for: a grade is set up by giving the two ends, not by
typing ten figures.

The band is also what says whether a transaction needs a second signature.
Organisation & System Setup, case 8: above a grade threshold a second
approval level is required, and the grade carries that flag rather than
each workflow carrying a copy of the rule.

THE PER-DIEM SCALE

Travel & Expense, case 2: the allowance on LPL.HR.31 is not typed by the
traveller. It is read from a scale — this grade, to this destination, from
this date — and foreign travel is paid in the destination's own currency,
which for Luuka means USD. A scale with no row for a grade and destination
is not a zero: it is a gap, and the form says so rather than paying
nothing.
"""

GRADE_CODES = tuple("G%d" % number for number in range(2, 21))
STEPS_A_GRADE = 10

# the lines of LPL.HR.31 the scale sets a rate for
LODGING, DAILY, CONVEYANCE = "Lodging", "Daily Allowance", "Conveyance"
SCALE_LINES = (LODGING, DAILY, CONVEYANCE)
SCALE_FIELDS = {LODGING: "lodging", DAILY: "daily_allowance", CONVEYANCE: "conveyance"}

HOME_CURRENCY = "UGX"
FOREIGN_CURRENCY = "USD"


# ── The band and its steps ────────────────────────────────────────────
def steps_between(minimum, maximum, count=STEPS_A_GRADE):
    """The steps of a grade, evenly spaced from the bottom of the band to
    the top, both ends included. Step 1 is the minimum and step 10 the
    maximum, which is what makes an increment a step and a promotion a
    grade."""
    minimum, maximum, count = _num(minimum), _num(maximum), int(count or 0)
    if count < 2 or maximum <= minimum:
        return []
    gap = (maximum - minimum) / (count - 1)
    return [{"step": number + 1, "amount": round(minimum + gap * number, 2)}
            for number in range(count)]


def step_of(amount, steps):
    """Which step a salary sits on, or the one below it where it falls
    between two."""
    amount = _num(amount)
    found = None
    for row in sorted(steps or [], key=lambda row: _num(row.get("amount"))):
        if _num(row.get("amount")) <= amount:
            found = row.get("step")
    return found


def next_step(step, steps):
    """The step an increment moves somebody to. At the top of the band
    there is nowhere to go but the next grade."""
    numbers = sorted(int(row.get("step") or 0) for row in steps or [])
    if not numbers or step is None:
        return None
    above = [number for number in numbers if number > int(step)]
    return above[0] if above else None


def in_band(amount, minimum, maximum):
    amount = _num(amount)
    if not amount:
        return True
    if minimum and amount < _num(minimum):
        return False
    if maximum and amount > _num(maximum):
        return False
    return True


def band_errors(facts):
    errors = []
    code = facts.get("grade_code")
    if code and code not in GRADE_CODES:
        errors.append("Luuka's structure runs G2 to G20. %s is not one of them." % code)
    minimum, maximum = facts.get("minimum"), facts.get("maximum")
    if minimum and maximum and _num(maximum) <= _num(minimum):
        errors.append("The top of the band must be above the bottom of it.")
    steps = facts.get("steps") or []
    if steps:
        numbers = [int(row.get("step") or 0) for row in steps]
        if len(set(numbers)) != len(numbers):
            errors.append("The same step is in the band twice.")
        if any(number < 1 for number in numbers):
            errors.append("A step is numbered from one.")
        amounts = [_num(row.get("amount")) for row in sorted(steps, key=lambda r: int(r.get("step") or 0))]
        if any(later < earlier for earlier, later in zip(amounts, amounts[1:])):
            errors.append("A step must be worth at least as much as the one below it.")
        outside = [row.get("step") for row in steps
                   if not in_band(row.get("amount"), minimum, maximum)]
        if outside and (minimum or maximum):
            errors.append("Step %s falls outside the band."
                          % ", ".join(str(number) for number in outside))
    return errors


def needs_second_approval(grade_flags, grade):
    """Organisation & Setup, case 8: above a configured grade a second
    signature is required. The grade carries the flag."""
    return bool((grade_flags or {}).get(grade))


# ── The per-diem scale ────────────────────────────────────────────────
def currency_for(destination):
    """Foreign travel is paid in the destination's currency; Luuka's own
    is the shilling."""
    if not destination:
        return HOME_CURRENCY
    if destination.get("currency"):
        return destination["currency"]
    return FOREIGN_CURRENCY if destination.get("is_foreign") else HOME_CURRENCY


def rate_row(scale, grade, destination, on=None):
    """The scale row in force for a grade and destination on a day: the
    newest one that had come into effect by then."""
    live = [row for row in scale or []
            if row.get("grade") == grade and row.get("destination") == destination
            and not (on and row.get("effective_from") and str(row["effective_from"]) > str(on))]
    if not live:
        return None
    return sorted(live, key=lambda row: str(row.get("effective_from") or ""))[-1]


def rates_for(row):
    """{line of LPL.HR.31: the rate a day}. A line the scale says nothing
    about is left out rather than set to nothing."""
    if not row:
        return {}
    out = {}
    for line, field in SCALE_FIELDS.items():
        if _num(row.get(field)):
            out[line] = _num(row[field])
    return out


def apply_scale(lines, rates):
    """Fill in what the traveller did not type. A rate already on a line
    is left alone — somebody put it there on purpose, and the scale is a
    default, not a ceiling."""
    filled, changed = [], 0
    for row in lines or []:
        rate = _num(row.get("rate"))
        scaled = rates.get(row.get("expense_type"))
        if not rate and scaled:
            row = dict(row, rate=scaled, from_scale=True)
            changed += 1
        filled.append(row)
    return {"lines": filled, "filled": changed}


def scale_gap(rates, lines):
    """The lines on the form that the scale says nothing about. Said, not
    silently paid at whatever was typed."""
    return [row.get("expense_type") for row in lines or []
            if row.get("expense_type") in SCALE_LINES and not rates.get(row.get("expense_type"))]


def scale_errors(facts):
    errors = []
    if not facts.get("grade"):
        errors.append("A per-diem rate belongs to a grade.")
    if not facts.get("destination"):
        errors.append("And to a destination.")
    if not facts.get("effective_from"):
        errors.append("Say from when the rate applies. A scale without a date cannot be "
                      "superseded.")
    if not any(_num(facts.get(field)) for field in SCALE_FIELDS.values()):
        errors.append("A rate of nothing on every line is not a rate.")
    for field in SCALE_FIELDS.values():
        if _num(facts.get(field)) < 0:
            errors.append("A rate cannot be less than nothing.")
    return errors


def destination_errors(facts):
    errors = []
    if not facts.get("destination_name"):
        errors.append("Give the destination a name.")
    if facts.get("is_foreign") and not facts.get("country"):
        errors.append("Say which country a foreign destination is in.")
    if facts.get("is_foreign") and currency_for(facts) == HOME_CURRENCY:
        errors.append("Foreign travel is not paid in shillings. Name the currency.")
    return errors


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
