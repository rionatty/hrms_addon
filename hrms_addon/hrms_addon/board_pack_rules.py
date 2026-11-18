# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack's quarter: the rules, without a Frappe import
(scripts/verify_board_pack.py). board_pack.py asks the facts for each month
by plant (board_facts.month_figures: a GROUP BY over HR Employee Month, HR
Pay Fact, HR Safety Fact and Finance's lines) and hands the months here.
board_rules.py is the attendance board's, not this.

Luuka's quarterly HR Board Report (LPL HR Board Report Q3 2026 v3): head
count by plant, recruitment, exits and attrition, churn by employment type
and the movement reconciliation, the year-on-year comparison, the wage bill
and its components, overtime, labour cost against revenue, and safety.
Decided with the user on 17 Nov 2026: revenue and kilograms produced are
typed in each quarter by Finance; the wage bill comes from the payroll.

A month's figures by plant: {plant: {field: value}}, COUNTS and AMOUNTS.
The plant with no branch on record is NO_PLANT, a row of its own, so the
plants always add up to the total.

Definitions the board reads, written on the pack itself:
  head count          still employed when the day is over: joined on or
                      before it, and relieved after it, if at all
  casual              paid by the week (pay category Weekly or Per Piece);
                      expatriates are the foreign staff; the rest permanent.
                      Pay is split the same way, so the components and the
                      two populations add up to the wage bill
  monthly attrition   exits in the month over the average of the opening
                      and closing head count, as a percentage
  quarter churn       exits in the quarter over the average of the
                      quarter's opening and closing head count of that type
  reconciliation      opening + hires - exits + transfers in - transfers out
  incidents           everything recorded but near misses, which are shown
                      apart
  cost per kg         the plant's wage bill over the kilograms it produced
  labour cost         staff cost over revenue; for each plant and month,
                      Finance's staff cost where typed, else the payroll's
                      wage bill
"""

import calendar
import datetime

NO_PLANT = "No Plant"
CASUAL_CATEGORIES = ("Weekly", "Per Piece")
PERMANENT, CASUAL = "Permanent", "Casual"
MALE, FEMALE = "Male", "Female"
GROUPS = ("Basic", "Per Meter", "Overtime", "Special Overtime", "Arrears", "Other")
SEVERITIES = ("Near Miss", "First Aid", "Medical Treatment", "Lost Time", "Fatality")
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")
# a month's counts and amounts, per plant, as board_facts.month_figures reads them
COUNTS = ("opening", "closing", "casual", "expatriate", "male", "female", "casual_opening", "hires", "hires_casual",
          "replacements", "additions", "unclassified", "exits", "exits_casual", "regrettable", "voluntary",
          "involuntary", "transfers_in", "transfers_out", "conversions", "payroll_heads", "incidents",
          "near_misses", "first_aid", "medical", "lost_time", "fatalities", "off_site")
AMOUNTS = ("wage_bill", "basic", "per_meter", "overtime", "special_overtime", "arrears", "other_pay", "expatriates",
           "casual_pay", "overtime_all", "revenue", "output_kg", "staff_cost", "hours_worked", "days_worked",
           "days_absent", "ot_hours", "training_hours", "attendance_days", "clock_days", "days_lost")
# worked out from the others
DERIVED = ("permanent", "permanent_opening", "hires_permanent", "exits_permanent", "staff_cost_used")
FIELDS = COUNTS + AMOUNTS
# the permanent staff's pay, by component group; expatriates and casuals are populations of their own
GROUP_FIELDS = {"Basic": "basic", "Per Meter": "per_meter", "Overtime": "overtime",
                "Special Overtime": "special_overtime", "Arrears": "arrears", "Other": "other_pay"}
POPULATION_ROWS = (("Expatriates", "expatriates"), ("Casuals", "casual_pay"))
# the board's ratings, and the areas it rates
RATINGS = ("On Track", "Watch", "Action Needed")
AREAS = ("Workforce Stability", "Talent Acquisition", "Retention & Turnover", "Safety (EHS)",
         "Compensation & Payroll", "Learning & Capability", "Compliance & Governance", "HR Digitalisation")
METRICS = ("Workforce productivity & ROI", "Regrettable attrition", "AI / digital adoption impact", "Quality of hire",
           "Revenue / cost per employee", "Talent risk & succession coverage", "Skills gap against strategy")
LTIFR_HOURS = 1000000.0


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


def quarters_back(year, quarter, count):
    """[(year, quarter)] of the `count` quarters ending with this one, oldest first."""
    out = [(int(year), quarter)]
    while len(out) < count:
        out.insert(0, quarter_before(*out[0]))
    return out


def quarter_of(day):
    day = _date(day)
    return day.year, QUARTERS[(day.month - 1) // 3]


def label(year, quarter):
    months = quarter_months(year, quarter)
    return "%s – %s %d" % (MONTH_NAMES[months[0][1] - 1], MONTH_NAMES[months[-1][1] - 1], int(year))


def short_label(year, quarter):
    return "%s %s" % (quarter, str(int(year))[-2:])


def quarter_end(year, quarter):
    return month_bounds(*quarter_months(year, quarter)[-1])[1]


def plants_of(months):
    """The plants a set of months shows, by name, the one with no plant last."""
    found = {plant for month in months if month for plant, figures in month.items()
             if any(_num(figures.get(field)) for field in FIELDS)}
    return sorted(found - {NO_PLANT}) + ([NO_PLANT] if NO_PLANT in found else [])


# ── A month's figures, completed ──────────────────────────────────────
def complete(month):
    """A month's figures with the derived fields: the permanent staff (an
    expatriate is permanent staff), and the staff cost the labour ratio uses:
    Finance's for that plant and month where typed, else the wage bill."""
    out = {}
    for plant, figures in (month or {}).items():
        row = {field: _num(figures.get(field)) for field in FIELDS}
        row["permanent"] = row["closing"] - row["casual"]
        row["permanent_opening"] = row["opening"] - row["casual_opening"]
        row["hires_permanent"] = row["hires"] - row["hires_casual"]
        row["exits_permanent"] = row["exits"] - row["exits_casual"]
        row["staff_cost_used"] = row["staff_cost"] if row["staff_cost"] else row["wage_bill"]
        row["typed"] = 1 if row["staff_cost"] else 0
        out[plant or NO_PLANT] = row
    return out


