# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Careers portal: the Job Opening page and the Job Application Form (/apply).

The page itself is templates/generators/job_opening.html; the form is the
Web Form job_application_form. This supplies them with data.
"""

import frappe
from frappe.utils import format_date

from hrms_addon.hrms_addon import jd_rules


def job_posting_details(job_opening):
    """The Job Title's Job Description, as far as a candidate should see it.

    A Jinja method (hooks.py jinja), called by the Job Opening page when the
    opening's "Show Job Description on Careers Page" box is ticked. Only the
    parts jd_rules.posting_details lets out are returned. Returns {} when
    there is nothing to show.
    """
    designation = job_opening.get("designation") if job_opening else None
    if not designation or not frappe.db.exists("Designation", designation):
        return {}

    doc = frappe.get_doc("Designation", designation)
    return jd_rules.posting_details(
        purpose=doc.get("custom_jd_purpose"),
        key_result_areas=doc.get("custom_jd_key_result_areas"),
        specifications=doc.get("custom_jd_specifications"),
        competencies=doc.get("custom_jd_competencies"),
        specification_order=frappe.get_all("JD Specification Type", order_by="creation asc", pluck="name"),
        category_order=frappe.get_all("JD Competency Category", order_by="creation asc", pluck="name"),
    )


@frappe.whitelist(allow_guest=True)
def get_opening_summary(job_opening):
    """Title and key facts of the job being applied for, for the heading of
    the Job Application Form. Candidates are mostly not logged in.

    Only a published Job Opening is described, so this cannot be used to
    read openings that are not on the careers portal.
    """
    opening = frappe.db.get_value(
        "Job Opening",
        {"name": job_opening, "publish": 1},
        ["job_title", "company", "location", "employment_type", "status", "closes_on", "route"],
        as_dict=True,
    )
    if not opening:
        return None
    return {
        "job_title": opening.job_title,
        "company": opening.company,
        "location": opening.location,
        "employment_type": opening.employment_type,
        "is_open": opening.status == "Open",
        "closes_on": format_date(opening.closes_on, "d MMM, YYYY") if opening.closes_on else None,
        "route": "/" + opening.route if opening.route else None,
    }
