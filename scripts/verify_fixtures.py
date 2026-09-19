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
    "allow_bulk_edit": "Check",
}
DOCTYPE_PROPERTIES = {"field_order": "Data", "search_fields": "Data", "default_print_format": "Data"}
# Created at runtime by the Workflow (frappe/workflow/doctype/workflow), not
# by these fixtures, but legitimately named in a field_order.
RUNTIME_FIELDS = {"Job Requisition": {"workflow_state"}, "Employee Onboarding": {"workflow_state"}}

fail = []


def load(name):
    path = os.path.join(FIXTURES, name)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []


def find_doctype_json(doctype):
    """A doctype definition from this app or the three upstream apps."""
    folder = doctype.lower().replace(" ", "_")
    roots = [os.path.join(REPO, "hrms_addon")] + [os.path.join(APPS_ROOT, app, app) for app in ("frappe", "erpnext", "hrms")]
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def _ast_literal(node):
    """ast literal, treating _("x") translation calls as "x"."""
    import ast

    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_" and node.args:
        return _ast_literal(node.args[0])
    if isinstance(node, ast.Dict):
        return {_ast_literal(k): _ast_literal(v) for k, v in zip(node.keys, node.values)}
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_ast_literal(e) for e in node.elts]
    if isinstance(node, ast.Constant):
        return node.value
    return None


def load_hrms_custom_fields():
    """Custom fields HRMS itself creates on install (hrms/setup.py), keyed by
    doctype. They are not in any doctype JSON, but our fields can anchor on
    them — the Job Description tab goes after HRMS's `skills` table."""
    import ast

    path = os.path.join(APPS_ROOT, "hrms", "hrms", "setup.py")
    if not os.path.exists(path):
        return {}
    found = {}
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if not isinstance(node, ast.Dict):
            continue
        value = _ast_literal(node)
        if not isinstance(value, dict):
            continue
        for doctype, fields in value.items():
            if isinstance(doctype, str) and isinstance(fields, list) and fields and all(
                isinstance(f, dict) and f.get("fieldname") for f in fields
            ):
                found.setdefault(doctype, {f["fieldname"]: f for f in fields})
    return found


HRMS_CUSTOM_FIELDS = None


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


HRMS_CUSTOM_FIELDS = load_hrms_custom_fields()


def doctype_in_repo(doctype):
    folder = doctype.lower().replace(" ", "_")
    return bool(glob.glob(os.path.join(REPO, "hrms_addon", "**", "doctype", folder, folder + ".json"), recursive=True))


def upstream_fields(doctype):
    """Standard fields plus the custom fields HRMS installs on this doctype."""
    return {**standard_fields(doctype), **HRMS_CUSTOM_FIELDS.get(doctype, {})}


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
    if fn in upstream_fields(dt):
        fail.append("%s: collides with a standard or HRMS-installed field" % where)
    if fn in by_dt.setdefault(dt, {}):
        fail.append("%s: defined twice" % where)
    by_dt[dt][fn] = f

    ft = f.get("fieldtype")
    if ft == "Link":
        if not f.get("options"):
            fail.append("%s: Link without options" % where)
        elif meta(f["options"]) is None:
            fail.append("%s: Link target doctype %r not found upstream" % (where, f["options"]))
    if ft == "Table":
        child = meta(f.get("options") or "")
        if child is None:
            fail.append("%s: Table child doctype %r not found here or upstream" % (where, f.get("options")))
        elif not child.get("istable"):
            fail.append("%s: Table options %r is not a child table (istable)" % (where, f.get("options")))
        elif doctype_in_repo(f["options"]) and child.get("module") != MODULE:
            fail.append("%s: this app's child doctype %r has module %r" % (where, f["options"], child.get("module")))
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
    std = upstream_fields(dt)
    for fn, f in fields.items():
        after = f.get("insert_after")
        if not after:
            fail.append("%s.%s: missing insert_after (a custom field without one sorts to the TOP)" % (dt, fn))
        elif after not in std and after not in fields:
            fail.append("%s.%s: insert_after %r is not a field on %s" % (dt, fn, after, dt))
