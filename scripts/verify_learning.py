"""Verify Learning, Training & Certification (Luuka's LMS, phases 1 and 2), without a bench:

    python scripts/verify_learning.py

The LMS blueprint (LuukaLearn, 12 Aug 2026) and the decisions of 17 Nov 2026:
a joiner's onboarding is not held until their mandatory training is done,
training keeps its approval (Training Needs Assessment, then the Training
Calendar), and phases 1 and 2 come first: the masters, the rules engine,
the certification register with its escalating alerts, and the Learning
Passport, Training Matrix and compliance reports.

  1  the rules: who a rule asks, when it is due, what counts as done and
     for how long, a certificate's status and its alert ladder, the light,
     the coverage and the score
  2  the paper: every field and option the rules and the glue name is on
     its doctype, the categories and the ladder seeded as the blueprint has them
  3  the glue: what it reads and writes, what it refuses, how it chases
  4  wiring: events, the daily and weekly jobs, the migrate seed, the
     Training Program's fields, the menus and connections, the Employee
     form's way to the passport, the page and the reports
"""
import datetime
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {field["fieldname"]: field for field in doctype(name)["fields"]}


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %s" % (detail,)) if detail != "" else ""))


R = load("learning_rules")
D = datetime.date
TODAY = D(2026, 11, 17)
S = R.settings_from()

# ── 1. The rules ──────────────────────────────────────────────────────
# settings
check("the defaults are the prototype's: 30 days for training, 90 for a certificate, 40/35/25 for the score",
      (S["due_soon_days"], S["certificate_due_soon_days"], S["weight_training"], S["weight_competency"],
       S["weight_assessment"], S["matrix_green_from"], S["matrix_amber_from"]) == (30, 90, 40, 35, 25, 85, 65), S)
check("the default ladder: 180 the employee, then one rung more each step, management on the day",
      [(days, tuple(who)) for days, who in S["tiers"]] == [
          (180, ("employee",)), (120, ("employee", "supervisor")),
          (90, ("employee", "supervisor", "head_of_department")),
          (60, ("employee", "supervisor", "head_of_department", "hr")),
          (30, ("employee", "supervisor", "head_of_department", "hr")),
          (0, ("employee", "supervisor", "head_of_department", "hr", "management"))], S["tiers"])
check("the ladder as HR set it, the earliest warning first, a rung telling nobody left out",
      R.tiers_from([{"days_before": 30, "hr": 1}, {"days_before": 90, "employee": 1, "supervisor": 1},
                    {"days_before": 10}]) == [(90, ["employee", "supervisor"]), (30, ["hr"])])
check("settings as saved, the defaults for the empty ones",
      R.settings_from({"due_soon_days": 14, "certificate_due_soon_days": None})["due_soon_days"] == 14
      and R.settings_from({"certificate_due_soon_days": ""})["certificate_due_soon_days"] == 90)
check("the settings refused: weights all nought, amber above green, two alerts on one day",
      len(R.settings_errors({"weight_training": 0, "weight_competency": 0, "weight_assessment": 0,
                             "matrix_green_from": 60, "matrix_amber_from": 70,
                             "tiers_rows": [{"days_before": 30}, {"days_before": 30}]})) == 3
      and not R.settings_errors(dict(R.DEFAULTS, tiers_rows=[{"days_before": 0}, {"days_before": 30}])))

# the rule
check("a rule needs its training, or its certificate",
      R.rule_errors({"requirement_type": "Mandatory"}) == ["Pick the training the employee must do."]
      and R.rule_errors({"requirement_type": "Certification"}) == ["Pick the certificate the employee must hold."]
      and not R.rule_errors({"requirement_type": "Certification", "certification": "Forklift Operator"})
      and not R.rule_errors({"requirement_type": "Onboarding", "training_program": "Induction"}))
check("a refresher is repeated; a repeat the payroll of months does not know is refused",
      R.rule_errors({"requirement_type": "Refresher", "training_program": "Fire Safety", "repeat": "Once"})
      == ["A refresher is repeated: say how often."]
      and R.rule_errors({"requirement_type": "Mandatory", "training_program": "PPE", "repeat": "Fortnightly"})
      and not R.rule_errors({"requirement_type": "Refresher", "training_program": "Fire Safety",
                             "repeat": "Every Year"}))
check("no type, or days below nought, refused",
      R.rule_errors({}) and R.rule_errors({"requirement_type": "Mandatory", "training_program": "PPE",
                                            "due_within_days": -1}))
