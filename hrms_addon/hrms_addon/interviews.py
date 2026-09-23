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

  validate_shortlist / shortlist_on_update / mark_shortlisted / unmark_shortlisted
                       its controller's validate, on_update, on_submit and
                       on_cancel: HR screens and shares it with the HOD, whose
                       approval submits it (interview_shortlist_approval.py)
  setup_shortlist_workflow_on_migrate
                       after_migrate: that screening workflow
  get_shortlist_candidates / get_candidate_details
                       applicants written out from their Bio-Data (Get
                       Applicants, Refresh Details)
  schedule_interviews  an HRMS Interview per candidate, back to back, with the
                       Interview Type's panel

and the Interview Report (one per Job Opening and interview day):

  validate_report      its controller's validate: complete once past Draft, and
                       the sign-off block filled as the approvers act
  close_report         its controller's on_submit (the approval): the day's
                       interviews closed with the panel's decisions and the
                       applicants moved on
  get_interview_results
                       the day's panel and candidates, with the score sheets
                       averaged and counted (Get Interview Results)
  create_job_offers    a draft Job Offer for each candidate offered the job
  unblock_cancel       Interview and Job Offer on_cancel: the shortlist and the
                       report that list them do not stop a correction
  setup_report_workflow_on_migrate
                       after_migrate: its approval workflow, from
                       interview_report_approval.py
"""

import frappe
from frappe import _
from frappe.utils import escape_html, today

from hrms_addon.hrms_addon import cv_screening
from hrms_addon.hrms_addon import cv_screening_rules
from hrms_addon.hrms_addon import interview_report_approval as approval
from hrms_addon.hrms_addon import interview_rules as rules
from hrms_addon.hrms_addon import interview_shortlist_approval as screening
from hrms_addon.hrms_addon import workflows


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
    """Interview Shortlist validate: every applicant once, each one of this opening's,
    the HOD named before it is shared (the requisition's HOD unless changed), their
    reason given when they return it, and the screening sign-offs as each screener acts."""
    if not doc.get("head_of_department") and doc.get("job_opening"):
        requisition = frappe.db.get_value("Job Opening", doc.job_opening, "job_requisition")
        if requisition:
            doc.head_of_department = frappe.db.get_value("Job Requisition", requisition, "custom_hod")

    before = doc.get_doc_before_save()
    old_state = before.get(screening.STATE_FIELD) if before else None
    new_state = doc.get(screening.STATE_FIELD)
    applicants = [row.job_applicant for row in doc.candidates if row.job_applicant]
    opening_of = dict(
        frappe.get_all("Job Applicant", filters={"name": ["in", applicants]}, fields=["name", "job_title"], as_list=True)
    ) if applicants else {}
    errors = rules.shortlist_errors(doc.job_opening, doc.candidates, opening_of, submitting=doc.docstatus == 1)
    errors += screening.screening_errors(old_state, new_state, doc.get("head_of_department"), doc.get("hod_comments"))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Interview Shortlist"))
    doc.candidate_count = len(doc.candidates)
    if doc.docstatus == 0 and new_state in (None, screening.DRAFT, screening.RETURNED):
        _screen_rows(doc)

    current = {field: before.get(field) for field in screening.STAMP_FIELDS} if before else {}
    for field, value in screening.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)


def shortlist_on_update(doc):
    """When the shortlist moves on, only the person who acts next is told: the HOD
    it is shared with, or back to whoever prepared it when the HOD returns it."""
    before = doc.get_doc_before_save()
    old_state = before.get(screening.STATE_FIELD) if before else None
    new_state = doc.get(screening.STATE_FIELD)
    if old_state == new_state:
        return
    from frappe.desk.form.assign_to import _add, close_all_assignments

    close_all_assignments(doc.doctype, doc.name, ignore_permissions=True)
    user = screening.assignee(old_state, new_state, doc.get("head_of_department"), doc.owner)
    if user:
        _add(
            {
                "assign_to": [user],
                "doctype": doc.doctype,
                "name": doc.name,
                "description": _("Interview shortlist for {0}: {1}").format(doc.designation or doc.job_opening, _(new_state)),
            },
            ignore_permissions=True,
        )


def setup_shortlist_workflow_on_migrate():
    """after_migrate: the shortlist's screening workflow (workflows.py)."""
    workflows.setup_on_migrate(screening, "Interview Shortlist screening")


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
    context = cv_screening.context_for(job_opening)
    found = [candidate_details(applicant, context) for applicant in applicants if applicant not in skip]
    return sorted(found, key=cv_screening_rules.sort_key)


@frappe.whitelist()
def get_candidate_details(job_applicants: str) -> dict:
    """The shortlist columns for these applicants (JSON list): Refresh Details, or a row added by hand."""
    frappe.has_permission("Interview Shortlist", "write", throw=True)
    contexts = {}
    return {applicant: candidate_details(applicant, contexts=contexts)
            for applicant in frappe.parse_json(job_applicants) or []}


def candidate_details(applicant, context=None, contexts=None):
    """One applicant as the shortlist lists them, written out from their Bio-Data,
    and screened against the job they applied for (cv_screening.py)."""
    doc = frappe.get_doc("Job Applicant", applicant)
    if context is None:
        contexts = {} if contexts is None else contexts
        if doc.job_title not in contexts:
            contexts[doc.job_title] = cv_screening.context_for(doc.job_title)
        context = contexts[doc.job_title]
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
        **cv_screening.screen(doc, context),
    }