print("custom fields: names, links, selects, HTML, insert_after chains checked")

# ── 2. Same-name mapping Job Requisition -> Job Opening ──────────────
jr, jo = by_dt.get("Job Requisition", {}), by_dt.get("Job Opening", {})
# Job Opening fields about its careers page, not the requisition's content
JOB_OPENING_ONLY = {"custom_show_job_description"}
mapped = 0
for fn, f in jo.items():
    if f["fieldtype"] in BREAKS or fn in JOB_OPENING_ONLY:
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
        # ours, upstream's own, or one HRMS creates in code (hrms/setup.py):
        # Meta adds every custom field before it applies property setters
        if (fn not in standard_fields(dt) and fn not in by_dt.get(dt, {})
                and fn not in HRMS_CUSTOM_FIELDS.get(dt, {})):
            fail.append("%s: field %r does not exist on %s" % (where, fn, dt))
    else:
        fail.append("%s: doctype_or_field %r" % (where, level))
        continue

    if prop not in allowed:
        fail.append("%s: property %r not allowed at %s level" % (where, prop, level))
    elif s.get("property_type") != allowed[prop]:
        fail.append("%s: property_type %r should be %r" % (where, s.get("property_type"), allowed[prop]))

    if prop == "search_fields":
        known = set(upstream_fields(dt)) | set(by_dt.get(dt, {})) | {"name"}
        for name in [n.strip() for n in (s.get("value") or "").split(",") if n.strip()]:
            if name not in known:
                fail.append("%s: search field %r does not exist on %s" % (where, name, dt))

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


def simulate_layout(dt, hrms_first=True):
    """Port of frappe.model.meta.Meta.sort_fields for one doctype.

    Frappe loads custom fields ORDER BY idx (Meta.add_custom_fields), and a
    custom field's idx is set from its insert_after target. Two fields that
    anchor on the same target get the same idx, and then the database
    decides which comes first. hrms_first chooses that order, so callers can
    require a layout to hold either way.
    """
    m = meta(dt)
    std = {f["fieldname"]: dict(f) for f in m["fields"]}
    std_order = [fn for fn in (m.get("field_order") or list(std)) if fn in std]
    sequence = [std[fn] for fn in std_order]
    runtime = [
        {"fieldname": fn, "fieldtype": "Link", "hidden": 1, "is_custom_field": 1}
        for fn in sorted(RUNTIME_FIELDS.get(dt, ()))
    ]
    hrms_installed = [dict(f, is_custom_field=1) for f in HRMS_CUSTOM_FIELDS.get(dt, {}).values()]
    ours = [dict(f, is_custom_field=1) for f in by_dt.get(dt, {}).values()]
    sequence += (hrms_installed + ours if hrms_first else ours + hrms_installed) + runtime
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
    return {fn: where[0] for fn, where in positions_of(field_order, fields).items()}


def positions_of(field_order, fields):
    """{fieldname: (tab, section label, column index)} as the form renders it.

    Fields before the first Tab Break sit in "Details"; a Section Break
    starts column 0 of a new section; each Column Break moves one column right.
    """
    tab, section, column, placement = "Details", "", 0, {}
    for fn in field_order:
        fieldtype = fields[fn]["fieldtype"]
        if fieldtype == "Tab Break":
            tab, section, column = fields[fn].get("label") or fn, "", 0
        elif fieldtype == "Section Break":
            section, column = fields[fn].get("label") or fn, 0
        elif fieldtype == "Column Break":
            column += 1
        placement[fn] = (tab, section, column)
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
        elif f["fieldtype"] == "Column Break":
            print("          | next column")
        elif f["fieldtype"] == "Heading":
            print("          ## %s" % (f.get("label") or fn))
        else:
            print("          %s%s" % (f.get("label") or fn, hidden))