check("how long a training counts: the repeat in months; a certificate counts to its own expiry",
      [R.repeat_months({"requirement_type": "Refresher", "repeat": label}) for label, _months in R.REPEATS]
      == [0, 3, 6, 12, 24, 36]
      and R.repeat_months({"requirement_type": "Certification", "repeat": "Every Year"}) == 0)

EMP = {"status": "Active", "company": "LPL", "branch": "Kawempe", "department": "Extrusion",
       "designation": "Machine Operator", "grade": "G4", "employment_type": "Permanent",
       "operates_machinery": 1, "date_of_joining": D(2020, 3, 1)}
check("an empty list is everybody", R.in_scope({}, EMP))
check("a rule for one plant and two departments asks those in them, nobody else",
      R.in_scope({"branches": ["Kawempe"], "departments": ["Extrusion", "Printing"]}, EMP)
      and not R.in_scope({"branches": ["Namanve"]}, EMP)
      and not R.in_scope({"departments": ["Printing"]}, EMP))
check("job titles, grades and employment types narrow it the same way",
      R.in_scope({"designations": ["Machine Operator"], "grades": ["G4"], "employment_types": ["Permanent"]}, EMP)
      and not R.in_scope({"designations": ["Supervisor"]}, EMP)
      and not R.in_scope({"grades": ["G9"]}, EMP)
      and not R.in_scope({"employment_types": ["Casual"]}, EMP))
check("another company's rule, a machine operators' rule for an office hand, one who has left: nothing asked",
      not R.in_scope({"company": "Other"}, EMP)
      and not R.in_scope({"operators_only": 1}, dict(EMP, operates_machinery=0))
      and R.in_scope({"operators_only": 1}, EMP)
      and not R.in_scope({}, dict(EMP, status="Left")))

ONBOARD = {"requirement_type": "Onboarding", "due_within_days": 7, "applies_from": D(2026, 11, 1)}
check("onboarding is due so many days after joining, for those who joined once the rule applied",
      R.first_due(ONBOARD, dict(EMP, date_of_joining=D(2026, 11, 10)), TODAY) == D(2026, 11, 17)
      and R.first_due(ONBOARD, EMP, TODAY) is None)
STANDING = {"requirement_type": "Mandatory", "due_within_days": 30, "applies_from": D(2026, 11, 1)}
check("a standing rule is due so many days after the latest of: the rule applying, coming under it, joining",
      R.first_due(STANDING, EMP, D(2026, 11, 17)) == D(2026, 12, 17)
      and R.first_due(STANDING, EMP, D(2026, 10, 1)) == D(2026, 12, 1)
      and R.first_due(STANDING, dict(EMP, date_of_joining=D(2027, 1, 4)), TODAY) == D(2027, 2, 3))

# done, and for how long
check("never done: nothing done, due when first due",
      R.programme_state(D(2026, 12, 1), 12, []) == {"completed_on": None, "valid_until": None,
                                                    "due_date": D(2026, 12, 1), "evidence": None})
once = R.programme_state(D(2026, 12, 1), 0, [(D(2025, 5, 2), "EV-1")])
check("done once and once is enough: it counts for good", once["completed_on"] == D(2025, 5, 2)
      and once["valid_until"] is None and once["evidence"] == "EV-1", once)
yearly = R.programme_state(D(2026, 12, 1), 12, [(D(2025, 1, 31), "EV-1"), (D(2026, 1, 31), "EV-2")])
check("repeated: the last time counts for the repeat, and it is due again on the day it stops",
      yearly == {"completed_on": D(2026, 1, 31), "valid_until": D(2027, 1, 31), "due_date": D(2027, 1, 31),
                 "evidence": "EV-2"}, yearly)

CERT = {"name": "CERT-1", "issue_date": D(2026, 1, 10), "expiry_date": D(2027, 1, 10),
        "verification_status": "Unverified"}
check("the certificate that runs longest counts",
      R.certificate_state(D(2026, 12, 1), [dict(CERT, name="A", expiry_date=D(2026, 6, 1)), CERT])["evidence"]
      == "CERT-1")
check("a revoked or rejected certificate does not count, nor an unchecked one where only checked count",
      R.certificate_state(None, [dict(CERT, revoked=1)])["evidence"] is None
      and R.certificate_state(None, [dict(CERT, verification_status="Rejected")])["evidence"] is None
      and R.certificate_state(None, [CERT], only_verified=1)["evidence"] is None
      and R.certificate_state(None, [dict(CERT, verification_status="Verified")], only_verified=1)["evidence"]
      == "CERT-1")
