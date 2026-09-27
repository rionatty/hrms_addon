"""Checks for a Job Requisition's headcount against the staffing plan, run
without a bench.

staffing_rules.py imports nothing from Frappe, so it is loaded directly: the
gap is the plan's positions less the people the job title has and the
positions already being filled; asking beyond it is said in numbers; with no
plan nothing is measured. It also checks the glue in job_requisition.py
(drawn on every save until the requisition is decided, and for the form on
behalf of whoever writes requisitions), the Headcount section's fields and
their place on the form, the form script, and against Frappe HR
(../ERPNext, or FRAPPE_APPS_ROOT) what the figures rest on.

    python scripts/verify_staffing.py
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
UPSTREAM_OK = os.path.isdir(APPS_ROOT)
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(app, *parts):
    return open(os.path.join(APPS_ROOT, app, app, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def function(source, name):
    """A function's text, up to the first line not inside it."""
    start = source.index("def %s(" % name)
    depth = start - (source.rfind(chr(10), 0, start) + 1)
    lines = source[start:].split(chr(10))
    kept = [lines[0]]
    for line in lines[1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= depth:
            break
        kept.append(line)
    return chr(10).join(kept)


R = load("staffing_rules")
print("loaded staffing_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
for args, wanted in (
        ((5, 3, 1, 1, True), {"gap": 1, "over_by": 0, "verdict": R.WITHIN}),
        ((5, 3, 1, 2, True), {"gap": 1, "over_by": 1, "verdict": "1 above the plan"}),
        ((5, 3, 2, 1, True), {"gap": 0, "over_by": 1, "verdict": "1 above the plan"}),
        ((5, 6, 0, 2, True), {"gap": -1, "over_by": 2, "verdict": "2 above the plan"}),
        ((5, 3, 0, 0, True), {"gap": 2, "over_by": 0, "verdict": R.WITHIN}),
        ((0, 3, 1, 4, False), {"gap": None, "over_by": 0, "verdict": R.NO_PLAN}),
        (("5", "3", None, "2", True), {"gap": 2, "over_by": 0, "verdict": R.WITHIN}),
):
    got = R.headcount(*args)
    if got != wanted:
        fail.append("headcount%r should be %r, is %r" % (args, wanted, got))
openings = [{"vacancies": 2, "job_requisition": "JR-2"}, {"vacancies": 0, "job_requisition": None},
            {"vacancies": 1, "job_requisition": "JR-1"}]
requisitions = [{"name": "JR-2", "no_of_positions": 2}, {"name": "JR-3", "no_of_positions": 3},
                {"name": "JR-4", "no_of_positions": 0}, {"name": "JR-1", "no_of_positions": 1}]
if R.being_filled(openings, requisitions, "JR-1") != 2 + 1 + 3 + 1:
    fail.append("being filled: the openings (one with no number counts one), the requisitions without an opening, "
                "never this requisition's own: %r" % R.being_filled(openings, requisitions, "JR-1"))
if R.being_filled([], [], None) != 0 or R.being_filled(None, None) != 0:
    fail.append("nothing being filled is nought")
plans = [{"name": "SP-2025", "from_date": "2025-01-01", "to_date": "2025-12-31", "number_of_positions": 4},
         {"name": "SP-2026", "from_date": "2026-01-01", "to_date": "2026-12-31", "number_of_positions": 6},
         {"name": "SP-2026-H2", "from_date": "2026-07-01", "to_date": "2026-12-31", "number_of_positions": 7}]
if (R.plan_for(plans, "2026-03-01") or {}).get("name") != "SP-2026" \
        or (R.plan_for(plans, "2026-09-27") or {}).get("name") != "SP-2026-H2" \
        or R.plan_for(plans, "2027-01-01") is not None or (R.plan_for(plans, "2026-12-31") or {}).get("name") != "SP-2026-H2":
    fail.append("the plan covering the day, the latest starting first, its last day included")
if set(R.LIVE_STATUSES) != {"Pending", "Open & Approved"}:
    fail.append("a live requisition is Pending or Open & Approved: %r" % (R.LIVE_STATUSES,))
print("the rules: the gap, what is asked beyond it, what is already being filled, the plan for the day")

# ── 2. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "job_requisition.py")
validate = function(glue, "validate")
if "if new_state not in (rules.APPROVED, rules.REJECTED) or old_state not in (rules.APPROVED, rules.REJECTED):" \
        not in validate or 'values = headcount_values(doc.get("designation"), doc.get("company"), ' \
                              'doc.get("no_of_positions"),' not in validate \
        or "doc.update({field: values[field] for field in HEADCOUNT_FIELDS})" not in validate:
    fail.append("validate draws the headcount on every save until the requisition is decided, then keeps it; "
                "only the section's own fields are set")
values = function(glue, "headcount_values")
for needle, why in (
        ('frappe.db.count("Employee", {"designation": designation, "status": "Active",', "active people with the job title"),
        ('"company": ["in", companies]}', "across the company and those under it, as Frappe HR counts"),
        ('filters={"designation": designation, "status": "Open",', "the open openings for it"),
        ('"status": ["in", list(staffing_rules.LIVE_STATUSES)], "name": ["!=", requisition or ""]}',
         "the other live requisitions"),
        ('filters[rules.STATE_FIELD] = ["not in", [rules.DRAFT, rules.REJECTED]]', "a draft or a refusal is not on its way"),
        ("staffing_rules.being_filled(openings, others, requisition)", "being filled, this requisition's own left out"),
        ("staffing_rules.headcount(planned, current, filling, requested, bool(plan))", "the gap and the verdict")):
    if needle not in values:
        fail.append("headcount_values: %s" % why)
plan = function(glue, "_staffing_plan")
if 'filters={"company": company, "docstatus": 1}' not in plan or '"designation": designation}' not in plan \
        or 'company = frappe.db.get_value("Company", company, "parent_company")' not in plan \
        or "staffing_rules.plan_for(" not in plan:
    fail.append("the plan: a submitted one with a line for the job title, the company's own else its parent's")
if not re.search(r"@frappe\.whitelist\(\)\ndef get_headcount\(", glue) \
        or 'frappe.has_permission("Job Requisition", "write", throw=True)' not in function(glue, "get_headcount"):
    fail.append("get_headcount is whitelisted for whoever writes requisitions")
if tuple(re.findall(r'"(custom_[a-z_]+)"', glue.split("HEADCOUNT_FIELDS = (", 1)[1].split(")", 1)[0])) != (
        "custom_staffing_plan", "custom_planned_positions", "custom_current_headcount", "custom_positions_filling",
        "custom_headcount_gap", "custom_against_plan"):
    fail.append("HEADCOUNT_FIELDS are the Headcount section's fields")
print("glue: drawn until decided, the plan, the people, what is being filled, for the form too")

# ── 3. The fields and the form ────────────────────────────────────────
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
setters = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "property_setter.json"))}
hooks = read("hrms_addon", "hooks.py")
wanted = [("custom_headcount_section", "Section Break"), ("custom_staffing_plan", "Link"),
          ("custom_planned_positions", "Int"), ("custom_current_headcount", "Int"), ("custom_headcount_cb", "Column Break"),
          ("custom_positions_filling", "Int"), ("custom_headcount_gap", "Int"), ("custom_against_plan", "Data")]