def _screen_rows(doc):
    """Each candidate screened again while HR has the list, so the HOD sees the
    applicant as they stand when it is shared. The order is HR's."""
    context = cv_screening.context_for(doc.job_opening)
    for row in doc.candidates:
        if row.job_applicant and frappe.db.exists("Job Applicant", row.job_applicant):
            row.update(cv_screening.screen(frappe.get_doc("Job Applicant", row.job_applicant), context))


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


# ── The interview report ──────────────────────────────────────────────


def validate_report(doc):
    """Interview Report validate: complete once past Draft, and its sign-off block
    filled as the HR Manager and the Executive Director act."""
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    errors = rules.report_errors(doc.candidates, doc.recommendations, complete=approval.leaves_draft(new_state))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Interview Report"))

    current = {field: before.get(field) for field in approval.STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)
    if doc.is_new() and not doc.get("prepared_by"):
        doc.prepared_by = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")


@frappe.whitelist()
def get_interview_results(job_opening: str, interview_date: str) -> dict:
    """The day's panel and candidates for an Interview Report.

    Every Interview for the opening on that date (not cancelled), in the order
    they were held: the panel is everyone who sat on any of them, and each
    candidate comes with their Bio-Data written out, the panel's score sheets
    averaged and counted, and their salary expectation.
    """
    frappe.has_permission("Interview Report", "write", throw=True)
    interviews = frappe.get_all(
        "Interview",
        filters={"job_opening": job_opening, "scheduled_on": interview_date, "docstatus": ["!=", 2]},
        fields=["name", "job_applicant"],
        order_by="from_time asc, creation asc",
    )

    panel, seated = [], set()
    for interview in interviews:
        for user in frappe.get_all(
            "Interview Detail", filters={"parent": interview.name, "parenttype": "Interview"}, pluck="interviewer", order_by="idx asc"
        ):
            if user and user not in seated:
                seated.add(user)
                panel.append({
                    "interviewer": user,
                    "interviewer_name": frappe.db.get_value("User", user, "full_name") or user,
                    "designation": _designation_of(user),
                })

    candidates, listed = [], set()
    for interview in interviews:
        if interview.job_applicant in listed:
            continue
        listed.add(interview.job_applicant)
        details = candidate_details(interview.job_applicant)
        sheets = frappe.get_all(
            "Interview Feedback",
            filters={"interview": interview.name, "docstatus": 1},
            fields=["custom_score_percent as percent", "custom_max_score as maximum", "custom_recommendation as recommendation"],
        )
        summary = rules.panel_summary(sheets)
        salary = frappe.db.get_value(
            "Job Applicant", interview.job_applicant, ["currency", "lower_range", "upper_range"], as_dict=True
        ) or {}
        candidates.append({
            "job_applicant": details["job_applicant"],
            "applicant_name": details["applicant_name"],
            "phone_number": details["phone_number"],
            "email_id": details["email_id"],
            "qualification": "\n".join(part for part in (details["education"], details["certifications"]) if part),
            "experience": details["work_experience"],
            "average_score": summary["average"] or 0,
            "score_band": summary["band"],
            "panel_recommendations": summary["tally"],
            "decision": summary["decision"],
            "remarks": rules.salary_remark(salary.get("currency"), salary.get("lower_range"), salary.get("upper_range")),
            "interview": interview.name,
        })
    return {"panel": panel, "candidates": candidates}