check("one that never runs out counts for good",
      R.certificate_state(None, [dict(CERT, expiry_date=None)])["valid_until"] is None
      and R.certificate_state(None, [dict(CERT, expiry_date=None)])["completed_on"] == D(2026, 1, 10))

ROW = {"requirement_type": "Mandatory"}
check("done and still counting: Compliant", R.status_on(dict(ROW, completed_on=D(2026, 1, 5)), TODAY) == "Compliant")
check("done, and it stops counting within 30 days: Due Soon",
      R.status_on(dict(ROW, completed_on=D(2025, 12, 1), valid_until=D(2026, 12, 1),
                       due_date=D(2026, 12, 1)), TODAY) == "Due Soon")
check("it stopped counting: Overdue",
      R.status_on(dict(ROW, completed_on=D(2025, 10, 1), valid_until=D(2026, 10, 1),
                       due_date=D(2026, 10, 1)), TODAY) == "Overdue")
check("never done: Overdue past the due day, Due Soon within 30 days of it, else Pending",
      R.status_on(dict(ROW, due_date=D(2026, 11, 16)), TODAY) == "Overdue"
      and R.status_on(dict(ROW, due_date=D(2026, 11, 17)), TODAY) == "Due Soon"
      and R.status_on(dict(ROW, due_date=D(2026, 12, 17)), TODAY) == "Due Soon"
      and R.status_on(dict(ROW, due_date=D(2026, 12, 18)), TODAY) == "Pending"
      and R.status_on(ROW, TODAY) == "Pending")
check("a certificate not yet held turns Due Soon on the training window, not the certificate one",
      R.status_on({"requirement_type": "Certification", "due_date": D(2027, 1, 16)}, TODAY) == "Pending"
      and R.status_on({"requirement_type": "Certification", "due_date": D(2026, 12, 17)}, TODAY) == "Due Soon")
check("a certificate held turns Due Soon 90 days before it runs out",
      R.status_on({"requirement_type": "Certification", "completed_on": D(2026, 1, 1), "valid_until": D(2027, 2, 1)},
                  TODAY) == "Due Soon"
      and R.status_on({"requirement_type": "Certification", "completed_on": D(2026, 1, 1),
                       "valid_until": D(2027, 3, 1)}, TODAY) == "Compliant")
check("Not Applicable stays so", R.status_on(dict(ROW, status="Not Applicable", due_date=D(2020, 1, 1)), TODAY)
      == "Not Applicable")

# the certificate
check("a certificate runs out so many months after it was issued; never when the certification does not expire",
      R.expiry_for(D(2026, 1, 15), 12) == D(2027, 1, 15) and R.expiry_for(D(2026, 1, 15), 0) is None
      and R.expiry_for(D(2026, 8, 31), 6) == D(2027, 2, 28))
check("a certificate's status: revoked, renewed, run out, within 90 days, valid, never runs out",
      [R.certificate_status(dict(CERT, **extra), TODAY) for extra in (
          {"revoked": 1}, {"renewed_by": "CERT-2"}, {"expiry_date": D(2026, 11, 16)},
          {"expiry_date": D(2027, 2, 15)}, {"expiry_date": D(2027, 2, 16)}, {"expiry_date": None})]
      == ["Revoked", "Renewed", "Expired", "Due Soon", "Valid", "Valid"])
check("on its last day a certificate still counts: Due Soon, Expired from the day after",
      R.certificate_status(dict(CERT, expiry_date=TODAY), TODAY) == "Due Soon"
      and R.certificate_status(dict(CERT, expiry_date=TODAY - datetime.timedelta(days=1)), TODAY) == "Expired")
check("a certificate refused: no issue date, issued after today, running out before it was issued, revoked "
      "without a reason",
      R.certificate_errors({}, TODAY) == ["Enter the date it was issued."]
      and R.certificate_errors({"issue_date": D(2026, 11, 18)}, TODAY) == ["It cannot be issued after today."]
      and R.certificate_errors({"issue_date": D(2026, 1, 1), "expiry_date": D(2025, 12, 1)}, TODAY)
      == ["It cannot run out before it was issued."]
      and R.certificate_errors({"issue_date": D(2026, 1, 1), "revoked": 1}, TODAY) == ["Say why it is revoked."]
      and not R.certificate_errors({"issue_date": D(2026, 1, 1), "revoked": 1, "revoke_reason": "Forged"}, TODAY))
