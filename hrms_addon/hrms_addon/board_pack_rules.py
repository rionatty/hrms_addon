# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack's figures: the rules, without a Frappe import
(scripts/verify_board_pack.py). board_pack.py reads and writes the site; board_rules.py is the attendance board's, not this.

Luuka's quarterly HR Board Report (LPL HR Board Report Q3 2026 v3): head
count by plant, recruitment, exits and attrition, churn by employment type
and the movement reconciliation, the year-on-year comparison, the wage bill
and its components, overtime, labour cost against revenue, and safety.
Decided with the user on 17 Nov 2026: revenue and kilograms produced are
typed in each quarter by Finance; the wage bill comes from the payroll.

  HR Monthly Snapshot   a month's figures by plant, taken from the site at
                        the month's end (or imported, for the months before
                        the system: 2025 is what the board compares with)
  HR Board Report       a quarter's tables, worked out from three months'
                        snapshots, the quarter before and the same quarter a
                        year before, with HR's own words beside them

Definitions the board reads, written on the pack itself:
  head count          still employed when the day is over: joined on or
                      before it, and relieved after it, if at all
  casual              paid by the week (pay category Weekly or Per Piece);
                      everyone else is permanent
  monthly attrition   exits in the month over the average of the opening
                      and closing head count, as a percentage
  quarter churn       exits in the quarter over the average of the
                      quarter's opening and closing head count of that type
  cost per kg         the plant's wage bill over the kilograms it produced
  labour cost         staff cost (Finance's figure where typed, else the
                      payroll wage bill) over revenue
"""

import calendar
import datetime

CASUAL_CATEGORIES = ("Weekly", "Per Piece")
PERMANENT, CASUAL = "Permanent", "Casual"
ADDITION = "New Addition"
MALE, FEMALE = "Male", "Female"
GROUPS = ("Basic", "Per Meter", "Overtime", "Special Overtime", "Arrears", "Other")
SEVERITIES = ("Near Miss", "First Aid", "Medical Treatment", "Lost Time", "Fatality")
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")
# a snapshot's counts and amounts, per plant
COUNTS = ("opening", "closing", "permanent", "casual", "male", "female", "permanent_opening", "casual_opening",
          "hires", "hires_permanent", "hires_casual", "replacements", "additions", "exits", "exits_permanent",
          "exits_casual", "regrettable", "incidents", "near_misses", "lost_time", "fatalities")
AMOUNTS = ("wage_bill", "basic", "per_meter", "overtime", "special_overtime", "arrears", "other_pay", "expatriates",
           "casual_pay", "revenue", "output_kg", "staff_cost")
GROUP_FIELDS = {"Basic": "basic", "Per Meter": "per_meter", "Overtime": "overtime",
                "Special Overtime": "special_overtime", "Arrears": "arrears", "Other": "other_pay"}
# the board's ratings, and the areas it rates
RATINGS = ("On Track", "Watch", "Action Needed")
AREAS = ("Workforce Stability", "Talent Acquisition", "Retention & Turnover", "Safety (EHS)",
         "Compensation & Payroll", "Learning & Capability", "Compliance & Governance", "HR Digitalisation")
METRICS = ("Workforce productivity & ROI", "Regrettable attrition", "AI / digital adoption impact", "Quality of hire",
           "Revenue / cost per employee", "Talent risk & succession coverage", "Skills gap against strategy")


# ── Months and quarters ───────────────────────────────────────────────
def quarter_months(year, quarter):
    """[(year, month)] of a quarter, Q1 to Q4."""
    first = QUARTERS.index(quarter) * 3 + 1
    return [(int(year), month) for month in range(first, first + 3)]


def month_bounds(year, month):
    return datetime.date(year, month, 1), datetime.date(year, month, calendar.monthrange(year, month)[1])


def quarter_before(year, quarter):
    index = QUARTERS.index(quarter)
    return (int(year), QUARTERS[index - 1]) if index else (int(year) - 1, "Q4")


def quarter_of(day):
    day = _date(day)
    return day.year, QUARTERS[(day.month - 1) // 3]


def label(year, quarter):
    months = quarter_months(year, quarter)
    return "%s – %s %d" % (MONTH_NAMES[months[0][1] - 1], MONTH_NAMES[months[-1][1] - 1], int(year))


# ── A month's snapshot, by plant ──────────────────────────────────────
def kind_of(person):
    """Casual where paid by the week, else permanent."""
    return CASUAL if person.get("pay_category") in CASUAL_CATEGORIES else PERMANENT


def employed_on(person, day):
    """Employed during the day: joined by it, not relieved before it."""
    joined, relieved = _date(person.get("date_of_joining")), _date(person.get("relieving_date"))
    return bool(joined) and joined <= day and (not relieved or relieved >= day)


def employed_after(person, day):
    """Still employed when the day is over: joined by it, and relieved after
    it, if at all. A month's opening is this on the day before it, its
    closing this on its last day, so that opening, plus hires, less exits,
    is the closing exactly: one whose last day was the 30th is the month's
    exit, not the next month's opening."""
    joined, relieved = _date(person.get("date_of_joining")), _date(person.get("relieving_date"))
    return bool(joined) and joined <= day and (not relieved or relieved > day)


