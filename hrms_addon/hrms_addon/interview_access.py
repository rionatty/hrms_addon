# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a panel member sees of the interviews. The rules are in
interview_access_rules.py (no Frappe import; scripts/verify_interview_access.py).

  *_has_permission      hooks.py has_permission: a panel member reads the
                        interviews they sit on, files and changes only their
                        own score sheets, and reads a colleague's only once
                        their own is in
  *_query_conditions    hooks.py permission_query_conditions: the same for
                        lists, reports and link searches
  get_feedback          the Interview's Feedback tab (hooks.py
                        override_whitelisted_methods): the panel's sheets, for
                        whoever may see them yet
  sees_panel_scores     the same test, for the tab's averages per criterion
  hide_panel_average    Interview Feedback on_submit and on_cancel: the
                        Interview's average rating shows once the whole panel
                        has scored
  get_candidate_pack    the candidate as the panel needs them: what they
                        applied with, read from their application. A panel
                        member has no access to the Job Applicant itself,
                        which also holds their NIN, family and health.
  download_cv           the CV they uploaded, for the same people
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import interview_access_rules as rules
from hrms_addon.hrms_addon import interview_rules


def _narrowed(doctype, user):
    return rules.narrowed(doctype, frappe.get_roles(user))


# ── has_permission ────────────────────────────────────────────────────
# Frappe v16 treats anything but True as a refusal, so each returns a bool.


def interview_has_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if not _narrowed("Interview", user):
        return True
    return rules.allowed("Interview", ptype, {"on_panel": _on_panel(doc.name, user)})


def feedback_has_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if not _narrowed("Interview Feedback", user):
        return True
    own = doc.get("interviewer") == user
    return rules.allowed("Interview Feedback", ptype,
                         {"own": own, "submitted_own": not own and _submitted_own(doc.get("interview"), user)})


def type_has_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if not _narrowed("Interview Type", user):
        return True
    return rules.allowed("Interview Type", ptype, {})


def shortlist_has_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if not _narrowed("Interview Shortlist", user):
        return True
    return rules.allowed("Interview Shortlist", ptype,
                         {"sits_for_opening": _sits_for_opening(doc.get("job_opening"), user)})


def report_has_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if not _narrowed("Interview Report", user):
        return True
    listed = bool(doc.name) and bool(frappe.db.exists(
        "Interview Report Panel Member", {"parent": doc.name, "parenttype": "Interview Report", "interviewer": user}))
    return rules.allowed("Interview Report", ptype, {"listed": listed})


# ── permission_query_conditions ───────────────────────────────────────


def interview_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if not _narrowed("Interview", user):
        return ""
    return ("exists (select 1 from `tabInterview Detail` ha_detail where ha_detail.parent = `tabInterview`.name "
            "and ha_detail.parenttype = 'Interview' and ha_detail.interviewer = {0})").format(frappe.db.escape(user))


def feedback_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if not _narrowed("Interview Feedback", user):
        return ""
    return ("(`tabInterview Feedback`.interviewer = {0} or `tabInterview Feedback`.interview in "
            "(select ha_sheet.interview from `tabInterview Feedback` ha_sheet "
            "where ha_sheet.interviewer = {0} and ha_sheet.docstatus = 1))").format(frappe.db.escape(user))


def shortlist_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if not _narrowed("Interview Shortlist", user):
        return ""
    return ("exists (select 1 from `tabInterview` ha_interview join `tabInterview Detail` ha_detail "
            "on ha_detail.parent = ha_interview.name and ha_detail.parenttype = 'Interview' "
            "where ha_interview.job_opening = `tabInterview Shortlist`.job_opening "
            "and ha_detail.interviewer = {0})").format(frappe.db.escape(user))


def report_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if not _narrowed("Interview Report", user):
        return ""
    return ("exists (select 1 from `tabInterview Report Panel Member` ha_member "
            "where ha_member.parent = `tabInterview Report`.name and ha_member.parenttype = 'Interview Report' "
            "and ha_member.interviewer = {0})").format(frappe.db.escape(user))


def _on_panel(interview, user):
    return bool(interview) and bool(frappe.db.exists(
        "Interview Detail", {"parent": interview, "parenttype": "Interview", "interviewer": user}))


def _submitted_own(interview, user):
    return bool(interview) and bool(frappe.db.exists(
        "Interview Feedback", {"interview": interview, "interviewer": user, "docstatus": 1}))


