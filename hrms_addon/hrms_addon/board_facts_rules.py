# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack's facts: what a month is made of, row by row. No Frappe
import (scripts/verify_board_facts.py); board_facts.py reads the site, writes
the rows and asks them back with GROUP BY.

The facts replace the 33 columns a plant used to carry on HR Snapshot Plant.
Each is a table of rows, so any figure can be cut by plant, department,
section, gender, age, tenure or population, and a month's rows stay as they
were built once the month is locked.

  HR Employee Month   one row per employee per month, frozen as at the
                      month's end: where they work, what they are paid as,
                      whether they opened and closed the month, joined, left,
                      moved plant or were converted, and the month's pay,
                      overtime, absence and training. An imported row (the
                      months before the system) has no employee and counts
                      `heads` people at once: every count is a SUM.
  HR Movement         each hire, exit, transfer and conversion, effective on
                      its day, with where from and where to
  HR Pay Fact         the month's earnings by plant, section, population and
                      salary component: one GROUP BY over the slips
  HR Safety Fact      the month's incidents by plant, department, severity,
                      hazard and on or off site, with the days lost

Definitions the board reads, written on the pack itself:
  population      Casual when paid by the week (pay category Weekly or Per
                  Piece), Expatriate when foreign, else Permanent. They never
                  overlap, so pay by population adds up to the wage bill.
  head count      still employed when the day is over: joined on or before
                  it, and relieved after it, if at all
  transfer        a move between plants, from an Employee Transfer or from
                  the employee's history of changes to their plant
  conversion      a change of population, casual to permanent the usual one
  reconciliation  opening + hires - exits + transfers in - transfers out =
                  closing, by plant; and beside it the payroll's head count
"""

import calendar
import datetime
import json

PERMANENT, CASUAL, EXPATRIATE = "Permanent", "Casual", "Expatriate"
POPULATIONS = (PERMANENT, CASUAL, EXPATRIATE)
CASUAL_CATEGORIES = ("Weekly", "Per Piece")
# the row of a table for the people and the pay with no plant on record, so the plants add up to the total
NO_PLANT = "No Plant"
HIRE, EXIT, TRANSFER, CONVERSION = "Hire", "Exit", "Transfer", "Conversion"
MOVEMENTS = (HIRE, EXIT, TRANSFER, CONVERSION)
# a hire's reason, from the requisition it was made against (Job Requisition.custom_reason_type)
ADDITION, REPLACEMENT, UNCLASSIFIED = "Addition", "Replacement", "Unclassified"
HIRE_REASONS = (ADDITION, REPLACEMENT, UNCLASSIFIED)
ADDITION_REASONS = ("New Addition", "New Position")
REPLACEMENT_REASONS = ("Replacement",)
VOLUNTARY, INVOLUNTARY = "Voluntary", "Involuntary"
AGE_BANDS = ("Under 25", "25-34", "35-44", "45-54", "55 and Over", "Unknown")
TENURE_BANDS = ("Under 1 Year", "1-2 Years", "3-5 Years", "6-10 Years", "Over 10 Years")
SYSTEM, IMPORTED = "System", "Imported"
SOURCES = (SYSTEM, IMPORTED)
# a month's build, as its HR Monthly Snapshot shows it
NOT_BUILT, QUEUED, BUILDING, BUILT, FAILED = "Not Built", "Queued", "Building", "Built", "Failed"
STATUSES = (NOT_BUILT, QUEUED, BUILDING, BUILT, FAILED, IMPORTED)
# what a month's figures may be read from
READY = (BUILT, IMPORTED)
# safety: a near miss is reported, never counted as an incident
NEAR_MISS, FIRST_AID, MEDICAL, LOST_TIME, FATALITY = "Near Miss", "First Aid", "Medical Treatment", "Lost Time", "Fatality"
SEVERITIES = (NEAR_MISS, FIRST_AID, MEDICAL, LOST_TIME, FATALITY)
INCIDENT_SEVERITIES = tuple(severity for severity in SEVERITIES if severity != NEAR_MISS)
# LTIFR: lost-time injuries (a fatality is one) per million hours worked
LTIFR_HOURS = 1000000.0
LOST_TIME_SEVERITIES = (LOST_TIME, FATALITY)
# attendance as worked days
WORKED, HALF_DAY, ABSENT = ("Present", "Work From Home"), "Half Day", "Absent"
# what a pay fact's group is when no component group claims the pay (the slip's gross over its earnings)
OTHER = "Other"
# how the fact rows are written: a chunk, then a commit, so a big month never holds one long transaction
CHUNK = 500
# the counts of an HR Employee Month row; each a whole number of people, so every figure is a SUM
COUNTS = ("heads", "opening", "closing", "hired", "exited", "transferred", "converted", "paid")
MEASURES = ("gross_pay", "ot_pay", "ot_hours", "hours_worked", "days_worked", "days_absent", "training_hours",
            "attendance_days", "clock_days")
# the cuts the facts can be read by: what a report may group HR Employee Month by
CUTS = {"branch": "Plant", "department": "Department", "work_section": "Section", "designation": "Designation",
        "grade": "Grade", "population": "Population", "gender": "Gender", "age_band": "Age Band",
        "tenure_band": "Tenure Band", "employment_type": "Employment Type"}


# ── Who the person is ─────────────────────────────────────────────────
def population(pay_category, foreign=False):
    """Expatriate when foreign, Casual when paid by the week, else Permanent.
    Exactly one, so pay by population adds up to the wage bill."""
    if _int(foreign):
        return EXPATRIATE
    if (pay_category or "") in CASUAL_CATEGORIES:
        return CASUAL
    return PERMANENT


def is_permanent(population_name):
    """Head count's split: an expatriate is on the permanent staff."""
    return population_name != CASUAL