for fieldname, fieldtype in wanted:
    row = custom.get("Job Requisition-" + fieldname) or {}
    if row.get("fieldtype") != fieldtype:
        fail.append("Job Requisition has no %s (%s)" % (fieldname, fieldtype))
    if fieldtype not in ("Section Break", "Column Break") and not (row.get("read_only") and row.get("no_copy")):
        fail.append("%s is worked out, never typed or copied" % fieldname)
    if '"Job Requisition-%s",' % fieldname not in hooks:
        fail.append("hooks.py fixtures must list Job Requisition-%s" % fieldname)
if (custom.get("Job Requisition-custom_staffing_plan") or {}).get("options") != "Staffing Plan":
    fail.append("the plan is a link to Frappe HR's Staffing Plan")
order = json.loads((setters.get("Job Requisition-main-field_order") or {}).get("value") or "[]")
at = order.index("status") if "status" in order else -1
if order[at + 1:at + 1 + len(wanted)] != [name for name, _type in wanted] \
        or order[at + 1 + len(wanted):at + 2 + len(wanted)] != ["custom_reason_section"]:
    fail.append("the Headcount section sits between the status and the reason, in the form's field order")
if (custom.get("Job Requisition-custom_headcount_section") or {}).get("insert_after") != "status" \
        or (custom.get("Job Requisition-custom_reason_section") or {}).get("insert_after") != "custom_against_plan":
    fail.append("insert_after says the same as the field order")