# ── 5. Job Requisition layout expectations ───────────────────────────
JR = "Job Requisition"
order, fields = simulate_layout(JR)
placement = tabs_of(order, fields)
print_layout(JR, order, fields)
print()

EXPECT_TAB = {
    "Details": ["custom_employment_type", "custom_reason_type", "reason_for_requesting", "requested_by",
                "custom_recruitment_heading", "custom_external_advert", "custom_internal_advert",
                "custom_head_hunt", "custom_reference_to_database"],
    "Job Description": ["description", "custom_reporting_line", "custom_subordinates"],
    "Approvals": ["custom_supervisor", "custom_hod", "custom_hr_officer", "custom_hrm_decision", "custom_ed_date"],
}
for tab, names in EXPECT_TAB.items():
    for fn in names:
        if placement.get(fn) != tab:
            fail.append("Job Requisition.%s lands in tab %r, expected %r" % (fn, placement.get(fn), tab))

# Mode of Recruitment sits UNDER the reason, in the same left column, with
# Reason Details alone in the right-hand column of that section.
positions = positions_of(order, fields)
REASON = "Reason for Requisition"
left_column = ["custom_reason_type", "custom_recruitment_heading", "custom_external_advert",
               "custom_internal_advert", "custom_head_hunt", "custom_reference_to_database"]
for fn in left_column:
    if positions.get(fn, (None,))[1:] != (REASON, 0):
        fail.append("Job Requisition.%s is at %s, expected section %r column 0" % (fn, positions.get(fn), REASON))
if [fn for fn in order if fn in left_column] != left_column:
    fail.append("Mode of Recruitment must come after the reason, in order: %s" % left_column)
if positions.get("reason_for_requesting", (None,))[1:] != (REASON, 1):
    fail.append("Reason Details is at %s, expected section %r column 1" % (positions.get("reason_for_requesting"), REASON))
if (fields.get("custom_recruitment_heading") or {}).get("fieldtype") != "Heading":
    fail.append("Mode of Recruitment title must be a Heading: a Section Break would leave the column")

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

# Connections is the standard connections_tab, visible and holding the
# dashboard (Frappe puts the list in the first tab with show_dashboard,
# frappe/public/js/frappe/form/form.js), straight after Job Description.
for prop in ("hidden", "show_dashboard"):
    if setter_index.get((JR, "connections_tab", prop)):
        fail.append("connections_tab must keep its standard %s: Connections is a tab of its own" % prop)
connections = fields.get("connections_tab") or {}
if connections.get("fieldtype") != "Tab Break" or not connections.get("show_dashboard") or connections.get("hidden"):
    fail.append("connections_tab must be a visible Tab Break that shows the dashboard")
tabs = [fields[fn].get("label") for fn in order if fields[fn]["fieldtype"] == "Tab Break" and not fields[fn].get("hidden")]
if tabs != ["Job Description", "Connections", "Approvals"]:
    fail.append("Job Requisition tabs after Details are %s, expected Job Description, Connections, Approvals" % tabs)
crowded = sorted(fn for fn, tab in placement.items()
                 if tab == "Connections" and fn != "connections_tab" and not fields[fn].get("hidden"))
if crowded:
    fail.append("the Connections tab must hold only the list; fields in it: %s" % crowded)
print("Job Requisition layout: every expected field is on its expected tab, Connections tab after Job Description")

# ── 6. Job Opening layout expectations ───────────────────────────────
JO = "Job Opening"
order, fields = simulate_layout(JO)
placement = tabs_of(order, fields)
stray = sorted(fn for fn in by_dt.get(JO, {}) if placement.get(fn) != "Details")
if stray:
    fail.append("Job Opening custom fields outside the first tab: %s" % stray)
print("Job Opening layout: all custom fields on the first tab")