# ── The quarter, from its months ──────────────────────────────────────
def quarter(months, before=None, last_year=None, plants=None, target=5.0, previous=None):
    """The board's tables for a quarter.

    months: the quarter's three months, {plant: figures} each, in order;
    before: the month before the quarter (its closing is the quarter's
    opening); last_year: the same quarter's three months a year before;
    previous: the quarter before's three months; plants: the order the
    plants are shown in, NO_PLANT last when it has anything.
    """
    months = [complete(month) for month in months]
    last_year = [complete(month) for month in last_year or []]
    previous = [complete(month) for month in previous or []]
    start = complete(before) if before else {}
    plants = list(plants or plants_of(months))
    end = months[-1] if months else {}
    out = {"plants": plants, "target": target}
    rows = plants + [None]

    def get(snapshot, plant, field):
        if plant is None:
            return sum(_num(figures.get(field)) for figures in (snapshot or {}).values())
        return _num(((snapshot or {}).get(plant) or {}).get(field))

    def summed(snapshots, plant, field):
        return sum(get(snapshot, plant, field) for snapshot in snapshots)

    # head count at the quarter's end
    head = []
    for plant in rows:
        closing = get(end, plant, "closing")
        head.append({"plant": plant, "permanent": get(end, plant, "permanent"), "casual": get(end, plant, "casual"),
                     "expatriate": get(end, plant, "expatriate"), "total": closing,
                     "share": percent(closing, get(end, None, "closing")), "male": get(end, plant, "male"),
                     "female": get(end, plant, "female"),
                     "qoq": closing - get(start, plant, "closing") if start else None,
                     "permanent_share_start": percent(get(start, plant, "permanent"), get(start, plant, "closing"))
                     if start else None,
                     "permanent_share_end": percent(get(end, plant, "permanent"), closing),
                     "conversions": summed(months, plant, "conversions")})
    out["head_count"] = head
    out["monthly_head_count"] = [get(month, None, "closing") for month in months]
    out["monthly_head_count_last_year"] = [get(month, None, "closing") for month in last_year]
    out["monthly_permanent"] = [get(month, None, "permanent") for month in months]
    out["yoy_head_count"] = [{"plant": plant,
                              "months": [(get(old, plant, "closing") if old else None, get(new, plant, "closing"))
                                         for old, new in zip(_pad(last_year, len(months)), months)],
                              "permanent_share": (percent(get(last_year[-1], plant, "permanent"),
                                                          get(last_year[-1], plant, "closing"))
                                                  if last_year else None,
                                                  percent(get(end, plant, "permanent"), get(end, plant, "closing")))}
                             for plant in rows]
    # recruitment, by what the hire was for
    out["recruitment"] = [{
        "plant": plant, "replacements": summed(months, plant, "replacements"),
        "additions": summed(months, plant, "additions"), "unclassified": summed(months, plant, "unclassified"),
        "permanent": summed(months, plant, "hires_permanent"), "casual": summed(months, plant, "hires_casual"),
        "total": summed(months, plant, "hires"),
        "last_year": summed(last_year, plant, "hires") if last_year else None,
        "previous": summed(previous, plant, "hires") if previous else None,
    } for plant in rows]
    # exits and attrition, month by month, each month against the target
    exits = []
    for plant in rows:
        monthly = []
        for month in months:
            rate = attrition(get(month, plant, "exits"), get(month, plant, "opening"), get(month, plant, "closing"))
            monthly.append({"exits": get(month, plant, "exits"), "rate": rate,
                            "over_target": rate is not None and target is not None and rate > target})
        rates = [entry["rate"] for entry in monthly if entry["rate"] is not None]
        old_rates = [rate for rate in (attrition(get(month, plant, "exits"), get(month, plant, "opening"),
                                                 get(month, plant, "closing")) for month in last_year)
                     if rate is not None]
        exits.append({"plant": plant, "months": monthly, "total": sum(entry["exits"] for entry in monthly),
                      "average": round(sum(rates) / len(rates), 1) if rates else None,
                      "regrettable": summed(months, plant, "regrettable"),
                      "voluntary": summed(months, plant, "voluntary"),
                      "involuntary": summed(months, plant, "involuntary"),
                      "last_year": summed(last_year, plant, "exits") if last_year else None,
                      "last_year_average": round(sum(old_rates) / len(old_rates), 1) if old_rates else None,
                      "previous_regrettable": summed(previous, plant, "regrettable") if previous else None,
                      "over_target": any(entry["over_target"] for entry in monthly),
                      "over_target_months": [index for index, entry in enumerate(monthly) if entry["over_target"]]})
    out["exits"] = exits
    # churn by employment type over the quarter, and the reconciliation
    churn, reconciliation = [], []
    for plant in rows:
        def opened(field, snaps=months):
            return get(snaps[0] if snaps else {}, plant, field)

        def closed(field, snaps=months):
            return get(snaps[-1] if snaps else {}, plant, field)

        row = {"plant": plant}
        for kind, opening_field, closing_field, exit_field in (
                ("permanent", "permanent_opening", "permanent", "exits_permanent"),
                ("casual", "casual_opening", "casual", "exits_casual")):
            gone = summed(months, plant, exit_field)
            row[kind] = (gone, attrition(gone, opened(opening_field), closed(closing_field)))
            if last_year:
                gone_before = summed(last_year, plant, exit_field)
                row[kind + "_last_year"] = (gone_before, attrition(gone_before, opened(opening_field, last_year),
                                                                   closed(closing_field, last_year)))
        exits_all = summed(months, plant, "exits")
        row["casual_share_of_exits"] = percent(summed(months, plant, "exits_casual"), exits_all) if exits_all else None
        row["casual_share_of_workforce"] = percent(closed("casual"), closed("closing")) if closed("closing") else None
        churn.append(row)
        opening = opened("opening")
        moved_in, moved_out = summed(months, plant, "transfers_in"), summed(months, plant, "transfers_out")
        expected = opening + summed(months, plant, "hires") - summed(months, plant, "exits") + moved_in - moved_out
        reconciliation.append({"plant": plant, "opening": opening, "hires": summed(months, plant, "hires"),
                               "exits": summed(months, plant, "exits"), "transfers_in": moved_in,
                               "transfers_out": moved_out, "conversions": summed(months, plant, "conversions"),
                               "expected": expected, "reported": closed("closing"),
                               "variance": closed("closing") - expected, "payroll_heads": closed("payroll_heads"),
                               "payroll_variance": closed("closing") - closed("payroll_heads")})
    out["churn"], out["reconciliation"] = churn, reconciliation
    # pay, output and cost per kg
    wage = []
    for plant in rows:
        monthly = []
        for month in months:
            bill, kg = get(month, plant, "wage_bill"), get(month, plant, "output_kg")
            monthly.append({"wage_bill": bill, "output_kg": kg, "cost_per_kg": round(bill / kg) if kg else None})
        bill = sum(entry["wage_bill"] for entry in monthly)
        kg = sum(entry["output_kg"] for entry in monthly)
        old, prior = summed(last_year, plant, "wage_bill"), summed(previous, plant, "wage_bill")
        heads = [get(month, plant, "closing") for month in months]
        old_heads = [get(month, plant, "closing") for month in last_year]
        prior_kg = summed(previous, plant, "output_kg")
        wage.append({"plant": plant, "months": monthly, "wage_bill": round(bill, 2),
                     "cost_per_kg": round(bill / kg) if kg else None,
                     "previous_cost_per_kg": round(prior / prior_kg) if previous and prior_kg else None,
                     "last_year": round(old, 2) if last_year else None, "yoy": change(bill, old) if last_year else None,
                     "previous": round(prior, 2) if previous else None,
                     "qoq": change(bill, prior) if previous else None,
                     "overtime": round(summed(months, plant, "overtime_all"), 2),
                     "overtime_last_year": round(summed(last_year, plant, "overtime_all"), 2) if last_year else None,
                     "overtime_share": percent(summed(months, plant, "overtime_all"), bill) if bill else None,
                     "per_employee_month": round(bill / (sum(heads) / len(heads)) / len(months))
                     if months and sum(heads) else None,
                     "per_employee_month_last_year": round(old / (sum(old_heads) / len(old_heads)) / len(last_year))
                     if last_year and sum(old_heads) else None})
    out["wage_bill"] = wage
    # the components of the permanent staff's pay, then expatriates and casuals: rows that add up to the wage bill
    total_now = summed(months, None, "wage_bill")
    total_before = summed(last_year, None, "wage_bill") if last_year else None
    components = [{"group": group, "now": round(summed(months, None, GROUP_FIELDS[group]), 2),
                   "last_year": round(summed(last_year, None, GROUP_FIELDS[group]), 2) if last_year else None}
                  for group in GROUPS]
    components += [{"group": name, "now": round(summed(months, None, field), 2),
                    "last_year": round(summed(last_year, None, field), 2) if last_year else None}
                   for name, field in POPULATION_ROWS]
    increase = total_now - (total_before or 0)
    for row in components:
        row["yoy"] = change(row["now"], row["last_year"]) if row["last_year"] is not None else None
        row["share_of_increase"] = percent(row["now"] - (row["last_year"] or 0), increase) \
            if last_year and increase > 0 else None
        row["share_of_bill"] = percent(row["now"], total_now) if total_now else None
    out["components"] = components
    out["components_total"] = {"now": round(sum(row["now"] for row in components), 2),
                               "last_year": round(sum(row["last_year"] or 0 for row in components), 2)
                               if last_year else None, "wage_bill": round(total_now, 2)}
    # labour cost against revenue: each plant and month at its own staff cost
    labour = []
    for plant in rows:
        revenue = summed(months, plant, "revenue")
        cost = summed(months, plant, "staff_cost_used")
        typed = summed(months, plant, "staff_cost")
        bill = summed(months, plant, "wage_bill")
        heads = [get(month, plant, "closing") for month in months]
        average = sum(heads) / len(heads) if heads else 0
        kg = summed(months, plant, "output_kg")
        old_revenue = summed(previous, plant, "revenue")
        old_cost = summed(previous, plant, "staff_cost_used")
        old_heads = [get(month, plant, "closing") for month in previous]
        old_average = sum(old_heads) / len(old_heads) if old_heads else 0
        typed_months = sum(1 for month in months for name, figures in month.items()
                           if (plant is None or name == plant) and figures.get("typed"))
        cells = sum(1 for month in months for name, figures in month.items()
                    if (plant is None or name == plant) and (figures.get("wage_bill") or figures.get("staff_cost")))
        labour.append({"plant": plant, "revenue": revenue, "staff_cost": round(cost, 2), "typed_cost": round(typed, 2),
                       "from_finance": "All" if cells and typed_months >= cells else ("Part" if typed_months else ""),
                       "share": percent(cost, revenue) if revenue else None,
                       "previous_share": percent(old_cost, old_revenue) if previous and old_revenue else None,
                       "previous_revenue": old_revenue if previous else None,
                       "monthly_share": [percent(get(month, plant, "staff_cost_used"), get(month, plant, "revenue"))
                                         if get(month, plant, "revenue") else None for month in months],
                       "revenue_per_employee": round(revenue / average) if average and revenue else None,
                       "previous_revenue_per_employee": round(old_revenue / old_average)
                       if previous and old_average and old_revenue else None,
                       "wage_per_employee": round(bill / average) if average else None,
                       "cost_per_kg": round(bill / kg) if kg else None,
                       "output_per_employee_month": round(kg / average / max(len(months), 1)) if average and kg else None})
    out["labour_cost"] = labour
    # safety: incidents (near misses apart), lost time, days lost, LTIFR
    out["safety"] = [{"plant": plant, "months": [get(month, plant, "incidents") for month in months],
                      "near_miss_months": [get(month, plant, "near_misses") for month in months],
                      "total": summed(months, plant, "incidents"),
                      "near_misses": summed(months, plant, "near_misses"),
                      "last_year": summed(last_year, plant, "incidents") if last_year else None,
                      "lost_time": summed(months, plant, "lost_time"),
                      "fatalities": summed(months, plant, "fatalities"),
                      "off_site": summed(months, plant, "off_site"),
                      "days_lost": round(summed(months, plant, "days_lost"), 1),
                      "hours_worked": round(summed(months, plant, "hours_worked"), 1),
                      "ltifr": ltifr(summed(months, plant, "lost_time") + summed(months, plant, "fatalities"),
                                     summed(months, plant, "hours_worked"))}
                     for plant in rows]
    # people: training, absence and the clock
    out["people"] = [{"plant": plant, "training_hours": round(summed(months, plant, "training_hours"), 1),
                      "training_per_employee": round(summed(months, plant, "training_hours")
                                                     / (sum(get(month, plant, "closing") for month in months)
                                                        / len(months)), 2)
                      if months and sum(get(month, plant, "closing") for month in months) else None,
                      "absence_rate": percent(summed(months, plant, "days_absent"),
                                              summed(months, plant, "attendance_days"))
                      if summed(months, plant, "attendance_days") else None,
                      "clock_share": percent(summed(months, plant, "clock_days"),
                                             summed(months, plant, "attendance_days"))
                      if summed(months, plant, "attendance_days") else None,
                      "ot_hours": round(summed(months, plant, "ot_hours"), 1)}
                     for plant in rows]
    return out