def close_report(doc):
    """Interview Report on_submit, the Executive Director's approval: each interview
    closed with the panel's decision (Cleared or Rejected, as on the score sheets)
    and each applicant still undecided moved on: Accepted for an offer,
    Shortlisted to be interviewed again, Rejected.

    Runs as the approver, who need not have rights on Interviews. An interview
    already closed or cancelled by hand is left alone, and one HRMS refuses to
    close is noted on the report for HR while the rest still go ahead.
    """
    refused = []
    for row in doc.candidates:
        result = rules.result_for(row.decision)
        if row.interview and result:
            problem = _close_interview(row.interview, result)
            if problem:
                refused.append("%s (%s): %s" % (row.applicant_name or row.job_applicant, row.interview, problem))
        current = frappe.db.get_value("Job Applicant", row.job_applicant, "status")
        status = rules.applicant_status_after(row.decision, current)
        if status:
            frappe.db.set_value("Job Applicant", row.job_applicant, "status", status)
    if refused:
        message = _("These interviews could not be closed; close them from the Interview:") + "<br>" + "<br>".join(
            escape_html(reason) for reason in refused
        )
        doc.add_comment("Comment", message)
        frappe.msgprint(message, title=_("Interviews"), indicator="orange")


def _close_interview(name, result):
    """Submit one draft Interview with its result. Returns why HRMS refused, or None."""
    interview = frappe.get_doc("Interview", name)
    # closed, cancelled, or marked Cancelled by HR (a no-show, say): theirs to keep
    if interview.docstatus != 0 or interview.status == "Cancelled":
        return None
    interview.status = result
    interview.flags.ignore_permissions = True
    frappe.db.savepoint("hrms_addon_close_interview")
    # HRMS asks on every submit whether to update the applicant; close_report does that
    muted = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        interview.submit()
    except frappe.ValidationError as error:
        frappe.db.rollback(save_point="hrms_addon_close_interview")
        return str(error)
    finally:
        frappe.flags.mute_messages = muted
    return None


@frappe.whitelist(methods=["POST"])
def create_job_offers(report: str) -> dict:
    """A draft Job Offer for each candidate the approved report offers the job, for
    HR to fill in the terms and send; a candidate who already has one is linked to it.

    Each offer is made on its own, so one HRMS refuses (no vacancy left under the
    staffing plan, say) is reported and the rest still go ahead.
    """
    doc = frappe.get_doc("Interview Report", report)
    doc.check_permission("read")
    frappe.has_permission("Job Offer", "create", throw=True)
    if doc.docstatus != 1:
        frappe.throw(_("Job Offers are made once the report is approved."))
    applicants = [row.job_applicant for row in doc.candidates if row.job_applicant]
    existing = dict(
        frappe.get_all(
            "Job Offer",
            filters={"job_applicant": ["in", applicants], "docstatus": ["!=", 2]},
            fields=["job_applicant", "name"],
            as_list=True,
        )
    ) if applicants else {}
    to_create, to_link = rules.offer_plan(doc.candidates, existing)
    rows = {row.job_applicant: row for row in doc.candidates}
    company = frappe.db.get_value("Job Opening", doc.job_opening, "company")

    created, linked, refused = [], [], []
    for applicant, offer in to_link:
        rows[applicant].db_set("job_offer", offer)
        linked.append(offer)
    for applicant in to_create:
        row = rows[applicant]
        offer = frappe.get_doc({
            "doctype": "Job Offer",
            "job_applicant": applicant,
            "offer_date": today(),
            "company": company,
            "designation": doc.designation,
        })
        frappe.db.savepoint("hrms_addon_job_offer")
        try:
            offer.insert()
        except frappe.ValidationError as error:
            frappe.db.rollback(save_point="hrms_addon_job_offer")
            frappe.clear_messages()
            refused.append("%s: %s" % (row.applicant_name or applicant, error))
            continue
        row.db_set("job_offer", offer.name)
        created.append(offer.name)
    return {"created": created, "linked": linked, "refused": refused}


# Documents that record the Interviews and Job Offers made from them (hooks.py
# auto_cancel_exempted_doctypes lists them too)
RECORDS = ("Interview Shortlist", "Interview Report")


def unblock_cancel(doc, method=None):
    """Interview and Job Offer on_cancel: the shortlist and the report list the
    interviews and offers made from them, as records, so cancelling one to
    correct it does not need the approved shortlist or report cancelled first."""
    doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + RECORDS


def setup_report_workflow_on_migrate():
    """after_migrate: the Interview Report's approval workflow (workflows.py)."""
    workflows.setup_on_migrate(approval, "Interview Report approval")


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