# ── 6b. Designation (Job Title) — Job Description template ──────────
DS = "Designation"
if by_dt.get(DS):
    order, fields = simulate_layout(DS)
    positions = positions_of(order, fields)
    print_layout(DS, order, fields)
    print()

    # HRMS's own Designation fields must stay on the first tab, whichever
    # order the database returns tied custom fields in. Anchoring the JD tab
    # on "description" ties it with HRMS's appraisal_template (same idx), and
    # if the tab loads first it swallows Appraisal Template and Skills;
    # anchoring on "skills" is safe in both orders.
    for hrms_first in (True, False):
        o, f = simulate_layout(DS, hrms_first=hrms_first)
        p = positions_of(o, f)
        label = "HRMS fields loaded %s" % ("first" if hrms_first else "last")
        for fn in HRMS_CUSTOM_FIELDS.get(DS, {}):
            if p.get(fn, ("?",))[0] != "Details":
                fail.append("Designation.%s (installed by HRMS) was pulled into tab %r (%s)" % (fn, p.get(fn, ("?",))[0], label))
        stray = sorted(fn for fn in by_dt[DS] if p.get(fn, ("?",))[0] != "Job Description")
        if stray:
            fail.append("Designation JD fields outside the Job Description tab (%s): %s" % (label, stray))

    # Every section of LPL/JD/SM/001, in the order the JD prints them.
    JD_SECTIONS = [
        "Job Details",
        "Job Purpose Statement",
        "Key Result Areas (Balanced Scorecard Framework)",
        "Reporting Relationships",
        "Stakeholder Management",
        "Decision-Making Authority / Mandates / Constraints",
        "Work Cycle & Planning Horizon",
        "ISO Responsibilities (ISO 9001, ISO 22000, ISO 45001, ISO 14001)",
        "Ideal Job Specifications",
        "Competency Framework",
        "Sign-Off",
    ]
    rendered = [fields[fn].get("label") for fn in order
                if fields[fn]["fieldtype"] == "Section Break" and positions[fn][0] == "Job Description"]
    if rendered != JD_SECTIONS:
        fail.append("Job Description sections %s do not match the JD's %s" % (rendered, JD_SECTIONS))
    print("Designation layout: %d JD sections in JD order, HRMS fields untouched" % len(JD_SECTIONS))

# ── 6c. Job Applicant — Pre-Interview Bio-Data Form (LPL/HR/19) ──────
JA = "Job Applicant"
if by_dt.get(JA):
    m = meta(JA)
    baseline = positions_of([fn for fn in m["field_order"]], {f["fieldname"]: f for f in m["fields"]})
    # Salary history and expectation, on HRMS's own tab; the score sheet
    # (LPL/HR/17) prints them for every panel member
    SALARY_FIELDS = {"custom_previous_salary", "custom_current_benefits", "custom_expected_benefits", "custom_notice_period"}
    # the opening's Branch, beside the Job Opening and Designation
    DETAILS_FIELDS = {"custom_branch"}
    BIO_SECTIONS = [
        "Personal Information",
        "Parents' Details",
        "Next of Kin Details",
        "Professional Qualifications / Other Qualifications",
        "A'Level and O'Level Results",
        "Employment History",
        "Skills Possessed",
        "Language Proficiency",
        "Declaration",
    ]
    for hrms_first in (True, False):
        order, fields = simulate_layout(JA, hrms_first=hrms_first)
        positions = positions_of(order, fields)
        moved = sorted(fn for fn, where in baseline.items() if positions.get(fn, ("?",))[0] != where[0])
        if moved:
            fail.append("Job Applicant standard fields moved to another tab: %s" % moved)
        for fn in by_dt[JA]:
            expected = "Salary Expectation" if fn in SALARY_FIELDS else "Details" if fn in DETAILS_FIELDS else "Bio-Data"
            if positions.get(fn, ("?",))[0] != expected:
                fail.append("Job Applicant.%s lands in tab %r, expected %r" % (fn, positions.get(fn, ("?",))[0], expected))
        tabs = [fields[fn].get("label") for fn in order if fields[fn]["fieldtype"] == "Tab Break"]
        if tabs != ["Salary Expectation", "Bio-Data"]:
            fail.append("Job Applicant tabs after Details are %s, expected Salary Expectation then Bio-Data" % tabs)
        sections = [fields[fn].get("label") for fn in order
                    if fields[fn]["fieldtype"] == "Section Break" and positions[fn][0] == "Bio-Data"]
        if sections != BIO_SECTIONS:
            fail.append("Bio-Data sections %s do not follow the paper form %s" % (sections, BIO_SECTIONS))
        for fn, f in by_dt[JA].items():
            if f["fieldtype"] == "Table":
                before = order[order.index(fn) - 1]
                if fields[before]["fieldtype"] != "Section Break" or positions[fn][2] != 0:
                    fail.append("Job Applicant.%s must open its own section, full width" % fn)
        if "custom_branch" in order and order[order.index("custom_branch") - 1] != "designation":
            fail.append("Job Applicant.custom_branch must follow Designation, beside the Job Opening")
    order, fields = simulate_layout(JA)
    print_layout(JA, order, fields)
    print()
    print("Job Applicant layout: salary history with the salary expectation, %d Bio-Data sections in the form's order"
          % len(BIO_SECTIONS))

