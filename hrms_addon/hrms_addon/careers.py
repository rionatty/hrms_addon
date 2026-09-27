# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Careers portal: the Job Opening page and the Job Application Form (/apply).

The page itself is templates/generators/job_opening.html; the form is the
Web Form job_application_form. This supplies them with data.
"""

import frappe
from frappe.utils import format_date, get_url

from hrms_addon.hrms_addon import jd_rules
from hrms_addon.hrms_addon import opening_rules


def job_share_links(job_opening):
    """A Jinja method (hooks.py jinja): the Job Opening page's Share card and
    its preview on the networks, only while the job is published and open."""
    if not job_opening or not job_opening.get("publish") or job_opening.get("status") != "Open":
        return {}
    return share_card(job_opening)


def share_card(job_opening):
    """{"url", "text", "links", "image"}: the job's own address, the line it
    is shared with, each network's share link and the picture a preview
    shows (the website's logo). Empty while it is not on the website."""
    route = job_opening.get("route")
    if not route or not job_opening.get("publish"):
        return {}
    url = get_url("/" + route.lstrip("/"))
    logo = frappe.get_website_settings("app_logo") or frappe.get_website_settings("banner_image")
    return {
        "url": url,
        "text": opening_rules.share_text(job_opening.get("job_title"), job_opening.get("company")),
        "links": opening_rules.share_links(url, job_opening.get("job_title"), job_opening.get("company")),
        "image": get_url(logo) if logo else None,
    }


def has_job_description(designation):
    """Whether the Job Title has a job description a candidate could read:
    a purpose, responsibilities, requirements or competencies."""
    if not designation or not frappe.db.exists("Designation", designation):
        return False
    return bool(posting_details_of(frappe.get_doc("Designation", designation)))


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
    return posting_details_of(frappe.get_doc("Designation", designation))


def posting_details_of(designation):
    """jd_rules.posting_details of a Job Title (the Designation document).

    The careers page shows them, and a Job Requisition takes them as its
    Responsibilities (job_requisition.job_description_for), so both say the
    same and neither lets out more.
    """
    return jd_rules.posting_details(
        purpose=designation.get("custom_jd_purpose"),
        key_result_areas=designation.get("custom_jd_key_result_areas"),
        specifications=designation.get("custom_jd_specifications"),
        competencies=designation.get("custom_jd_competencies"),
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
        # the questions only: never the answers the job needs
        "screening_questions": frappe.get_all(
            "Screening Question",
            filters={"parent": job_opening, "parenttype": "Job Opening", "parentfield": "custom_screening_questions"},
            fields=["name", "question", "answer_type"],
            order_by="idx asc",
        ),
    }