def snapshot(people, slips, incidents, finance, first, last, groups=None):
    """{plant: figures} for a month.

    people: [{"name", "branch", "gender", "pay_category", "date_of_joining",
    "relieving_date", "regrettable", "hire_reason"}], everyone who was
    employed at any time in the month; slips: [{"branch", "employee",
    "gross", "foreign", "components": {component: amount}}] submitted in it;
    incidents: [{"branch", "severity"}]; finance: {plant: {"revenue",
    "output_kg", "staff_cost"}}; groups: {component: group}.
    """
    first, last = _date(first), _date(last)
    groups = groups or {}
    casual = {person["name"] for person in people if kind_of(person) == CASUAL}
    plants = {}

    def row(plant):
        return plants.setdefault(plant or "", dict.fromkeys(COUNTS + AMOUNTS, 0))

    day_before = first - datetime.timedelta(days=1)
    for person in people:
        figures = row(person.get("branch"))
        kind = kind_of(person)
        if employed_after(person, day_before):
            figures["opening"] += 1
            figures["permanent_opening" if kind == PERMANENT else "casual_opening"] += 1
        if employed_after(person, last):
            figures["closing"] += 1
            figures["permanent" if kind == PERMANENT else "casual"] += 1
            if person.get("gender") in (MALE, FEMALE):
                figures[person["gender"].lower()] += 1
        joined, relieved = _date(person.get("date_of_joining")), _date(person.get("relieving_date"))
        if joined and first <= joined <= last:
            figures["hires"] += 1
            figures["hires_permanent" if kind == PERMANENT else "hires_casual"] += 1
            figures["additions" if person.get("hire_reason") == ADDITION else "replacements"] += 1
        if relieved and first <= relieved <= last:
            figures["exits"] += 1
            figures["exits_permanent" if kind == PERMANENT else "exits_casual"] += 1
            if int(_num(person.get("regrettable"))):
                figures["regrettable"] += 1
    for slip in slips or ():
        figures = row(slip.get("branch"))
        gross = _num(slip.get("gross"))
        figures["wage_bill"] += gross
        if slip.get("foreign"):
            figures["expatriates"] += gross
        if slip.get("employee") in casual:
            figures["casual_pay"] += gross
        counted = 0.0
        for component, amount in (slip.get("components") or {}).items():
            field = GROUP_FIELDS.get(groups.get(component) or "Other", "other_pay")
            figures[field] += _num(amount)
            counted += _num(amount)
        figures["other_pay"] += max(gross - counted, 0.0) if slip.get("components") else gross
    for incident in incidents or ():
        figures = row(incident.get("branch"))
        figures["incidents"] += 1
        severity = incident.get("severity")
        if severity == "Near Miss":
            figures["near_misses"] += 1
        elif severity == "Lost Time":
            figures["lost_time"] += 1
        elif severity == "Fatality":
            figures["fatalities"] += 1
    for plant, typed in (finance or {}).items():
        figures = row(plant)
        for field in ("revenue", "output_kg", "staff_cost"):
            figures[field] += _num(typed.get(field))
    for figures in plants.values():
        for field in AMOUNTS:
            figures[field] = round(figures[field], 2)
    return {plant: figures for plant, figures in plants.items() if any(figures.values())}


def component_group(component):
    """The group a salary component falls in, by its name, until HR say otherwise."""
    name = (component or "").lower()
    words = name.replace("-", " ").split()
    if "special" in words and ("overtime" in name or "ot" in words):
        return "Special Overtime"
    if "overtime" in name or words[:1] == ["ot"]:
        return "Overtime"
    if "meter" in name or "metre" in name:
        return "Per Meter"
    if "arrear" in name:
        return "Arrears"
    if "basic" in name:
        return "Basic"
    return "Other"