def age_band(born, on):
    born, on = _date(born), _date(on)
    if not born or not on or born > on:
        return AGE_BANDS[-1]
    years = whole_years(born, on)
    for limit, band in ((25, "Under 25"), (35, "25-34"), (45, "35-44"), (55, "45-54")):
        if years < limit:
            return band
    return "55 and Over"


def whole_years(start, end):
    """Completed years from start to end."""
    start, end = _date(start), _date(end)
    if not start or not end or end < start:
        return 0
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return max(years, 0)


def tenure_years(joined, on):
    """Years of service, to one decimal place."""
    joined, on = _date(joined), _date(on)
    if not joined or not on or on < joined:
        return 0.0
    return round((on - joined).days / 365.25, 1)


def tenure_band(joined, on):
    years = whole_years(joined, on)
    if years < 1:
        return "Under 1 Year"
    if years < 3:
        return "1-2 Years"
    if years < 6:
        return "3-5 Years"
    if years < 11:
        return "6-10 Years"
    return "Over 10 Years"


def hire_class(requisition_reason):
    """A new post or a new addition adds capacity; a replacement backfills a
    leaver; a hire with no requisition is not classified at all."""
    if requisition_reason in ADDITION_REASONS:
        return ADDITION
    if requisition_reason in REPLACEMENT_REASONS:
        return REPLACEMENT
    return UNCLASSIFIED


def plant(value):
    return value or NO_PLANT


# ── Months and quarters ───────────────────────────────────────────────
def month_start(day):
    day = _date(day)
    return day.replace(day=1) if day else None


def month_end(day):
    day = _date(day)
    return day.replace(day=calendar.monthrange(day.year, day.month)[1]) if day else None


