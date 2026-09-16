# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Move ISO Responsibilities, Ideal Job Specifications and Competency
Framework from text boxes into their child tables.

Same approach as jd_text_sections_to_tables. Each ISO box becomes one row
for its standard; each line of the specification and competency boxes
becomes a row. The old fields are then deleted.

Competencies are Skills, so a competency the Skill list lacks is created as
a Skill first and the row links to something real.

Nothing is dropped silently. A line that cannot become a row, such as a
competency too long to be a Skill name, is written as a comment on that
Job Title for someone to add by hand.

ORDER MATTERS. This post_model_sync patch runs after seed_jd_masters, so
the standards, specification types and categories the rows use exist; and
before fixtures, so the new Table fields do not exist on Designation yet.
Rows are inserted straight into the child tables with their parentfield
set, and attach once fixtures create the fields a moment later.

Defensive on purpose: a patch that raises stops the whole migrate. Each
Job Title is handled inside its own savepoint, and a failure is rolled back
and logged, not raised; the Skills that Job Title created are rolled back
with it. Rows are only added to a table that has none, so a re-run cannot
double up.
"""

import frappe
from frappe.utils.data import escape_html

from hrms_addon.hrms_addon import jd_rules

SAVEPOINT = "hrms_addon_jd_profile_sections"

REMOVED_FIELDS = (
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
)


def execute():
    columns = set(frappe.db.get_table_columns("Designation"))
    present = [field for field in jd_rules.PROFILE_TEXT_FIELDS if field in columns]
    if present:
        skills = jd_rules.name_lookup(frappe.get_all("Skill", pluck="name"))
        for values in frappe.get_all("Designation", fields=["name", *present]):
            if not any(values.get(field) for field in present):
                continue
            frappe.db.savepoint(SAVEPOINT)
            try:
                skills.update(_move(values, skills))
            except Exception:
                frappe.db.rollback(save_point=SAVEPOINT)
                frappe.log_error(title="HRMS Addon: JD text not moved into tables for %s" % values.name)

    for name in REMOVED_FIELDS:
        frappe.delete_doc_if_exists("Custom Field", name)


def _move(values, skills):
    """Moves one Job Title's text. Returns the Skills it created, as a lookup."""
    tables, new_skills, unconverted = jd_rules.profile_sections_to_rows(values, skills)

    for field in list(tables):
        if tables[field] and frappe.db.exists(
            jd_rules.TABLES[field], {"parent": values.name, "parenttype": "Designation", "parentfield": field}
        ):
            tables[field] = []  # already has rows: leave them alone
    if not tables["custom_jd_competencies"]:
        new_skills = []

    for name in new_skills:
        frappe.get_doc({"doctype": "Skill", "skill_name": name}).insert(ignore_permissions=True)

    for field, rows in tables.items():
        for idx, row in enumerate(rows, start=1):
            frappe.get_doc(
                {
                    "doctype": jd_rules.TABLES[field],
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

    return jd_rules.name_lookup(new_skills)
