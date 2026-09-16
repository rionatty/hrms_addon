"""Static checks for hrms_addon/fixtures, run without a bench.

A broken custom-field fixture does not fail loudly: a wrong insert_after
silently drops the field at the bottom of the form, a Link to a doctype
that does not exist breaks the form at runtime, and a name that does not
follow "<doctype>-<fieldname>" gets duplicated on the next export. None of
that is visible until someone runs `bench migrate` on a real site, so this
checks it against the actual upstream doctype definitions instead.

Needs local checkouts of frappe, erpnext and hrms (the doctype JSON is read
directly). By default they are looked for next to this repo at
../ERPNext/{frappe,erpnext,hrms}; override with FRAPPE_APPS_ROOT.

    python scripts/verify_fixtures.py
"""
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "hrms_addon", "fixtures")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
MODULE = "HRMS Addon"

BREAKS = {"Section Break", "Column Break", "Tab Break"}
# Properties this file is allowed to set, with the property_type Frappe's
# Customize Form declares for each (frappe/custom/doctype/customize_form).
ALLOWED_PROPERTIES = {
    "label": "Data",
    "reqd": "Check",
    "fetch_from": "Small Text",
    "fetch_if_empty": "Check",
    "read_only": "Check",
    "hidden": "Check",
    "options": "Text",
    "description": "Text",
}

fail = []


def load(name):
    path = os.path.join(FIXTURES, name)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []


def find_doctype_json(doctype):
    """Locate a doctype definition anywhere in the three upstream apps."""
    folder = doctype.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


if not os.path.isdir(APPS_ROOT):
    print("SKIPPED: upstream apps not found at %s (set FRAPPE_APPS_ROOT)" % APPS_ROOT)
    sys.exit(0)

custom_fields = load("custom_field.json")
setters = load("property_setter.json")
print("fixtures: %d custom fields, %d property setters" % (len(custom_fields), len(setters)))

_meta_cache = {}


def meta(doctype):
    if doctype not in _meta_cache:
        _meta_cache[doctype] = find_doctype_json(doctype)
    return _meta_cache[doctype]


def standard_fieldnames(doctype):
    m = meta(doctype)
    return {f["fieldname"] for f in m["fields"]} if m else set()


# ── 1. Custom fields ─────────────────────────────────────────────────
by_dt = {}
for f in custom_fields:
    dt, fn = f.get("dt"), f.get("fieldname")
    where = "%s.%s" % (dt, fn)

    if f.get("doctype") != "Custom Field":
        fail.append("%s: doctype is %r" % (where, f.get("doctype")))
    if f.get("name") != "%s-%s" % (dt, fn):
        fail.append("%s: name %r should be %r" % (where, f.get("name"), "%s-%s" % (dt, fn)))
    if not (fn or "").startswith("custom_"):
        fail.append("%s: fieldname must start with custom_" % where)
    if f.get("module") != MODULE:
        fail.append("%s: module is %r" % (where, f.get("module")))
    if meta(dt) is None:
        fail.append("%s: doctype %r not found upstream" % (where, dt))
        continue
    if fn in standard_fieldnames(dt):
        fail.append("%s: collides with a standard field" % where)
    if fn in by_dt.setdefault(dt, {}):
        fail.append("%s: defined twice" % where)
    by_dt[dt][fn] = f

    ft = f.get("fieldtype")
    if ft == "Link":
        if not f.get("options"):
            fail.append("%s: Link without options" % where)
        elif meta(f["options"]) is None:
            fail.append("%s: Link target doctype %r not found upstream" % (where, f["options"]))
    if ft == "Select":
        opts = [o for o in (f.get("options") or "").split("\n") if o.strip()]
        if not opts:
            fail.append("%s: Select without options" % where)
    if ft in BREAKS and f.get("options"):
        fail.append("%s: %s should not have options" % (where, ft))
    if ft == "Check" and f.get("fetch_from"):
        # fetch_if_empty treats 0 as empty, so an unticked box is re-ticked
        # from the source on every save — the user can never clear it.
        fail.append("%s: fetch_from on a Check field silently undoes unticking" % where)