def add_months(day, count):
    day = month_start(day)
    total = day.month - 1 + int(count)
    return datetime.date(day.year + total // 12, total % 12 + 1, 1)


def months_between(first, last):
    """Each month's first day from first's month to last's, oldest first."""
    first, last = month_start(first), month_start(last)
    out = []
    while first and last and first <= last:
        out.append(first)
        first = add_months(first, 1)
    return out


def as_at(month, today):
    """The day a month is read as at: its last day, or today while it runs."""
    last, today = month_end(month), _date(today)
    return min(last, today) if today else last


def employed_after(joined, relieved, day):
    """Still employed when the day is over: joined by it, relieved after it.
    A month's opening is this on the day before it, its closing this on its
    last day: one whose last day was the 30th is the month's exit, not the
    next month's opening, so opening + hires - exits = closing exactly."""
    joined, relieved, day = _date(joined), _date(relieved), _date(day)
    return bool(joined) and joined <= day and (not relieved or relieved > day)


# ── Movements: transfers and conversions ──────────────────────────────
def transfer_moves(transfers):
    """Moves from submitted Employee Transfers: [{"name", "employee",
    "transfer_date", "details": [{"fieldname", "current", "new"}]}]. A
    change of plant is a transfer; a change of pay category that changes the
    population is a conversion."""
    out = []
    for transfer in transfers or ():
        for detail in transfer.get("details") or ():
            move = _move(detail.get("fieldname"), detail.get("current"), detail.get("new"), transfer.get("employee"),
                         transfer.get("transfer_date"), "Employee Transfer", transfer.get("name"))
            if move:
                out.append(move)
    return out


def version_moves(versions):
    """Moves from the Employee's history of changes: [{"name", "docname",
    "creation", "data"}], data as Frappe writes it ({"changed": [[field,
    old, new], ...]}). Effective on the day the change was saved."""
    out = []
    for version in versions or ():
        try:
            data = json.loads(version.get("data") or "{}") if isinstance(version.get("data"), str) \
                else (version.get("data") or {})
        except ValueError:
            continue
        for change in data.get("changed") or ():
            if not isinstance(change, (list, tuple)) or len(change) < 3:
                continue
            move = _move(change[0], change[1], change[2], version.get("docname"), version.get("creation"), "Version",
                         version.get("name"))
            if move:
                out.append(move)
    return out


def _move(fieldname, old, new, employee, effective, source_doctype, source_name):
    old, new = "" if old is None else str(old), "" if new is None else str(new)
    day = _date(effective)
    if not employee or not day or old == new:
        return None
    if fieldname == "branch":
        return {"movement_type": TRANSFER, "employee": employee, "effective_date": day, "from_branch": old or None,
                "to_branch": new or None, "source_doctype": source_doctype, "source_name": source_name}
    if fieldname == "custom_pay_category":
        if population(old) == population(new):
            return None
        return {"movement_type": CONVERSION, "employee": employee, "effective_date": day, "from_category": old or None,
                "to_category": new or None, "from_population": population(old), "to_population": population(new),
                "source_doctype": source_doctype, "source_name": source_name}
    return None


def merge_moves(from_transfers, from_versions, window_days=31):
    """One list, oldest first. A plant change saved by an Employee Transfer is
    also in the employee's history: the transfer's own row is kept (its date
    is the transfer's), the history's dropped when it says the same move
    within window_days of it."""
    kept = list(from_transfers or ())
    for move in from_versions or ():
        twin = next((other for other in from_transfers or ()
                     if other["employee"] == move["employee"] and other["movement_type"] == move["movement_type"]
                     and (other.get("to_branch"), other.get("to_category")) == (move.get("to_branch"),
                                                                                 move.get("to_category"))
                     and abs((other["effective_date"] - move["effective_date"]).days) <= window_days), None)
        if not twin:
            kept.append(move)
    return sorted(kept, key=lambda move: (move["effective_date"], move["employee"], move["movement_type"]))


def attribute_at(current, moves, day, kind):
    """What the employee's plant (kind "branch") or pay category (kind
    "category") was when the day was over: the "from" of the earliest move
    after it, else what it is now. moves: this employee's, any order."""
    day = _date(day)
    field_from = "from_branch" if kind == "branch" else "from_category"
    wanted = TRANSFER if kind == "branch" else CONVERSION
    later = sorted((move for move in moves or () if move["movement_type"] == wanted and move["effective_date"] > day),
                   key=lambda move: move["effective_date"])
    return later[0].get(field_from) if later else current


# ── A month's rows ────────────────────────────────────────────────────
def employee_month(person, first, day, moves=None, measures=None, separation=None, hire=None):
    """One employee's HR Employee Month row, or None when they were not with
    the company in the month (up to the day it is read as at).

    person: {"name", "employee_name", "branch", "department", "work_section",
    "designation", "grade", "employment_type", "gender", "date_of_birth",
    "date_of_joining", "relieving_date", "pay_category", "foreign"}, as they
    are now; moves: their transfers and conversions after the month began;
    measures: the month's pay, hours, absence and training; separation:
    {"reason", "exit_type", "regrettable"}; hire: {"reason", "job_requisition"}.
    """
    first, day = _date(first), _date(day)
    joined, relieved = _date(person.get("date_of_joining")), _date(person.get("relieving_date"))
    opening_day = first - datetime.timedelta(days=1)
    opening = employed_after(joined, relieved, opening_day)
    closing = employed_after(joined, relieved, day)
    hired = bool(joined and first <= joined <= day)
    exited = bool(relieved and first <= relieved <= day)
    if not (opening or closing or hired or exited):
        return None
    moves = moves or []
    # as the month ended: for one who left, as they left
    at = min(day, relieved) if exited else day
    branch = attribute_at(person.get("branch"), moves, at, "branch")
    category = attribute_at(person.get("pay_category"), moves, at, "category")
    kind = population(category, person.get("foreign"))
    opening_branch = attribute_at(person.get("branch"), moves, opening_day, "branch") if opening else branch
    opening_kind = population(attribute_at(person.get("pay_category"), moves, opening_day, "category"),
                              person.get("foreign")) if opening else kind
    measures = measures or {}
    separation = separation or {}
    hire = hire or {}
    row = {
        "employee": person.get("name"), "employee_name": person.get("employee_name"),
        "branch": branch or None, "department": person.get("department"), "work_section": person.get("work_section"),
        "designation": person.get("designation"), "grade": person.get("grade"),
        "employment_type": person.get("employment_type"), "pay_category": category, "population": kind,
        "gender": person.get("gender"), "age_band": age_band(person.get("date_of_birth"), at),
        "tenure_band": tenure_band(joined, at), "is_foreign": 1 if _int(person.get("foreign")) else 0,
        "opening_branch": opening_branch or None, "opening_population": opening_kind,
        "heads": 1, "opening": int(opening), "closing": int(closing), "hired": int(hired), "exited": int(exited),
        "transferred": int(bool(opening and (opening_branch or "") != (branch or ""))),
        "converted": int(bool(opening and opening_kind != kind)),
        "hire_reason": hire_class(hire.get("reason")) if hired else None,
        "job_requisition": hire.get("job_requisition") if hired else None,
        "exit_reason": separation.get("reason") if exited else None,
        "exit_type": separation.get("exit_type") if exited else None,
        "regrettable": 1 if exited and _int(separation.get("regrettable")) else 0,
        "paid": 1 if _num(measures.get("gross_pay")) or _int(measures.get("paid")) else 0,
    }
    for field in MEASURES:
        row[field] = round(_num(measures.get(field)), 2)
    return row


def movement_rows(person, first, day, moves=None, separation=None, hire=None):
    """The person's HR Movement rows effective in the month (up to day): the
    hire, the exit, and each transfer and conversion, where it counts."""
    first, day = _date(first), _date(day)
    joined, relieved = _date(person.get("date_of_joining")), _date(person.get("relieving_date"))
    separation, hire = separation or {}, hire or {}
    out = []
    base = {"employee": person.get("name"), "employee_name": person.get("employee_name"),
            "department": person.get("department"), "designation": person.get("designation"),
            "work_section": person.get("work_section"), "heads": 1}
    if joined and first <= joined <= day:
        branch = attribute_at(person.get("branch"), moves, joined, "branch")
        category = attribute_at(person.get("pay_category"), moves, joined, "category")
        out.append(dict(base, movement_type=HIRE, effective_date=joined, branch=branch, to_branch=branch,
                        to_category=category, population=population(category, person.get("foreign")),
                        to_population=population(category, person.get("foreign")),
                        hire_reason=hire_class(hire.get("reason")), job_requisition=hire.get("job_requisition"),
                        job_applicant=hire.get("job_applicant"), tenure_years=0.0, tenure_band=TENURE_BANDS[0]))
    for move in sorted(moves or (), key=lambda move: move["effective_date"]):
        if not first <= move["effective_date"] <= day:
            continue
        if move["movement_type"] == TRANSFER:
            category = attribute_at(person.get("pay_category"), moves, move["effective_date"], "category")
            out.append(dict(base, movement_type=TRANSFER, effective_date=move["effective_date"],
                            branch=move.get("to_branch"), from_branch=move.get("from_branch"),
                            to_branch=move.get("to_branch"), population=population(category, person.get("foreign")),
                            source_doctype=move.get("source_doctype"), source_name=move.get("source_name"),
                            tenure_years=tenure_years(joined, move["effective_date"]),
                            tenure_band=tenure_band(joined, move["effective_date"])))
        elif move["movement_type"] == CONVERSION:
            branch = attribute_at(person.get("branch"), moves, move["effective_date"], "branch")
            out.append(dict(base, movement_type=CONVERSION, effective_date=move["effective_date"], branch=branch,
                            from_category=move.get("from_category"), to_category=move.get("to_category"),
                            from_population=population(move.get("from_category"), person.get("foreign")),
                            to_population=population(move.get("to_category"), person.get("foreign")),
                            population=population(move.get("to_category"), person.get("foreign")),
                            source_doctype=move.get("source_doctype"), source_name=move.get("source_name"),
                            tenure_years=tenure_years(joined, move["effective_date"]),
                            tenure_band=tenure_band(joined, move["effective_date"])))
    if relieved and first <= relieved <= day:
        branch = attribute_at(person.get("branch"), moves, relieved, "branch")
        category = attribute_at(person.get("pay_category"), moves, relieved, "category")
        out.append(dict(base, movement_type=EXIT, effective_date=relieved, branch=branch, from_branch=branch,
                        from_category=category, population=population(category, person.get("foreign")),
                        from_population=population(category, person.get("foreign")),
                        exit_reason=separation.get("reason"), exit_type=separation.get("exit_type"),
                        regrettable=1 if _int(separation.get("regrettable")) else 0,
                        source_doctype="Employee Separation" if separation.get("name") else "Employee",
                        source_name=separation.get("name") or person.get("name"),
                        tenure_years=tenure_years(joined, relieved), tenure_band=tenure_band(joined, relieved)))
    for row in out:
        row.setdefault("source_doctype", "Employee")
        row.setdefault("source_name", person.get("name"))
    return out


def attendance_measures(row, hours_per_day):
    """An employee's month of attendance, from the GROUP BY: hours worked
    where the clock recorded them, else the day's standard hours."""
    hours = _num(row.get("hours")) + _num(row.get("unclocked")) * _num(hours_per_day)
    return {"hours_worked": round(hours, 2), "days_worked": round(_num(row.get("worked")), 2),
            "days_absent": round(_num(row.get("absent")), 2), "ot_hours": round(_num(row.get("ot_hours")), 2),
            "attendance_days": round(_num(row.get("days")), 2), "clock_days": round(_num(row.get("clocked")), 2)}


def pay_rows(details, grosses, groups):
    """The month's HR Pay Fact rows. details: the GROUP BY of earnings
    [{"branch", "work_section", "population", "salary_component", "amount",
    "heads"}]; grosses: the GROUP BY of the slips [{"branch", "work_section",
    "population", "gross", "heads"}]; groups: {component: group}. What the
    earnings do not reach of the gross goes to Other, with no component, so
    the rows add up to the wage bill exactly. The SQL may give one plant,
    section and population in several groups (by pay category, before the
    population is known): they are one here, before anything is taken away."""
    lines, grossed, counted = {}, {}, {}
    for line in details or ():
        key = (line.get("branch") or None, line.get("work_section") or None, line.get("population") or PERMANENT)
        found = lines.setdefault(key + (line.get("salary_component"),), [0.0, 0])
        found[0] += _num(line.get("amount"))
        found[1] += int(_num(line.get("heads")))
        counted[key] = counted.get(key, 0.0) + _num(line.get("amount"))
    for line in grosses or ():
        key = (line.get("branch") or None, line.get("work_section") or None, line.get("population") or PERMANENT)
        found = grossed.setdefault(key, [0.0, 0])
        found[0] += _num(line.get("gross"))
        found[1] += int(_num(line.get("heads")))
    rows = []
    for (branch, section, population, component), (amount, heads) in lines.items():
        if round(amount, 2):
            rows.append({"branch": branch, "work_section": section, "population": population,
                         "component_group": groups.get(component) or OTHER, "salary_component": component,
                         "amount": round(amount, 2), "heads": heads})
    for (branch, section, population), (gross, heads) in grossed.items():
        rest = round(gross - counted.get((branch, section, population), 0.0), 2)
        if abs(rest) >= 0.01:
            rows.append({"branch": branch, "work_section": section, "population": population, "component_group": OTHER,
                         "salary_component": None, "amount": rest, "heads": heads})
    return rows


def standard_hours(heads, hours_per_day, days_per_month):
    """The hours a month's people work at the standard day and month: what
    LTIFR is read over where the clock gave none."""
    return round(_num(heads) * _num(hours_per_day) * _num(days_per_month), 2)


def days_lost(sick_days, rest_days):
    """An incident's days lost: the longer of the sick days recorded on it
    and the rest its medical reports gave."""
    return max(_num(sick_days), _num(rest_days))


def ltifr(lost_time, hours):
    """Lost-time injuries per million hours worked; None with no hours."""
    return round(_num(lost_time) * LTIFR_HOURS / _num(hours), 2) if _num(hours) else None


# ── The reconciliation ────────────────────────────────────────────────
def reconciliation(openings, closings):
    """By plant, then the total: opening + hires - exits + transfers in -
    transfers out = expected; against the closing head count, and against
    the heads the payroll paid. openings: {plant: {"opening",
    "transferred"}} grouped by the plant the month opened in; closings:
    {plant: {"closing", "hired", "exited", "transferred", "paid"}} grouped by
    the plant it closed in."""
    plants = sorted(set(openings or {}) | set(closings or {}), key=lambda name: (name == NO_PLANT, name))
    rows = []
    for name in plants:
        start, end = (openings or {}).get(name) or {}, (closings or {}).get(name) or {}
        row = {"branch": name, "opening": _int(start.get("opening")), "hires": _int(end.get("hired")),
               "exits": _int(end.get("exited")), "transfers_in": _int(end.get("transferred")),
               "transfers_out": _int(start.get("transferred")), "closing": _int(end.get("closing")),
               "payroll_heads": _int(end.get("paid"))}
        rows.append(_balanced(row))
    total = {"branch": None}
    for field in ("opening", "hires", "exits", "transfers_in", "transfers_out", "closing", "payroll_heads"):
        total[field] = sum(row[field] for row in rows)
    return rows, _balanced(total)


def _balanced(row):
    row["expected"] = row["opening"] + row["hires"] - row["exits"] + row["transfers_in"] - row["transfers_out"]
    row["variance"] = row["closing"] - row["expected"]
    row["payroll_variance"] = row["closing"] - row["payroll_heads"]
    return row


# ── The old board pack's months ───────────────────────────────────────
LEGACY_GROUPS = (("basic", "Basic"), ("per_meter", "Per Meter"), ("overtime", "Overtime"),
                 ("special_overtime", "Special Overtime"), ("arrears", "Arrears"), ("other_pay", "Other"))


def legacy_rows(row):
    """A plant's month as the old board pack kept it (one HR Snapshot Plant
    row, 33 columns) as fact rows: (HR Employee Month rows, HR Pay Fact rows,
    HR Safety Fact rows), every total it held kept exactly.

    The old row split some figures by population and others not at all, so
    where a figure was not split it is laid on the populations in a fixed
    order, which keeps both totals: additions on the permanent hires first,
    regrettable exits on the permanent exits first, the men and women on the
    permanent staff first; and the expatriates' and casuals' pay, which the
    old row also left inside the component groups, taken out of Other first,
    then Basic and the rest, so the components and the two populations add
    up to the old wage bill."""
    branch = row.get("branch") or None
    count = lambda field: _int(row.get(field))  # noqa: E731
    months = []

    def person_row(kind, **counts):
        if not any(counts.values()):
            return
        base = {"branch": branch, "opening_branch": branch, "population": kind, "opening_population": kind,
                "heads": max(1, max(counts.values()))}
        base.update(dict.fromkeys(COUNTS[1:], 0))
        base.update(counts)
        months.append(base)

    male, female = count("male"), count("female")
    hires = {PERMANENT: count("hires_permanent"), CASUAL: count("hires_casual")}
    exits = {PERMANENT: count("exits_permanent"), CASUAL: count("exits_casual")}
    additions, regrettable = count("additions"), count("regrettable")
    for kind, opening, closing in ((PERMANENT, count("permanent_opening"), count("permanent")),
                                   (CASUAL, count("casual_opening"), count("casual"))):
        men = min(male, closing)
        women = min(female, closing - men)
        male, female = male - men, female - women
        person_row(kind, opening=opening, closing=closing - men - women)
        if men:
            person_row(kind, closing=men)
            months[-1]["gender"] = "Male"
        if women:
            person_row(kind, closing=women)
            months[-1]["gender"] = "Female"
        added = min(additions, hires[kind])
        additions -= added
        for reason, number in ((ADDITION, added), (REPLACEMENT, hires[kind] - added)):
            if number:
                person_row(kind, hired=number)
                months[-1]["hire_reason"] = reason
        lost = min(regrettable, exits[kind])
        regrettable -= lost
        if lost:
            person_row(kind, exited=lost)
            months[-1]["regrettable"] = 1
        if exits[kind] - lost:
            person_row(kind, exited=exits[kind] - lost)
    for field in ("hired", "exited", "transferred", "converted", "regrettable", "paid"):
        for month in months:
            month.setdefault(field, 0)
    amounts = {group: _num(row.get(field)) for field, group in LEGACY_GROUPS}
    take = _num(row.get("expatriates")) + _num(row.get("casual_pay"))
    for group in ("Other", "Basic", "Per Meter", "Overtime", "Special Overtime", "Arrears"):
        cut = min(take, amounts[group])
        amounts[group] -= cut
        take -= cut
    pay = [{"branch": branch, "population": PERMANENT, "component_group": group, "salary_component": None,
            "amount": round(amount, 2), "heads": 0} for group, amount in amounts.items() if round(amount, 2)]
    for kind, field in ((EXPATRIATE, "expatriates"), (CASUAL, "casual_pay")):
        if round(_num(row.get(field)), 2):
            pay.append({"branch": branch, "population": kind, "component_group": OTHER, "salary_component": None,
                        "amount": round(_num(row.get(field)), 2), "heads": 0})
    safety = []
    rest = count("incidents") - count("near_misses") - count("lost_time") - count("fatalities")
    for severity, number in ((NEAR_MISS, count("near_misses")), (LOST_TIME, count("lost_time")),
                             (FATALITY, count("fatalities")), (None, max(rest, 0))):
        if number:
            safety.append({"branch": branch, "department": None, "severity": severity, "hazard": None,
                           "off_site": 0, "incidents": number, "days_lost": 0})
    return months, pay, safety


# ── Data quality ──────────────────────────────────────────────────────
DATA_CHECKS = (
    ("blank_branch", "Active employees with no plant"),
    ("left_without_date", "Left with no relieving date"),
    ("hires_without_requisition", "Hires with no requisition"),
    ("slips_without_branch", "Salary slips with no plant"),
)


def data_quality(counts):
    """[{key, label, count}] in the panel's order, and how many in all."""
    rows = [{"key": key, "label": label, "count": _int((counts or {}).get(key))} for key, label in DATA_CHECKS]
    return rows, sum(row["count"] for row in rows)


# ── What the month's header says ──────────────────────────────────────
def may_build(locked, source):
    """A month is built from the site again unless it is locked or imported."""
    return not _int(locked) and (source or SYSTEM) != IMPORTED


def refresh_due(months, today, back):
    """The months the nightly job builds again: the month running and the
    `back` months before it, oldest first."""
    today = month_start(today)
    window = {add_months(today, -offset) for offset in range(0, max(_int(back), 0) + 1)}
    return sorted(month for month in (month_start(m) for m in months) if month in window)


def fact_name(month, employee):
    """A system row's name: the month and the employee, so a rebuild writes
    the same names again."""
    return "%s %s" % (month_start(month).strftime("%Y-%m"), employee)


def chunks(rows, size=CHUNK):
    rows = list(rows)
    return [rows[start:start + size] for start in range(0, len(rows), size)]


# ── Helpers ───────────────────────────────────────────────────────────
def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