def _sits_for_opening(opening, user):
    if not opening:
        return False
    sat = frappe.get_all("Interview Detail", filters={"parenttype": "Interview", "interviewer": user}, pluck="parent")
    return bool(sat) and bool(frappe.db.exists("Interview", {"name": ["in", sat], "job_opening": opening}))


# ── the panel's scores ────────────────────────────────────────────────


def sees_panel_scores(interview, user=None):
    """True when `user` may see the panel's scores on this interview: HR, or a
    panel member who has submitted their own sheet."""
    user = user or frappe.session.user
    return not _narrowed("Interview Feedback", user) or _submitted_own(interview, user)


@frappe.whitelist()
def get_feedback(interview: str) -> list:
    """Frappe HR's Feedback tab: every submitted sheet, for whoever may see
    them yet. Frappe HR's own asks only whether the reader may read feedback
    at all, for any interview."""
    frappe.has_permission("Interview", "read", interview, throw=True)
    if not sees_panel_scores(interview):
        return []
    from hrms.hr.doctype.interview.interview import get_feedback as hrms_get_feedback

    return hrms_get_feedback(interview)


def hide_panel_average(doc, method=None):
    """Interview Feedback on_submit and on_cancel, after Frappe HR's own has
    averaged every sheet into the Interview: the average shows once the
    whole panel has scored."""
    if not doc.get("interview"):
        return
    panel = frappe.get_all("Interview Detail", filters={"parent": doc.interview, "parenttype": "Interview"},
                           pluck="interviewer")
    sheets = frappe.get_all("Interview Feedback", filters={"interview": doc.interview, "docstatus": 1},
                            fields=["interviewer", "average_rating"])
    frappe.db.set_value("Interview", doc.interview, "average_rating", rules.revealed_average(panel, sheets),
                        update_modified=False)


# ── the candidate, for the panel ──────────────────────────────────────


@frappe.whitelist()
def get_candidate_pack(interview: str) -> dict:
    """What the candidate applied with, for whoever may read the interview:
    the post, their education, work experience, certifications, skills,
    languages, their answers to the screening questions, the cover letter,
    and whether there is a CV to open."""
    frappe.has_permission("Interview", "read", interview, throw=True)
    applicant = frappe.db.get_value("Interview", interview, "job_applicant")
    if not applicant or not frappe.db.exists("Job Applicant", applicant):
        return {}
    doc = frappe.get_doc("Job Applicant", applicant)
    certification_types = frappe.get_all("Qualification Type", filters={"is_certification": 1}, pluck="name")
    qualifications = doc.get("custom_qualifications") or []
    return {
        "applicant_name": doc.applicant_name,
        "designation": doc.get("designation") or "",
        "education": interview_rules.qualification_lines(qualifications, certification_types, certifications=False),
        "work_experience": interview_rules.experience_lines(doc.get("custom_employment_history") or []),
        "certifications": interview_rules.qualification_lines(qualifications, certification_types, certifications=True),
        "skills": [row.skill for row in doc.get("custom_skills") or [] if row.skill],
        "languages": [interview_rules.language_line(row) for row in doc.get("custom_languages") or [] if row.language],
        "answers": [{"question": row.question, "answer": row.answer or ""}
                    for row in doc.get("custom_screening_answers") or [] if row.question],
        "cover_letter": doc.get("cover_letter") or "",
        "has_cv": bool(doc.get("resume_attachment")),
        "cv_link": doc.get("resume_link") or "",
    }


@frappe.whitelist()
def download_cv(interview: str):
    """The CV the candidate uploaded, opened in the browser, for whoever may
    read the interview. The file is private to the application."""
    frappe.has_permission("Interview", "read", interview, throw=True)
    applicant = frappe.db.get_value("Interview", interview, "job_applicant")
    url = frappe.db.get_value("Job Applicant", applicant, "resume_attachment") if applicant else None
    if not url:
        frappe.throw(_("The candidate uploaded no CV."))
    if url.startswith(("http://", "https://")):
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = url
        return
    name = frappe.db.get_value("File", {"file_url": url, "attached_to_doctype": "Job Applicant",
                                        "attached_to_name": applicant}, "name") \
        or frappe.db.get_value("File", {"file_url": url}, "name")
    if not name:
        frappe.throw(_("The CV file is missing."))
    file_doc = frappe.get_doc("File", name)
    with open(file_doc.get_full_path(), "rb") as handle:
        content = handle.read()
    frappe.local.response["filename"] = file_doc.file_name
    frappe.local.response["filecontent"] = content
    frappe.local.response["type"] = "download"
    frappe.local.response["display_content_as"] = "inline"
