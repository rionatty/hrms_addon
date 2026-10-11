"""Checks the monthly allowances managed on the Salary Structure Assignment,
without a bench.

    python scripts/verify_standing_allowances.py

  1  what the panel shows: running, still to start, ended; one left to run
     shown without a last day
  2  adding one: an earning, an amount, a first day not before the
     employee's first assignment or their joining, and never two of one
     component at once
  3  a new amount: from a later day the allowance as it was ends the day
     before; from its own first day only while no slip has paid it
  4  the last day, running it on again, and taking one off
  5  wiring: the panel's two fields on the assignment, the To Date setter on
     Additional Salary, the form script's calls, and the server working
     under the user's own permissions

The rules are loaded without Frappe.
"""
import ast
import datetime
import importlib.util
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)
        print("FAIL", label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("standing_allowance_rules")
D = datetime.date


def rec(name, component, amount, start, end=None):
    return {"name": name, "salary_component": component, "amount": amount, "from_date": start, "to_date": end}


HOUSE = rec("A1", "House Rent Allowance", 72342, "2026-01-01", "2099-12-31")
TRANSPORT = rec("A2", "Transport Allowance", 70000, "2026-01-01", "2099-12-31")
MEALS = rec("A3", "Meals Allowance", 30000, "2026-11-01", "2099-12-31")
ACTING = rec("A4", "Acting Allowance", 100000, "2026-03-01", "2026-06-30")

# ── 1. the panel ────────────────────────────────────────────────────────
rows = R.view([ACTING, MEALS, TRANSPORT, HOUSE], "2026-10-12", paid={"A1", "A2", "A4"})
check([(row["salary_component"], row["state"]) for row in rows] ==
      [("House Rent Allowance", R.RUNNING), ("Transport Allowance", R.RUNNING), ("Meals Allowance", R.STARTS),
       ("Acting Allowance", R.ENDED)], "running first, then those to start, then those ended: %s"
      % [(row["salary_component"], row["state"]) for row in rows])
check(rows[0]["to_date"] is None and rows[3]["to_date"] == D(2026, 6, 30), "one left to run shows no last day")
check([row["paid"] for row in rows] == [True, True, False, True], "which a slip has paid")
check(R.total_running(rows) == 142342, "what the running ones add up to a month: %s" % R.total_running(rows))
check(R.state(ACTING, "2026-06-30") == R.RUNNING and R.state(ACTING, "2026-07-01") == R.ENDED
      and R.state(ACTING, "2026-02-28") == R.STARTS and R.state(ACTING, "2026-03-01") == R.RUNNING,
      "the first and the last day are days it runs")
check(R.is_open(None) and R.is_open("2099-12-31") and not R.is_open("2026-06-30"), "left to run, or not")
check(R.last_day(None) == R.OPEN_END and R.last_day("2026-06-30") == D(2026, 6, 30)
      and R.last_day(None, "2026-12-31") == D(2026, 12, 31) and R.last_day("2026-06-30", "2026-12-31") == D(2026, 6, 30),
      "the last day kept on record: the open end, and never past the day the employee leaves")
check(R.view(None, "2026-10-12") == [] and R.total_running([]) == 0, "nobody's allowances")

# ── 2. adding ───────────────────────────────────────────────────────────
def adding(**more):
    facts = {"salary_component": "Meals Allowance", "component": {"type": "Earning", "disabled": 0}, "amount": 30000,
             "from_date": "2026-11-01", "to_date": None, "joined": "2025-06-01", "relieving": None,
             "assigned_from": "2026-01-01", "others": [HOUSE, TRANSPORT]}
    facts.update(more)
    return R.add_errors(facts)


check(adding() == [], "an earning, an amount and a first day: added")
check(adding(salary_component=None) and "Choose the allowance." in adding(salary_component=None), "no allowance chosen")
check(any("not a salary component" in e for e in adding(component=None)), "a component that does not exist")
check(any("is a deduction" in e for e in adding(component={"type": "Deduction", "disabled": 0})), "a deduction is no allowance")
check(any("is disabled" in e for e in adding(component={"type": "Earning", "disabled": 1})), "a disabled component")
check(any("more than nothing" in e for e in adding(amount=0)) and any("more than nothing" in e for e in adding(amount=-5)),
      "an amount of nothing, or less")
check(adding(from_date=None) == ["Enter the day it starts."], "no first day")
check(any("cannot be before the first" in e for e in adding(to_date="2026-10-31")), "a last day before the first")
check(any("no salary structure assignment yet" in e for e in adding(assigned_from=None)), "no assignment yet")
check(any("first salary structure assignment on 01-01-2026" in e for e in adding(from_date="2025-12-01")),
      "before the employee's first assignment")
check(any("joined on 01-06-2025" in e for e in adding(from_date="2025-05-01", assigned_from="2025-01-01")),
      "before the employee joined")
check(any("leaves on 31-12-2026" in e for e in adding(relieving="2026-12-31", to_date="2027-01-31"))
      and any("leaves on 31-10-2026" in e for e in adding(relieving="2026-10-31"))
      and adding(relieving="2026-12-31") == [], "past the day the employee leaves; one left to run stops there itself")
twice = adding(salary_component="House Rent Allowance", from_date="2026-06-01")
check(len(twice) == 1 and "House Rent Allowance of 72,342 already runs from 01-01-2026. Change its amount or end it"
      in twice[0], "a second one of a component that is running: %s" % twice)
check(adding(salary_component="Acting Allowance", from_date="2026-07-01", others=[ACTING]) == [],
      "the same component again once the earlier one has ended")
check(any("already runs from 01-03-2026 to 30-06-2026" in e
          for e in adding(salary_component="Acting Allowance", from_date="2026-06-30", others=[ACTING])),
      "but not on its last day")
check(R.overlaps("2026-01-01", None, "2030-01-01", None) and not R.overlaps("2026-01-01", "2026-06-30", "2026-07-01", None)
      and R.overlaps("2026-01-01", "2026-06-30", "2026-06-30", "2026-12-31") and not R.overlaps(None, None, "2026-01-01", None),
      "two runs meet when they share a day")

# ── 3. a new amount ─────────────────────────────────────────────────────
later = R.change_plan(HOUSE, 90000, "2026-11-01", paid=True)
check(later == {"kind": R.SUCCEED, "end_on": D(2026, 10, 31)},
      "from a later day: the allowance as it was ends the day before: %s" % later)
check(R.change_plan(HOUSE, 90000, "2026-01-01", paid=False) == {"kind": R.CORRECT},
      "from its own first day, while no slip has paid it: put right in place")
paid_from_start = R.change_plan(HOUSE, 90000, "2026-01-01", paid=True)
check("errors" in paid_from_start and "A salary slip has paid" in paid_from_start["errors"][0],
      "from its own first day once paid: refused, the day the new amount starts is asked for")
check("errors" in R.change_plan(HOUSE, 72342, "2026-11-01") and "already has" in R.change_plan(HOUSE, 72342, "2026-11-01")["errors"][0],
      "the same amount is no change")
check("errors" in R.change_plan(HOUSE, 0, "2026-11-01") and "errors" in R.change_plan(HOUSE, 90000, None),
      "no amount, or no day")
check("before the allowance did on 01-01-2026" in R.change_plan(HOUSE, 90000, "2025-12-01")["errors"][0],
      "a new amount from before the allowance began")
check("ends on 30-06-2026" in R.change_plan(ACTING, 120000, "2026-07-01")["errors"][0], "a new amount after it has ended")
check(R.change_plan(ACTING, 120000, "2026-06-30") == {"kind": R.SUCCEED, "end_on": D(2026, 6, 29)},
      "a new amount for its last day alone")

# ── 4. the last day, and taking one off ─────────────────────────────────
check(R.end_errors(HOUSE, "2026-10-31") == [], "a last day")
check("before it started on 01-01-2026" in R.end_errors(HOUSE, "2025-12-31")[0], "a last day before it started")
check(R.end_errors(ACTING, None, [ACTING]) == [], "running it on again with nothing in its way")
second = rec("A5", "Acting Allowance", 120000, "2026-09-01", "2099-12-31")
blocked = R.end_errors(ACTING, None, [ACTING, second])
check(len(blocked) == 1 and "Acting Allowance of 120,000 already runs from 01-09-2026" in blocked[0],
      "running it on into a later one of the same component is refused: %s" % blocked)
check(R.end_errors(ACTING, "2026-08-31", [ACTING, second]) == [] and R.end_errors(ACTING, "2026-09-01", [ACTING, second]) != [],
      "a later last day up to the day before the next one starts")
check(R.end_errors(ACTING, "2026-05-31", [ACTING, second]) == [], "an earlier last day never runs into anything")
check(R.remove_errors(MEALS, paid=False) == [] and "stays on record" in R.remove_errors(HOUSE, paid=True)[0],
      "one never paid is taken off; one a slip has paid is ended instead")

# ── 5. wiring ───────────────────────────────────────────────────────────
custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
ours = {row["fieldname"]: row for row in custom if row["dt"] == "Salary Structure Assignment"}
check(ours.get("custom_allowances_section", {}).get("fieldtype") == "Section Break"
      and ours["custom_allowances_section"]["label"] == "Allowances"
      and ours["custom_allowances_section"]["insert_after"] == "payroll_payable_account",
      "the Allowances section sits after the assignment's pay fields")
check(ours.get("custom_allowances_html", {}).get("fieldtype") == "HTML"
      and ours["custom_allowances_html"]["insert_after"] == "custom_allowances_section",
      "the panel is an HTML field under it, one field per anchor")
check("custom_section" not in ours, "no field named custom_section")
setters = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "property_setter.json"))}
to_date = setters.get("Additional Salary-to_date-allow_on_submit", {})
check((to_date.get("doc_type"), to_date.get("field_name"), to_date.get("property"), to_date.get("value")) ==
      ("Additional Salary", "to_date", "allow_on_submit", "1"), "an allowance's To Date can be set after submit")