# ── 6c2. Interview Feedback — the score sheet (LPL/HR/17) ────────────
IFB = "Interview Feedback"
if by_dt.get(IFB):
    for hrms_first in (True, False):
        order, fields = simulate_layout(IFB, hrms_first=hrms_first)
        visible_sections = [fields[fn].get("label") for fn in order
                            if fields[fn]["fieldtype"] == "Section Break" and not fields[fn].get("hidden")]
        expected_sections = ["Details", "Candidate Interview Evaluation", "Total Score", "Suitability & Recommendation"]
        if visible_sections != expected_sections:
            fail.append("Interview Feedback sections %s, expected %s" % (visible_sections, expected_sections))
        for field, after in (("custom_scores", "custom_evaluation_section"), ("custom_recommendation", "feedback"),
                             ("custom_interviewer_designation", "interviewer")):
            if field in order and order[order.index(field) - 1] != after:
                fail.append("Interview Feedback.%s must follow %s, follows %s" % (field, after, order[order.index(field) - 1]))
    print("Interview Feedback layout: details, the evaluation grid, the total, then suitability and the recommendation")

# ── 6d. Employee — statutory numbers, the Personal Bio-Data tab ──────
EM = "Employee"
if by_dt.get(EM):
    m = meta(EM)
    baseline = positions_of([fn for fn in m["field_order"]], {f["fieldname"]: f for f in m["fields"]})
    ids = ["custom_nin", "custom_tin", "custom_nssf_no"]
    # The Personal Bio-Data Form (LPL/HR/16) in its own order, after Personal
    # Details; place of birth beside the date of birth; the professional
    # certificates between Education and Previous Work Experience, as on the form
    BIO_TAB = "Personal Bio-Data"
    BIO_SECTIONS = ["Home and Residence", "Spouse", "Parents", "Next of Kin", "Children", "Declaration"]
    ELSEWHERE = {"custom_place_of_birth": ("Overview", "date_of_birth"),
                 "custom_professional_section": ("Profile", "education"),
                 "custom_professional_qualifications": ("Profile", "custom_professional_section")}
    for hrms_first in (True, False):
        order, fields = simulate_layout(EM, hrms_first=hrms_first)
        positions = positions_of(order, fields)
        moved = sorted(fn for fn, where in baseline.items() if positions.get(fn, ("?",))[0] != where[0])
        if moved:
            fail.append("Employee standard fields moved to another tab: %s" % moved)
        for fn in ids:
            if positions.get(fn) != ("Personal Details", "Identity & Statutory Numbers", 0):
                fail.append("Employee.%s is at %s, expected Personal Details / Identity & Statutory Numbers, first column"
                            % (fn, positions.get(fn)))
        if [fn for fn in order if fn in ids + ["passport_number"]] != ids + ["passport_number"]:
            fail.append("Employee NIN, TIN and NSSF No. must come first in the section, before Passport Number")
        tabs = [fields[fn].get("label") or fn for fn in order if fields[fn]["fieldtype"] == "Tab Break"]
        if BIO_TAB not in tabs or tabs[tabs.index(BIO_TAB) - 1] != "Personal Details" or tabs[tabs.index(BIO_TAB) + 1] != "Profile":
            fail.append("Employee tab %r must sit between Personal Details and Profile; tabs are %s" % (BIO_TAB, tabs))
        for fn in by_dt[EM]:
            if fn in ids:
                continue
            tab, after = ELSEWHERE.get(fn, (BIO_TAB, None))
            if positions.get(fn, ("?",))[0] != tab:
                fail.append("Employee.%s lands in tab %r, expected %r" % (fn, positions.get(fn, ("?",))[0], tab))
            if after and order[order.index(fn) - 1] != after:
                fail.append("Employee.%s must follow %s, follows %s" % (fn, after, order[order.index(fn) - 1]))
        sections = [fields[fn].get("label") for fn in order
                    if fields[fn]["fieldtype"] == "Section Break" and positions[fn][0] == BIO_TAB]
        if sections != BIO_SECTIONS:
            fail.append("Personal Bio-Data sections %s do not follow the paper form %s" % (sections, BIO_SECTIONS))
        profile = [fn for fn in order if positions[fn][0] == "Profile" and fields[fn]["fieldtype"] == "Section Break"]
        if profile != ["educational_qualification", "custom_professional_section", "previous_work_experience",
                       "history_in_company"]:
            fail.append("Employee Profile sections %s: professional certificates must follow Education" % profile)
        for fn, f in by_dt[EM].items():
            if f["fieldtype"] == "Table":
                before = order[order.index(fn) - 1]
                if fields[before]["fieldtype"] != "Section Break" or positions[fn][2] != 0:
                    fail.append("Employee.%s must open its own section, full width" % fn)
    order, fields = simulate_layout(EM)
    print_layout(EM, order[order.index("personal_details"):order.index("employment_details")], fields)
    print()
    print("Employee layout: NIN, TIN and NSSF No. open the Identity & Statutory Numbers section; the Personal "
          "Bio-Data tab follows Personal Details in the form's order; nothing standard moves")

