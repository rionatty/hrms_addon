"""Verify succession in depth (succession_rules.py, succession_risk.py,
talent_pools.py, retention.py), without a bench:

    python scripts/verify_succession_risk.py

The talent blueprint, section 6 and section 9: each critical role's risk as
the probability of losing its holder times what losing them would cost; the
bench across the roles (ready now, two or more); successors named for
several roles; successors ranked, with emergency cover, a target date and
the council's decision, their box and flight risk beside them, the bench at
permission level 1; talent pools confirmed by the council and successors
nominated from them; flight risk kept as a history, with retention actions,
told to HR and the council and tied to the roles it touches.
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


def spec_of(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {row["fieldname"]: row for row in spec_of(name)["fields"]}


def body_of(source, name):
    return source.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0] if "def %s(" % name in source else ""


S = load("succession_rules")
print("loaded succession_rules.py without Frappe")

# ── 1. Probability, impact, risk ──────────────────────────────────────
TODAY = "2026-11-18"
check("nobody holds the role: it is lost already", S.loss_probability({"holder": None}, TODAY)[0] == 1.0)
check("an exit raised is certain", S.loss_probability({"holder": "E", "exit_due": "2027-01-31"}, TODAY)[0] == 1.0)
check("a retirement inside the window", S.loss_probability({"holder": "E", "retirement": "2027-06-30"}, TODAY)[0] == 0.8
      and S.loss_probability({"holder": "E", "retirement": "2031-06-30"}, TODAY)[0] == 0.05)
check("the flight risk last assessed, as Talent Settings put it",
      S.loss_probability({"holder": "E", "flight_risk": "High"}, TODAY)[0] == 0.6
      and S.loss_probability({"holder": "E", "flight_risk": "High"}, TODAY, {"probability_high": 75})[0] == 0.75
      and S.loss_probability({"holder": "E", "flight_risk": "Low"}, TODAY)[0] == 0.1)
probability, reasons = S.loss_probability({"holder": "E", "flight_risk": "Medium", "retirement": "2027-02-01"}, TODAY)
check("the likeliest way counts, every reason said", probability == 0.8 and reasons[0].startswith("Retires on")
      and "Flight risk Medium" in reasons, reasons)
check("a shorter retirement window", S.loss_probability({"holder": "E", "retirement": "2027-06-30"}, TODAY,
                                                         {"retirement_months": 3})[0] == 0.05)
check("impact: the factors weighed", S.impact([{"factor": "SPOF", "score": 5}, {"factor": "Time", "score": 2}],
                                               {"SPOF": 2, "Time": 1}) == 4.0 and S.impact([]) is None)
check("factor rows: each named once, 1 to 5",
      S.factor_errors([{"factor": "A", "score": 3}]) == []
      and "A is scored twice." in S.factor_errors([{"factor": "A", "score": 3}, {"factor": "A", "score": 4}])
      and "A is scored 1 to 5." in S.factor_errors([{"factor": "A", "score": 7}]))
check("risk = probability x impact, out of a hundred", S.role_risk(0.6, 4.0) == 48.0 and S.role_risk(1, None) is None)
check("High from 45, Medium from 20; the typed level where nothing is scored",
      [S.risk_level(score) for score in (48, 45, 20, 19.9)] == ["High", "High", "Medium", "Low"]
      and S.risk_level(None, "Medium") == "Medium")
heat = S.heat_map([{"name": "R1", "probability": 0.6, "impact": 4.5}, {"name": "R2", "probability": 0.1, "impact": 2},
                   {"name": "R3", "probability": 0.3, "impact": None}])
check("the heat map: impact High first, probability Low first; an unscored role counted apart",
      heat["rows"][0]["impact"] == "High" and heat["rows"][0]["cells"][2]["roles"] == ["R1"]
      and heat["rows"][2]["cells"][0]["roles"] == ["R2"] and heat["unscored"] == 1)

# ── 2. The bench across the roles ─────────────────────────────────────
bench = S.bench_index([{"ready_now": 1, "successors": 2}, {"ready_now": 0, "successors": 1},
                       {"ready_now": 2, "successors": 3}, {"ready_now": 0, "successors": 0}])
check("bench strength: roles with somebody ready now, with two or more, with nobody",
      (bench["roles"], bench["ready_now"], bench["ready_now_share"], bench["two_or_more"], bench["two_share"],
       bench["none"]) == (4, 2, 50.0, 2, 50.0, 1), bench)
check("successors named for several roles",
      S.overlap([{"employee": "A", "position": "P1"}, {"employee": "A", "position": "P2"},
                 {"employee": "B", "position": "P1"}, {"employee": "A", "position": "P1"}]) == {"A": ["P1", "P2"]})
check("a rank given once, a readiness the levels know, the council's decision of three",
      S.candidate_errors([{"employee": "A", "rank": 1, "readiness": "Ready Now"},
                          {"employee": "B", "rank": 2, "readiness": "Emerging", "council_decision": "Endorsed"}]) == []
      and "Rank 1 is given twice." in S.candidate_errors([{"employee": "A", "rank": 1}, {"employee": "B", "rank": 1}])
      and S.candidate_errors([{"employee": "A", "readiness": "Soon"}]) != []
      and "The incumbent cannot succeed themselves." in S.candidate_errors([{"employee": "H"}], incumbent="H"))
check("the bench in the council's order, the unranked after, readiest first",
      [row["employee"] for row in S.ranked([{"employee": "C", "readiness": "Ready Now"},
                                            {"employee": "B", "rank": 2, "readiness": "Emerging"},
                                            {"employee": "A", "rank": 1, "readiness": "Emerging"},
                                            {"employee": "D", "readiness": "Emerging"}])] == ["A", "B", "C", "D"])
check("ranks given after the highest", [rank for _row, rank in S.next_ranks([{"rank": 3}, {}, {"rank": 1}, {}])]
      == [4, 5])

# ── 3. Talent pools ───────────────────────────────────────────────────
check("a pool draws from the boxes it names, from every box where it names none",
      S.eligible(9, [9, 6]) and not S.eligible(5, [9, 6]) and S.eligible(5, []))
check("the members a pool takes in: eligible, not already active, once",
      [row["employee"] for row in S.members_to_add(
          [{"employee": "A", "box": 9}, {"employee": "B", "box": 5}, {"employee": "C", "box": 6},
           {"employee": "C", "box": 6}, {"employee": "D", "box": 9}],
          [{"employee": "D", "status": "Confirmed"}, {"employee": "E", "status": "Exited"}], [9, 6])] == ["A", "C"])
check("a confirmed member is exited, never taken off",
      "Ann was confirmed in the pool. Exit them rather than take them off." in S.member_errors(
          [{"name": "M1", "employee": "A", "employee_name": "Ann", "status": "Confirmed"}], []))
check("an exit has its day and its reason",
      S.member_errors([], [{"employee": "A", "status": "Exited"}]) != []
      and S.member_errors([], [{"employee": "A", "status": "Exited", "exited_on": "2026-11-01",
                                "exit_reason": "Promoted"}]) == [])
check("nobody active in a pool twice", S.member_errors([], [{"employee": "A", "status": "Proposed"},
                                                           {"employee": "A", "status": "Confirmed"}]) != [])
check("a pool grown for some roles fits them only", S.pool_fits(["Supervisor"], "Supervisor")
      and not S.pool_fits(["Supervisor"], "Manager") and S.pool_fits([], "Anything"))

# ── 4. Flight risk ────────────────────────────────────────────────────
WATCHED = ("High", "Medium")
check("top talent at a watched level is told once a level, worse told again",
      S.alert_needed(1, "Medium", WATCHED) and not S.alert_needed(1, "Medium", WATCHED, "Medium")
      and S.alert_needed(1, "High", WATCHED, "Medium") and not S.alert_needed(1, "Medium", WATCHED, "High")
      and not S.alert_needed(0, "High", WATCHED) and not S.alert_needed(1, "Low", WATCHED))
check("a retention action says what is done, and how it went once closed",
      S.retention_errors([{"action": "Market pay review", "status": "Planned"}]) == []
      and S.retention_errors([{"action": "", "status": "Planned"}]) != []
      and S.retention_errors([{"action": "x", "status": "Done"}]) != [])
check("open and overdue retention actions", S.open_retention([{"status": "Planned", "due": "2026-11-01"},
                                                              {"status": "Done", "due": "2026-10-01"},
                                                              {"status": "In Progress"}], TODAY) == (2, 1))

# ── 5. The doctypes ───────────────────────────────────────────────────
position = fields("Succession Position")
check("a role: its criticality rows, impact, probability, risk and why; the successors counted",
      position["criticality"]["options"] == "Role Criticality" and {"impact_score", "loss_probability", "role_risk",
                                                                    "risk_reasons", "successors", "two_or_more"}
      <= set(position) and all(position[name].get("read_only") and position[name].get("allow_on_submit")
                               for name in ("impact_score", "loss_probability", "role_risk", "risk_reasons")))
check("the bench at permission level 1", position["candidates"].get("permlevel") == 1)
perms = {(row["role"], row.get("permlevel", 0)): row for row in spec_of("Succession Position")["permissions"]}
check("level 1 for HR, the council and the head of department who names successors; level 2 (the boxes) not theirs",
      perms.get(("Head of Department", 1), {}).get("write") and ("Head of Department", 2) not in perms
      and perms.get(("Talent Council", 2), {}).get("read") and perms.get(("HR Manager", 2), {}).get("read")
      and not perms.get(("Talent Council", 0), {}).get("delete"))
candidate = fields("Succession Candidate")
check("a successor: readiness a Readiness Level, rank, emergency cover, target date, the council's decision, the pool",
      candidate["readiness"]["fieldtype"] == "Link" and candidate["readiness"]["options"] == "Readiness Level"
      and {"rank", "emergency_cover", "target_ready_date", "council_decision", "talent_pool", "other_roles"}
      <= set(candidate) and candidate["talent_pool"]["options"] == "Talent Pool"
      and set(candidate["council_decision"]["options"].split("\n")) - {""} == set(S.COUNCIL_DECISIONS))
check("the successor's latest box and flight risk read in, at level 2",
      all(candidate[name].get("permlevel") == 2 and candidate[name].get("read_only")
          for name in ("latest_box", "flight_risk", "box_name")))
pool = fields("Talent Pool")
member = fields("Talent Pool Member")
check("a pool: type, owner, target roles, eligible boxes, members; a member entered, confirmed, exited",
      {"pool_type", "pool_owner", "target_roles", "eligible_boxes", "members", "status", "confirmed_by"} <= set(pool)
      and pool["target_roles"]["fieldtype"] == "Table MultiSelect" and pool["eligible_boxes"]["fieldtype"]
      == "Table MultiSelect" and {"entered_on", "confirmed_on", "exited_on", "exit_reason", "status"} <= set(member)
      and member["box"].get("permlevel") == 1)
risk = spec_of("Flight Risk Assessment")
risk_fields = fields("Flight Risk Assessment")
check("a flight risk assessment is its own record, insert only: no role writes it",
      not risk.get("istable") and not any(row.get("write") for row in risk["permissions"])
      and {"employee", "placement", "assessed_on", "risk", "previous_risk", "drivers", "roles_affected", "alerted"}
      <= set(risk_fields) and risk_fields["drivers"]["fieldtype"] == "Table MultiSelect")
retention = fields("Retention Action")
check("a retention action: driver, action, owner, due, cost, status, outcome",
      {"driver", "action", "action_owner", "due", "cost", "status", "outcome"} <= set(retention)
      and retention["driver"]["options"] == "Retention Driver")
placement = fields("Talent Placement")
check("a placement's retention actions at level 1, kept after it is finalised",
      placement["retention_actions"].get("permlevel") == 1 and placement["retention_actions"].get("allow_on_submit"))

# ── 6. The glue ───────────────────────────────────────────────────────
RISK = read("hrms_addon", "hrms_addon", "succession_risk.py")
POOLS = read("hrms_addon", "hrms_addon", "talent_pools.py")
RETENTION = read("hrms_addon", "hrms_addon", "retention.py")
TALENT = read("hrms_addon", "hrms_addon", "talent.py")
check("every save of a role reads its risk and its bench", "succession_risk.fill(doc)" in body_of(TALENT, "position_validate")
      and "succession_risk.fill(doc)" in body_of(TALENT, "position_before_update_after_submit"))
check("the holder's retirement and latest flight risk read for the probability",
      '"date_of_retirement"' in body_of(RISK, "_holder_facts") and "latest_risk(" in body_of(RISK, "_holder_facts"))
check("the latest boxes newest first and without a cut-off",
      "order by finalised_on desc, creation desc" in body_of(RISK, "latest_boxes") and "limit" not in body_of(RISK, "latest_boxes"))
check("the other roles a successor is named for, counted in one query",
      "count(distinct candidate.parent)" in body_of(RISK, "named_for") and "group by candidate.employee" in body_of(RISK, "named_for"))
check("a factor reweighed: the roles read again in the background",
      "frappe.enqueue(" in body_of(RISK, "factor_on_update"))
check("the council confirms a pool's members", "frappe.only_for(CONFIRMERS)" in body_of(POOLS, "confirm_members"))
check("successors nominated from a pool: confirmed members only, the readiness their box draws",
      "pool_members(pool, doc.designation)" in body_of(POOLS, "nominate_from_pool")
      and "masters.suggested_readiness(row.box)" in body_of(POOLS, "pool_members")
      and 'has_permlevel_access_to("candidates", permission_type="write")' in body_of(POOLS, "nominate_from_pool"))
check("an assessment refuses to change once made", "if not doc.is_new():" in body_of(RETENTION, "assessment_validate"))
check("an assessment reaches the placement, the bench rows and the roles held",
      "frappe.db.set_value(PLACEMENT" in body_of(RETENTION, "assessment_after_insert")
      and "`tabSuccession Candidate` set flight_risk" in body_of(RETENTION, "assessment_after_insert")
      and "succession_risk.refresh_position(name)" in body_of(RETENTION, "assessment_after_insert"))
check("told to HR and the council once a level, with the roles it touches",
      "rules.alert_needed(" in body_of(RETENTION, "assessment_after_insert")
      and '"Talent Council"' in body_of(RETENTION, "assessment_after_insert")
      and "roles_affected" in body_of(RETENTION, "assessment_after_insert"))
check("a flight risk changed on a placement's form is kept as an assessment too",
      "retention.placement_changed(doc)" in body_of(TALENT, "placement_on_update"))
check("the old successor slate's readiness stays readable: the levels are named as before",
      'READINESS = (READY_NOW, READY_SOON, EMERGING, GAP)' in read("hrms_addon", "hrms_addon", "talent_rules.py"))

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_succession_risk: OK")
