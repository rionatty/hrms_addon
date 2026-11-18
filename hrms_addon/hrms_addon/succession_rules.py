# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Succession in depth (the talent blueprint, section 6): what losing each
critical role's holder would cost and how likely it is, how deep the bench
is across the roles, who is named for several roles at once, the talent
pools successors are drawn from, and flight risk kept as a history.

No Frappe import (scripts/verify_succession_risk.py); succession_risk.py,
talent_pools.py and retention.py read and write the site.

ROLE RISK = PROBABILITY OF LOSS x IMPACT

  probability  the likeliest way the holder goes: an exit already raised,
               a retirement date inside the window Talent Settings give, or
               the flight risk last assessed for them (High, Medium, Low)
  impact       the role's Criticality Factor rows, each 1 to 5, weighed as
               the factor says (a single point of failure, output at stake,
               safety, how long it takes to fill from outside...)
  risk         probability x impact, out of a hundred; High from 45, Medium
               from 20. Without any factor rows the role keeps the risk HR
               typed, as before

The heat map lays the roles on three bands of each: probability (under a
quarter, under a half, a half and over) by impact (under 2.5, under 3.75,
3.75 and over).
"""

import datetime

READY_NOW, READY_SOON, EMERGING, GAP = "Ready Now", "Ready in 1-2 Years", "Emerging", "Gap"
READINESS = (READY_NOW, READY_SOON, EMERGING, GAP)
LEVELS = ("Low", "Medium", "High")
RISKS = ("High", "Medium", "Low")
# how likely the holder is to go, by what is known
PROBABILITY = {"exit": 1.0, "retirement": 0.8, "High": 0.6, "Medium": 0.35, "Low": 0.1, None: 0.05}
RETIREMENT_MONTHS = 24
HIGH_FROM, MEDIUM_FROM = 45.0, 20.0
COUNCIL_DECISIONS = ("Endorsed", "Develop First", "Not Endorsed")
FACTOR_SEED = (
    ("Single point of failure", 2, "Nobody else can do the work today"),
    ("Output at stake", 1.5, "Production, quality or revenue lost while the role is empty"),
    ("Safety and compliance", 1.5, "Licences, safety duties or regulatory sign-off the role carries"),
    ("Time to fill from outside", 1, "Months to recruit and bring a newcomer up to speed"),
    ("Specialist knowledge", 1, "Process, machine or customer knowledge held by the holder"),
)


# ── Role risk ─────────────────────────────────────────────────────────
def loss_probability(facts, today, settings=None):
    """(probability 0 to 1, [reasons]) of losing the holder. facts: "exit_due"
    (an exit raised), "retirement" (the date of retirement), "flight_risk"
    (High, Medium, Low or none), "holder" (somebody holds the role)."""
    settings = settings or {}
    chances = dict(PROBABILITY)
    for level, key in (("High", "probability_high"), ("Medium", "probability_medium"), ("Low", "probability_low")):
        if settings.get(key) not in (None, ""):
            chances[level] = max(0.0, min(1.0, _number(settings[key]) / 100.0))
    months = int(_number(settings.get("retirement_months"))) or RETIREMENT_MONTHS
    if not facts.get("holder"):
        return 1.0, ["Nobody holds the role"]
    found = []
    if facts.get("exit_due"):
        found.append((chances["exit"], "Exit raised for %s" % str(facts["exit_due"])[:10]))
    retires = _day(facts.get("retirement"))
    start = _day(today)
    if retires and start and retires >= start and (retires - start).days <= months * 30.5:
        found.append((chances["retirement"], "Retires on %s" % retires.isoformat()))
    risk = facts.get("flight_risk")
    if risk in ("High", "Medium", "Low"):
        found.append((chances[risk], "Flight risk %s" % risk))
    if not found:
        return chances[None], ["Nothing known"]
    found.sort(key=lambda item: -item[0])
    return round(found[0][0], 2), [reason for _chance, reason in found]


def impact(rows, weights=None):
    """The role's impact, 1 to 5: its Criticality Factor rows weighed as each
    factor says (1 where it says nothing). None without any row."""
    given = [(_number(row.get("score")), _number((weights or {}).get(row.get("factor"), 1.0)) or 1.0)
             for row in rows or [] if _number(row.get("score")) > 0]
    total = sum(weight for _score, weight in given)
    if not given or not total:
        return None
    return round(sum(score * weight for score, weight in given) / total, 2)


def factor_errors(rows):
    errors = []
    seen = set()
    for row in rows or []:
        if not row.get("factor"):
            errors.append("A criticality row names its factor.")
            continue
        if row["factor"] in seen:
            errors.append("%s is scored twice." % row["factor"])
        seen.add(row["factor"])
        if not 1 <= _number(row.get("score")) <= 5:
            errors.append("%s is scored 1 to 5." % row["factor"])
    return errors


def role_risk(probability, impact_score):
    """Probability x impact, out of a hundred; None without an impact."""
    if impact_score in (None, ""):
        return None
    return round(_number(probability) * _number(impact_score) * 20.0, 1)


def risk_level(score, typed=None):
    """High, Medium or Low from the score; the typed one without a score."""
    if score in (None, ""):
        return typed
    score = _number(score)
    return "High" if score >= HIGH_FROM else "Medium" if score >= MEDIUM_FROM else "Low"


def probability_band(probability):
    probability = _number(probability)
    return "High" if probability >= 0.5 else "Medium" if probability >= 0.25 else "Low"


def impact_band(score):
    score = _number(score)
    return "High" if score >= 3.75 else "Medium" if score >= 2.5 else "Low"


def heat_map(roles):
    """The roles laid on impact (rows, High first) by probability (columns,
    Low first): {"rows": [{"impact", "cells": [{"probability", "count",
    "roles": [names]}]}], "unscored": n}. roles: [{"name", "probability",
    "impact"}]; a role with no impact is counted apart."""
    cells = {(i, p): [] for i in LEVELS for p in LEVELS}
    unscored = 0
    for role in roles or []:
        if role.get("impact") in (None, "") or not _number(role.get("impact")):
            unscored += 1
            continue
        cells[(impact_band(role["impact"]), probability_band(role.get("probability")))].append(role.get("name"))
    return {"rows": [{"impact": i, "cells": [{"probability": p, "count": len(cells[(i, p)]), "roles": cells[(i, p)]}
                                             for p in LEVELS]} for i in reversed(LEVELS)],
            "unscored": unscored}


# ── The bench across the roles ────────────────────────────────────────
def bench_index(roles):
    """How deep the bench is across the critical roles. roles: [{"ready_now",
    "successors"}], successors counting everyone named but a Gap. Returns
    {"roles", "ready_now", "ready_now_share", "two_or_more", "two_share",
    "none", "none_share"}."""
    rows = list(roles or [])
    total = len(rows)
    ready = len([row for row in rows if int(_number(row.get("ready_now")))])
    two = len([row for row in rows if int(_number(row.get("successors"))) >= 2])
    none = len([row for row in rows if not int(_number(row.get("successors")))])
    return {"roles": total, "ready_now": ready, "ready_now_share": _share(ready, total), "two_or_more": two,
            "two_share": _share(two, total), "none": none, "none_share": _share(none, total)}


def overlap(candidates):
    """Successors named for more than one role: {employee: [roles]}.
    candidates: [{"employee", "position"}]."""
    found = {}
    for row in candidates or []:
        if row.get("employee") and row.get("position"):
            roles = found.setdefault(row["employee"], [])
            if row["position"] not in roles:
                roles.append(row["position"])
    return {employee: roles for employee, roles in found.items() if len(roles) > 1}


def candidate_errors(rows, incumbent=None, levels=None):
    """What the bench's rows must carry beyond a name: a readiness the
    Readiness Levels know, a rank each once, a target date for anybody not
    ready now, a council decision of the known ones."""
    errors = []
    levels = set(levels or READINESS)
    ranks = []
    for row in rows or []:
        who = row.get("employee_name") or row.get("employee") or "A successor"
        if row.get("readiness") and row["readiness"] not in levels:
            errors.append("%s: %s is not a readiness level." % (who, row["readiness"]))
        rank = int(_number(row.get("rank")))
        if rank:
            if rank in ranks:
                errors.append("Rank %d is given twice." % rank)
            ranks.append(rank)
        if row.get("council_decision") and row["council_decision"] not in COUNCIL_DECISIONS:
            errors.append("%s: the council's decision is one of %s." % (who, ", ".join(COUNCIL_DECISIONS)))
        if row.get("employee") and row.get("employee") == incumbent:
            errors.append("The incumbent cannot succeed themselves.")
    return errors


def ranked(rows):
    """The bench in the order the council ranked it, the unranked after,
    readiest first."""
    order = {name: index for index, name in enumerate(READINESS)}
    return sorted(rows or [], key=lambda row: (int(_number(row.get("rank"))) or 999,
                                               order.get(row.get("readiness"), 9),
                                               str(row.get("employee_name") or row.get("employee") or "")))


def next_ranks(rows):
    """Ranks for the unranked rows, after the highest given."""
    top = max([int(_number(row.get("rank"))) for row in rows or []] or [0])
    out = []
    for row in rows or []:
        if not int(_number(row.get("rank"))):
            top += 1
            out.append((row, top))
    return out


# ── Talent pools ──────────────────────────────────────────────────────
POOL_TYPES = ("Leadership", "Technical Specialist", "Critical Role", "High Potential", "Graduate")
PROPOSED, CONFIRMED, EXITED = "Proposed", "Confirmed", "Exited"
MEMBER_STATES = (PROPOSED, CONFIRMED, EXITED)


def eligible(box, boxes):
    """Whether a placement's box is one the pool draws from (any box where
    the pool names none)."""
    boxes = {int(_number(item)) for item in boxes or () if int(_number(item))}
    return not boxes or int(_number(box)) in boxes


def members_to_add(placements, existing, boxes):
    """The placements a pool takes in: finalised, in an eligible box, and not
    an active member already. placements: [{"employee", "box", ...}]."""
    active = {row.get("employee") for row in existing or [] if row.get("status") != EXITED}
    out, seen = [], set()
    for row in placements or []:
        employee = row.get("employee")
        if not employee or employee in active or employee in seen or not eligible(row.get("box"), boxes):
            continue
        seen.add(employee)
        out.append(row)
    return out


def member_errors(before, after):
    """A pool keeps its history: a confirmed member is exited, with the day
    and the reason, never taken off; an exit has its day and reason.
    before, after: [{"name", "employee", "status", "exited_on", "exit_reason"}]."""
    errors = []
    kept = {row.get("name") for row in after or [] if row.get("name")}
    for row in before or []:
        if row.get("status") in (CONFIRMED, EXITED) and row.get("name") not in kept:
            errors.append("%s was confirmed in the pool. Exit them rather than take them off."
                          % (row.get("employee_name") or row.get("employee")))
    seen = set()
    for row in after or []:
        who = row.get("employee_name") or row.get("employee") or "A member"
        if row.get("status") != EXITED:
            if row.get("employee") in seen:
                errors.append("%s is in the pool twice." % who)
            seen.add(row.get("employee"))
        if row.get("status") == EXITED and not (row.get("exited_on") and _text(row.get("exit_reason"))):
            errors.append("%s: say when and why they left the pool." % who)
        if row.get("status") and row["status"] not in MEMBER_STATES:
            errors.append("%s: a member is Proposed, Confirmed or Exited." % who)
    return errors


def pool_fits(target_roles, designation):
    """Whether a pool is grown for a role: it names that role, or none."""
    roles = [role for role in target_roles or () if role]
    return not roles or designation in roles


# ── Flight risk, as a history ─────────────────────────────────────────
def alert_needed(top_talent, risk, watched, alerted_level=None):
    """Whether a flight-risk assessment is told to HR and the council: top
    talent at a watched level, and not already told at this level or worse
    since the last time it was lower."""
    if not top_talent or risk not in (watched or ()):
        return False
    order = {"High": 0, "Medium": 1, "Low": 2}
    if alerted_level and order.get(alerted_level, 9) <= order.get(risk, 9):
        return False
    return True


def retention_errors(rows):
    """Each retention action: what is done about which driver, by whom and
    by when; a closed one says how it went."""
    errors = []
    for number, row in enumerate(rows or [], 1):
        if not _text(row.get("action")):
            errors.append("Retention action %d says nothing to do." % number)
        if row.get("status") in ("Done", "Dropped") and not _text(row.get("outcome")):
            errors.append("Retention action %d is %s: say how it went." % (number, str(row["status"]).lower()))
        if _number(row.get("cost")) < 0:
            errors.append("Retention action %d: the cost is not below 0." % number)
    return errors


def open_retention(rows, today):
    """(open, overdue) retention actions."""
    live = [row for row in rows or [] if row.get("status") not in ("Done", "Dropped")]
    late = [row for row in live if row.get("due") and str(row["due"])[:10] < str(today)[:10]]
    return len(live), len(late)


# ── Small helpers ─────────────────────────────────────────────────────
def _share(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))


def _day(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "")[:10]
    try:
        return datetime.date(*(int(part) for part in text.split("-"))) if text else None
    except (TypeError, ValueError):
        return None