TIERS = S["tiers"]
check("no alert while more than 180 days are left", R.tier_due(181, TIERS) is None and R.tier_due(None, TIERS) is None)
check("each rung sent once, as it is reached",
      R.tier_due(180, TIERS) == 180 and R.tier_due(150, TIERS, [180]) is None and R.tier_due(119, TIERS, [180]) == 120
      and R.tier_due(30, TIERS, [180, 120, 90, 60]) == 30 and R.tier_due(0, TIERS, [180, 120, 90, 60, 30]) == 0)
check("a certificate entered late gets the most urgent rung it has reached, not the ones before",
      R.tier_due(25, TIERS) == 30 and R.tier_due(-40, TIERS) == 0)
check("a rung already passed is not sent after a more urgent one; run out and told: nothing more",
      R.tier_due(-5, TIERS, [0]) is None and R.tier_due(45, TIERS, [30]) is None)
check("who each rung tells", R.audiences_for(TIERS, 120) == ["employee", "supervisor"]
      and R.audiences_for(TIERS, 0)[-1] == "management" and R.audiences_for(TIERS, 7) == [])
check("the rungs sent, kept as text on the certificate",
      R.sent_list("180,120") == [180, 120] and R.sent_list(None) == [] and R.with_sent("180", 120) == "180,120"
      and R.with_sent("", 0) == "0")

# the employee
REQS = [
    {"requirement_type": "Mandatory", "status": "Compliant", "completed_on": D(2026, 3, 1)},
    {"requirement_type": "Refresher", "status": "Due Soon", "completed_on": D(2025, 12, 1),
     "valid_until": D(2026, 12, 1)},
    {"requirement_type": "Mandatory", "status": "Pending"},
    {"requirement_type": "Certification", "status": "Overdue", "completed_on": D(2025, 1, 1),
     "valid_until": D(2026, 1, 1)},
    {"requirement_type": "Recommended", "status": "Overdue"},
    {"requirement_type": "Mandatory", "status": "Not Applicable", "completed_on": D(2024, 1, 1)},
]
figures = R.summary(REQS, TODAY)
check("what the rules ask now: four; two of them done and still counting (a recommendation and what no longer "
      "applies are not counted)", (figures["required"], figures["done"], figures["coverage"]) == (4, 2, 50.0), figures)
check("anything overdue makes the light Overdue", figures["light"] == "Overdue"
      and (figures["overdue"], figures["due_soon"]) == (1, 1), figures)
check("nothing overdue but something due soon: Due Soon; all done: Compliant; nothing asked: Not Applicable",
      R.summary(REQS[:3], TODAY)["light"] == "Due Soon" and R.summary(REQS[:1], TODAY)["light"] == "Compliant"
      and R.summary(REQS[4:], TODAY)["light"] == "Not Applicable")
check("the score, from what there is a figure for: coverage alone is the score",
      R.summary(REQS, TODAY)["score"] == 50)
check("coverage 50 and assessments 80, weighted 40 and 25: 62",
      R.summary(REQS, TODAY, assessment=80)["score"] == round((50 * 40 + 80 * 25) / 65.0))
check("coverage, competency and assessments weighted 40/35/25 when all are there",
      R.summary(REQS, TODAY, assessment=80, competency=70)["score"] == round((50 * 40 + 70 * 35 + 80 * 25) / 100.0))
check("no score while nothing is measured", R.summary([], TODAY)["score"] is None
      and R.summary([], TODAY)["coverage"] is None)
check("a matrix cell: done over required, as a percentage, coloured by the bands",
      R.coverage_of(REQS, TODAY) == (2, 4) and R.percent(2, 4) == 50.0 and R.percent(0, 0) is None
      and [R.heat(value) for value in (85, 84.9, 65, 64.9, None)] == ["green", "amber", "amber", "red", None])
check("a session's hours: the result's, else its own length, else the programme's",
      R.event_hours("2026-11-02 08:00:00", "2026-11-02 12:30:00") == 4.5
      and R.event_hours("2026-11-02 08:00:00", "2026-11-02 12:30:00", 8, 6) == 6
      and R.event_hours(None, None, 3) == 3)
check("a month on is the same day, or the month's last", R.add_months(D(2026, 1, 31), 1) == D(2026, 2, 28)
      and R.add_months(D(2024, 1, 31), 1) == D(2024, 2, 29) and R.add_months(D(2026, 11, 17), 14) == D(2028, 1, 17))

