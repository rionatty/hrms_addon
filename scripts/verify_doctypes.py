"""Verify that every DocType and Script Report in this app can be synced by
`bench migrate`, without a bench:

    python scripts/verify_doctypes.py

Syncing a DocType imports its Python module (DocType.on_update runs the
module's on_doctype_update), so a DocType folder without its .py stops the
whole migrate with "Module import failed", and nothing after it is synced:
not the DocTypes after it, not the fixtures, not the after_migrate hooks.
That happened with two child tables in September 2026. For every DocType:

  1. its folder has __init__.py, and its name scrubs to the folder name;
  2. it is in this app's module, and it is a DocType;
  3. its controller .py is there and defines the class Frappe looks for;
  4. every Table field names a child table that exists, here or upstream;
  5. every Link field names a DocType that exists, here or upstream.

And every standard Script Report has its __init__.py and an execute().

Upstream DocTypes are read from FRAPPE_APPS_ROOT (default ../ERPNext); without
it, checks 4 and 5 cover this app's DocTypes only.
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
MODULE = "HRMS Addon"
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def scrub(name):
    return name.lower().replace(" ", "_").replace("-", "_")


def index(root):
    """{DocType name: istable} for every DocType JSON under root."""
    found = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", "public", "www")]
        if os.path.basename(os.path.dirname(folder)) != "doctype":
            continue
        name = os.path.basename(folder)
        if name + ".json" not in files:
            continue
        try:
            spec = json.load(open(os.path.join(folder, name + ".json"), encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(spec, dict) and spec.get("doctype") == "DocType" and spec.get("name"):
            found[spec["name"]] = bool(spec.get("istable"))
    return found


mine = index(APP)
upstream = {}
if os.path.isdir(APPS_ROOT):
    for app in ("frappe", "erpnext", "hrms"):
        if os.path.isdir(os.path.join(APPS_ROOT, app)):
            upstream.update(index(os.path.join(APPS_ROOT, app)))
known = dict(upstream, **mine)

checked = 0
for folder in sorted(os.listdir(os.path.join(APP, "doctype"))):
    path = os.path.join(APP, "doctype", folder)
    spec_path = os.path.join(path, folder + ".json")
    if not os.path.isfile(spec_path):
        continue
    checked += 1
    spec = json.load(open(spec_path, encoding="utf-8"))
    name = spec.get("name") or folder
    if not os.path.isfile(os.path.join(path, "__init__.py")):
        fail.append("%s: no __init__.py, so its module cannot be imported" % name)
    if spec.get("doctype") != "DocType":
        fail.append("%s: the JSON is a %r, not a DocType" % (name, spec.get("doctype")))
    if scrub(name) != folder:
        fail.append("%s: the folder must be %s, not %s" % (name, scrub(name), folder))
    if spec.get("module") != MODULE:
        fail.append("%s: module is %r, not %r" % (name, spec.get("module"), MODULE))
    if not spec.get("custom"):
        controller = os.path.join(path, folder + ".py")
        classname = name.replace(" ", "").replace("-", "")
        if not os.path.isfile(controller):
            fail.append("%s: no %s.py, and migrate stops at this DocType with 'Module import failed'"
                        % (name, folder))
        elif not re.search(r"^class %s\(" % re.escape(classname), open(controller, encoding="utf-8").read(), re.M):
            fail.append("%s: %s.py does not define class %s" % (name, folder, classname))
    for field in spec.get("fields") or []:
        options = (field.get("options") or "").strip()
        if field.get("fieldtype") in ("Table", "Table MultiSelect"):
            if options not in mine and not (upstream and options in upstream):
                fail.append("%s.%s: its table %r is not a DocType here%s" % (
                    name, field.get("fieldname"), options, " or upstream" if upstream else ""))
            elif options in known and not known[options]:
                fail.append("%s.%s: %r is not a child table" % (name, field.get("fieldname"), options))
        elif field.get("fieldtype") == "Link" and upstream and options and options not in known:
            fail.append("%s.%s: links to %r, which is not a DocType here or upstream"
                        % (name, field.get("fieldname"), options))
print("doctypes: %d, each with its module, controller class and the tables and links it names" % checked)

reports = 0
for folder in sorted(os.listdir(os.path.join(APP, "report"))) if os.path.isdir(os.path.join(APP, "report")) else []:
    path = os.path.join(APP, "report", folder)
    spec_path = os.path.join(path, folder + ".json")
    if not os.path.isfile(spec_path):
        continue
    reports += 1
    spec = json.load(open(spec_path, encoding="utf-8"))
    name = spec.get("name") or folder
    if scrub(name) != folder:
        fail.append("report %s: the folder must be %s" % (name, scrub(name)))
    if not os.path.isfile(os.path.join(path, "__init__.py")):
        fail.append("report %s: no __init__.py" % name)
    if spec.get("ref_doctype") and spec["ref_doctype"] not in known:
        fail.append("report %s: ref_doctype %r is not a DocType" % (name, spec["ref_doctype"]))
    if spec.get("report_type") == "Script Report" and spec.get("is_standard") == "Yes":
        script = os.path.join(path, folder + ".py")
        if not os.path.isfile(script) or "def execute(" not in open(script, encoding="utf-8").read():
            fail.append("report %s: a Script Report needs %s.py with execute()" % (name, folder))
print("script reports: %d, each with its module and execute()" % reports)
if not upstream:
    print("(no upstream apps at %s: tables and links checked against this app only)" % APPS_ROOT)

if fail:
    print("\nFAILED:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("\nALL DOCTYPE CHECKS PASSED")
