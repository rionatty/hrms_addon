# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interviews: Luuka's Candidate Interview Evaluation / Score Form (LPL/HR/17)
on HRMS's Interview Feedback.

The rules live in interview_rules.py (no Frappe import; tested by
scripts/verify_interviews.py). This wires them into HRMS:

  feedback_validate    Interview Feedback validate: a sheet starts with every
                       criterion, its totals are worked out, the result follows
                       the recommendation, and HRMS's average rating becomes the
                       sheet's percentage, so the Interview's panel average and
                       star summary use the scores
  get_score_criteria   the rows a new sheet starts with, for the form script
  get_skill_wise_average_rating
                       the Interview's Feedback tab shows the panel's average per
                       criterion instead of per HRMS skill (hooks.py
                       override_whitelisted_methods)
  seed_interview_criteria / after_install
                       LPL/HR/17's groups and criteria, once: a patch on existing
                       sites, after_install on new ones (Frappe marks patches as
                       run on install without running them)

and the Interview Shortlist (one per Job Opening, like Luuka's shortlist sheet):

  validate_shortlist / mark_shortlisted / unmark_shortlisted
                       its controller's validate, on_submit and on_cancel
  get_shortlist_candidates / get_candidate_details
                       applicants written out from their Bio-Data (Get
                       Applicants, Refresh Details)
  schedule_interviews  an HRMS Interview per candidate, back to back, with the
                       Interview Type's panel
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import interview_rules as rules


def feedback_validate(doc, method=None):
    """Runs after HRMS's own validate, so the average rating set here stands."""
    if not doc.get("custom_scores"):
        for row in _sheet_rows():
            doc.append("custom_scores", row)
    groups = _groups_of({row.criterion for row in doc.custom_scores if row.criterion})
    for row in doc.custom_scores:
        if row.criterion in groups:
            row.criteria_group = groups[row.criterion]

    errors = rules.score_sheet_errors(doc.custom_scores, doc.get("custom_recommendation"), submitting=doc.docstatus == 1)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Score Sheet"))

    summary = rules.score_summary(doc.custom_scores)
    doc.custom_total_score = summary["total"]
    doc.custom_max_score = summary["maximum"]
    doc.custom_score_percent = summary["percent"]
    doc.custom_score_band = summary["band"]
    doc.average_rating = rules.average_rating(summary)
    if doc.get("custom_recommendation"):
        doc.result = rules.result_for(doc.custom_recommendation)
    doc.custom_interviewer_designation = _designation_of(doc.interviewer)


@frappe.whitelist()
def get_score_criteria():
    """The rows a new score sheet starts with: every criterion not disabled, in order."""
    return _sheet_rows()


@frappe.whitelist()
def get_skill_wise_average_rating(interview: str) -> list[dict]:
    """The panel's average per criterion, for the Interview's Feedback tab.

    Same shape as HRMS's version (skill, and a 0-1 rating the tab multiplies
    by 5). An interview scored the HRMS way, on skills, keeps its skills.
    """
    frappe.has_permission("Interview", "read", interview, throw=True)
    sheets = [
        frappe.get_all(
            "Interview Feedback Score",
            filters={"parent": name, "parenttype": "Interview Feedback", "parentfield": "custom_scores"},
            fields=["criterion", "score"],
            order_by="idx asc",
        )
        for name in frappe.get_all(
            "Interview Feedback", filters={"interview": interview, "docstatus": 1}, pluck="name", order_by="creation asc"
        )
    ]
    averages = rules.criterion_averages(sheets)
    if not averages:
        from hrms.hr.doctype.interview.interview import get_skill_wise_average_rating as hrms_averages

        return hrms_averages(interview)
    return [{"skill": criterion, "rating": average / rules.TOP_SCORE} for criterion, average in averages]


# ── The interview shortlist ───────────────────────────────────────────


def validate_shortlist(doc):
    """Interview Shortlist validate: every applicant once, each one of this opening's."""
    applicants = [row.job_applicant for row in doc.candidates if row.job_applicant]
    opening_of = dict(
        frappe.get_all("Job Applicant", filters={"name": ["in", applicants]}, fields=["name", "job_title"], as_list=True)
    ) if applicants else {}
    errors = rules.shortlist_errors(doc.job_opening, doc.candidates, opening_of, submitting=doc.docstatus == 1)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Interview Shortlist"))
    doc.candidate_count = len(doc.candidates)


@frappe.whitelist()
def get_shortlist_candidates(job_opening: str, exclude: str | None = None) -> list[dict]:
    """Everyone who applied for the opening and can still be shortlisted, written out.

    exclude: JSON list of applicants already on the shortlist.
    """
    frappe.has_permission("Interview Shortlist", "write", throw=True)
    skip = set(frappe.parse_json(exclude) or [])
    applicants = frappe.get_all(
        "Job Applicant",
        filters={"job_title": job_opening, "status": ["in", list(rules.SHORTLISTABLE_STATUSES)]},
        pluck="name",
        order_by="creation asc",
    )
    return [candidate_details(applicant) for applicant in applicants if applicant not in skip]


@frappe.whitelist()
def get_candidate_details(job_applicants: str) -> dict:
    """The shortlist columns for these applicants (JSON list): Refresh Details, or a row added by hand."""
    frappe.has_permission("Interview Shortlist", "write", throw=True)
    return {applicant: candidate_details(applicant) for applicant in frappe.parse_json(job_applicants) or []}


def candidate_details(applicant):
    """One applicant as the shortlist lists them, written out from their Bio-Data."""
    doc = frappe.get_doc("Job Applicant", applicant)
    certification_types = frappe.get_all("Qualification Type", filters={"is_certification": 1}, pluck="name")
    qualifications = doc.get("custom_qualifications") or []
    return {
        "job_applicant": doc.name,
        "applicant_name": doc.applicant_name,
        "phone_number": doc.phone_number,
        "email_id": doc.email_id,
        "education": rules.qualification_lines(qualifications, certification_types, certifications=False),
        "work_experience": rules.experience_lines(doc.get("custom_employment_history") or []),
        "certifications": rules.qualification_lines(qualifications, certification_types, certifications=True),
    }


def mark_shortlisted(doc):
    """On submit: the applicants still open become Shortlisted. One already turned
    down, on hold for another reason or hired keeps their status."""
    for row in doc.candidates:
        if frappe.db.get_value("Job Applicant", row.job_applicant, "status") in ("Open", "Replied", "Hold"):
            frappe.db.set_value("Job Applicant", row.job_applicant, "status", "Shortlisted")


def unmark_shortlisted(doc):
    """On cancel: back to Open, unless another submitted shortlist still lists them."""
    for row in doc.candidates:
        if frappe.db.get_value("Job Applicant", row.job_applicant, "status") != "Shortlisted":
            continue
        elsewhere = frappe.db.exists(
            "Interview Shortlist Candidate",
            {"job_applicant": row.job_applicant, "parent": ["!=", doc.name], "docstatus": 1},
        )
        if not elsewhere:
            frappe.db.set_value("Job Applicant", row.job_applicant, "status", "Open")


@frappe.whitelist(methods=["POST"])
def schedule_interviews(shortlist: str, interview_type: str, scheduled_on: str, from_time: str, minutes: int) -> dict:
    """An Interview for every candidate on a submitted shortlist not yet given one:
    back-to-back slots from `from_time`, with the Interview Type's panel.

    Each candidate is booked on their own, so one HRMS refuses (an Interview
    Type for another position, say) is reported and the rest still go ahead.
    """
    doc = frappe.get_doc("Interview Shortlist", shortlist)
    doc.check_permission("read")
    frappe.has_permission("Interview", "create", throw=True)
    if doc.docstatus != 1:
        frappe.throw(_("Submit the shortlist before scheduling its interviews."))
    panel = frappe.get_all("Interviewer", filters={"parent": interview_type, "parenttype": "Interview Type"}, pluck="user")
    if not panel:
        frappe.throw(_("Interview Type {0} has no interviewers: add the panel to it first.").format(interview_type))
    pending = [row for row in doc.candidates if not row.interview]
    try:
        slots = rules.interview_slots(from_time, minutes, len(pending))
    except ValueError as error:
        frappe.throw(_(str(error)))

    booked, refused = [], []
    for row, (start, end) in zip(pending, slots):
        interview = frappe.get_doc({
            "doctype": "Interview",
            "interview_type": interview_type,
            "job_applicant": row.job_applicant,
            "scheduled_on": scheduled_on,
            "from_time": start,
            "to_time": end,
            "interview_details": [{"interviewer": user} for user in panel],
        })
        frappe.db.savepoint("hrms_addon_schedule_interview")
        try:
            interview.insert()
        except frappe.ValidationError as error:
            frappe.db.rollback(save_point="hrms_addon_schedule_interview")
            frappe.clear_messages()
            refused.append("%s: %s" % (row.applicant_name or row.job_applicant, error))
            continue
        row.db_set("interview", interview.name)
        booked.append(interview.name)
    return {"booked": booked, "refused": refused}


def seed_interview_criteria():
    groups, criteria = rules.criteria_seed_plan(
        frappe.get_all("Interview Criteria Group", pluck="name"), frappe.get_all("Interview Criterion", pluck="name")
    )
    for record in groups + criteria:
        frappe.get_doc(record).insert(ignore_permissions=True)


def after_install():
    seed_interview_criteria()


def _sheet_rows():
    group_order = dict(frappe.get_all("Interview Criteria Group", fields=["name", "sort_order"], as_list=True))
    criteria = frappe.get_all("Interview Criterion", fields=["name", "criteria_group", "sort_order", "disabled"])
    for criterion in criteria:
        criterion["group_order"] = group_order.get(criterion.criteria_group)
    return rules.sheet_rows(criteria)


def _groups_of(criteria):
    if not criteria:
        return {}
    return dict(
        frappe.get_all(
            "Interview Criterion", filters={"name": ["in", sorted(criteria)]}, fields=["name", "criteria_group"], as_list=True
        )
    )


def _designation_of(user):
    if not user:
        return ""
    return frappe.db.get_value("Employee", {"user_id": user}, "designation", order_by="status asc") or ""
