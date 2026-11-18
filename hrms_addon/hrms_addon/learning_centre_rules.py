# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Learning Command Centre: the rules, without a Frappe import
(scripts/verify_learning_centre.py). learning_centre.py reads the site.

The brief's sections 21, 22 and 27 (18 Nov 2026): one set of counts per
plant and department (Learning Snapshot, kept each month), from which every
figure, the Learning Health Score and its nine parts, the plants side by side,
the trends and the insights are worked out the same way.

  counts      what the database counted: headcount, required and done (all,
              and mandatory), overdue, certificates valid, expiring and run
              out, people trained, hours, attended and marked, assessed and
              passed, competent and assessed skills, critical skills covered,
              application reviews, KPIs, spend and budget
  health      the nine parts as percentages, each weighed in Learning
              Settings, over those with data
  insights    findings drawn from the counts by fixed rules, each linking to
              the list behind it: no outside service
"""

COUNTS = ("headcount", "required", "done", "overdue", "due_soon", "mandatory_required", "mandatory_done",
          "cert_valid", "cert_expiring", "cert_expired", "trained", "hours", "sessions", "attended", "marked",
          "assessed", "passed", "competent", "skills_assessed", "critical_ok", "critical_total", "reviews_done",
          "review_score", "kpis_measured", "kpis_improved", "spend", "budget")
PARTS = ("mandatory", "certification", "coverage", "competency", "attendance", "assessment", "effectiveness",
         "budget_use", "critical")
# the settings' keys of the parts (learning_rules.HEALTH_PARTS), in the same order
PART_SETTING = dict(zip(PARTS, ("mandatory", "certification", "coverage", "competency", "attendance", "assessment",
                                "effectiveness", "budget", "critical")))
HEALTHY, WATCH, AT_RISK, NO_DATA = "Healthy", "Watch", "At Risk", "No Data"
HIGH, MEDIUM, LOW = "High", "Medium", "Low"


def blank():
    return {key: 0.0 for key in COUNTS}


def add(into, counts):
    """Counts summed: a plant from its departments, the company from its plants."""
    for key in COUNTS:
        into[key] = round(_num(into.get(key)) + _num(counts.get(key)), 2)
    return into


def share(part, whole):
    return round(100.0 * _num(part) / _num(whole), 1) if _num(whole) else None


def budget_use(spend, budget):
    """How close spend runs to the budget for the period: 100 on budget,
    less the further it runs over or under. None without a budget."""
    if not _num(budget):
        return None
    return round(max(0.0, 100.0 - abs(_num(spend) - _num(budget)) * 100.0 / _num(budget)), 1)


def parts_of(counts):
    """The nine parts of the health score, as percentages (None: no data)."""
    reviews = _num(counts.get("review_score")) / _num(counts.get("reviews_done")) if _num(counts.get("reviews_done")) \
        else None
    improved = share(counts.get("kpis_improved"), counts.get("kpis_measured"))
    effectiveness = [value for value in (reviews, improved) if value is not None]
    return {
        "mandatory": share(counts.get("mandatory_done"), counts.get("mandatory_required")),
        "certification": share(counts.get("cert_valid"), _num(counts.get("cert_valid")) + _num(counts.get("cert_expired"))),
        "coverage": share(counts.get("trained"), counts.get("headcount")),
        "competency": share(counts.get("competent"), counts.get("skills_assessed")),
        "attendance": share(counts.get("attended"), counts.get("marked")),
        "assessment": share(counts.get("passed"), counts.get("assessed")),
        "effectiveness": round(sum(effectiveness) / len(effectiveness), 1) if effectiveness else None,
        "budget_use": budget_use(counts.get("spend"), counts.get("budget")),
        "critical": share(counts.get("critical_ok"), counts.get("critical_total")),
    }


def health(parts, weights, green=85, amber=65):
    """(score, status): the parts with data weighed (weights by PARTS' keys
    or the settings' own), re-weighed over those with data."""
    have = []
    for key in PARTS:
        weight = weights.get(key, weights.get(PART_SETTING[key]))
        if parts.get(key) is not None and _num(weight) > 0:
            have.append((_num(parts[key]), _num(weight)))
    total = sum(weight for _value, weight in have)
    if not total:
        return None, NO_DATA
    score = round(sum(value * weight for value, weight in have) / total, 1)
    return score, HEALTHY if score >= _num(green) else WATCH if score >= _num(amber) else AT_RISK


def figures(counts):
    """The tiles' figures from a set of counts."""
    return {
        "headcount": int(_num(counts.get("headcount"))), "trained": int(_num(counts.get("trained"))),
        "coverage": share(counts.get("trained"), counts.get("headcount")),
        "compliance": share(counts.get("done"), counts.get("required")),
        "mandatory": share(counts.get("mandatory_done"), counts.get("mandatory_required")),
        "certification": share(counts.get("cert_valid"), _num(counts.get("cert_valid")) + _num(counts.get("cert_expired"))),
        "expiring": int(_num(counts.get("cert_expiring"))), "expired": int(_num(counts.get("cert_expired"))),
        "overdue": int(_num(counts.get("overdue"))), "hours": round(_num(counts.get("hours")), 1),
        "spend": round(_num(counts.get("spend")), 2), "budget": round(_num(counts.get("budget")), 2),
        "budget_used": share(counts.get("spend"), counts.get("budget")),
        "cost_per_employee": round(_num(counts.get("spend")) / _num(counts.get("trained")), 2)
        if _num(counts.get("trained")) else None,
        "attendance": share(counts.get("attended"), counts.get("marked")),
        "pass_rate": share(counts.get("passed"), counts.get("assessed")),
        "competency": share(counts.get("competent"), counts.get("skills_assessed")),
    }


def month_series(snapshots, key):
    """[(month label, value)] of a figure over the months kept, in order.
    snapshots: [{"month_start", ...counts}]."""
    out = []
    for row in sorted(snapshots or (), key=lambda row: str(row.get("month_start"))):
        value = figures(row).get(key) if key in figures(blank()) else parts_of(row).get(key)
        out.append((str(row.get("month_start"))[:7], value))
    return out


# ── Insights ──────────────────────────────────────────────────────────
def insights(lines, programmes=(), covers=(), budgets=(), providers=(), threshold=85, pass_floor=60,
             provider_drop=-5):
    """Findings drawn from the data by fixed rules, the most pressing first:
    [{"severity", "text", "route", "filters"}].

    lines:      [{"branch", "department", counts...}] plant and department counts
    programmes: [{"training_program", "assessed", "pass_rate", "held", "behaviour_on", "reviews_done"}]
    covers:     [{"skill", "branch", "status", "critical"}]
    budgets:    [{"name", "status", "utilisation"}]
    providers:  [{"name", "trend", "score"}]"""
    found = []
    plants = {}
    for line in lines or ():
        add(plants.setdefault(line.get("branch") or "", blank()), line)
    for plant, counts in sorted(plants.items()):
        done = share(counts["done"], counts["required"])
        if done is not None and done < threshold:
            found.append({"severity": HIGH if done < threshold - 20 else MEDIUM,
                          "text": "%s: %g%% of required training done, below %g%%." % (plant or "No plant", done,
                                                                                        threshold),
                          "route": ["query-report", "Training Compliance"], "filters": {"branch": plant}})
        if counts["cert_expiring"]:
            found.append({"severity": MEDIUM,
                          "text": "%s: %d certificate(s) run out within 90 days." % (plant or "No plant",
                                                                                     counts["cert_expiring"]),
                          "route": ["query-report", "Certification Expiry"], "filters": {"branch": plant}})
        if counts["cert_expired"]:
            found.append({"severity": HIGH, "text": "%s: %d certificate(s) have run out." % (
                plant or "No plant", counts["cert_expired"]),
                "route": ["List", "Employee Certification"], "filters": {"status": "Expired", "branch": plant}})
    worst = sorted((line for line in lines or () if line.get("department") and _num(line.get("required"))),
                   key=lambda line: share(line.get("done"), line.get("required")))[:3]
    for line in worst:
        done = share(line.get("done"), line.get("required"))
        if done is not None and done < threshold:
            found.append({"severity": MEDIUM, "text": "%s, %s: %g%% done, %d overdue." % (
                line.get("department"), line.get("branch") or "", done, int(_num(line.get("overdue")))),
                "route": ["List", "Employee Training Requirement"],
                "filters": {"department": line.get("department"), "status": "Overdue"}})
    for row in programmes or ():
        if row.get("pass_rate") is not None and _num(row.get("assessed")) >= 3 and _num(row["pass_rate"]) < pass_floor:
            found.append({"severity": MEDIUM, "text": "%s: only %g%% passed." % (row["training_program"], row["pass_rate"]),
                          "route": ["query-report", "Training Effectiveness"], "filters": {}})
        if row.get("behaviour_on") and _num(row.get("held")) and not _num(row.get("reviews_done")):
            found.append({"severity": LOW, "text": "%s: held, but no supervisor has said how it is applied." %
                          row["training_program"], "route": ["List", "Application Review Sheet"],
                          "filters": {"training_program": row["training_program"]}})
    for row in covers or ():
        if row.get("critical") and row.get("status") in ("No Cover", "Single Point of Failure"):
            found.append({"severity": HIGH, "text": "%s at %s: %s." % (row["skill"], row.get("branch") or "every plant",
                                                                        row["status"].lower()),
                          "route": ["query-report", "Skills Cover"], "filters": {"branch": row.get("branch") or ""}})
    for row in budgets or ():
        if row.get("status") in ("Near the Limit", "Over Budget"):
            found.append({"severity": HIGH if row["status"] == "Over Budget" else MEDIUM,
                          "text": "Training budget %s is %g%% used." % (row["name"], _num(row.get("utilisation"))),
                          "route": ["Form", "Training Budget", row["name"]], "filters": {}})
    for row in providers or ():
        if row.get("trend") is not None and _num(row["trend"]) <= provider_drop:
            found.append({"severity": LOW, "text": "%s: ratings falling (%g points)." % (row["name"], _num(row["trend"])),
                          "route": ["Form", "Training Provider", row["name"]], "filters": {}})
    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    return sorted(found, key=lambda item: order[item["severity"]])


def view_for(roles):
    """The version of the centre a user opens on: the company's for HR and
    management, a plant's, a department's, a supervisor's team, or the
    employee's own."""
    roles = set(roles or ())
    if roles & {"HR Manager", "System Manager", "General Manager", "Executive Director", "Management Viewer",
                "Auditor"}:
        return "Company"
    if roles & {"HR User", "Plant Manager", "Branch Manager"}:
        return "Plant"
    if "Head of Department" in roles:
        return "Department"
    if "Supervisor" in roles:
        return "My Team"
    return "My Learning"


VIEWS = ("Company", "Plant", "Department", "My Team", "My Learning")


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