# ── 2. The paper ──────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "learning.py")
G = sys.modules.get("learning")  # never imported: it needs Frappe
requirement, certificate, rule = (fields("Employee Training Requirement"), fields("Employee Certification"),
                                  fields("Training Rule"))
kept = re.search(r"KEPT = \(([^)]*)\)", GLUE).group(1)
for field in re.findall(r'"(\w+)"', kept) + ["alerts_sent", "reason", "recommended_by"]:
    check("Employee Training Requirement has %s" % field, field in requirement)
for field in ("employee", "employee_name", "certification", "certificate_no", "issue_date", "expiry_date", "status",
              "days_to_expiry", "company", "branch", "department", "designation", "issuing_body", "level",
              "provider", "cost", "training_event", "attachment", "verification_status", "verified_by",
              "verified_on", "revoked", "revoke_reason", "renewed_by", "remarks", "alerts_sent"):
    check("Employee Certification has %s" % field, field in certificate)
for field in ("rule_name", "requirement_type", "training_program", "certification", "enabled", "due_within_days",
              "repeat", "applies_from", "company", "operators_only", "branches", "departments", "designations",
              "grades", "employment_types"):
    check("Training Rule has %s" % field, field in rule)
for table, child, field in re.findall(r'\("(\w+)", "(Training Rule [\w ]+)", "(\w+)"\)', GLUE):
    check("%s is the table of %s, which has %s" % (table, child, field),
          rule.get(table, {}).get("options") == child and field in fields(child))
check("the glue reads each of the rule's five lists", len(re.findall(r'\("\w+", "Training Rule [\w ]+", "\w+"\)',
                                                                   GLUE)) == 5)
check("each list is one of the rules' scopes", [table for table, _field in R.SCOPES]
      == ["branches", "departments", "designations", "grades", "employment_types"])
options = lambda spec, field: [value for value in spec[field]["options"].split("\n") if value]  # noqa: E731
check("a requirement's statuses are the rules'", options(requirement, "status") == list(R.REQUIREMENT_STATUSES))
check("a requirement's types are the rules'", options(requirement, "requirement_type") == list(R.REQUIREMENT_TYPES))
check("a rule's types are the rules'", options(rule, "requirement_type") == list(R.RULE_TYPES))
check("a rule's repeats are the rules'", options(rule, "repeat") == [label for label, _months in R.REPEATS])
check("a certificate's statuses are the rules'", options(certificate, "status") == list(R.CERTIFICATE_STATUSES))
check("a certificate's checks are the rules'", options(certificate, "verification_status") == list(R.VERIFICATIONS))
settings = fields("Learning Settings")
for field in list(R.DEFAULTS) + ["notify_due_soon", "notify_overdue", "weekly_digest", "alert_tiers"]:
    check("Learning Settings has %s" % field, field in settings)
for field, default in R.DEFAULTS.items():
    check("Learning Settings' %s defaults as the rules do" % field,
          str(settings.get(field, {}).get("default") or "0") == str(default), settings.get(field, {}).get("default"))
tier = fields("Certification Alert Tier")
check("an alert rung names days and each of the five audiences", set(R.AUDIENCES) | {"days_before"} <= set(tier))
check("the settings are a single doctype", doctype("Learning Settings").get("issingle") == 1)
check("the categories seeded are the blueprint's eight, four of them mandatory",
      [name for name, _flag in R.CATEGORIES] == ["Mandatory", "Technical", "EHS", "Quality", "Leadership",
                                                  "Soft Skills", "Certification", "Refresher"]
      and sum(flag for _name, flag in R.CATEGORIES) == 4)
check("a certification is a Certification category by default",
      fields("Certification")["training_category"].get("default") == "Certification")
check("a rule's training and its certificate show by its type",
      "Certification" in rule["certification"].get("depends_on", "")
      and "Certification" in rule["training_program"].get("mandatory_depends_on", ""))
check("a rule's requirement is the rule's: its training and due date cannot be typed over",
      requirement["training_program"].get("read_only_depends_on") == "eval:doc.training_rule"
      and requirement["due_date"].get("read_only_depends_on") == "eval:doc.training_rule")
custom = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
program_fields = {row["fieldname"]: row for row in custom if row["dt"] == "Training Program"}
for field, kind, target in (("custom_training_category", "Link", "Training Category"),
                            ("custom_delivery_mode", "Select", None), ("custom_duration_hours", "Float", None),
                            ("custom_cost_per_person", "Currency", None),
                            ("custom_certification", "Link", "Certification")):
    row = program_fields.get(field, {})
    check("Training Program has %s, a %s" % (field, kind), row.get("fieldtype") == kind
          and (target is None or row.get("options") == target), row)
