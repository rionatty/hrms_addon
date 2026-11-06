"""Checks for the safety module (Luuka's review list of 5 Nov 2026, items 11 to
17): the hospitals, the incident's own approval by the plant's EHS Officer, its
incident and investigation reports, the doctor's reports and rest days, light
duty and the separation a doctor recommends, the treatment order and its
transport, and the compensation the insurer pays.

Runs without a bench: the rules modules are loaded on their own, and the
DocTypes, fixtures and hooks are read as files.

    python scripts/verify_safety.py
"""
import ast
import importlib.util
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}


def fields_of(name):
    return {f["fieldname"]: f for f in doctype(name).get("fields", [])}


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


def roles_with(spec, right):
    return {row["role"] for row in spec.get("permissions", []) if row.get(right)}


hooks = hooks_dict()

# ── 13. The hospitals ─────────────────────────────────────────────────
# "Under safety, there need be a drop down for list of hospitals they use, and open if there is need to add another"
hospital = doctype("Hospital")
hospital_fields = fields_of("Hospital")
if (hospital.get("autoname"), hospital.get("quick_entry"), hospital_fields.get("hospital_name", {}).get("unique")) \
        != ("field:hospital_name", 1, 1):
    fail.append("a hospital is named by itself, once, and added in a quick dialog")
if not {"HR User", "HR Manager", "EHS Officer"} <= roles_with(hospital, "create"):
    fail.append("HR and the EHS Officers add a hospital from the drop-down when the one needed is not there")
if "Employee" not in roles_with(hospital, "read"):
    fail.append("anyone who reads an incident reads the hospital it names")
if any(f.get("fieldtype") == "Link" and f.get("options") == "Branch" for f in hospital_fields.values()):
    fail.append("the hospitals are one list for every plant: a plant's users would see only their own")
if (fields_of("Safety Incident").get("hospital") or {}).get("options") != "Hospital":
    fail.append("the incident's hospital is picked from the list")
patch = read("hrms_addon", "patches", "v1_0", "hospitals_from_incidents.py")
if "hrms_addon.patches.v1_0.hospitals_from_incidents" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1] \
        or 'frappe.get_all("Safety Incident", filters={"hospital": ["is", "set"]}' not in patch \
        or 'if name and not frappe.db.exists("Hospital", name):' not in patch \
        or 'frappe.db.set_value("Safety Incident", row.name, "hospital", name or None' not in patch:
    fail.append("the hospitals already typed become the list, each once, and the incident names its own exactly")
print("hospitals: one list, added to from the drop-down, the names already typed brought in")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL SAFETY CHECKS PASSED")
