# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training providers: the rules, without a Frappe import
(scripts/verify_learning_providers.py). learning_providers.py reads and
writes the site.

The brief's section 12 (18 Nov 2026): a provider's contacts, expertise,
accreditations and contracts with their expiry, its trainers, and a rating
row for each session it gave, from what that session's people said and
did. Providers are ranked on the brief's five factors, each weighed in
Learning Settings:

  cost        cost per trainee against the cheapest provider's (cheapest 100)
  quality     how the trainees rated the trainer (the evaluation form's
              trainer items)
  feedback    the trainees' overall evaluation score
  learning    the share of those assessed who passed
  impact      how the trainees applied it (level 3) and the KPIs that
              improved (level 4)
"""

import datetime

# the evaluation form's items about the trainer: the quality of delivery
TRAINER_ITEMS = ("Training methodology by the trainer", "The trainer was knowledgeable",
                 "Trainer met the training objectives / expectations")
FACTORS = ("cost", "quality", "feedback", "learning", "impact")
VALID, EXPIRING, EXPIRED = "Valid", "Expiring", "Expired"
EXPIRY_STATUSES = (VALID, EXPIRING, EXPIRED)
EXPIRY_WINDOW = 60
IN_HOUSE, EXTERNAL = "In-House", "External"
PROVIDER_TYPES = (EXTERNAL, IN_HOUSE)


def rating_row(session, ratings, results, reviews, impacts):
    """One session's rating of its provider.

    session: {"name", "training_program", "day", "trainees", "cost", "evaluation_score"}
    ratings: [{"item", "rating"}] of its evaluation forms (Excellent 5 .. Below Average 1)
    results: [{"effective"}]; reviews: [{"status", "score"}]; impacts: [{"result"}]"""
    values = {"Excellent": 5, "Very Good": 4, "Good": 3, "Average": 2, "Below Average": 1}
    trainer = [values[row["rating"]] for row in ratings or () if row.get("item") in TRAINER_ITEMS
               and row.get("rating") in values]
    judged = [row for row in results or () if row.get("effective") in ("Effective", "Not Effective")]
    done = [row for row in reviews or () if row.get("status") == "Done"]
    measured = [row for row in impacts or () if row.get("result")]
    application = round(sum(_num(row.get("score")) for row in done) / len(done), 1) if done else None
    improved = round(100.0 * sum(1 for row in measured if row.get("result") == "Improved") / len(measured), 1) \
        if measured else None
    impact = [value for value in (application, improved) if value is not None]
    trainees = int(_num(session.get("trainees")))
    return {
        "training_event": session.get("name"), "training_program": session.get("training_program"),
        "session_date": session.get("day"), "trainees": trainees, "cost": round(_num(session.get("cost")), 2),
        "cost_per_trainee": round(_num(session.get("cost")) / trainees, 2) if trainees else 0.0,
        "quality": round(100.0 * sum(trainer) / (5 * len(trainer)), 1) if trainer else None,
        "feedback": round(_num(session.get("evaluation_score")), 1) if session.get("evaluation_score") else None,
        "learning": round(100.0 * sum(1 for row in judged if row["effective"] == "Effective") / len(judged), 1)
        if judged else None,
        "impact": round(sum(impact) / len(impact), 1) if impact else None,
    }


def provider_figures(rows):
    """A provider's figures over its rating rows: sessions, trainees, spend,
    cost per trainee and the average of each factor with data."""
    rows = list(rows or ())
    trainees = sum(int(_num(row.get("trainees"))) for row in rows)
    spend = round(sum(_num(row.get("cost")) for row in rows), 2)
    out = {"sessions": len(rows), "trainees": trainees, "spend": spend,
           "cost_per_trainee": round(spend / trainees, 2) if trainees else None}
    for factor in ("quality", "feedback", "learning", "impact"):
        values = [_num(row.get(factor)) for row in rows if row.get(factor) not in (None, "")]
        out[factor] = round(sum(values) / len(values), 1) if values else None
    return out


def rank(providers, weights):
    """Each provider's factor scores and weighted score, best first; those
    with no score last. providers: {name: provider_figures(...)}.
    weights: {factor: weight}. The cost score is the cheapest cost per
    trainee over this one's (the cheapest 100)."""
    costs = [figures["cost_per_trainee"] for figures in providers.values() if figures.get("cost_per_trainee")]
    cheapest = min(costs) if costs else None
    ranked = []
    for name, figures in providers.items():
        scores = {"cost": round(100.0 * cheapest / figures["cost_per_trainee"], 1)
                  if cheapest and figures.get("cost_per_trainee") else None}
        for factor in ("quality", "feedback", "learning", "impact"):
            scores[factor] = figures.get(factor)
        have = [(_num(scores[factor]), _num(weights.get(factor))) for factor in FACTORS
                if scores[factor] is not None and _num(weights.get(factor)) > 0]
        total = sum(weight for _value, weight in have)
        score = round(sum(value * weight for value, weight in have) / total, 1) if total else None
        ranked.append(dict(figures, provider=name, score=score, **{factor + "_score": scores[factor]
                                                                   for factor in FACTORS}))
    ranked.sort(key=lambda row: (row["score"] is None, -(row["score"] or 0), row["provider"]))
    for position, row in enumerate(ranked, 1):
        row["rank"] = position if row["score"] is not None else 0
    return ranked


def trend(rows, recent=3):
    """Whether a provider's ratings are falling: the average of its last
    `recent` sessions' factors against the ones before. None without enough."""
    scored = [row for row in sorted(rows or (), key=lambda row: str(row.get("session_date") or ""))
              if session_score(row) is not None]
    if len(scored) < recent + 1:
        return None
    last = [session_score(row) for row in scored[-recent:]]
    before = [session_score(row) for row in scored[:-recent]]
    return round(sum(last) / len(last) - sum(before) / len(before), 1)


def session_score(row):
    values = [_num(row.get(factor)) for factor in ("quality", "feedback", "learning", "impact")
              if row.get(factor) not in (None, "")]
    return round(sum(values) / len(values), 1) if values else None


def expiry_status(expiry, today, window=EXPIRY_WINDOW):
    """Valid, Expiring within the window, Expired; Valid where it does not expire."""
    expiry, today = _date(expiry), _date(today)
    if not expiry:
        return VALID
    if expiry < today:
        return EXPIRED
    return EXPIRING if (expiry - today).days <= window else VALID


def provider_errors(doc):
    errors = []
    for row in doc.get("accreditations") or ():
        if _date(row.get("valid_from")) and _date(row.get("expiry_date")) and \
                _date(row.get("expiry_date")) < _date(row.get("valid_from")):
            errors.append("An accreditation cannot run out before it starts.")
            break
    for row in doc.get("contracts") or ():
        if _date(row.get("start_date")) and _date(row.get("end_date")) and \
                _date(row.get("end_date")) < _date(row.get("start_date")):
            errors.append("A contract cannot end before it starts.")
            break
    return errors


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