check("the Training Program's fields follow its pass mark, in order",
      [program_fields[field]["insert_after"] for field in ("custom_training_category", "custom_delivery_mode",
                                                           "custom_duration_hours", "custom_cost_per_person",
                                                           "custom_certification")]
      == ["custom_pass_mark", "custom_training_category", "custom_delivery_mode", "custom_duration_hours",
          "custom_cost_per_person"])
result_fields = {row["fieldname"] for row in custom if row["dt"] == "Training Result Employee"}
check("the marks and the result the glue reads are on Training Result Employee",
      {"custom_marks", "custom_effective"} <= result_fields)
check("the employee's machine flag the rules read is on the Employee",
      any(row["dt"] == "Employee" and row["fieldname"] == "custom_operates_machinery" for row in custom))
for name, roles in (("Employee Certification", {"HR User", "HR Manager", "Head of Department", "General Manager"}),
                    ("Employee Training Requirement", {"HR User", "HR Manager", "Head of Department", "Supervisor"}),
                    ("Training Rule", {"HR Manager"}), ("Certification", {"HR Manager"})):
    have = {row["role"] for row in doctype(name)["permissions"]}
    check("%s opens to %s" % (name, ", ".join(sorted(roles))), roles <= have, have)
check("only HR set up the rules and the catalogue: HR User reads them",
      all(not row.get("write") for name in ("Training Rule", "Certification", "Training Category")
          for row in doctype(name)["permissions"] if row["role"] == "HR User"))
check("a supervisor and a head of department may recommend, not delete",
      all(row.get("create") and not row.get("delete") for row in doctype("Employee Training Requirement")["permissions"]
          if row["role"] in ("Supervisor", "Head of Department")))

# ── 3. The glue ───────────────────────────────────────────────────────
check("no SQL of its own", "frappe.db.sql" not in GLUE)
check("the rules decide; the glue only reads and writes",
      all(name in GLUE for name in ("rules.in_scope(", "rules.first_due(", "rules.programme_state(",
                                    "rules.certificate_state(", "rules.status_on(", "rules.tier_due(",
                                    "rules.certificate_status(", "rules.summary(")))
check("a rule's requirement is written as it is, stamped, without a form's save",
      "doc.db_insert()" in GLUE and "doc.creation = doc.modified = now()" in GLUE
      and "doc.set_new_name()" in GLUE)
check("only what changed is written, and the record's modified date is left alone",
      'frappe.db.set_value(REQUIREMENT, row.name, changed, update_modified=False)' in GLUE)
check("what no longer applies is kept as Not Applicable, not deleted",
      '_employee_values(facts, {"status": rules.NOT_APPLICABLE})' in GLUE
      and '{"status": rules.NOT_APPLICABLE}' in GLUE)
check("a rule deleted takes its requirements with it, before Frappe checks the links",
      'frappe.db.delete(REQUIREMENT, {"training_rule": doc.name})' in GLUE)
check("a certificate or a session deleted or cancelled: nothing names it as proof any more",
      GLUE.count("_let_go(") >= 4 and '"evidence": None, "evidence_type": None' in GLUE)
check("a rule's requirement is not made by hand", "A rule's requirement is made by its rule." in GLUE)
check("a recommendation is the user's: by them, today, not twice while open",
      "doc.recommended_by = frappe.session.user" in GLUE and "already has {1} recommended and not yet done" in GLUE)
check("only HR check a certificate; whoever did and when is kept",
      "Only HR check a certificate." in GLUE and "doc.verified_by, doc.verified_on = frappe.session.user, today()"
      in GLUE)
check("the same certificate twice is refused: by its number, and by its issue date",
      "number {2}" in GLUE and "issued on {2}" in GLUE)
check("a newer certificate renews the older ones of its kind, and deleting it lets them stand again",
      '"renewed_by": doc.name, "status": rules.RENEWED' in GLUE and '"renewed_by": None' in GLUE)
check("entered already run out, nobody is chased; a new expiry is chased afresh",
      'doc.alerts_sent = "0"' in GLUE and 'has_value_changed("expiry_date")' in GLUE)
check("a session that gives a certificate makes it for those who passed, unchecked, and takes back its own "
      "unchecked ones from those who no longer passed",
      "def sync_certificates" in GLUE and '"verification_status": rules.UNVERIFIED' in GLUE
      and "row.verification_status == rules.UNVERIFIED" in GLUE)
