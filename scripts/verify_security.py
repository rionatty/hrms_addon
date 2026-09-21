"""Verify security and access control, without a bench:

    python scripts/verify_security.py

The Security & Access Control sheet of Luuka's revised testing scripts,
and Employee Master case 6:

  case 1  role-based authorisation for the defined roles, including an
          Auditor who is read-only
  case 2  record-level security holding a user to their branch
  case 4  read-only access for Auditor and management
  case 5  field-level security: salary and bank details to HR and Payroll
          only (the same thing Employee Master case 6 asks for)

  Case 3, two-person control on payroll posting, is payroll's and is
  deferred with it.

  1  the fields that go out of reach, and who is let at them
  2  what a read-only role may and may not do
  3  the paper: the Property Setters that move the fields, and the report
  4  the glue grants and never revokes, and says where something is open
  5  wiring: run on migrate, and a way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import glob
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder,
                                      folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def hooks_dict():
    tree = ast.parse(read("hrms_addon", "hooks.py"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


S = load("security_rules")
hooks = hooks_dict()
SETTERS = json.load(open(os.path.join(PACKAGE, "fixtures", "property_setter.json"),
                         encoding="utf-8"))
print("loaded security_rules.py without Frappe")

# ── 1. The fields out of reach ────────────────────────────────────────
employee = fields_of(upstream_doctype("Employee"))
if not employee:
    fail.append("Employee was not found upstream, so nothing here can be checked")
for fieldname in S.PROTECTED:
    if fieldname not in employee:
        fail.append("Employee has no %s: the field being protected does not exist" % fieldname)
    if employee.get(fieldname, {}).get("permlevel"):
        fail.append("%s is already at a level upstream; check before moving it" % fieldname)
for fieldname in ("bank_ac_no", "iban", "ctc"):
    if fieldname not in S.PROTECTED:
        fail.append("%s is a salary or bank detail and must be out of reach" % fieldname)
if S.PROTECTED_LEVEL != 1:
    fail.append("the protected fields go to level one: %s" % S.PROTECTED_LEVEL)

# test case 5: HR and Payroll, and nobody else
if set(S.PRIVILEGED_ROLES) != {"HR Manager", "HR User", "Payroll Officer"}:
    fail.append("only HR and Payroll see the salary and bank fields: %s"
                % (S.PRIVILEGED_ROLES,))
grants = S.privileged_grants()
if set(grants["Employee"]) != set(S.PRIVILEGED_ROLES):
    fail.append("the level-one grant is to those roles and no others: %s" % grants)
leaks = S.level_one_leaks([
    {"role": "HR Manager", "permlevel": 1, "read": 1},
    {"role": "Employee", "permlevel": 1, "read": 1},
    {"role": "Auditor", "permlevel": 1, "read": 1},
    {"role": "Employee", "permlevel": 0, "read": 1}])
if sorted(leaks) != ["Auditor", "Employee"]:
    fail.append("anybody outside HR and Payroll at level one is named: %s" % leaks)
if S.level_one_leaks([{"role": "System Manager", "permlevel": 1, "read": 1}]):
    fail.append("the System Manager is not a leak: they administer the site")
print("the fields: salary and bank at level one, HR and Payroll and nobody else")

# ── 2. The read-only roles ────────────────────────────────────────────
if "Auditor" not in S.READ_ONLY_ROLES:
    fail.append("test case 1 names an Auditor")
for ptype in ("write", "create", "delete", "submit", "cancel"):
    if ptype in S.READ_ONLY_PTYPES:
        fail.append("a read-only role must not be granted %s" % ptype)
    if ptype not in S.FORBIDDEN_PTYPES:
        fail.append("%s must be one of the things a read-only role may not have" % ptype)
for ptype in ("read", "report", "export"):
    if ptype not in S.READ_ONLY_PTYPES:
        fail.append("an auditor must be able to %s" % ptype)
grants = S.read_only_grants(["Employee", "Appraisal"])
if set(grants) != {"Employee", "Appraisal"}:
    fail.append("every document named is granted: %s" % sorted(grants))
if any(ptype in S.FORBIDDEN_PTYPES
       for roles in grants.values() for ptypes in roles.values() for ptype in ptypes):
    fail.append("and none of them with anything but read")
if S.leaks({"role": "Auditor", "write": 1}) != ["write"]:
    fail.append("an auditor given write is a leak")
if S.leaks({"role": "Auditor", "read": 1}):
    fail.append("and one given read is not")
if S.leaks({"role": "HR Manager", "write": 1}):
    fail.append("an HR Manager with write is not a leak: it is their job")
print("the roles: an auditor reads everything and changes nothing")

# ── 3. Holding somebody to their branch ───────────────────────────────
permission = S.branch_permission("hro@luuka", "Kawempe")
if permission["allow"] != "Branch" or permission["for_value"] != "Kawempe":
    fail.append("a branch permission holds a user to a branch: %s" % permission)
if not permission["apply_to_all_doctypes"]:
    fail.append("and to every document unless one is named")
if S.branch_permission("hro@luuka", "Kawempe", "Leave Application")["applicable_for"] \
        != "Leave Application":
    fail.append("or to the one named")
unheld = S.unheld(["Leave Application", "Appraisal"], ["Leave Application"])
if unheld != ["Appraisal"]:
    fail.append("a document with no branch on it cannot be held by one, and is named: %s"
                % unheld)

rows = S.matrix([
    {"parent": "Employee", "role": "Auditor", "permlevel": 0, "read": 1, "report": 1},
    {"parent": "Employee", "role": "HR Manager", "permlevel": 1, "read": 1, "write": 1},
    {"parent": "Appraisal", "role": "HR User", "permlevel": 0, "read": 1, "write": 1}])
if [row["document"] for row in rows] != ["Appraisal", "Employee", "Employee"]:
    fail.append("the matrix reads by document: %s" % [row["document"] for row in rows])
if not rows[1]["read_only"] or rows[2]["read_only"]:
    fail.append("and says which rows are read-only: %s" % rows)
if rows[2]["level"] != 1:
    fail.append("and at which level")
print("the branch: a user held to one, and the matrix that says who may do what")

# ── 4. The paper ──────────────────────────────────────────────────────
setters = {row["name"]: row for row in SETTERS}
for row in S.property_setters():
    found = setters.get(row["name"])
    if not found:
        fail.append("%s is not in the property setter fixtures" % row["name"])
        continue
    if found.get("property") != "permlevel" or str(found.get("value")) != "1":
        fail.append("%s must put the field at level one: %s" % (row["name"], found))
    if found.get("doctype_or_field") != "DocField":
        fail.append("%s is a field property, not a doctype one" % row["name"])
listed = hooks.get("fixtures", [])
names = []
for block in listed:
    if block.get("dt") == "Property Setter":
        names = block["filters"][0][2]
for row in S.property_setters():
    if row["name"] not in names:
        fail.append("%s is not listed in hooks.py, so a migrate would not install it"
                    % row["name"])
report = json.load(open(os.path.join(APP, "report", "role_and_access_matrix",
                                     "role_and_access_matrix.json"), encoding="utf-8"))
if report.get("is_standard") != "Yes":
    fail.append("the matrix is a standard report")
if "Auditor" not in [row["role"] for row in report.get("roles", [])]:
    fail.append("and an auditor may read it")
print("the paper: the setters that move the fields, listed and installed")

# ── 5. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "security.py")
for needle, why in (
    ("rules.read_only_grants(", "the read-only grants come from the rules"),
    ("rules.privileged_grants(", "and so does who sees level one"),
    ("rules.leaks(", "a read-only role given write is noticed"),
    ("rules.level_one_leaks(", "and so is anybody else at level one"),
    ("rules.branch_permission(", "a user is held to their branch by a User Permission"),
    ("rules.matrix(", "and the matrix is built by the rules"),
    ("setup_custom_perms", "granting a custom rule copies the standard ones first"),
    ("add_permission", "and the grant is Frappe's own"),
):
    if needle not in glue:
        fail.append("security.py: %s (%r not found)" % (why, needle))
for forbidden, why in (
    ("remove_permission", "this app grants and never revokes"),
    ("frappe.db.delete", "and deletes nobody's permissions"),
):
    if forbidden in glue:
        fail.append("security.py: %s (%r found)" % (why, forbidden))
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef hold_to_branch\(', glue):
    fail.append("security.hold_to_branch changes something: a whitelisted POST method")
if "frappe.only_for(" not in glue:
    fail.append("and only an administrator or HR Manager may call it")
if "savepoint" not in glue:
    fail.append("the setup must not fail the deploy: a savepoint, like the workflows")
report_py = read("hrms_addon", "hrms_addon", "report", "role_and_access_matrix",
                 "role_and_access_matrix.py")
if "security.audit(" not in report_py:
    fail.append("the matrix reads the permissions the site actually has")
print("glue: granted and never revoked, and said where something is open")

# ── 6. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.security.setup_on_migrate" not in hooks.get("after_migrate", []):
    fail.append("the roles and the grants must be set on every migrate")
migrate = hooks.get("after_migrate", [])
if migrate.index("hrms_addon.hrms_addon.security.setup_on_migrate") \
        > migrate.index("hrms_addon.hrms_addon.navigation.setup_on_migrate"):
    fail.append("the grants are made before the navigation that leads to the documents")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if "Role and Access Matrix" not in nav:
    fail.append("the matrix has no way in")
if '"Role and Access Matrix": "Custom DocPerm"' not in nav:
    fail.append("and the report must say which document it is for")
print("wiring: set on migrate, before the navigation, with a way in")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL SECURITY CHECKS PASSED")
