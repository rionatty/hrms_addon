"""Verify every doctype's own permission rows pass Frappe's checks, without a bench:

    python scripts/verify_doctype_permissions.py

The deploy grants the read-only roles on every doctype of this app
(security.setup_on_migrate), and Frappe then checks all of that doctype's
rows, not only the new ones (validate_permissions in
frappe/core/doctype/doctype/doctype.py). One row it refuses stops the grant:
on 18 Nov 2026 a General Manager who could submit a Plant Day Sheet without
write, and Import on doctypes that were not importable, failed the deploy's
security setup. These are the same rules, read from the JSON:

  1  every row has a basic right (select, read, write, create, submit, cancel)
  2  one row for a role, level and if-owner
  3  cancel needs submit; submit, cancel and amend need write; import needs create
  4  submit and amend only where the doctype is submittable
  5  import only where the doctype allows import
  6  a level above 0 only for a role with a rule at level 0
  7  and the checks themselves catch each of those
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
EVERYONE = ("All", "Desk User")
fail = []


def refused(doc):
    """What Frappe would refuse in this doctype's permission rows."""
    rows = doc.get("permissions") or []
    submittable, importable = int(doc.get("is_submittable") or 0), int(doc.get("allow_import") or 0)
    found = []
    for index, row in enumerate(rows):
        def has(right):
            return int(row.get(right) or 0)

        level = has("permlevel")
        where = "row %d (%s, level %d)" % (index + 1, row.get("role"), level)
        if not (has("select") or has("read") or has("write") or has("create") or has("submit") or has("cancel")):
            found.append(where + ": no basic right")
        if any(other is not row and other.get("role") == row.get("role") and int(other.get("permlevel") or 0) == level
               and int(other.get("if_owner") or 0) == has("if_owner") for other in rows):
            found.append(where + ": a second row for the same role and level")
        if has("cancel") and not has("submit"):
            found.append(where + ": cancel without submit")
        if (has("submit") or has("cancel") or has("amend")) and not has("write"):
            found.append(where + ": submit, cancel or amend without write")
        if has("import") and not has("create"):
            found.append(where + ": import without create")
        if has("submit") and not submittable:
            found.append(where + ": submit on a doctype that is not submittable")
        elif has("amend") and not submittable:
            found.append(where + ": amend on a doctype that is not submittable")
        if has("import") and not importable:
            found.append(where + ": import on a doctype that does not allow import")
        if level > 0 and row.get("role") not in EVERYONE and not any(
                other is not row and other.get("role") == row.get("role") and not int(other.get("permlevel") or 0)
                for other in rows):
            found.append(where + ": a level above 0 with no rule at level 0")
    return found


checked = 0
for path in sorted(glob.glob(os.path.join(APP, "doctype", "*", "*.json"))):
    name = os.path.basename(os.path.dirname(path))
    if os.path.basename(path) != name + ".json":
        continue
    doc = json.load(open(path, encoding="utf-8"))
    if doc.get("doctype") != "DocType" or doc.get("istable"):
        continue
    checked += 1
    for problem in refused(doc):
        fail.append("%s: %s" % (doc.get("name"), problem))
if checked < 50:
    fail.append("only %d doctypes were read: the folder moved?" % checked)
print("1-6  the permission rows of %d doctypes, read as Frappe reads them" % checked)

# 7: each rule catches what it is for
GOOD = {"role": "HR Manager", "read": 1, "write": 1, "create": 1}
CASES = [
    ("no basic right", {"is_submittable": 0}, [{"role": "HR User", "print": 1}]),
    ("a second row", {}, [GOOD, dict(GOOD)]),
    ("cancel without submit", {"is_submittable": 1}, [dict(GOOD, cancel=1)]),
    ("submit without write", {"is_submittable": 1}, [{"role": "General Manager", "read": 1, "submit": 1}]),
    ("import without create", {"allow_import": 1}, [{"role": "HR Manager", "read": 1, "write": 1, "import": 1}]),
    ("submit, not submittable", {"is_submittable": 0}, [dict(GOOD, submit=1)]),
    ("import, not importable", {"allow_import": 0}, [dict(GOOD, **{"import": 1})]),
    ("level 1 alone", {}, [GOOD, {"role": "Accounts User", "read": 1, "permlevel": 1}]),
]
for label, settings, rows in CASES:
    if not refused(dict(settings, permissions=rows)):
        fail.append("the check let through: " + label)
if refused({"is_submittable": 1, "allow_import": 1, "permissions": [
        dict(GOOD, submit=1, cancel=1, amend=1, **{"import": 1}), {"role": "HR Manager", "read": 1, "permlevel": 1},
        {"role": "All", "read": 1, "permlevel": 2}]}):
    fail.append("the check refused rows Frappe accepts")
print("7    each rule catches its case, and lets the right rows through")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL DOCTYPE PERMISSION CHECKS PASSED")