# ── A quarter in one line: what the trends and the KPIs read ──────────
SUMMARY_FIELDS = ("head_count", "permanent_share", "hires", "exits", "attrition", "casual_churn", "permanent_churn",
                  "regrettable", "wage_bill", "overtime", "overtime_share", "revenue", "staff_cost", "staff_cost_share",
                  "revenue_per_employee", "wage_per_employee", "revenue_to_wage", "cost_per_kg", "output_per_employee",
                  "incidents", "near_misses", "lost_time", "ltifr", "days_lost", "training_per_employee",
                  "absence_rate", "clock_share", "conversions")


def summary(months, plant=None):
    """One quarter (or any months) in figures: for one plant, or all of them
    with plant None. Each a number, or None where it cannot be worked out."""
    months = [complete(month) for month in months if month is not None]
    if not months:
        return dict.fromkeys(SUMMARY_FIELDS)

    def get(month, field):
        if plant is None:
            return sum(_num(figures.get(field)) for figures in month.values())
        return _num((month.get(plant) or {}).get(field))

    def total(field):
        return sum(get(month, field) for month in months)

    first, last = months[0], months[-1]
    heads = [get(month, "closing") for month in months]
    average = sum(heads) / len(heads) if heads else 0
    rates = [rate for rate in (attrition(get(month, "exits"), get(month, "opening"), get(month, "closing"))
                               for month in months) if rate is not None]
    bill, revenue, kg = total("wage_bill"), total("revenue"), total("output_kg")
    cost = total("staff_cost_used")
    revenue_head = revenue / average if average and revenue else None
    wage_head = bill / average if average and bill else None
    return {
        "head_count": get(last, "closing") if any(heads) else None,
        "permanent_share": percent(get(last, "permanent"), get(last, "closing")) if get(last, "closing") else None,
        "hires": total("hires"), "exits": total("exits"),
        "attrition": round(sum(rates) / len(rates), 1) if rates else None,
        "casual_churn": attrition(total("exits_casual"), get(first, "casual_opening"), get(last, "casual")),
        "permanent_churn": attrition(total("exits_permanent"), get(first, "permanent_opening"), get(last, "permanent")),
        "regrettable": total("regrettable"),
        "wage_bill": round(bill, 2) if bill else None,
        "overtime": round(total("overtime_all"), 2) if bill else None,
        "overtime_share": percent(total("overtime_all"), bill) if bill else None,
        "revenue": revenue or None, "staff_cost": round(cost, 2) if cost else None,
        "staff_cost_share": percent(cost, revenue) if revenue else None,
        "revenue_per_employee": round(revenue_head) if revenue_head else None,
        "wage_per_employee": round(wage_head) if wage_head else None,
        "revenue_to_wage": round(revenue_head / wage_head, 1) if revenue_head and wage_head else None,
        "cost_per_kg": round(bill / kg) if kg else None,
        "output_per_employee": round(kg / average / len(months)) if average and kg else None,
        "incidents": total("incidents"), "near_misses": total("near_misses"),
        "lost_time": total("lost_time") + total("fatalities"),
        "ltifr": ltifr(total("lost_time") + total("fatalities"), total("hours_worked")),
        "days_lost": round(total("days_lost"), 1),
        "training_per_employee": round(total("training_hours") / average, 2) if average else None,
        "absence_rate": percent(total("days_absent"), total("attendance_days")) if total("attendance_days") else None,
        "clock_share": percent(total("clock_days"), total("attendance_days")) if total("attendance_days") else None,
        "conversions": total("conversions"),
    }


def trends(quarters, plant=None):
    """[(year, quarter, summary)] for each of the quarters given:
    [(year, quarter, [three months])], oldest first."""
    return [(year, quarter, summary(months, plant)) for year, quarter, months in quarters]


def overtime_series(months_by_key):
    """[(month number, overtime of every kind, every population)] for the
    months given: {(year, month): month figures}."""
    return [(month, round(sum(_num(figures.get("overtime_all")) for figures in (snapshot or {}).values()), 2))
            for (year, month), snapshot in sorted(months_by_key.items())]


# ── Rates ─────────────────────────────────────────────────────────────
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


def ltifr(lost_time, hours):
    return round(_num(lost_time) * LTIFR_HOURS / _num(hours), 2) if _num(hours) else None


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
