# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LMS phase 5, value: the rules, without a Frappe import
(scripts/verify_learning_value.py). learning_value.py reads and writes the
site.

The blueprint's section 4.10 (17 Nov 2026): from what a training cost to what
it brought.

  costs        each session's costs, line by line (trainer, venue,
               transport, meals, materials, certification, other), and the
               time of the trainees who came, worked out from their section's
               labour cost per person-shift over the hours of a shift
  budget       a year's training budget for a company, a plant or a
               department: spent (sessions held), committed (sessions still
               to be held: their costs typed, else the programme's cost per
               person for each invited), what remains, how much is used. HR
               and Finance are told once when it reaches its alert level
  ROI          a programme's benefit (the Training Impact Reviews') over its
               cost; where no benefit is valued, a benefit score from the four
               levels: reaction 20, learning 20, behaviour 30, results 30, those
               with data re-weighted
  providers    ranked by their benefit score, then their cost per trainee
  health       a plant's learning and capability health: required training
               done, certificates valid, attendance, reaction, application,
               competency and critical skills cover, equally weighted over
               those with data
"""

COST_TYPES = ("Trainer", "Venue", "Transport", "Meals", "Materials", "Certification", "Other")
WITHIN, NEAR, OVER = "Within Budget", "Near the Limit", "Over Budget"
BUDGET_STATUSES = (WITHIN, NEAR, OVER)
BENEFIT_WEIGHTS = (("reaction", 20), ("pass_rate", 20), ("application", 30), ("kpi_share", 30))
HEALTH_PARTS = (("compliance", "Required Training Done"), ("certificates", "Certificates Valid"),
                ("attendance", "Attendance"), ("reaction", "Reaction"), ("application", "Application"),
                ("competency", "Competency"), ("cover", "Critical Skills Covered"))


def direct_cost(lines):
    return round(sum(_num(line.get("amount")) for line in lines or ()), 2)


def hourly_rate(labour_rate, shift_hours):
    """A person-hour's cost from the section's labour cost per person-shift."""
    return _num(labour_rate) / _num(shift_hours) if _num(labour_rate) and _num(shift_hours) else 0.0


def time_cost(trainee_rates, hours):
    """The trainees' time: each one who came, the session's hours at their rate."""
    return round(sum(_num(rate) for rate in trainee_rates or ()) * _num(hours), 2)


def session_cost(lines, trainee_rates, hours, attended):
    direct = direct_cost(lines)
    spent_time = time_cost(trainee_rates, hours)
    total = round(direct + spent_time, 2)
    return {"direct": direct, "time": spent_time, "total": total,
            "per_trainee": round(total / attended, 2) if attended else 0.0}


def planned_cost(lines, cost_per_person, invited):
    """A session still to be held: its costs typed, else the programme's cost per
    person for each one invited."""
    typed = direct_cost(lines)
    return typed if typed else round(_num(cost_per_person) * int(_num(invited)), 2)


def in_scope(budget, event):
    """Whether a session counts against a budget: the budget's company and year,
    its plant and department if it names them."""
    if budget.get("company") and budget.get("company") != event.get("company"):
        return False
    if int(_num(budget.get("year"))) != int(_num(event.get("year"))):
        return False
    for field, key in (("branch", "branch"), ("department", "department")):
        if budget.get(field) and budget.get(field) != event.get(key):
            return False
    return True


def budget_state(amount, spent, committed, alert_at):
    used = _num(spent) + _num(committed)
    utilisation = round(100.0 * used / _num(amount), 1) if _num(amount) else None
    if utilisation is None:
        status = WITHIN
    elif utilisation > 100:
        status = OVER
    elif utilisation >= _num(alert_at):
        status = NEAR
    else:
        status = WITHIN
    return {"spent": round(_num(spent), 2), "committed": round(_num(committed), 2),
            "remaining": round(_num(amount) - used, 2), "utilisation": utilisation or 0.0, "status": status}


def newly_alerting(alerted, status):
    """(tell now, alerted after): told once on reaching the alert level; the
    mark comes off when it falls back below."""
    reached = status in (NEAR, OVER)
    return reached and not int(_num(alerted)), int(reached)


def roi(benefit, cost):
    if not _num(benefit) or not _num(cost):
        return None
    return round(100.0 * (_num(benefit) - _num(cost)) / _num(cost), 1)


def benefit_score(levels):
    """The four levels weighed: reaction 20, learning 20, behaviour 30, results
    30, re-weighted over those with data. `levels` holds percentages."""
    have = [(_num(levels.get(key)), weight) for key, weight in BENEFIT_WEIGHTS if levels.get(key) is not None]
    total = sum(weight for _value, weight in have)
    return round(sum(value * weight for value, weight in have) / total, 1) if total else None


def kpi_share(kpis, improved):
    return round(100.0 * improved / kpis, 1) if kpis else None


def rank_providers(rows):
    """Best first: the higher benefit score, then the lower cost per trainee;
    those with no score last."""
    return sorted(rows, key=lambda row: (row.get("score") is None, -(row.get("score") or 0),
                                         _num(row.get("per_trainee")), str(row.get("provider") or "")))


def health(parts, green=85, amber=65):
    """(score, status) over the parts with data, each a percentage."""
    have = [_num(parts[key]) for key, _label in HEALTH_PARTS if parts.get(key) is not None]
    if not have:
        return None, "No Data"
    score = round(sum(have) / len(have), 1)
    return score, ("Healthy" if score >= green else "Watch" if score >= amber else "At Risk")


def percent(part, whole):
    return round(100.0 * _num(part) / _num(whole), 1) if _num(whole) else None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# ── Budget lines, actuals and the forecast (18 Nov 2026) ──────────────
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
# how the Budget vs Actual report groups: (label, the key of a line, an actual or a commitment)
GROUP_BY = (("Plant", "branch"), ("Department", "department"), ("Category", "training_category"),
            ("Programme", "training_program"), ("Provider", "provider"), ("Month", "month"),
            ("Cost Type", "cost_type"), ("Cost Centre", "cost_center"))
GROUP_KEY = dict(GROUP_BY)


def lines_total(lines):
    return round(sum(_num(line.get("amount")) for line in lines or ()), 2)


def line_errors(lines):
    errors = []
    for line in lines or ():
        if _num(line.get("amount")) <= 0:
            errors.append("Every budget line needs an amount.")
            break
        if line.get("month") and line.get("month") not in MONTHS:
            errors.append("A line's month is one of the twelve.")
            break
    return errors


def month_of(day):
    """The month's name of a date (a datetime, a date or its text)."""
    text = str(day or "")[:10]
    try:
        return MONTHS[int(text[5:7]) - 1]
    except (ValueError, IndexError):
        return None


