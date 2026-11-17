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