check("passed: marked Present, and no marks that found the training ineffective for them",
      "training_rules.PRESENT" in GLUE and "training_rules.NOT_EFFECTIVE" in GLUE)
check("marks count only where the result says whether the training worked: the column reads nought otherwise",
      'return bool(result and result.get("custom_effective"))' in GLUE)
check("a cancelled session counts for nothing", '"event_status": ["!=", EVENT_CANCELLED]' in GLUE
      and '"docstatus": 1' in GLUE)
check("an employee is brought up to date only when something a rule reads changed",
      all(field in GLUE for field in ('"company"', '"branch"', '"department"', '"designation"', '"grade"',
                                      '"employment_type"', '"status"', '"date_of_joining"',
                                      '"custom_operates_machinery"'))
      and "doc.get_doc_before_save()" in GLUE)
check("the work is done in the background, after the save is committed",
      GLUE.count("enqueue_after_commit=True") >= 2)
check("the daily job brings everyone up to date, then chases certificates and training",
      re.search(r"def daily\(\):.*?refresh_all\(\).*?chase_certificates\(s, day\).*?chase_requirements\(s, day\)",
                GLUE, re.S))
check("each training alert once per due date, the marks of past due dates dropped so the field never fills",
      'mark = "%s %s" % (row.status, row.due_date or "")' in GLUE
      and 'part.endswith(" %s" % (row.due_date or ""))' in GLUE)
check("training due soon to the employee and supervisor; overdue to the head of department as well",
      "[rules.EMPLOYEE, rules.SUPERVISOR] + ([rules.HEAD] if status == rules.OVERDUE else [])" in GLUE)
check("each rung's audience: the employee, their supervisor, the heads of department and HR of their plant, "
      "and management", all(name in GLUE for name in ("employee.user_id", "_supervisor_user(employee)",
                                                       "people.people_for(HEAD_ROLE", "people.hr_officers(",
                                                       "people.people_for(GM_ROLE")))
check("nobody who has left is chased", GLUE.count("employee.status == rules.ACTIVE") >= 1
      and "employee.status != rules.ACTIVE" in GLUE)
check("the weekly digest goes to each plant's HR and opens the matrix for that plant",
      "/app/query-report/Training%20Matrix" in GLUE and "people.hr_officers(branch)" in GLUE)
check("the passport is whitelisted, opens the user's own by default, and checks who may see it",
      re.search(r"@frappe\.whitelist\(\)\ndef passport\(employee=None\):", GLUE)
      and '{"user_id": frappe.session.user}' in GLUE and "if not can_see(facts):" in GLUE)
check("who may see a passport: HR; the employee; their supervisor; managers through their own permissions",
      'frappe.has_permission("Employee", "read", doc=facts.name, user=user)' in GLUE
      and "facts.user_id == user" in GLUE
      and 'frappe.db.get_value("Employee", facts.reports_to, "user_id") == user' in GLUE)
check("the alerts go through the app's own notices", "people.notify(" in GLUE)
check("the categories and the ladder seeded once, then HR's", "if not frappe.db.exists(CATEGORY, name):" in GLUE
      and 'if not doc.get("alert_tiers"):' in GLUE)

# ── 4. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
for needle, what in (
        ('"hrms_addon.hrms_addon.learning.employee_on_update"', "an employee's change reaches the rules"),
        ('"on_update_after_submit": "hrms_addon.hrms_addon.learning.event_changed"', "a held session changed"),
        ('"hrms_addon.hrms_addon.learning.event_on_trash"', "a session deleted"),
        ('"hrms_addon.hrms_addon.learning.result_changed"', "marks given or taken back"),
        ('"hrms_addon.hrms_addon.learning.setup_on_migrate"', "seeded on migrate"),
        ('"Training Program": "hrms_addon.hrms_addon.connections.training_program_dashboard"',
         "the Training Program's connections")):
    check("hooks: " + what, needle in HOOKS)
check("hooks: a session held or cancelled", HOOKS.count('"hrms_addon.hrms_addon.learning.event_changed"') == 3)
check("hooks: results submitted, changed or cancelled", HOOKS.count('"hrms_addon.hrms_addon.learning.result_changed"')
      == 3)
check("hooks: the daily job in the long queue, the digest weekly",
      re.search(r'"daily_long": \[\s*(#[^\n]*\n\s*)*"hrms_addon\.hrms_addon\.learning\.daily"', HOOKS)
      and re.search(r'"weekly": \[\s*(#[^\n]*\n\s*)*"hrms_addon\.hrms_addon\.learning\.weekly"', HOOKS))
