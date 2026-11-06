# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Careers portal: the Job Opening page and the Job Application Form (/apply).

The page itself is templates/generators/job_opening.html; the form is the
Web Form job_application_form. This supplies them with data, and makes the
job list the site's home for a visitor who is not signed in (home_page).

  save_draft / load_draft  Save for later: the application kept against the
                    candidate's email, and a link emailed that brings it back
                    on any device for 30 days (application_draft_rules.py)
  drop_drafts       Job Applicant after_insert: applied, the saved one goes
  purge_drafts      daily: one kept past its days goes
"""

import json

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.rate_limiter import rate_limit
from frappe.utils import format_date, get_url, getdate, now_datetime, today

from hrms_addon.hrms_addon import application_draft_rules as drafts
from hrms_addon.hrms_addon import jd_rules
from hrms_addon.hrms_addon import opening_rules

DRAFT = "Job Application Draft"
APPLY_FORM = "job-application-form"


# the job list, www/jobs
JOBS_PAGE = "jobs"
# an application's own number, by the year it came in: APP-2026-0001. Frappe
# HR names an applicant after their email (fndolo993@gmail.com-3 is the
# third application from that address).
APPLICATION_ID = "APP-{year}-.####"


def application_id(year):
    """The next application number of `year`, from Frappe's own series."""
    return make_autoname(APPLICATION_ID.format(year=year), "Job Applicant")


def number_application(doc, method=None):
    """Job Applicant before_insert: the application's number, once."""
    if not doc.get("custom_application_id"):
        doc.custom_application_id = application_id(getdate().year)


def home_page(user):
    """The site's home (hooks.py get_website_user_home_page): the job list
    for a visitor who is not signed in, so the top bar's Home and the bare
    address open it rather than the login page (Luuka, 4 Oct 2026). Anyone
    signed in, and a home page an administrator sets in Website Settings,
    keep Frappe's own lookup: None."""
    if (user or "Guest") != "Guest" or frappe.db.get_single_value("Website Settings", "home_page"):
        return None
    return JOBS_PAGE


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


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def save_draft(email=None, job_opening=None, values=None):
    """Save for later (Luuka, 5 Nov 2026: "an option for temporary saving so
    that someone can start from there anytime"): what the candidate has typed
    is kept against their email and the opening, and a link that brings it
    back is emailed to them. The key travels only in that email: the answer
    here never carries it."""
    email = str(email or "").strip().lower()
    if job_opening and not frappe.db.exists("Job Opening", {"name": job_opening, "publish": 1}):
        frappe.throw(_("This opening is not on the careers page."))
    kept = drafts.kept_values(values, _form_fields())
    errors = drafts.draft_errors(email, kept)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Save for later"))
    name = frappe.db.get_value(DRAFT, {"email": email, "job_opening": job_opening or ["is", "not set"]}, "name")
    doc = frappe.get_doc(DRAFT, name) if name else frappe.new_doc(DRAFT)
    doc.update({"email": email, "job_opening": job_opening or None, "saved_values": json.dumps(kept),
                "expires_on": drafts.expires_on(today()), "sent_on": now_datetime()})
    if not doc.get("draft_key"):
        doc.draft_key = frappe.generate_hash(length=drafts.KEY_LENGTH)
    doc.flags.ignore_permissions = True
    doc.save() if name else doc.insert()
    title = frappe.db.get_value("Job Opening", job_opening, "job_title") if job_opening else None
    frappe.sendmail(
        recipients=[email], subject=_("Finish your application{0}").format(" for %s" % title if title else ""),
        message=_("<p>Your application is saved. Open this link on any phone or computer to finish it, until "
                  "{0}:</p><p><a href=\"{1}\">{1}</a></p><p>If you did not ask for this, you can ignore this "
                  "email.</p>").format(format_date(doc.expires_on, "d MMM, YYYY"),
                                       drafts.link(get_url(), job_opening, doc.draft_key)))
    return {"sent_to": email, "kept_until": str(doc.expires_on)}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=30, seconds=60 * 60)
def load_draft(key=None):
    """What a saved application's link brings back: the opening and the
    answers, while it is kept; nothing for a key that is not there."""
    if not drafts.usable_key(key):
        return {}
    found = frappe.db.get_value(DRAFT, {"draft_key": key}, ["job_opening", "saved_values", "expires_on"], as_dict=True)
    if not found or drafts.expired(found.expires_on, today()):
        return {}
    try:
        values = json.loads(found.saved_values or "{}")
    except ValueError:
        values = {}
    return {"job_opening": found.job_opening, "values": values}


def drop_drafts(doc, method=None):
    """Job Applicant after_insert: applied, the application saved for later
    goes."""
    if doc.get("email_id"):
        frappe.db.delete(DRAFT, {"email": str(doc.email_id).strip().lower(),
                                 "job_opening": doc.get("job_title") or ["is", "not set"]})


def purge_drafts():
    """Daily: an application saved and not finished in its days goes."""
    frappe.db.delete(DRAFT, {"expires_on": ["<", today()]})


def _form_fields():
    """The fields the Job Application Form asks for."""
    return [row.fieldname for row in frappe.get_all("Web Form Field", filters={
        "parenttype": "Web Form", "parent": APPLY_FORM}, fields=["fieldname"], limit_page_length=0) if row.fieldname]


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
