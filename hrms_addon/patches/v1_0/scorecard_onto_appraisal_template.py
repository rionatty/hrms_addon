# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Move the role scorecards onto Frappe HR's own Appraisal Template.

The balanced scorecard first went into a BSC Appraisal Template of our
own, standing beside the module Frappe HR already ships. It belongs on
theirs: one template document per role, found by the appraisal through
their own `appraisal_template` link, the way both appraisal forms live on
their Appraisal rather than beside it.

This carries across whatever a site already imported — the four
perspectives and their weights, the KPIs, the competencies, and where the
sheet came from — and then takes the old DocType away, before
`remove_orphan_doctypes()` does it for us at the end of the same migrate
and the scorecards go with it. Deleting a DocType does not drop its table,
and this does not drop it either: `tabBSC Appraisal Template` and the
child rows still pointing at it are left as they are, so what was carried
across can be read back if it needs checking.

Two things it must not assume:

  * post_model_sync runs BEFORE fixtures are synced, so the fields it
    writes onto Appraisal Template do not exist yet. It makes them itself,
    from this app's own fixture file, and the fixture sync that follows
    finds them already there.
  * the old DocType's Python is gone with this commit, so nothing here may
    load its controller: its rows are read straight from the table.

Safe on a site that never had it, and safe to run twice.
"""

import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

OLD = "BSC Appraisal Template"
NEW = "Appraisal Template"
# old fieldname -> new, for the scorecard's own fields
FIELDS = (
    ("designation", "custom_designation"),
    ("review_year", "custom_review_year"),
    ("department", "custom_department"),
    ("grade", "custom_grade"),
    ("review_period", "custom_review_period"),
    ("company", "custom_company"),
    ("is_active", "custom_is_active"),
    ("source_file", "custom_source_file"),
    ("source_sheet", "custom_source_sheet"),
    ("import_remarks", "custom_import_remarks"),
)
# old table field -> new, and the child DocType, which stays ours
TABLES = (
    ("perspectives", "custom_perspectives", "BSC Template Perspective", ("perspective", "weight")),
    ("kpis", "custom_kpis", "BSC Template KPI", ("perspective", "kpi", "timing")),
    ("competencies", "custom_competencies", "BSC Template Competency",
     ("competency", "indicators", "weight")),
)


def execute():
    _make_fields()
    if frappe.db.exists("DocType", OLD) and frappe.db.table_exists(OLD):
        for old in frappe.get_all(OLD, fields="*"):
            _carry(old)
    frappe.delete_doc_if_exists("DocType", OLD, force=1)

    # the appraisals that named their template through our own link
    if frappe.db.has_column("Appraisal", "custom_bsc_template"):
        frappe.db.sql("""
            update `tabAppraisal`
               set appraisal_template = custom_bsc_template
             where ifnull(custom_bsc_template, '') != ''
               and ifnull(appraisal_template, '') = ''
        """)
    frappe.delete_doc_if_exists("Custom Field", "Appraisal-custom_bsc_template")
    # their own template link is Luuka's scorecard now, so it is shown again
    frappe.delete_doc_if_exists("Property Setter", "Appraisal-appraisal_template-hidden")


def _make_fields():
    """The scorecard's fields on their template, from this app's own fixture
    file — fixtures are only synced after every patch has run."""
    path = frappe.get_app_path("hrms_addon", "fixtures", "custom_field.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    wanted = [row for row in rows if row.get("dt") == NEW]
    if not wanted:
        return
    fields = []
    for row in wanted:
        spec = {key: value for key, value in row.items()
                if key not in ("doctype", "dt", "name", "owner", "modified_by", "creation", "modified")}
        fields.append(spec)
    create_custom_fields({NEW: fields}, ignore_validate=True)


def _carry(old):
    name = old.get("name")
    if frappe.db.get_value(NEW, {"custom_designation": old.get("designation"),
                                 "custom_review_year": old.get("review_year")}, "name"):
        return  # already carried across
    new = frappe.new_doc(NEW)
    new.template_title = _title(old)
    for was, now in FIELDS:
        new.set(now, old.get(was))
    for was, now, child, columns in TABLES:
        rows = frappe.get_all(child, filters={"parent": name, "parenttype": OLD, "parentfield": was},
                              fields=list(columns), order_by="idx asc")
        for row in rows:
            new.append(now, dict(row))
    new.flags.ignore_permissions = True
    new.flags.ignore_mandatory = True
    new.insert()


def _title(old):
    """Their template is named after its title, so the role and the year
    name it; a title already taken is kept apart rather than clashing."""
    title = " ".join(("%s %s" % (old.get("designation") or old.get("name"),
                                 old.get("review_year") or "")).split())
    if not frappe.db.exists(NEW, title):
        return title
    nth = 2
    while frappe.db.exists(NEW, "%s (%d)" % (title, nth)):
        nth += 1
    return "%s (%d)" % (title, nth)