for field in program_fields:
    if field.startswith("custom_") and field != "custom_pass_mark":
        check("hooks: the fixture Training Program-%s is shipped" % field, '"Training Program-%s"' % field in HOOKS)
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for entry in ("Learning Passport", "Employee Training Requirement", "Employee Certification", "Training Matrix",
              "Training Compliance", "Certification Expiry", "Training Rule", "Certification", "Training Category",
              "Learning Settings"):
    check("the menus name %s, on the card and in the sidebar" % entry, NAV.count('("%s", ' % entry) >= 2)
check("the passport sits at the top of the Tenure sidebar", '"learning-passport": "graduation-cap"' in NAV)
CONNECTIONS = read("hrms_addon", "hrms_addon", "connections.py")
check("an employee's requirements and certificates under Learning on their form",
      'LEARNING_DOCS = ["Employee Training Requirement", "Employee Certification"]' in CONNECTIONS
      and '{"label": _("Learning"), "items": list(LEARNING_DOCS)}' in CONNECTIONS)
for folder in ("certification", "training_rule", "training_category"):
    check("%s lists what hangs off it" % folder,
          os.path.exists(os.path.join(APP, "doctype", folder, folder + "_dashboard.py")))
EMPLOYEE_JS = read("hrms_addon", "public", "js", "employee.js")
check("the Employee form opens the passport",
      'frappe.set_route("learning-passport", frm.doc.name)' in EMPLOYEE_JS)
page = json.load(open(os.path.join(APP, "page", "learning_passport", "learning_passport.json"), encoding="utf-8"))
page_roles = {row["role"] for row in page["roles"]}
check("every employee opens their own passport; supervisors, heads, HR and management theirs",
      {"Employee", "Supervisor", "Head of Department", "HR User", "HR Manager", "General Manager"} <= page_roles)
PAGE_JS = read("hrms_addon", "hrms_addon", "page", "learning_passport", "learning_passport.js")
check("the page asks the server, escapes what it is given, and goes to the employee picked",
      '"hrms_addon.hrms_addon.learning.passport"' in PAGE_JS and "frappe.utils.escape_html" in PAGE_JS
      and 'frappe.set_route("learning-passport", value)' in PAGE_JS)
check("the page lists what needs doing first", 'const LP_ORDER = ["Overdue", "Due Soon", "Pending", "Compliant", '
      '"Not Applicable"];' in PAGE_JS)
check("the page's lights are the rules' statuses", all('"%s"' % status in PAGE_JS or "%s:" % status in PAGE_JS
                                                       for status in R.LIGHTS))
for name, ref in (("Training Matrix", "Employee Training Requirement"),
                  ("Certification Expiry", "Employee Certification"),
                  ("Training Compliance", "Employee Training Requirement")):
    folder = name.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    source = read("hrms_addon", "hrms_addon", "report", folder, folder + ".py")
    check("%s is a script report on %s, for HR, heads, management and the auditor" % (name, ref),
          spec["report_type"] == "Script Report" and spec["ref_doctype"] == ref
          and {"HR User", "HR Manager", "Head of Department", "General Manager", "Auditor"}
          <= {row["role"] for row in spec["roles"]})
    check("%s reads through the user's own permissions" % name, "frappe.get_list(" in source)
MATRIX = read("hrms_addon", "hrms_addon", "report", "training_matrix", "training_matrix.py")
check("the matrix counts what the rules ask, not what was recommended or no longer applies",
      '"status": ["!=", rules.NOT_APPLICABLE], "requirement_type": ["!=", rules.RECOMMENDED]' in MATRIX)
check("the matrix is a tree from plant to employee",
      'LEVELS = ("branch", "department", "designation", "employee")' in MATRIX
      and "tree: true" in read("hrms_addon", "hrms_addon", "report", "training_matrix", "training_matrix.js"))
EXPIRY = read("hrms_addon", "hrms_addon", "report", "certification_expiry", "certification_expiry.py")
check("the expiry report leaves out what was renewed or revoked, and says who has been told",
      '"status": ["not in", [rules.RENEWED, rules.REVOKED]]' in EXPIRY and "told=" in EXPIRY)
COMPLIANCE = read("hrms_addon", "hrms_addon", "report", "training_compliance", "training_compliance.py")
check("the compliance report works each employee out as the passport does",
      "rules.summary(mine, day, s, assessment=marks.get(employee))" in COMPLIANCE)

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_learning: OK")