js = read("hrms_addon", "public", "js", "job_requisition.js")
for needle, why in (
        ("\tdesignation(frm) {", "the job title"), ("\tcompany(frm) {\n\t\tha_fill_headcount(frm);", "the company"),
        ("\tno_of_positions(frm) {\n\t\tha_fill_headcount(frm);", "the number of positions"),
        ('frappe\n\t\t.xcall("hrms_addon.hrms_addon.job_requisition.get_headcount", {', "the server draws it"),
        ("if (HA_DECIDED.includes(frm.doc.workflow_state)) {\n\t\treturn;", "a decided requisition keeps its figures"),
        ('String(frm.doc.custom_against_plan || "").includes("above the plan")', "the notice after a reload too"),
        ("} else if (frm.ha_headcount_intro) {", "only its own notice is cleared")):
    if needle not in js:
        fail.append("job_requisition.js: %s" % why)
if "ha_fill_headcount(frm);\n\t},\n\tcompany(frm)" not in js:
    fail.append("job_requisition.js: the job title draws the headcount too")
print("fields: the Headcount section after the status, worked out and read-only; the form draws it live")

# ── 4. What Frappe HR must still do ───────────────────────────────────
if UPSTREAM_OK:
    detail = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "staffing_plan_detail",
                                                             "staffing_plan_detail.json"))["fields"]}
    plan_fields = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "staffing_plan",
                                                                "staffing_plan.json"))["fields"]}
    if not {"designation", "number_of_positions", "vacancies", "current_count"} <= detail \
            or not {"company", "from_date", "to_date", "staffing_details"} <= plan_fields:
        fail.append("Frappe HR's Staffing Plan changed its fields: recheck _staffing_plan")
    plan_code = upstream("hrms", "hr", "doctype", "staffing_plan", "staffing_plan.py")
    if "detail.number_of_positions = cint(detail.vacancies) + cint(detail.current_count)" not in plan_code:
        fail.append("Frappe HR no longer counts a plan's positions as its people plus its vacancies: recheck 'planned'")
    if 'parent_company = frappe.get_cached_value("Company", company, "parent_company")' not in plan_code \
            or '{"designation": designation, "status": "Active", "company": ("in", company_set)}' not in plan_code:
        fail.append("Frappe HR counts people or looks for plans differently now: recheck headcount_values")
    requisition = json.loads(upstream("hrms", "hr", "doctype", "job_requisition", "job_requisition.json"))
    status = next((f for f in requisition["fields"] if f["fieldname"] == "status"), {})
    if not set(R.LIVE_STATUSES) <= set((status.get("options") or "").split(chr(10))):
        fail.append("Frappe HR's requisition statuses changed: recheck LIVE_STATUSES")
    opening = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "job_opening",
                                                            "job_opening.json"))["fields"]}
    if not {"designation", "status", "company", "vacancies", "job_requisition"} <= opening:
        fail.append("Frappe HR's Job Opening changed: recheck the openings being filled")
    upstream_note = "checked against Frappe HR"
else:
    upstream_note = "Frappe HR not found at %s, upstream contract not checked" % APPS_ROOT
print("upstream: %s" % upstream_note)

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL STAFFING CHECKS PASSED")