# ── 6e. Employee Onboarding and Job Offer — onboarding ───────────────
EO = "Employee Onboarding"
if by_dt.get(EO):
    m = meta(EO)
    baseline = positions_of([fn for fn in m["field_order"]], {f["fieldname"]: f for f in m["fields"]})
    EO_AFTER = {"custom_branch": "company", "custom_onboarding_status": "boarding_status",
                "custom_hr_officer": "boarding_begins_on", "custom_head_of_department": "custom_hr_officer",
                "custom_orientation_section": "amended_from"}
    EO_SECTIONS = ["Employee Details", "Onboarding Activities", "Orientation", "HR Manager Approval"]
    for hrms_first in (True, False):
        order, fields = simulate_layout(EO, hrms_first=hrms_first)
        positions = positions_of(order, fields)
        moved = sorted(fn for fn, where in baseline.items() if positions.get(fn, ("?",))[1] != where[1])
        if moved:
            fail.append("Employee Onboarding standard fields moved to another section: %s" % moved)
        for fn, after in EO_AFTER.items():
            if fn in order and order[order.index(fn) - 1] != after:
                fail.append("Employee Onboarding.%s must follow %s, follows %s" % (fn, after, order[order.index(fn) - 1]))
        sections = [fields[fn].get("label") for fn in order if fields[fn]["fieldtype"] == "Section Break"]
        if sections != EO_SECTIONS:
            fail.append("Employee Onboarding sections %s, expected %s" % (sections, EO_SECTIONS))
    order, fields = simulate_layout(EO)
    print_layout(EO, order, fields)
    print()
    print("Employee Onboarding layout: branch and status up top, the HR Officer and HOD with the dates, "
          "orientation and the HR Manager's approval after the activities")
