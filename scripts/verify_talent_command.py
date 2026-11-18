"""Verify the executives' talent views (talent_command_rules.py,
talent_command.py, page/talent_command, talent_council.py and the Talent
Council Pack print), without a bench:

    python scripts/verify_talent_command.py

The talent blueprint, section 10, and the review of 18 Nov 2026: plants and
departments side by side on the nine boxes against the distribution guide
and the review before, the succession heat map (impact by probability), the
bench, top talent and flight risk, the 9 x 9 movement, the graduate funnel;
each figure opening its list; one cached call adding up in SQL, scoped to
the plants the user sees; a council pack as a print and as slides; the
figures the HR board pack reads; the desk's nine-box panel on the latest
review only, in the boxes' own colours; all of it on the menu.
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(label, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else "   -> %r" % (detail,)))
    if not ok:
        fail.append(label)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def body_of(source, name):
    return source.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0] if "def %s(" % name in source else ""


C = load("talent_command_rules")
T = load("talent_rules")
N = load("navigation_rules")
print("loaded talent_command_rules.py without Frappe")

# ── 1. Side by side ───────────────────────────────────────────────────
rows = [{"grp": "Kawempe", "box": 9, "n": 2}, {"grp": "Kawempe", "box": 5, "n": 6},
        {"grp": "Namanve", "box": 5, "n": 3}, {"grp": None, "box": 1, "n": 1}, {"grp": "X", "box": 12, "n": 5}]
before = [{"grp": "Kawempe", "box": 5, "n": 4}]
groups = C.side_by_side(rows, before, T.GUIDE)
company = groups[0]
check("the company first, then each group; a blank group Not set; a box off the grid left out",
      [group["group"] for group in groups] == ["Company", "Kawempe", "Namanve", "Not set"] and company["total"] == 12)
kawempe = groups[1]
nine = next(row for row in kawempe["boxes"] if row["box"] == 9)
five = next(row for row in kawempe["boxes"] if row["box"] == 5)
check("each box's share, the guide's, the gap and the review before",
      (nine["n"], nine["share"], nine["guide"], nine["variance"]) == (2, 25.0, 10.0, 15.0)
      and (five["share"], five["last_share"]) == (75.0, 100.0), (nine, five))
check("top talent share", kawempe["top"] == 2 and kawempe["top_share"] == 25.0)
check("no review before: no last share", next(row for row in groups[2]["boxes"] if row["box"] == 5)["last_share"] is None)

# ── 2. The tiles and the board pack ───────────────────────────────────
facts = {"placed": 1800, "eligible": 2000, "top": 300, "at_risk": 12, "unprotected": 4, "retention_open": 20,
         "bench": {"roles": 40, "ready_now": 18, "ready_now_share": 45.0, "two_share": 30.0, "none": 6},
         "high_risk_roles": 5, "overlap": 3, "trainees": 25, "confirmed": 8, "investment_approved": 1000,
         "investment_actual": 400, "review": "TR-2026",
         "heat": {"rows": [{"impact": "High", "cells": [{"count": 1}, {"count": 2}, {"count": 3}]}]}}
tiles = C.kpis(facts)
check("eight tiles, each with a key the page opens a list for",
      [tile["key"] for tile in tiles] == ["placed", "top", "at_risk", "bench", "depth", "high_risk", "overlap", "trainees"])
check("the tiles say what each counts", tiles[0]["note"] == "90% of those in the review"
      and tiles[2]["note"] == "4 without a retention action" and tiles[3]["value"] == "45%")
board = C.board_figures(facts)
check("the board pack's talent figures: rated Watch with cover under 70%",
      board["risk_rating"] == "Watch" or board["risk_rating"] == "Action Needed")
check("top talent at risk with nothing done is Action Needed", board["risk_rating"] == "Action Needed"
      and board["unprotected"] == 4 and board["top_talent_share"] == 16.7 and board["heat"] == [[1, 2, 3]])
check("nothing at risk and cover over 70% is On Track", C.board_figures(
    {"bench": {"roles": 10, "ready_now_share": 80.0}, "placed": 10})["risk_rating"] == "On Track")
check("nothing known: an empty pack, not an error", C.board_figures({})["roles"] == 0)
matrix = {was: {now: 0 for now in range(10)} for was in range(10)}
matrix[5][6] = 4
matrix[0][3] = 2
matrix[4][0] = 1
lines = C.matrix_rows(matrix, {5: "Core Player"})
check("the movement matrix as rows: New first, each box's row, those gone",
      lines[0]["name"] == "New" and lines[0]["cells"][2] == 2 and lines[5]["name"] == "Core Player"
      and lines[5]["cells"][5] == 4 and lines[4]["gone"] == 1 and len(lines) == 10)
check("one cached answer per review, company and plants seen",
      C.cache_key(["Namanve", "Kawempe"], "TR", "LPL") == "ha_talent_command::TR::LPL::Kawempe,Namanve"
      and C.cache_key(None, "TR", None).endswith("::*"))

# ── 3. The site ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "talent_command.py")
check("one whitelisted call, cached ten minutes, a fresh read on asking",
      re.search(r"@frappe\.whitelist\(\)\ndef get_command\(", GLUE) is not None
      and "frappe.cache.get_value(key)" in body_of(GLUE, "get_command")
      and "frappe.cache.set_value(key, data, expires_in_sec=CACHE_SECONDS)" in body_of(GLUE, "get_command")
      and "CACHE_SECONDS = 600" in GLUE)
check("for those who read the boxes", "_check_access()" in body_of(GLUE, "get_command")
      and "talent_board.can_see_boxes()" in body_of(GLUE, "_check_access"))
check("scoped to the plants the user sees", "scope()" in body_of(GLUE, "get_command")
      and '"allow": "Branch"' in body_of(GLUE, "scope") and '.branch in %%(plants)s" % alias' in body_of(GLUE, "_where"))
figures = body_of(GLUE, "figures")
check("added up in SQL: GROUP BY by plant or department and box, never a query a person",
      "group by p.{field}, p.box" in figures and "frappe.get_doc(" not in figures
      and figures.count("frappe.db.sql(") >= 8)
check("the movement read in two GROUP BYs against the review before",
      "group by prev.box, cur.box" in figures and "group by prev.box" in figures and "cur.name is null" in figures)
check("the heat map, the bench and the overlap from the roles",
      "succession_rules.heat_map(" in figures and "succession_rules.bench_index(" in figures
      and "succession_risk.overlap(" in figures)
check("the graduate funnel by cohort", "graduates.funnel(" in figures)
check("the board pack can read the talent figures", "def board_figures(company=None, review=None):" in GLUE
      and "rules.board_figures(" in body_of(GLUE, "board_figures"))

# ── 4. The page ───────────────────────────────────────────────────────
page = json.load(open(os.path.join(APP, "page", "talent_command", "talent_command.json"), encoding="utf-8"))
placement = json.load(open(os.path.join(APP, "doctype", "talent_placement", "talent_placement.json"), encoding="utf-8"))
level_one = {row["role"] for row in placement["permissions"] if row.get("permlevel") == 1 and row.get("read")}
check("the page opens for exactly those who read the boxes, the executives among them",
      page["name"] == "talent-command" and {row["role"] for row in page["roles"]} == level_one
      and {"General Manager", "Executive Director"} <= level_one, (sorted(level_one), page["roles"]))
JS = read("hrms_addon", "hrms_addon", "page", "talent_command", "talent_command.js")
check("the page makes the one call", JS.count("hrms_addon.hrms_addon.talent_command.get_command") == 1)
for needle, what in (('this.go("Talent Placement", filters)', "a box opens its placements"),
                     ('this.go("Succession Position", { name: ["in", roles.roles] })', "a heat cell opens its roles"),
                     ('this.report("Talent Movement", filters)', "a matrix cell opens its movers"),
                     ('this.go("Graduate Trainee Program", { cohort:', "a funnel cell opens its trainees"),
                     ('data-split="by_department"', "plants or departments side by side")):
    check("the page: %s" % what, needle in JS)
movement = read("hrms_addon", "hrms_addon", "report", "talent_movement", "talent_movement.py")
check("Talent Movement filters by the box each came from and went to",
      'filters.get("from_box")' in movement and 'filters.get("to_box")' in movement)

# ── 5. The council pack ───────────────────────────────────────────────
COUNCIL = read("hrms_addon", "hrms_addon", "talent_council.py")
HOOKS = read("hrms_addon", "hooks.py")
pack = json.load(open(os.path.join(APP, "print_format", "talent_council_pack", "talent_council_pack.json"),
                      encoding="utf-8"))
check("a print of the review: the grid by plant, top talent, flight risks, succession cover, decisions",
      pack["doc_type"] == "Talent Review" and all(needle in pack["html"] for needle in (
          "talent_council_pack(doc.name)", "Plants Side by Side", "Top Talent", "Flight Risks", "Succession Coverage",
          "Decisions", "Graduate Pipeline")))
check("the print's figures for whoever may read the review and the boxes",
      '"hrms_addon.hrms_addon.talent_council.talent_council_pack"' in HOOKS
      and "talent_board.can_see_boxes()" in body_of(COUNCIL, "_allowed")
      and 'frappe.has_permission(REVIEW, "read", doc=review)' in body_of(COUNCIL, "_allowed"))
check("the pack as slides, with python-pptx, native tables and charts",
      re.search(r"@frappe\.whitelist\(\)\ndef download_deck\(", COUNCIL) is not None
      and "from pptx import Presentation" in COUNCIL and "add_chart(" in COUNCIL and "add_table(" in COUNCIL
      and 'frappe.local.response.type = "binary"' in COUNCIL)
check("the decisions counted in SQL", "group by p.suggested_decision" in body_of(COUNCIL, "decisions")
      and "group by c.council_decision" in body_of(COUNCIL, "decisions"))

# ── 6. The desk ───────────────────────────────────────────────────────
D = load("dashboards_rules")
DASH = read("hrms_addon", "hrms_addon", "dashboards.py")
check("the nine-box panel worked out on the site, no longer a count of every year's placements",
      "nine_box" not in D.GROUPS and "nine_box" in D.PANELS and "def panel_nine_box(self):" in DASH)
panel = DASH.split("def panel_nine_box(self):", 1)[1].split("\n    def ", 1)[0]
check("the latest review only, each box in its colour",
      "talent_command.latest_review(self.company)" in panel and '"talent_review": review' in panel
      and "rules.NINE_BOX_BANDS.get(" in panel and set(D.NINE_BOX_BANDS) == set(T.COLOURS))

# ── 7. On the menu ────────────────────────────────────────────────────
cards = {link[1] for card, links in N.CARDS["Performance"] for link in links}
sidebar = {entry[1] for entry in N.SIDEBAR["Performance"]}
talent_group = next(entries for name, _icon, entries in N.GROUPS["Performance"] if name == "Talent")
for name in ("talent-command", "Potential Assessment", "Calibration Session", "Talent Pool", "Flight Risk Assessment",
             "Graduate Cohort", "Rotation Assessment", "Mentoring Session", "Talent Calibration Log", "Talent Job Log",
             "Potential Criterion", "Criticality Factor", "Retention Driver"):
    check("%s is on the Performance page and its sidebar" % name, name in cards and name in sidebar)
for name in ("talent-command", "Potential Assessment", "Calibration Session", "Talent Pool", "Flight Risk Assessment",
             "Graduate Cohort", "Rotation Assessment", "Mentoring Session"):
    check("%s sits in the sidebar's Talent group" % name, name in talent_group)

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_talent_command: OK")
