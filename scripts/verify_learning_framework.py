"""Verify the competency framework, the Skills Bank and cover by shift (the LMS rebuild, 18 Nov 2026), without a
bench:

    python scripts/verify_learning_framework.py
"""
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


def fields(name):
    folder = name.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))
    return {field["fieldname"]: field for field in spec["fields"]}


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %s" % (detail,)) if detail != "" else ""))


R = load("competency_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
check("the brief's categories, every older type placed in one", list(R.CATEGORIES) == [
    "Core", "Functional", "Technical", "Safety", "Leadership", "Behavioural"]
      and set(R.TYPE_CATEGORY) == set(R.SKILL_TYPES) and set(R.TYPE_CATEGORY.values()) <= set(R.CATEGORIES))
check("five levels described by default", [level for level, _text in R.DEFAULT_DESCRIPTORS] == [1, 2, 3, 4, 5])
PROFILES = [{"designation": "Operator", "work_section": None, "skills": [{"skill": "5S", "required_level": "3 Works"}]},
            {"designation": "Operator", "work_section": "Extrusion", "skills": [
                {"skill": "Extruder", "required_level": "4 Competent Independently", "critical": 1, "weight": 3},
                {"skill": "5S", "required_level": "2 Basic Understanding", "critical": 0, "weight": 1}]}]
check("the profile that applies: the job title's for the section, else for every section",
      R.profile_for(PROFILES, "Operator", "Extrusion")["work_section"] == "Extrusion"
      and R.profile_for(PROFILES, "Operator", "Printing")["work_section"] is None
      and R.profile_for(PROFILES, "Supervisor", "Extrusion") is None)
check("a profile gives a skill its level and whether it is critical",
      R.profile_level(PROFILES[1], "Extruder") == (4, 1) and R.profile_level(PROFILES[1], "Lathe") == (None, None))
FIT = R.role_fit({"Extruder": "2 Basic Understanding", "5S": "4 Competent Independently"}, PROFILES[1])
check("a role fit: each skill's level against the level needed, weighed; the gaps, the missing, the critical gaps",
      (FIT["fit"], FIT["gaps"], FIT["missing"], FIT["critical_gaps"]) == (62.5, [("Extruder", 4, 2)], [], ["Extruder"]),
      FIT)
check("a role fit with nothing assessed, and with no profile", R.role_fit({}, PROFILES[1])["missing"]
      == ["Extruder", "5S"] and R.role_fit({}, None)["fit"] is None)
check("the people a skill needs per shift: its own, else the settings', never more than the crew",
      R.shift_need(3, 2, 10) == 3 and R.shift_need(None, 2, 10) == 2 and R.shift_need(5, 2, 4) == 4
      and R.shift_need(None, 2, None) == 2)
check("cover across a plant's shifts: none, one person, a shift short, enough",
      R.shift_cover({}, 2, ["Day", "Night"])["status"] == R.NO_COVER
      and R.shift_cover({"Day": 1}, 2, ["Day", "Night"])["status"] == R.SINGLE
      and R.shift_cover({"Day": 3, "Night": 1}, 2, ["Day", "Night"]) == {"status": R.THIN, "short": ["Night"]}
      and R.shift_cover({"Day": 2, "Night": 2}, 2, ["Day", "Night"]) == {"status": R.OK, "short": []})
check("the risk colours: red for none or one, amber thin, green enough", (R.RISK[R.NO_COVER], R.RISK[R.SINGLE],
                                                                          R.RISK[R.THIN], R.RISK[R.OK])
      == ("red", "red", "amber", "green"))
check("the levels at or above one, for a filter", R.level_names_from(4) == list(R.LEVEL_NAMES[3:])
      and R.level_names_from(0) == list(R.LEVEL_NAMES))

# ── 2. The paper ──────────────────────────────────────────────────────
profile = fields("Role Competency Profile")
check("a role profile: job title, section, plant, its skills", {"designation", "work_section", "branch", "skills"}
      <= set(profile) and profile["skills"]["options"] == "Role Competency Profile Skill")
row = fields("Role Competency Profile Skill")
check("a profile's skill: level needed on the scale, critical, weight", {"skill", "required_level", "critical", "weight"}
      <= set(row) and [v for v in row["required_level"]["options"].split("\n") if v] == list(R.LEVEL_NAMES))
check("a level descriptor per level", [v for v in fields("Skill Level Descriptor")["level"]["options"].split("\n") if v]
      == list(R.LEVEL_NAMES))
check("a machine a skill runs, in a section and plant", {"machine", "work_section", "branch"} <= set(fields("Skill Machine")))
custom = {row["fieldname"]: row for row in json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"),
                                                           encoding="utf-8")) if row["dt"] == "Skill"}
HOOKS = read("hrms_addon", "hooks.py")
for field, options in (("custom_competency_category", "Competency Category"), ("custom_level_descriptors",
                                                                              "Skill Level Descriptor"),
                       ("custom_machines", "Skill Machine"), ("custom_cover_per_shift", None)):
    check("Skill has %s, shipped" % field, field in custom and (options is None or custom[field].get("options") == options)
          and '"Skill-%s"' % field in HOOKS)
check("the skill's fields chained one after another", custom["custom_branch"]["insert_after"]
      == "custom_competency_category" and custom["custom_competency_category"]["insert_after"] == "custom_skill_type")

# ── 3. The glue and the wiring ────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "competency.py")
check("no SQL of its own", "frappe.db.sql" not in GLUE)
check("the level needed: the role's profile first", "rules.profile_for(profiles([doc.designation])" in GLUE
      and "level or rules.required_level(" in GLUE)
check("talent can ask how people fit a role, in one read", "def fit_for(employees, designation, work_section=None):"
      in GLUE and "rules.role_fit(" in GLUE)
check("the Skills Bank reads through the user's permissions, today's shift and leave each in one read",
      "frappe.get_list(ASSESSMENT" in GLUE and "def today_shifts(" in GLUE and "def on_leave(" in GLUE)
check("a machine's name finds its skills", "def skills_matching(text):" in GLUE and "MACHINE" in GLUE)
for name in ("skills_bank", "employee_fit"):
    check("%s is whitelisted" % name, re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, GLUE))
check("hooks: a skill's category and levels on save", '"hrms_addon.hrms_addon.competency.skill_validate"' in HOOKS)
check("the categories seeded by a patch", "hrms_addon.patches.v1_0.lms_competency_framework"
      in read("hrms_addon", "patches.txt"))
check("Skills Cover shows each plant's shifts", "def by_shift(filters):" in read(
    "hrms_addon", "hrms_addon", "report", "skills_cover", "skills_cover.py"))
page = json.load(open(os.path.join(APP, "page", "skills_bank", "skills_bank.json"), encoding="utf-8"))
check("the Skills Bank page asks the server", '"hrms_addon.hrms_addon.competency.skills_bank"' in read(
    "hrms_addon", "hrms_addon", "page", "skills_bank", "skills_bank.js") and page["name"] == "skills-bank")
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for entry in ("Role Competency Profile", "Skills Bank", "Competency Category"):
    check("the menus name %s, on the card and in the sidebar" % entry, NAV.count('("%s", ' % entry) >= 2)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_learning_framework: OK")
