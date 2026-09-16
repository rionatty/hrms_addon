"""Static checks for hrms_addon/fixtures, run without a bench.

A broken custom-field fixture does not fail loudly: a wrong insert_after
silently drops the field somewhere unexpected, a Link to a doctype that
does not exist breaks the form at runtime, and a name that does not follow
Frappe's naming gets duplicated on the next export. None of that shows
until someone runs `bench migrate` on a real site, so this checks it
against the actual upstream doctype definitions instead.

It also SIMULATES Frappe's field sorter (frappe/model/meta.py sort_fields,
including the field_order property setter and the Section Break walk) and
prints the resulting layout, then asserts where the important fields land.
That walk is the reason this exists in this form: a custom Section Break
inserted after a standard field is moved forward to the next Section
Break, straight past any Tab Breaks — which silently put the Job
Description sections inside the Connections tab.

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

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "hrms_addon", "fixtures")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
MODULE = "HRMS Addon"

BREAKS = {"Section Break", "Column Break", "Tab Break"}
NO_VALUE = BREAKS | {"HTML", "Button", "Heading", "Image", "Fold"}
# Properties this file may set, with the property_type Customize Form
# declares for each (frappe/custom/doctype/customize_form).
DOCFIELD_PROPERTIES = {
    "label": "Data",
    "reqd": "Check",
    "fetch_from": "Small Text",
    "fetch_if_empty": "Check",
    "read_only": "Check",
    "hidden": "Check",
    "show_dashboard": "Check",
    "depends_on": "Data",
    "options": "Text",
    "description": "Text",
}
DOCTYPE_PROPERTIES = {"field_order": "Data"}
# Created at runtime by the Workflow (frappe/workflow/doctype/workflow), not
# by these fixtures, but legitimately named in a field_order.
RUNTIME_FIELDS = {"Job Requisition": {"workflow_state"}}

fail = []


def load(name):
    path = os.path.join(FIXTURES, name)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []


def find_doctype_json(doctype):
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


def standard_fields(doctype):
    m = meta(doctype)
    return {f["fieldname"]: f for f in m["fields"]} if m else {}


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
    if fn == "custom_section":
        fail.append("%s: Section was removed (it duplicates Department)" % where)
    if f.get("module") != MODULE:
        fail.append("%s: module is %r" % (where, f.get("module")))
    if meta(dt) is None:
        fail.append("%s: doctype %r not found upstream" % (where, dt))
        continue
    if fn in standard_fields(dt):
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
    if ft == "Select" and not [o for o in (f.get("options") or "").split("\n") if o.strip()]:
        fail.append("%s: Select without options" % where)
    if ft in BREAKS and f.get("options"):
        fail.append("%s: %s should not have options" % (where, ft))
    if ft == "HTML" and f.get("options"):
        # ControlHTML.refresh_input re-renders only when there is content;
        # content would wipe the Connections list moved into this field.
        fail.append("%s: HTML field must have no options (it would be re-rendered over the moved content)" % where)
    if ft == "Check" and f.get("fetch_from"):
        # fetch_if_empty treats 0 as empty, so an unticked box is re-ticked
        # from the source on every save — the user can never clear it.
        fail.append("%s: fetch_from on a Check field silently undoes unticking" % where)

for dt, fields in by_dt.items():
    std = standard_fields(dt)
    for fn, f in fields.items():
        after = f.get("insert_after")
        if not after:
            fail.append("%s.%s: missing insert_after (a custom field without one sorts to the TOP)" % (dt, fn))
        elif after not in std and after not in fields:
            fail.append("%s.%s: insert_after %r is not a field on %s" % (dt, fn, after, dt))
print("custom fields: names, links, selects, HTML, insert_after chains checked")

# ── 2. Same-name mapping Job Requisition -> Job Opening ──────────────
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
setter_index = {}
for s in setters:
    dt, fn, prop = s.get("doc_type"), s.get("field_name"), s.get("property")
    level = s.get("doctype_or_field")
    expected_name = "%s-%s-%s" % (dt, fn or "main", prop)
    where = expected_name
    setter_index[(dt, fn, prop)] = s

    if s.get("doctype") != "Property Setter":
        fail.append("%s: doctype is %r" % (where, s.get("doctype")))
    if s.get("name") != expected_name:
        fail.append("%s: name %r should be %r (PropertySetter.autoname)" % (where, s.get("name"), expected_name))
    if s.get("module") != MODULE:
        fail.append("%s: module is %r" % (where, s.get("module")))
    if meta(dt) is None:
        fail.append("%s: doctype not found upstream" % where)
        continue

    if level == "DocType":
        if fn:
            fail.append("%s: a DocType-level setter must not have field_name" % where)
        allowed = DOCTYPE_PROPERTIES
    elif level == "DocField":
        allowed = DOCFIELD_PROPERTIES
        if fn not in standard_fields(dt) and fn not in by_dt.get(dt, {}):
            fail.append("%s: field %r does not exist on %s" % (where, fn, dt))
    else:
        fail.append("%s: doctype_or_field %r" % (where, level))
        continue

    if prop not in allowed:
        fail.append("%s: property %r not allowed at %s level" % (where, prop, level))
    elif s.get("property_type") != allowed[prop]:
        fail.append("%s: property_type %r should be %r" % (where, s.get("property_type"), allowed[prop]))

    if prop == "fetch_from":
        link, _, target = (s.get("value") or "").partition(".")
        link_df = standard_fields(dt).get(link)
        if not link_df or link_df.get("fieldtype") != "Link":
            fail.append("%s: fetch_from link %r is not a Link on %s" % (where, link, dt))
        else:
            src_dt = link_df["options"]
            if target not in standard_fields(src_dt) and target not in by_dt.get(src_dt, {}):
                fail.append("%s: fetch_from target %r not on %s" % (where, target, src_dt))
print("property setters: names, levels, properties, types and fetch targets checked")


# ── 4. Simulate Frappe's field sorter ────────────────────────────────
def update_order_based_on_insert_after(field_order, insertion_map):
    """Port of frappe.model.meta._update_field_order_based_on_insert_after."""
    retry = True
    while retry:
        retry = False
        for fieldname in list(insertion_map):
            if fieldname not in field_order:
                continue
            index = field_order.index(fieldname)
            for name in insertion_map.pop(fieldname):
                index += 1
                field_order.insert(index, name)
            retry = True
    for names in insertion_map.values():
        field_order.extend(names)


def simulate_layout(dt):
    """Port of frappe.model.meta.Meta.sort_fields for one doctype."""
    m = meta(dt)
    std = {f["fieldname"]: dict(f) for f in m["fields"]}
    std_order = [fn for fn in (m.get("field_order") or list(std)) if fn in std]
    sequence = [std[fn] for fn in std_order]
    runtime = [
        {"fieldname": fn, "fieldtype": "Link", "hidden": 1, "is_custom_field": 1}
        for fn in sorted(RUNTIME_FIELDS.get(dt, ()))
    ]
    sequence += [dict(f, is_custom_field=1) for f in by_dt.get(dt, {}).values()] + runtime
    fields = {f["fieldname"]: f for f in sequence}

    # DocField property setters change how the form renders (hidden tabs)
    for (sdt, sfn, prop), s in setter_index.items():
        if sdt == dt and sfn in fields and prop in ("hidden", "show_dashboard", "label"):
            fields[sfn][prop] = int(s["value"]) if prop != "label" else s["value"]

    field_order = []
    order_setter = setter_index.get((dt, None, "field_order"))
    if order_setter:
        field_order = [fn for fn in json.loads(order_setter["value"]) if fn in fields]
        if len(field_order) == len(sequence):
            return field_order, fields
        if sequence[0]["fieldname"] not in field_order:
            prepend, found = [], False
            for f in sequence:
                if f.get("is_custom_field"):
                    break
                if f["fieldname"] in field_order:
                    found = True
                    break
                prepend.append(f["fieldname"])
            field_order = prepend + field_order if found else prepend

    existing = set(field_order) if field_order else False
    insertion_map = {}
    for index, f in enumerate(sequence):
        fn = f["fieldname"]
        if existing and fn in existing:
            continue
        if not f.get("is_custom_field"):
            if existing:
                insertion_map.setdefault(sequence[index - 1]["fieldname"], []).append(fn)
            else:
                field_order.append(fn)
        elif f.get("insert_after"):
            target = original = f["insert_after"]
            if f["fieldtype"] in ("Section Break", "Column Break") and target in field_order:
                for current in field_order[field_order.index(target) + 1:]:
                    if fields[current]["fieldtype"] == "Section Break" or (
                        fields[current]["fieldtype"] == fields[original]["fieldtype"]
                    ):
                        break
                    target = current
            elif f["fieldtype"] == "Tab Break" and target in field_order:
                for current in field_order[field_order.index(target) + 1:]:
                    if fields[current]["fieldtype"] == "Tab Break":
                        break
                    target = current
            insertion_map.setdefault(target, []).append(fn)
        else:
            field_order.insert(0, fn)
    if insertion_map:
        update_order_based_on_insert_after(field_order, insertion_map)
    return field_order, fields


def tabs_of(field_order, fields):
    """{fieldname: tab label}; fields before the first Tab Break sit in Details."""
    tab, placement = "Details", {}
    for fn in field_order:
        if fields[fn]["fieldtype"] == "Tab Break":
            tab = fields[fn].get("label") or fn
        placement[fn] = tab
    return placement


def print_layout(dt, field_order, fields):
    print("\n  %s — simulated form layout" % dt)
    tab = "Details"
    print("    [tab] Details")
    for fn in field_order:
        f = fields[fn]
        hidden = " (hidden)" if f.get("hidden") else ""
        if f["fieldtype"] == "Tab Break":
            tab = f.get("label") or fn
            print("    [tab] %s%s" % (tab, hidden))
        elif f["fieldtype"] == "Section Break":
            print("       -- %s%s" % (f.get("label") or "(section)", hidden))
        elif f["fieldtype"] != "Column Break":
            print("          %s%s" % (f.get("label") or fn, hidden))


# ── 5. Job Requisition layout expectations ───────────────────────────
JR = "Job Requisition"
order, fields = simulate_layout(JR)
placement = tabs_of(order, fields)
print_layout(JR, order, fields)
print()

EXPECT_TAB = {
    "Details": ["custom_employment_type", "custom_reason_type", "reason_for_requesting", "requested_by",
                "custom_connections_section", "custom_connections_html"],
    "Job Description": ["description", "custom_external_advert", "custom_head_hunt", "custom_reporting_line",
                        "custom_subordinates"],
    "Approvals": ["custom_supervisor", "custom_hod", "custom_hr_officer", "custom_hrm_decision", "custom_ed_date"],
}
for tab, names in EXPECT_TAB.items():
    for fn in names:
        if placement.get(fn) != tab:
            fail.append("Job Requisition.%s lands in tab %r, expected %r" % (fn, placement.get(fn), tab))

order_setter = setter_index.get((JR, None, "field_order"))
if not order_setter:
    fail.append("Job Requisition has no field_order setter — the sorter walk would misplace sections")
else:
    listed = json.loads(order_setter["value"])
    known = set(standard_fields(JR)) | set(by_dt.get(JR, {})) | RUNTIME_FIELDS.get(JR, set())
    dupes = sorted({fn for fn in listed if listed.count(fn) > 1})
    if dupes:
        fail.append("Job Requisition field_order lists fields twice: %s" % dupes)
    unknown = sorted(set(listed) - known)
    if unknown:
        fail.append("Job Requisition field_order names fields that do not exist: %s" % unknown)
    missing = sorted(known - set(listed))
    if missing:
        fail.append("Job Requisition field_order omits %s — they would be placed by the sorter walk" % missing)

conn = setter_index.get((JR, "connections_tab", "hidden")), setter_index.get((JR, "connections_tab", "show_dashboard"))
if not conn[0] or conn[0]["value"] != "1" or not conn[1] or conn[1]["value"] != "0":
    fail.append("connections_tab must be hidden with show_dashboard=0, or the dashboard stays in a tab")
if (fields.get("custom_connections_section") or {}).get("depends_on") != "eval:!doc.__islocal":
    fail.append("custom_connections_section should only show on saved documents")
print("Job Requisition layout: every expected field is on its expected tab")

# ── 6. Job Opening layout expectations ───────────────────────────────
JO = "Job Opening"
order, fields = simulate_layout(JO)
placement = tabs_of(order, fields)
stray = sorted(fn for fn in by_dt.get(JO, {}) if placement.get(fn) != "Details")
if stray:
    fail.append("Job Opening custom fields outside the first tab: %s" % stray)
print("Job Opening layout: all custom fields on the first tab")

# ── 7. hooks.py lists what the fixture files contain ─────────────────
hooks = open(os.path.join(REPO, "hrms_addon", "hooks.py"), encoding="utf-8").read()
for dt_name, records in (("Custom Field", custom_fields), ("Property Setter", setters)):
    m = re.search(r'"dt":\s*"%s".*?"in",\s*(\[.*?\])' % re.escape(dt_name), hooks, re.S)
    if not m:
        fail.append("hooks.py: no fixtures entry for %s" % dt_name)
        continue
    listed = set(re.findall(r'"([^"]+)"', m.group(1)))
    actual = {r["name"] for r in records}
    if listed != actual:
        fail.append("hooks.py %s list out of step with the fixture file: missing %s, extra %s"
                    % (dt_name, sorted(actual - listed), sorted(listed - actual)))
print("hooks.py fixtures lists match the fixture files")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL FIXTURE CHECKS PASSED")