# ── The quarter, from its months ──────────────────────────────────────
def quarter(months, before=None, last_year=None, plants=None, target=5.0, previous=None):
    """The board's tables for a quarter.

    months: the quarter's three snapshots, {plant: figures} each, in order;
    before: the snapshot of the month before the quarter (its closing is
    the quarter's opening); last_year: the same quarter's three snapshots a
    year before; previous: the quarter before's three snapshots; plants:
    the order the plants are shown in.
    """
    months = list(months)
    last_year = list(last_year or [])
    previous = list(previous or [])
    plants = list(plants or sorted({plant for month in months for plant in month}))
    end = months[-1] if months else {}
    start = before or {}
    out = {"plants": plants, "target": target}

    def get(snapshot, plant, field):
        return _num(((snapshot or {}).get(plant) or {}).get(field))

    def total(snapshot, field):
        return sum(_num(figures.get(field)) for figures in (snapshot or {}).values())

    def summed(snapshots, plant, field):
        return sum(get(snapshot, plant, field) for snapshot in snapshots)

    def summed_all(snapshots, field):
        return sum(total(snapshot, field) for snapshot in snapshots)

    # head count at the quarter's end
    head = []
    for plant in plants + [None]:
        pick = (lambda field: get(end, plant, field)) if plant else (lambda field: total(end, field))
        was = (lambda field: get(start, plant, field)) if plant else (lambda field: total(start, field))
        closing = pick("closing")
        head.append({"plant": plant, "permanent": pick("permanent"), "casual": pick("casual"), "total": closing,
                     "share": percent(closing, total(end, "closing")), "male": pick("male"),
                     "female": pick("female"), "qoq": closing - was("closing") if start else None,
                     "permanent_share_start": percent(was("permanent"), was("closing")) if start else None,
                     "permanent_share_end": percent(pick("permanent"), closing)})
    out["head_count"] = head
    out["monthly_head_count"] = [total(month, "closing") for month in months]
    out["monthly_head_count_last_year"] = [total(month, "closing") for month in last_year]
    out["yoy_head_count"] = [{"plant": plant,
                              "months": [(get(old, plant, "closing") if old else None, get(new, plant, "closing"))
                                         for old, new in zip(_pad(last_year, len(months)), months)],
                              "permanent_share": (percent(get(last_year[-1], plant, "permanent"),
                                                          get(last_year[-1], plant, "closing"))
                                                  if last_year else None,
                                                  percent(get(end, plant, "permanent"), get(end, plant, "closing")))}
                             for plant in plants]
    # recruitment
    out["recruitment"] = [{
        "plant": plant,
        "replacements": summed(months, plant, "replacements") if plant else summed_all(months, "replacements"),
        "additions": summed(months, plant, "additions") if plant else summed_all(months, "additions"),
        "permanent": summed(months, plant, "hires_permanent") if plant else summed_all(months, "hires_permanent"),
        "casual": summed(months, plant, "hires_casual") if plant else summed_all(months, "hires_casual"),
        "total": summed(months, plant, "hires") if plant else summed_all(months, "hires"),
        "last_year": (summed(last_year, plant, "hires") if plant else summed_all(last_year, "hires"))
        if last_year else None,
        "previous": (summed(previous, plant, "hires") if plant else summed_all(previous, "hires"))
        if previous else None,
    } for plant in plants + [None]]
    # exits and attrition, month by month
    exits = []
    for plant in plants + [None]:
        monthly = []
        for month in months:
            gone = get(month, plant, "exits") if plant else total(month, "exits")
            opening = get(month, plant, "opening") if plant else total(month, "opening")
            closing = get(month, plant, "closing") if plant else total(month, "closing")
            monthly.append({"exits": gone, "rate": attrition(gone, opening, closing)})
        rates = [entry["rate"] for entry in monthly if entry["rate"] is not None]
        old = []
        for month in last_year:
            gone = get(month, plant, "exits") if plant else total(month, "exits")
            old.append(attrition(gone, get(month, plant, "opening") if plant else total(month, "opening"),
                                 get(month, plant, "closing") if plant else total(month, "closing")))
        old_rates = [rate for rate in old if rate is not None]
        exits.append({"plant": plant, "months": monthly, "total": sum(entry["exits"] for entry in monthly),
                      "average": round(sum(rates) / len(rates), 1) if rates else None,
                      "regrettable": summed(months, plant, "regrettable") if plant else summed_all(months, "regrettable"),
                      "last_year": (summed(last_year, plant, "exits") if plant else summed_all(last_year, "exits"))
                      if last_year else None,
                      "last_year_average": round(sum(old_rates) / len(old_rates), 1) if old_rates else None,
                      "over_target": any(rate > target for rate in rates)})
    out["exits"] = exits
    # churn by employment type over the quarter, and the reconciliation
    churn, reconciliation = [], []
    for plant in plants + [None]:
        def opened(field, snaps=months):
            first = snaps[0] if snaps else {}
            return get(first, plant, field) if plant else total(first, field)

        def closed(field, snaps=months):
            final = snaps[-1] if snaps else {}
            return get(final, plant, field) if plant else total(final, field)

        def gone(field, snaps=months):
            return summed(snaps, plant, field) if plant else summed_all(snaps, field)

        row = {"plant": plant}
        for kind, opening_field, closing_field, exit_field in (
                ("permanent", "permanent_opening", "permanent", "exits_permanent"),
                ("casual", "casual_opening", "casual", "exits_casual")):
            row[kind] = (gone(exit_field), rate_of(gone(exit_field), opened(opening_field), closed(closing_field)))
            if last_year:
                row[kind + "_last_year"] = (gone(exit_field, last_year),
                                            rate_of(gone(exit_field, last_year), opened(opening_field, last_year),
                                                    closed(closing_field, last_year)))
        churn.append(row)
        opening = opened("opening")
        expected = opening + gone("hires") - gone("exits")
        reconciliation.append({"plant": plant, "opening": opening, "hires": gone("hires"), "exits": gone("exits"),
                               "expected": expected, "reported": closed("closing"),
                               "variance": closed("closing") - expected})
    out["churn"], out["reconciliation"] = churn, reconciliation
    # pay, output and cost per kg
    wage = []
    for plant in plants + [None]:
        monthly = []
        for month in months:
            bill = get(month, plant, "wage_bill") if plant else total(month, "wage_bill")
            kg = get(month, plant, "output_kg") if plant else total(month, "output_kg")
            monthly.append({"wage_bill": bill, "output_kg": kg, "cost_per_kg": round(bill / kg) if kg else None})
        bill = sum(entry["wage_bill"] for entry in monthly)
        kg = sum(entry["output_kg"] for entry in monthly)
        old = summed(last_year, plant, "wage_bill") if plant else summed_all(last_year, "wage_bill")
        prior = summed(previous, plant, "wage_bill") if plant else summed_all(previous, "wage_bill")
        heads = [get(month, plant, "closing") if plant else total(month, "closing") for month in months]
        old_heads = [get(month, plant, "closing") if plant else total(month, "closing") for month in last_year]
        overtime = sum((get(month, plant, "overtime") + get(month, plant, "special_overtime")) if plant
                       else (total(month, "overtime") + total(month, "special_overtime")) for month in months)
        old_overtime = sum((get(month, plant, "overtime") + get(month, plant, "special_overtime")) if plant
                           else (total(month, "overtime") + total(month, "special_overtime")) for month in last_year)
        wage.append({"plant": plant, "months": monthly, "wage_bill": round(bill, 2),
                     "cost_per_kg": round(bill / kg) if kg else None,
                     "last_year": round(old, 2) if last_year else None, "yoy": change(bill, old) if last_year else None,
                     "previous": round(prior, 2) if previous else None,
                     "qoq": change(bill, prior) if previous else None,
                     "overtime": round(overtime, 2), "overtime_last_year": round(old_overtime, 2) if last_year else None,
                     "per_employee_month": round(bill / (sum(heads) / len(heads)) / len(months)) if months and sum(heads)
                     else None,
                     "per_employee_month_last_year": round(old / (sum(old_heads) / len(old_heads)) / len(last_year))
                     if last_year and sum(old_heads) else None})
    out["wage_bill"] = wage
    out["components"] = [{"group": group, "now": round(summed_all(months, GROUP_FIELDS[group]), 2),
                          "last_year": round(summed_all(last_year, GROUP_FIELDS[group]), 2) if last_year else None}
                         for group in GROUPS] + [
        {"group": "Expatriates", "now": round(summed_all(months, "expatriates"), 2),
         "last_year": round(summed_all(last_year, "expatriates"), 2) if last_year else None},
        {"group": "Casuals", "now": round(summed_all(months, "casual_pay"), 2),
         "last_year": round(summed_all(last_year, "casual_pay"), 2) if last_year else None}]
    increase = summed_all(months, "wage_bill") - (summed_all(last_year, "wage_bill") if last_year else 0)
    for row in out["components"]:
        row["yoy"] = change(row["now"], row["last_year"]) if row["last_year"] is not None else None
        row["share_of_increase"] = percent(row["now"] - (row["last_year"] or 0), increase) \
            if last_year and increase > 0 else None
    # labour cost against revenue
    labour = []
    for plant in plants + [None]:
        revenue = summed(months, plant, "revenue") if plant else summed_all(months, "revenue")
        typed = summed(months, plant, "staff_cost") if plant else summed_all(months, "staff_cost")
        bill = summed(months, plant, "wage_bill") if plant else summed_all(months, "wage_bill")
        cost = typed or bill
        heads = [get(month, plant, "closing") if plant else total(month, "closing") for month in months]
        average = sum(heads) / len(heads) if heads else 0
        kg = summed(months, plant, "output_kg") if plant else summed_all(months, "output_kg")
        old_revenue = summed(previous, plant, "revenue") if plant else summed_all(previous, "revenue")
        old_cost = (summed(previous, plant, "staff_cost") if plant else summed_all(previous, "staff_cost")) or             (summed(previous, plant, "wage_bill") if plant else summed_all(previous, "wage_bill"))
        labour.append({"plant": plant, "revenue": revenue, "staff_cost": cost, "from_finance": bool(typed),
                       "share": percent(cost, revenue) if revenue else None,
                       "previous_share": percent(old_cost, old_revenue) if previous and old_revenue else None,
                       "previous_revenue": old_revenue if previous else None,
                       "monthly_share": [percent((get(month, plant, "staff_cost") or get(month, plant, "wage_bill"))
                                                 if plant else (total(month, "staff_cost") or total(month, "wage_bill")),
                                                 get(month, plant, "revenue") if plant else total(month, "revenue"))
                                         if (get(month, plant, "revenue") if plant else total(month, "revenue")) else None
                                         for month in months],
                       "revenue_per_employee": round(revenue / average) if average else None,
                       "cost_per_kg": round(bill / kg) if kg else None,
                       "output_per_employee_month": round(kg / average / max(len(months), 1)) if average and kg else None})
    out["labour_cost"] = labour
    # safety
    out["safety"] = [{"plant": plant,
                      "months": [get(month, plant, "incidents") if plant else total(month, "incidents")
                                 for month in months],
                      "total": summed(months, plant, "incidents") if plant else summed_all(months, "incidents"),
                      "last_year": (summed(last_year, plant, "incidents") if plant else summed_all(last_year, "incidents"))
                      if last_year else None,
                      "lost_time": summed(months, plant, "lost_time") if plant else summed_all(months, "lost_time"),
                      "fatalities": summed(months, plant, "fatalities") if plant else summed_all(months, "fatalities")}
                     for plant in plants + [None]]
    return out