JOF = "Job Offer"
if by_dt.get(JOF):
    order, fields = simulate_layout(JOF)
    if "custom_branch" in order and order[order.index("custom_branch") - 1] != "company":
        fail.append("Job Offer.custom_branch must follow Company")
    print("Job Offer layout: Branch follows Company")

# ── 7. Removed fields are deleted by a patch ─────────────────────────
# Dropping a record from a fixture file never deletes it from a site that
# already imported it. Anything removed must be deleted by a listed patch,
# or the leftover gets placed by the sorter walk (see section 4).
REMOVED = (
    "Job Requisition-custom_section",
    "Job Opening-custom_section",
    "Job Requisition-custom_recruitment_section",
    "Job Requisition-custom_recruitment_cb",
    # JD text sections replaced by child tables
    "Designation-custom_jd_direct_reports",
    "Designation-custom_jd_reporting_cb",
    "Designation-custom_jd_indirect_reports",
    "Designation-custom_jd_internal_stakeholders",
    "Designation-custom_jd_stakeholder_cb",
    "Designation-custom_jd_external_stakeholders",
    "Designation-custom_jd_strategic_authority",
    "Designation-custom_jd_authority_cb1",
    "Designation-custom_jd_operational_authority",
    "Designation-custom_jd_authority_cb2",
    "Designation-custom_jd_managerial_authority",
    "Designation-custom_jd_short_term",
    "Designation-custom_jd_work_cycle_cb1",
    "Designation-custom_jd_medium_term",
    "Designation-custom_jd_work_cycle_cb2",
    "Designation-custom_jd_long_term",
    # ISO, specification and competency text replaced by child tables
    "Designation-custom_jd_iso_9001",
    "Designation-custom_jd_iso_22000",
    "Designation-custom_jd_ims_leadership",
    "Designation-custom_jd_iso_cb",
    "Designation-custom_jd_iso_45001",
    "Designation-custom_jd_iso_14001",
    "Designation-custom_jd_academic",
    "Designation-custom_jd_specs_cb1",
    "Designation-custom_jd_professional",
    "Designation-custom_jd_specs_cb2",
    "Designation-custom_jd_experience",
    "Designation-custom_jd_technical_competencies",
    "Designation-custom_jd_competency_cb",
    "Designation-custom_jd_behavioural_competencies",
    # Connections back in its own tab
    "Job Requisition-connections_tab-show_dashboard",
    "Job Requisition-connections_tab-hidden",
    "Job Requisition-custom_connections_section",
    "Job Requisition-custom_connections_html",
)
patch_sources = ""
for line in open(os.path.join(REPO, "hrms_addon", "patches.txt"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith(("#", "[")):
        path = os.path.join(REPO, *line.split(".")) + ".py"
        if os.path.exists(path):
            patch_sources += open(path, encoding="utf-8").read()
        else:
            fail.append("patches.txt lists %s but %s does not exist" % (line, path))
fixture_names = {r["name"] for r in custom_fields} | {s["name"] for s in setters}
for name in REMOVED:
    if name in fixture_names:
        fail.append("%s was removed but is back in the fixtures" % name)
    if '"%s"' % name not in patch_sources:
        fail.append("%s was removed from the fixtures but no listed patch deletes it" % name)
print("removed fields: %d, each absent from fixtures and deleted by a listed patch" % len(REMOVED))

# ── 8. hooks.py lists what the fixture files contain ─────────────────
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