hooks_source = read("hrms_addon", "hooks.py")
for name in ("Salary Structure Assignment-custom_allowances_section", "Salary Structure Assignment-custom_allowances_html",
             "Additional Salary-to_date-allow_on_submit"):
    check('"%s"' % name in hooks_source, "hooks fixtures list %s" % name)
check('"Salary Structure Assignment": "public/js/salary_structure_assignment.js"' in hooks_source,
      "the assignment's form script is attached")
glue = read("hrms_addon", "hrms_addon", "standing_allowances.py")
script = read("hrms_addon", "public", "js", "salary_structure_assignment.js")
whitelisted = {name: args for args, name in re.findall(r"@frappe\.whitelist\(([^)]*)\)\s*\ndef (\w+)\(", glue)}
check(set(whitelisted) == {"allowances", "add", "change", "end", "remove"}, "five calls for the panel: %s" % sorted(whitelisted))
for name in ("add", "change", "end", "remove"):
    check('methods=["POST"]' in whitelisted.get(name, ""), "%s changes something, so it takes POST only" % name)
called = set(re.findall(r'ha_standing_send\(frm, "(\w+)"', script)) | set(re.findall(r'HA_STANDING \+ "(\w+)"', script))
check(called == set(whitelisted), "the form script calls exactly those: %s" % sorted(called))
check('const HA_STANDING = "hrms_addon.hrms_addon.standing_allowances.";' in script, "at standing_allowances.py")
check("ignore_permissions" not in glue, "nothing is done past the user's own permissions on Additional Salary")
check("frappe.has_permission(RECORD, ptype, throw=True)" in glue and 'doc.check_permission("write")' in glue
      and glue.count('frappe.has_permission("Employee", "read"') == 2, "and on the employee")
new = glue.split("def _new(")[1].split("\ndef ")[0]
check('"is_recurring": 1' in new and '"overwrite_salary_structure_amount": 0' in new and "doc.submit()" in new
      and "rules.last_day(to_date, relieving)" in new,
      "an allowance is a submitted recurring Additional Salary, paid beside the structure, with a last day on record")
check("doc.disabled = 1" in glue.split("def _disable(")[1] and "doc.cancel()" not in glue,
      "one taken off is disabled, as HR may; nothing is cancelled")
check("pay.monthly_gross(employee)" in glue.split("def allowances(")[1].split("\ndef ")[0],
      "the panel's gross is the one every module uses")
tree = ast.parse(glue)
typed = [arg.arg for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in whitelisted
         for arg in node.args.args if arg.annotation is not None]
check(not typed, "no typed argument on a call the form makes (an empty value would be refused unseen): %s" % typed)
check("fields_dict.custom_allowances_html" in script and "frappe.utils.escape_html" in script,
      "the panel draws in its own field and escapes what it prints")
check('values[key] !== ""' in script, "an empty value is left out of what the form sends")

print()
print("FAILED: %d" % len(fail) if fail else "ALL STANDING ALLOWANCE CHECKS PASSED")
sys.exit(1 if fail else 0)