def attrition(exits, opening, closing):
    """Exits over the average of opening and closing head count, as a
    percentage; None with nobody to leave."""
    average = (_num(opening) + _num(closing)) / 2.0
    return round(100.0 * _num(exits) / average, 1) if average else None


def rate_of(exits, opening, closing):
    return attrition(exits, opening, closing)


def change(now, before):
    """The change from before to now, as a percentage; None from nothing."""
    before, now = _num(before), _num(now)
    return round(100.0 * (now - before) / before, 1) if before else None


def percent(part, whole, places=1):
    return round(100.0 * _num(part) / _num(whole), places) if _num(whole) else 0.0


def overtime_series(snapshots_by_month):
    """[(month number, overtime + special overtime)] for the months given:
    {(year, month): snapshot}."""
    return [(month, round(sum(_num(figures.get("overtime")) + _num(figures.get("special_overtime"))
                              for figures in (snapshot or {}).values()), 2))
            for (year, month), snapshot in sorted(snapshots_by_month.items())]


def default_ratings():
    return [{"area": area, "rating": "", "note": ""} for area in AREAS]


def default_metrics():
    return [{"number": "%02d" % index, "metric": metric, "reading": "", "tells": "", "status": ""}
            for index, metric in enumerate(METRICS, 1)]


def _pad(rows, size):
    rows = list(rows or [])
    return rows + [None] * (size - len(rows)) if len(rows) < size else rows[:size]


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
