# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Designation (Job Title) — Job Description template.

The JD fields themselves are fixtures (Job Description tab). This enforces
the rules for its tables from jd_rules.py: Key Result Areas, reporting
lines, stakeholders, decision areas, horizons, ISO responsibilities, job
specifications, competencies and the screening questions every opening for
the job starts with. Every table can be filled from a CSV
(Download / Upload under it), so rows are first cleaned of what Excel
writes into such a file.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import jd_rules

TABLE = "custom_jd_key_result_areas"


def validate(doc, method=None):
    _clean_uploaded_cells(doc)
    rows = doc.get(TABLE) or []
    _set_perspectives_from_kra(rows)
    perspectives = frappe.get_all("KRA Perspective", order_by="sort_order asc, name asc", pluck="name")
    errors = jd_rules.key_result_area_errors(rows, perspectives) + jd_rules.jd_table_errors(
        doc.name or doc.get("designation_name"),
        doc.get("custom_jd_reports_to"),
        doc.get("custom_jd_reporting_lines"),
        doc.get("custom_jd_stakeholders"),
        doc.get("custom_jd_decision_authorities"),
        doc.get("custom_jd_planning_horizons"),
        iso_responsibilities=doc.get("custom_jd_iso_responsibilities"),
        specifications=doc.get("custom_jd_specifications"),
        competencies=doc.get("custom_jd_competencies"),
        screening_questions=doc.get(jd_rules.SCREENING_TABLE),
    )
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Job Description"))


@frappe.whitelist()
def get_perspective_order():
    """KRA Perspective names in Display Order, for the form's running totals.

    Server-side so a user who may view a Job Title but has no access to the
    KRA Perspective list gets the order instead of a permission popup; the
    names are not sensitive.
    """
    return frappe.get_all("KRA Perspective", order_by="sort_order asc, name asc", pluck="name")


def _clean_uploaded_cells(doc):
    """Every uploadable table's cells as the rules expect them, before they run.

    Upload puts a CSV's cells into the rows as the file has them: a
    weighting Excel wrote as "25%", or curly quotes and dashes garbled by
    Excel's plain CSV format. jd_rules.uploaded_value repairs both; Link
    columns are left alone (Frappe has already checked them by now).
    """
    for fieldname in jd_rules.UPLOADABLE_TABLES:
        for row in doc.get(fieldname) or []:
            for df in row.meta.fields:
                value = row.get(df.fieldname)
                cleaned = jd_rules.uploaded_value(df.fieldtype, value, df.options)
                if cleaned != value:
                    row.set(df.fieldname, cleaned)


def _set_perspectives_from_kra(rows):
    """Each row's perspective, straight from its KRA.

    The form fetches it on pick, but that is the browser's copy: an API
    call or an import can send anything, and Frappe's own server-side
    fetch runs in link validation, not necessarily before this hook. The
    KRA master is the only authority on which perspective a KRA belongs to.
    """
    kras = sorted({row.kra for row in rows if row.get("kra")})
    if not kras:
        return
    perspective_of = dict(
        frappe.get_all("KRA", filters={"name": ["in", kras]}, fields=["name", "custom_perspective"], as_list=True)
    )
    for row in rows:
        if row.get("kra"):
            row.perspective = perspective_of.get(row.kra)