# insert_after must resolve to a standard field or a custom field on the same doctype
for dt, fields in by_dt.items():
    std = standard_fieldnames(dt)
    for fn, f in fields.items():
        after = f.get("insert_after")
        if not after:
            fail.append("%s.%s: missing insert_after (field lands at the bottom of the form)" % (dt, fn))
        elif after not in std and after not in fields:
            fail.append("%s.%s: insert_after %r is not a field on %s" % (dt, fn, after, dt))
print("custom fields: names, links, selects, insert_after chains checked")

# ── 2. Same-name mapping Job Requisition -> Job Opening ──────────────
# frappe.model.mapper.map_fields copies a value only when the TARGET has a
# field with the SAME fieldname. Every data field on Job Opening must exist
# on Job Requisition with the same type, or "Create Job Opening" leaves it blank.
jr, jo = by_dt.get("Job Requisition", {}), by_dt.get("Job Opening", {})
mapped = 0
for fn, f in jo.items():
    if f["fieldtype"] in BREAKS:
        continue
    src = jr.get(fn)
    if not src:
        fail.append("Job Opening.%s has no same-named field on Job Requisition, so it is never copied" % fn)
    elif (src["fieldtype"], src.get("options")) != (f["fieldtype"], f.get("options")):
        fail.append("Job Opening.%s differs in type/options from Job Requisition.%s" % (fn, fn))
    else:
        mapped += 1
print("requisition -> opening: %d data fields carry across by name" % mapped)

# ── 3. Property setters ──────────────────────────────────────────────
for s in setters:
    dt, fn, prop = s.get("doc_type"), s.get("field_name"), s.get("property")
    where = "%s.%s.%s" % (dt, fn, prop)
    if s.get("doctype") != "Property Setter":
        fail.append("%s: doctype is %r" % (where, s.get("doctype")))
    if s.get("name") != "%s-%s-%s" % (dt, fn, prop):
        fail.append("%s: name %r should be %r" % (where, s.get("name"), "%s-%s-%s" % (dt, fn, prop)))
    if s.get("doctype_or_field") != "DocField":
        fail.append("%s: doctype_or_field should be DocField" % where)
    if s.get("module") != MODULE:
        fail.append("%s: module is %r" % (where, s.get("module")))
    if prop not in ALLOWED_PROPERTIES:
        fail.append("%s: property %r not in the allowed set" % (where, prop))
    elif s.get("property_type") != ALLOWED_PROPERTIES[prop]:
        fail.append("%s: property_type %r should be %r" % (where, s.get("property_type"), ALLOWED_PROPERTIES[prop]))
    if meta(dt) is None:
        fail.append("%s: doctype not found upstream" % where)
    elif fn not in standard_fieldnames(dt) and fn not in by_dt.get(dt, {}):
        fail.append("%s: field %r does not exist on %s" % (where, fn, dt))

    if prop == "fetch_from":
        link, _, target = (s.get("value") or "").partition(".")
        link_df = next((f for f in (meta(dt) or {}).get("fields", []) if f["fieldname"] == link), None)
        if not link_df or link_df.get("fieldtype") != "Link":
            fail.append("%s: fetch_from link %r is not a Link on %s" % (where, link, dt))
        else:
            src_dt = link_df["options"]
            if target not in standard_fieldnames(src_dt) and target not in by_dt.get(src_dt, {}):
                fail.append("%s: fetch_from target %r not on %s" % (where, target, src_dt))
print("property setters: names, properties, types and fetch targets checked")

# ── 4. hooks.py lists what the fixture files contain ─────────────────
hooks = open(os.path.join(REPO, "hrms_addon", "hooks.py"), encoding="utf-8").read()
for label, dt_name, records in (("Custom Field", "Custom Field", custom_fields), ("Property Setter", "Property Setter", setters)):
    m = re.search(r'"dt":\s*"%s".*?"in",\s*(\[.*?\])' % re.escape(dt_name), hooks, re.S)
    if not m:
        fail.append("hooks.py: no fixtures entry for %s" % label)
        continue
    listed = set(re.findall(r'"([^"]+)"', m.group(1)))
    actual = {r["name"] for r in records}
    if listed != actual:
        fail.append("hooks.py %s list out of step with the fixture file: missing %s, extra %s"
                    % (label, sorted(actual - listed), sorted(listed - actual)))
print("hooks.py fixtures lists match the fixture files")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL FIXTURE CHECKS PASSED")
