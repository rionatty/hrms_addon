# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Move the Job Description text sections into their child tables.

Reporting Relationships, Stakeholder Management, Decision-Making Authority
and Work Cycle & Planning Horizon were free-text fields for a few hours
before becoming child tables. This carries anything already typed into
the new tables, then deletes the old fields.

Nothing is dropped silently. Each line becomes a row, or — when it cannot
safely become one, such as a report naming a Job Title that does not
exist — is written as a comment on that Job Title for someone to add by
hand. A row with a broken Job Title link would block the next save.

ORDER MATTERS. Migrate runs this post_model_sync patch after the child
DocTypes are synced but BEFORE fixtures, so the new Table fields do not yet
exist on Designation. Rows are therefore inserted straight into the child
tables with their parentfield set; they attach once fixtures create the
fields a moment later.

Defensive on purpose: a patch that raises stops the whole migrate. Each
Job Title is handled on its own and a failure is logged, not raised. Rows
are only added to a table that has none, so a re-run cannot double up.
"""

import frappe
from frappe.utils.data import escape_html

from hrms_addon.hrms_addon import jd_rules

REMOVED_FIELDS = (
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
)


def execute():
    columns = set(frappe.db.get_table_columns("Designation"))
    present = [field for field in jd_rules.OLD_TEXT_FIELDS if field in columns]
    if present:
        lookup = jd_rules.designation_lookup(frappe.get_all("Designation", pluck="name"))
        for values in frappe.get_all("Designation", fields=["name", *present]):
            if not any(values.get(field) for field in present):
                continue
            try:
                _move(values, lookup)
            except Exception:
                frappe.log_error(title="HRMS Addon: JD text not moved into tables for %s" % values.name)

    for name in REMOVED_FIELDS:
        frappe.delete_doc_if_exists("Custom Field", name)


def _move(values, lookup):
    tables, unconverted = jd_rules.text_sections_to_rows(values, lookup)

    for field, rows in tables.items():
        if not rows:
            continue
        child = jd_rules.TABLES[field]
        if frappe.db.exists(child, {"parent": values.name, "parenttype": "Designation", "parentfield": field}):
            continue
        for idx, row in enumerate(rows, start=1):
            frappe.get_doc(
                {
                    "doctype": child,
                    "parent": values.name,
                    "parenttype": "Designation",
                    "parentfield": field,
                    "idx": idx,
                    **row,
                }
            ).db_insert()

    if unconverted:
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "reference_doctype": "Designation",
                "reference_name": values.name,
                "content": "Job Description: these lines could not be moved into the new tables automatically "
                "and need adding by hand:<br>" + "<br>".join(escape_html(line) for line in unconverted),
            }
        ).insert(ignore_permissions=True)
