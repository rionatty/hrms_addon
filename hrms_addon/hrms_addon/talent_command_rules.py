# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Talent Command page and the Talent Council pack: what the
executives read about talent, laid out from figures the site adds up in
SQL (talent_command.py).

No Frappe import (scripts/verify_talent_command.py).

  side_by_side   each plant (or department) on the nine boxes, its share of
                 each box against the distribution guide and against the
                 same group in the review before
  kpis           the tiles across the top
  board_figures  what the HR board pack reads about talent: the risk in the
                 talent and the cover behind the critical roles
"""

BOXES = tuple(range(1, 10))
TOP = (6, 8, 9)
WATCHED = ("High", "Medium")


def _int(value):
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def share(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def by_group(rows):
    """{group: {box: n}} from [{"grp", "box", "n"}] SQL rows; a blank group
    is "Not set"."""
    out = {}
    for row in rows or []:
        box = _int(row.get("box"))
        if box not in BOXES:
            continue
        group = row.get("grp") or "Not set"
        out.setdefault(group, {})[box] = out.get(group, {}).get(box, 0) + int(_number(row.get("n")))
    return out


def side_by_side(rows, before=None, guide=None, top=TOP):
    """[{"group", "total", "top", "top_share", "boxes": [{"box", "n",
    "share", "last_share", "guide", "variance"}]}] for each group, the
    company first. rows, before: SQL rows of this review and the one before;
    guide: {box: share of 100}."""
    now, was = by_group(rows), by_group(before)
    company = {box: sum(counts.get(box, 0) for counts in now.values()) for box in BOXES}
    company_before = {box: sum(counts.get(box, 0) for counts in was.values()) for box in BOXES}
    groups = [("Company", company, company_before)] + [
        (group, now[group], was.get(group, {})) for group in sorted(now)]
    total_guide = sum(_number(value) for value in (guide or {}).values())
    out = []
    for group, counts, earlier in groups:
        total, total_before = sum(counts.values()), sum(earlier.values())
        boxes = []
        for box in BOXES:
            mine = share(counts.get(box, 0), total)
            expected = round(100.0 * _number((guide or {}).get(box)) / total_guide, 1) if total_guide else None
            boxes.append({"box": box, "n": counts.get(box, 0), "share": mine,
                          "last_share": share(earlier.get(box, 0), total_before) if total_before else None,
                          "guide": expected,
                          "variance": round(mine - expected, 1) if expected is not None and total else None})
        top_count = sum(counts.get(box, 0) for box in top)
        out.append({"group": group, "total": total, "top": top_count, "top_share": share(top_count, total),
                    "boxes": boxes})
    return out


def kpis(facts):
    """The tiles: [{"key", "label", "value", "note", "tone"}]. facts:
    "placed", "eligible", "top", "at_risk", "retention_open", "roles",
    "bench" (succession_rules.bench_index), "high_risk_roles", "overlap",
    "trainees", "confirmed", "investment"."""
    placed, eligible = int(_number(facts.get("placed"))), int(_number(facts.get("eligible")))
    bench = facts.get("bench") or {}
    tiles = [
        {"key": "placed", "label": "Placed", "value": placed,
         "note": "%d%% of those in the review" % round(share(placed, eligible)) if eligible else "Nobody in the review yet",
         "tone": "good" if eligible and placed >= eligible else "soon"},
        {"key": "top", "label": "Top Talent", "value": int(_number(facts.get("top"))),
         "note": "%d%% of those placed" % round(share(_number(facts.get("top")), placed)) if placed else "",
         "tone": "good"},
        {"key": "at_risk", "label": "Top Talent at Risk", "value": int(_number(facts.get("at_risk"))),
         "note": "%d without a retention action" % int(_number(facts.get("unprotected")))
         if facts.get("unprotected") else "Each with a retention action",
         "tone": "overdue" if _number(facts.get("at_risk")) else "good"},
        {"key": "bench", "label": "Ready-Now Cover", "value": "%d%%" % round(_number(bench.get("ready_now_share"))),
         "note": "%d of %d critical roles" % (int(_number(bench.get("ready_now"))), int(_number(bench.get("roles")))),
         "tone": "good" if _number(bench.get("ready_now_share")) >= 70 else "soon"
         if _number(bench.get("ready_now_share")) >= 40 else "overdue"},
        {"key": "depth", "label": "Two or More Successors", "value": "%d%%" % round(_number(bench.get("two_share"))),
         "note": "%d roles with nobody named" % int(_number(bench.get("none"))), "tone": "soon"},
        {"key": "high_risk", "label": "High-Risk Roles", "value": int(_number(facts.get("high_risk_roles"))),
         "note": "Probability of loss x impact", "tone": "overdue" if _number(facts.get("high_risk_roles")) else "good"},
        {"key": "overlap", "label": "Named for Several Roles", "value": int(_number(facts.get("overlap"))),
         "note": "Successors counted more than once", "tone": "soon" if _number(facts.get("overlap")) else "good"},
        {"key": "trainees", "label": "Graduate Trainees", "value": int(_number(facts.get("trainees"))),
         "note": "%d confirmed" % int(_number(facts.get("confirmed"))), "tone": "none"},
    ]
    return tiles


def matrix_rows(grid, names=None):
    """The 9 x 9 movement grid as rows for the page: [{"from", "name",
    "cells": [n for box 1..9], "gone", "total"}] and a "new" row."""
    names = names or {}
    out = []
    for was in (0,) + BOXES:
        row = (grid or {}).get(was) or {}
        cells = [int(row.get(now, 0)) for now in BOXES]
        out.append({"from": was, "name": names.get(was) or ("New" if not was else str(was)), "cells": cells,
                    "gone": int(row.get(0, 0)), "total": sum(cells) + int(row.get(0, 0))})
    return out


def board_figures(facts):
    """What the HR board pack reads about talent (board_pack.py may call
    talent_command.board_figures): {"review", "placed", "top_talent",
    "top_talent_share", "top_at_risk", "retention_open", "roles",
    "ready_now_share", "two_share", "gaps", "high_risk_roles",
    "heat": [[n]], "overlap", "trainees", "confirmed", "investment_approved",
    "investment_actual", "risk_rating", "notes"}. The rating is Action
    Needed where top talent is at risk with nothing done or most roles have
    nobody ready, Watch where either is under way, else On Track."""
    bench = facts.get("bench") or {}
    placed = int(_number(facts.get("placed")))
    top = int(_number(facts.get("top")))
    at_risk = int(_number(facts.get("at_risk")))
    unprotected = int(_number(facts.get("unprotected")))
    ready_share = _number(bench.get("ready_now_share"))
    if unprotected or (bench.get("roles") and ready_share < 40):
        rating = "Action Needed"
    elif at_risk or (bench.get("roles") and ready_share < 70):
        rating = "Watch"
    else:
        rating = "On Track"
    notes = []
    if at_risk:
        notes.append("%d top talent at flight risk, %d without a retention action" % (at_risk, unprotected))
    if bench.get("roles"):
        notes.append("%d%% of %d critical roles have a successor ready now" % (round(ready_share), bench["roles"]))
    if facts.get("high_risk_roles"):
        notes.append("%d critical roles at high risk of loss" % int(_number(facts["high_risk_roles"])))
    return {"review": facts.get("review"), "placed": placed, "top_talent": top,
            "top_talent_share": share(top, placed), "top_at_risk": at_risk, "unprotected": unprotected,
            "retention_open": int(_number(facts.get("retention_open"))), "roles": int(_number(bench.get("roles"))),
            "ready_now_share": ready_share, "two_share": _number(bench.get("two_share")),
            "gaps": int(_number(bench.get("none"))), "high_risk_roles": int(_number(facts.get("high_risk_roles"))),
            "heat": [[cell["count"] for cell in row["cells"]] for row in (facts.get("heat") or {}).get("rows") or []],
            "overlap": int(_number(facts.get("overlap"))), "trainees": int(_number(facts.get("trainees"))),
            "confirmed": int(_number(facts.get("confirmed"))),
            "investment_approved": round(_number(facts.get("investment_approved")), 2),
            "investment_actual": round(_number(facts.get("investment_actual")), 2),
            "risk_rating": rating, "notes": notes}


def cache_key(user_scope, review, company):
    """One cached answer per review, company and what the user may see."""
    return "ha_talent_command::%s::%s::%s" % (review or "", company or "", ",".join(sorted(user_scope or ())) or "*")