def budget_vs_actual(lines, actuals, commitments, key, this_month):
    """The budget, what was spent, what is committed, the forecast and what
    remains, grouped by `key` (GROUP_KEY's values).

    lines:       [{key..., "month", "amount"}] the budget lines
    actuals:     [{key..., "month", "amount"}] what sessions held cost
    commitments: [{key..., "month", "amount"}] what sessions to come are expected to cost
    this_month:  the month number today (1 to 12): a month before it is closed

    The forecast of a group is, month by month, what was spent where the month
    is closed, else the larger of the month's budget and what is spent and
    committed in it."""
    cells = {}

    def add(rows, field):
        for row in rows or ():
            group = row.get(key) or ""
            month = row.get("month") or ""
            cell = cells.setdefault(group, {}).setdefault(month, {"budget": 0.0, "actual": 0.0, "committed": 0.0})
            cell[field] += _num(row.get("amount"))

    add(lines, "budget")
    add(actuals, "actual")
    add(commitments, "committed")
    out = []
    for group, months in cells.items():
        budget = sum(cell["budget"] for cell in months.values())
        actual = sum(cell["actual"] for cell in months.values())
        committed = sum(cell["committed"] for cell in months.values())
        forecast = 0.0
        for month, cell in months.items():
            number = MONTHS.index(month) + 1 if month in MONTHS else None
            if number and number < int(this_month):
                forecast += cell["actual"]
            else:
                forecast += max(cell["budget"], cell["actual"] + cell["committed"])
        out.append({"group": group, "budget": round(budget, 2), "actual": round(actual, 2),
                    "committed": round(committed, 2), "forecast": round(forecast, 2),
                    "remaining": round(budget - actual - committed, 2),
                    "utilisation": round(100.0 * (actual + committed) / budget, 1) if budget else None,
                    "variance": round(budget - forecast, 2)})
    return sorted(out, key=lambda row: (-row["budget"], str(row["group"])))


def calendar_check(planned, remaining):
    """What a calendar's planned spend leaves of the budget: (over, by how much)."""
    if remaining is None:
        return False, 0.0
    over = _num(planned) - _num(remaining)
    return over > 0, round(max(over, 0.0), 2)
