# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interviews: Luuka's Candidate Interview Evaluation / Score Form (LPL/HR/17)
on HRMS's Interview Feedback.

The rules live in interview_rules.py (no Frappe import; tested by
scripts/verify_interviews.py). This wires them into HRMS:

  feedback_validate    Interview Feedback validate: a sheet starts with the
                       round's own criteria and weights (else the general list),
                       its weighted totals are worked out, the result follows
                       the recommendation, and HRMS's average rating becomes the
                       sheet's percentage, so the Interview's panel average and
                       star summary use the scores; it starts with the
                       interview's questions too, each scored. Submitting needs
                       the conflict tick, comments, every question scored, and an
                       Offer at the round's pass mark
  interview_validate   Interview validate: the Interview Type's round, questions
                       and criteria, as they were when it was booked
  interview_type_validate
                       Interview Type validate: its own list of criteria is sound
  get_round_criteria   Get Criteria from JD: a round's criteria from its JD's
                       competencies, weighed by priority, then the general list
  get_interview_questions
                       the questions a new score sheet starts with
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
  schedule_interviews  an HRMS Interview per candidate chosen (a batch, or
                       everyone), for a round (Interview Type) they do not have
                       yet, back to back, with the Interview Type's panel

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
from frappe.utils import (cint, escape_html, format_date, format_time, get_url_to_form, getdate, now_datetime,
                          strip_html, today)

from hrms_addon.hrms_addon import cv_screening
from hrms_addon.hrms_addon import cv_screening_rules
from hrms_addon.hrms_addon import interview_access as access
from hrms_addon.hrms_addon import interview_access_rules as access_rules
from hrms_addon.hrms_addon import interview_report_approval as approval
from hrms_addon.hrms_addon import interview_rules as rules
from hrms_addon.hrms_addon import interview_shortlist_approval as screening
from hrms_addon.hrms_addon import workflows


def feedback_validate(doc, method=None):
    """Runs after HRMS's own validate, so the average rating set here stands."""
    # a sheet is its interviewer's own: Frappe HR only checks they sit on the panel
    problem = access_rules.sheet_owner_error(doc.interviewer, frappe.session.user)
    if problem and not (frappe.flags.in_migrate or frappe.flags.in_patch or frappe.flags.in_install):
        frappe.throw(_(problem), frappe.PermissionError)
    start, own_list = _sheet_start(doc.get("interview"))
    if not doc.get("custom_scores"):
        for row in start:
            doc.append("custom_scores", row)
    # the weights and the N/A rule are the round's, whatever was posted: its
    # own list when the sheet scores exactly that, else the general one
    weights = {row["criterion"]: row["weight"] for row in start} if own_list else {}
    doc.custom_round_criteria = 1 if weights and {row.criterion for row in doc.custom_scores} == set(weights) else 0
    for row in doc.custom_scores:
        row.weight = weights.get(row.criterion, 1) if doc.custom_round_criteria else 1
    groups = _groups_of({row.criterion for row in doc.custom_scores if row.criterion})
    for row in doc.custom_scores:
        if row.criterion in groups:
            row.criteria_group = groups[row.criterion]
    # the interview's questions, each with what to look for, the candidate's
    # answer and its score
    if not doc.get("custom_answers") and doc.get("interview"):
        for row in _questions_asked(doc.interview):
            doc.append("custom_answers", row)

    submitting = doc.docstatus == 1
    recommendation = doc.get("custom_recommendation")
    errors = rules.score_sheet_errors(doc.custom_scores, recommendation, submitting=submitting,
                                      round_criteria=bool(doc.get("custom_round_criteria")))
    summary = rules.score_summary(doc.custom_scores)
    if submitting:
        # the Offer check waits until the scores themselves are right
        pass_mark = rules.pass_percent(frappe.db.get_value("Interview", doc.interview, "expected_average_rating")) \
            if doc.get("interview") else None
        errors += rules.submission_errors({} if errors else summary, recommendation, doc.get("feedback"),
                                          doc.get("custom_no_conflict"), doc.get("custom_answers"), pass_mark)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Score Sheet"))

    doc.custom_total_score = summary["total"]
    doc.custom_max_score = summary["maximum"]
    doc.custom_score_percent = summary["percent"]
    doc.custom_score_band = summary["band"]
    doc.custom_question_percent = rules.question_summary(doc.get("custom_answers"))["percent"]
    doc.average_rating = rules.average_rating(summary)
    if recommendation:
        doc.result = rules.result_for(recommendation)
    doc.custom_interviewer_designation = _designation_of(doc.interviewer)


@frappe.whitelist()
def get_score_criteria(interview: str | None = None) -> dict:
    """The rows a new score sheet starts with, and whether they are the
    round's own list (weighed, nothing N/A) or the general one."""
    if interview:
        frappe.has_permission("Interview", "read", interview, throw=True)
    rows, own_list = _sheet_start(interview)
    return {"rows": rows, "round_criteria": own_list}


def _sheet_start(interview):
    """The rows a new sheet starts with: the round's criteria as the interview
    was booked with them (its type's, for one booked before rounds had any),
    else the general list. Returns (rows, whether they are the round's)."""
    own = _criteria_of("Interview", interview) if interview else []
    if not own and interview:
        interview_type = frappe.db.get_value("Interview", interview, "interview_type")
        own = type_criteria(interview_type) if interview_type else []
    if own:
        return [{"criteria_group": row.criteria_group, "criterion": row.criterion, "weight": row.weight or 1}
                for row in own], True
    return _sheet_rows(), False


def interview_validate(doc, method=None):
    """An interview carries its type's round, questions and criteria as they
    were when it was booked: they are filled while it has none, and again
    when its type changes."""
    before = doc.get_doc_before_save()
    changed = before is not None and before.get("interview_type") != doc.get("interview_type")
    if doc.get("interview_type") and (changed or not doc.get("custom_questions")):
        doc.set("custom_questions", type_questions(doc.interview_type))
    if doc.get("interview_type") and (changed or not doc.get("custom_criteria")):
        doc.set("custom_criteria", type_criteria(doc.interview_type))
    doc.custom_round = frappe.db.get_value("Interview Type", doc.interview_type, "custom_round") \
        if doc.get("interview_type") else None
    # who came: a no-show or a withdrawal is Cancelled, someone who came is
    # Under Review while the panel scores
    status = rules.status_for_attendance(doc.get("custom_attendance"), doc.get("status"))
    if status and doc.docstatus == 0:
        doc.status = status


def type_questions(interview_type):
    """An Interview Type's questions, in order."""
    return frappe.get_all("Interview Question",
                          filters={"parent": interview_type, "parenttype": "Interview Type",
                                   "parentfield": "custom_questions"},
                          fields=["question", "guidance"], order_by="idx asc")


def type_criteria(interview_type):
    """An Interview Type's own list of criteria and their weights, in order."""
    return _criteria_of("Interview Type", interview_type)


def _criteria_of(doctype, name):
    return frappe.get_all("Interview Round Criterion",
                          filters={"parent": name, "parenttype": doctype, "parentfield": "custom_criteria"},
                          fields=["criterion", "criteria_group", "weight"], order_by="idx asc")


@frappe.whitelist()
def get_interview_questions(interview: str) -> list:
    """The questions a new score sheet starts with: the interview's own."""
    frappe.has_permission("Interview", "read", interview, throw=True)
    return _questions_asked(interview)


def _questions_asked(interview):
    """The interview's questions and what to look for, or its type's where it carries none."""
    asked = frappe.get_all("Interview Question",
                           filters={"parent": interview, "parenttype": "Interview", "parentfield": "custom_questions"},
                           fields=["question", "guidance"], order_by="idx asc")
    if not asked:
        interview_type = frappe.db.get_value("Interview", interview, "interview_type")
        asked = type_questions(interview_type) if interview_type else []
    return [{"question": row.question, "guidance": row.guidance} for row in asked]


def interview_type_validate(doc, method=None):
    """Interview Type validate: its own list of criteria, where it has one,
    lists each once, weighs each 1 to 5, and holds nothing switched off or
    never scored."""
    disabled = frappe.get_all("Interview Criterion", filters={"disabled": 1}, pluck="name")
    errors = rules.round_criteria_errors(doc.get("custom_criteria"), disabled)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Interview Type"))


@frappe.whitelist(methods=["POST"])
def get_round_criteria(designation: str) -> list:
    """The criteria a round starts with, from its JD (Get Criteria from JD):
    the JD's competencies weighed by their priority, then the general list
    once each. A competency not yet in the list of criteria is added to it,
    under Job Competencies."""
    frappe.has_permission("Interview Type", "write", throw=True)
    competencies = frappe.get_all("JD Competency",
                                  filters={"parent": designation, "parenttype": "Designation",
                                           "parentfield": "custom_jd_competencies"},
                                  fields=["competency", "priority"], order_by="idx asc")
    weights = dict(frappe.get_all("JD Requirement Priority", fields=["name", "weight"], as_list=True))
    rows, to_create = rules.round_criteria_plan(competencies, weights, _sheet_rows(),
                                                frappe.get_all("Interview Criterion", pluck="name"))
    if to_create:
        frappe.has_permission("Interview Criterion", "create", throw=True)
        if not frappe.db.exists("Interview Criteria Group", rules.JD_GROUP):
            frappe.get_doc({"doctype": "Interview Criteria Group", "group_name": rules.JD_GROUP, "sort_order": 5}).insert()
        for name in to_create:
            frappe.get_doc({"doctype": "Interview Criterion", "criterion_name": name,
                            "criteria_group": rules.JD_GROUP}).insert()
    groups = _groups_of({row["criterion"] for row in rows})
    for row in rows:
        row["criteria_group"] = groups.get(row["criterion"])
    return rows


@frappe.whitelist()
def get_skill_wise_average_rating(interview: str) -> list[dict]:
    """The panel's average per criterion, for the Interview's Feedback tab.

    Same shape as HRMS's version (skill, and a 0-1 rating the tab multiplies
    by 5). An interview scored the HRMS way, on skills, keeps its skills.
    """
    frappe.has_permission("Interview", "read", interview, throw=True)
    # a panel member sees the panel's marks once their own sheet is in
    if not access.sees_panel_scores(interview):
        return []
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
def get_shortlist_candidates(job_opening: str, exclude: str | None = None, filters: str | None = None) -> dict:
    """Everyone who applied for the opening and can still be shortlisted, written out
    and screened, the best first; with HR's filter, only the ones it keeps, and how
    many it left out.

    exclude: JSON list of applicants already on the shortlist.
    filters: JSON, as cv_screening_rules.shortlist_filter reads it.
    """
    frappe.has_permission("Interview Shortlist", "write", throw=True)
    wanted = cv_screening_rules.shortlist_filter(frappe.parse_json(filters) if filters else {})
    errors = cv_screening_rules.filter_errors(wanted)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Get Applicants"))
    skip = set(frappe.parse_json(exclude) or [])
    applicants = frappe.get_all(
        "Job Applicant",
        filters={"job_title": job_opening, "status": ["in", list(rules.SHORTLISTABLE_STATUSES)]},
        pluck="name",
        order_by="creation asc",
    )
    context = cv_screening.context_for(job_opening)
    found = [candidate_details(applicant, context, with_text=True) for applicant in applicants if applicant not in skip]
    kept, left_out = cv_screening_rules.filter_candidates(found, wanted)
    for row in kept:
        row.pop("search_text", None)
    return {"candidates": kept, "left_out": left_out}


@frappe.whitelist()
def get_candidate_details(job_applicants: str) -> dict:
    """The shortlist columns for these applicants (JSON list): Refresh Details, or a row added by hand."""
    frappe.has_permission("Interview Shortlist", "write", throw=True)
    contexts = {}
    return {applicant: candidate_details(applicant, contexts=contexts)
            for applicant in frappe.parse_json(job_applicants) or []}


def candidate_details(applicant, context=None, contexts=None, with_text=False):
    """One applicant as the shortlist lists them, written out from their Bio-Data,
    and screened against the job they applied for (cv_screening.py). with_text:
    their bio-data and CV as well, for HR's filter to look through."""
    doc = frappe.get_doc("Job Applicant", applicant)
    if context is None:
        contexts = {} if contexts is None else contexts
        if doc.job_title not in contexts:
            contexts[doc.job_title] = cv_screening.context_for(doc.job_title)
        context = contexts[doc.job_title]
    certification_types = frappe.get_all("Qualification Type", filters={"is_certification": 1}, pluck="name")
    qualifications = doc.get("custom_qualifications") or []
    details = {
        "job_applicant": doc.name,
        "applicant_name": doc.applicant_name,
        "phone_number": doc.phone_number,
        "email_id": doc.email_id,
        "education": rules.qualification_lines(qualifications, certification_types, certifications=False),
        "work_experience": rules.experience_lines(doc.get("custom_employment_history") or []),
        "certifications": rules.qualification_lines(qualifications, certification_types, certifications=True),
        **cv_screening.screen(doc, context),
    }
    if with_text:
        facts = cv_screening.applicant_facts(doc)
        details["search_text"] = "%s\n%s" % (facts["bio_data"], facts["cv"])
    return details


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
def schedule_interviews(shortlist: str, interview_type: str, scheduled_on: str, from_time: str, minutes: int,
                        applicants: str | None = None, gap: int | None = None, mode: str | None = None,
                        venue: str | None = None, meeting_link: str | None = None, send_invitations: int = 1) -> dict:
    """An Interview of this type, the round, for the candidates HR chose on a
    submitted shortlist (everyone on it when none is chosen) who are still in
    the running, do not have the round yet and cleared the round before it.

    Slots run from `from_time` on `scheduled_on`, `gap` minutes apart (HR
    Settings' gap when none is given), round the lunch break and within the
    day, the rest carried to the next working day of the company's holiday
    list; never in the past, and only while the Interview Type's panel is
    free. The candidates are then invited (send_invitations) and the panel
    sent its schedule, in the background.

    applicants: JSON list of the chosen job applicants, a batch.

    Each candidate is booked on their own, so one HRMS refuses (an Interview
    Type for another position, say) is reported and the rest still go ahead.
    """
    doc = frappe.get_doc("Interview Shortlist", shortlist)
    doc.check_permission("read")
    frappe.has_permission("Interview", "create", throw=True)
    if doc.docstatus != 1:
        frappe.throw(_("Submit the shortlist before scheduling its interviews."))
    if getdate(scheduled_on) < getdate(today()):
        frappe.throw(_("Interviews cannot be booked in the past."))
    panel = frappe.get_all("Interviewer", filters={"parent": interview_type, "parenttype": "Interview Type"}, pluck="user")
    if not panel:
        frappe.throw(_("Interview Type {0} has no interviewers: add the panel to it first.").format(interview_type))
    listed = [row.job_applicant for row in doc.candidates if row.job_applicant]
    already = set(frappe.get_all("Interview", filters={"job_applicant": ["in", listed or [""]],
                                                       "interview_type": interview_type, "docstatus": ["!=", 2]},
                                 pluck="job_applicant"))
    chosen = set(frappe.parse_json(applicants) or []) if applicants else set()
    statuses = dict(frappe.get_all("Job Applicant", filters={"name": ["in", listed or [""]]}, fields=["name", "status"],
                                   as_list=True))
    earlier = _earlier_round(interview_type)
    cleared = set(frappe.get_all("Interview", filters={"job_applicant": ["in", listed or [""]], "interview_type": ["in", earlier],
                                                       "docstatus": 1, "status": "Cleared"},
                                 pluck="job_applicant")) if earlier else set()
    plan = rules.booking_plan(listed, chosen, already, statuses, bool(earlier), cleared)
    pending = [row for row in doc.candidates if row.job_applicant in plan["book"]]

    settings = _interview_settings()
    holidays = _holidays(frappe.db.get_value("Job Opening", doc.job_opening, "company"))
    first_day = str(getdate(scheduled_on))
    if first_day in holidays:
        frappe.throw(_("{0} is not a working day: {1}.").format(format_date(first_day), holidays[first_day]))
    try:
        slots = rules.plan_slots(first_day, from_time, minutes, len(pending),
                                 gap=settings.gap if gap in (None, "") else gap, lunch=settings.lunch,
                                 day_end=settings.day_end, is_working_day=lambda day: day not in holidays)
    except ValueError as error:
        frappe.throw(_(str(error)))
    days = sorted({day for day, _start, _end in slots})
    problems = rules.clashes(slots, panel, _panel_busy(panel, days), _panel_leave(panel, days))
    if problems:
        frappe.throw("<br>".join([_("The panel is not free:")] + [escape_html(problem) for problem in problems]),
                     title=_("Schedule Interviews"))

    mode = mode if mode in rules.MODES else rules.MODES[0]
    venue = venue or frappe.db.get_value("Interview Type", interview_type, "custom_venue")
    booked, refused, booked_days = [], [], set()
    for row, (day, start, end) in zip(pending, slots):
        interview = frappe.get_doc({
            "doctype": "Interview",
            "interview_type": interview_type,
            "job_applicant": row.job_applicant,
            "scheduled_on": day,
            "from_time": start,
            "to_time": end,
            "custom_mode": mode,
            "custom_venue": venue if mode == "In Person" else None,
            "custom_meeting_link": meeting_link if mode == "Video Call" else None,
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
        booked_days.add(day)
    if booked:
        frappe.enqueue("hrms_addon.hrms_addon.interviews.send_booking_letters", interviews=booked,
                       invite=cint(send_invitations), enqueue_after_commit=True)
    names = {row.job_applicant: row.applicant_name or row.job_applicant for row in doc.candidates}
    return {
        "booked": booked,
        "refused": refused,
        "already": [names[applicant] for applicant in plan["already"]],
        "out": ["%s (%s)" % (names[applicant], status) for applicant, status in plan["out"]],
        "not_cleared": [names[applicant] for applicant in plan["not_cleared"]],
        "days": [format_date(day) for day in sorted(booked_days)],
    }


def _earlier_round(interview_type):
    """The Interview Types of the round before this one for the same JD."""
    this = frappe.db.get_value("Interview Type", interview_type, ["designation", "custom_round"], as_dict=True)
    if not this or not this.designation:
        return []
    types = frappe.get_all("Interview Type", filters={"designation": this.designation}, fields=["name", "custom_round"])
    return rules.earlier_round([(row.name, row.custom_round) for row in types], this.custom_round)


def _interview_settings():
    """HR Settings' interview day: the gap between candidates, the lunch break, the day's end."""
    value = lambda field: frappe.db.get_single_value("HR Settings", field)  # noqa: E731
    return frappe._dict(gap=value("custom_interview_gap") or 0,
                        lunch=(value("custom_lunch_from"), value("custom_lunch_to")),
                        day_end=value("custom_interview_day_end"))


def _holidays(company):
    """{'YYYY-MM-DD': what it is} on the company's default holiday list, weekly offs included."""
    holiday_list = frappe.db.get_value("Company", company, "default_holiday_list") if company else None
    if not holiday_list:
        return {}
    return {str(row.holiday_date): strip_html(row.description or "").strip() or _("Holiday")
            for row in frappe.get_all("Holiday", filters={"parent": holiday_list, "parenttype": "Holiday List"},
                                      fields=["holiday_date", "description"])}


def _panel_busy(panel, days):
    """The panel's other interviews on these days: [(user, date, from, to, interview)]."""
    others = {row.name: row for row in frappe.get_all(
        "Interview", filters={"scheduled_on": ["in", days or [""]], "docstatus": ["!=", 2], "status": ["!=", "Cancelled"]},
        fields=["name", "scheduled_on", "from_time", "to_time"])}
    if not others:
        return []
    return [(row.interviewer, str(others[row.parent].scheduled_on), others[row.parent].from_time,
             others[row.parent].to_time, row.parent)
            for row in frappe.get_all("Interview Detail", filters={"parent": ["in", list(others)], "parenttype": "Interview",
                                                                   "interviewer": ["in", panel]},
                                      fields=["parent", "interviewer"])]


def _panel_leave(panel, days):
    """The panel's leave over these days, applied for or approved: [(user, from, to)]."""
    employees = dict(frappe.get_all("Employee", filters={"user_id": ["in", panel]}, fields=["name", "user_id"], as_list=True))
    if not employees or not days:
        return []
    return [(employees[row.employee], str(row.from_date), str(row.to_date))
            for row in frappe.get_all("Leave Application",
                                      filters={"employee": ["in", list(employees)], "docstatus": ["!=", 2],
                                               "status": ["in", ["Open", "Approved"]], "from_date": ["<=", days[-1]],
                                               "to_date": [">=", days[0]]},
                                      fields=["employee", "from_date", "to_date"])]


# ── Letters: the invitation, the panel's schedule, the regret ─────────


def send_booking_letters(interviews, invite=1):
    """Background, once a round is booked: each candidate invited (when HR
    asked for it) and each panel member sent their schedule."""
    if cint(invite):
        for name in interviews:
            _quietly(_invite, name)
    _quietly(_send_panel_schedules, interviews)


@frappe.whitelist(methods=["POST"])
def send_invitation(interview: str) -> list:
    """Send Invitation, on the Interview: the candidate invited again, by
    email and, where HR Settings says so, by SMS."""
    frappe.has_permission("Interview", "write", interview, throw=True)
    sent = _invite(interview)
    if not sent:
        frappe.throw(_("Nothing was sent: the candidate has no email address or phone to reach, or HR Settings has no "
                       "Invitation template."))
    return sent


def _invite(name):
    """The invitation to one interview. Returns where it went."""
    interview = frappe.get_doc("Interview", name)
    applicant = frappe.db.get_value("Job Applicant", interview.job_applicant, ["applicant_name", "email_id", "phone_number"],
                                    as_dict=True) or frappe._dict()
    context = _invitation_context(interview, applicant)
    sent = []
    template = frappe.db.get_single_value("HR Settings", "custom_invitation_template")
    if applicant.email_id and template and frappe.db.exists("Email Template", template):
        subject, message = _render(template, context)
        frappe.sendmail(recipients=[applicant.email_id], subject=subject, message=message, sender=_hiring_sender(),
                        reference_doctype="Interview", reference_name=name)
        sent.append(applicant.email_id)
    if applicant.phone_number and frappe.db.get_single_value("HR Settings", "custom_send_invitation_sms") \
            and frappe.db.get_single_value("SMS Settings", "sms_gateway_url"):
        # the text is the system's own, not a user's message: sent as the
        # process, without SMS Settings' check on who may type one
        from frappe.core.doctype.sms_settings.sms_settings import _send_sms

        _send_sms([applicant.phone_number], rules.invitation_sms(context["company"], context["designation"], context["date"],
                                                                 context["time"], context["mode"], context["venue"]),
                  success_msg=False)
        sent.append(applicant.phone_number)
    if sent:
        frappe.db.set_value("Interview", name, "custom_invited_on", now_datetime(), update_modified=False)
        interview.add_comment("Info", _("Invitation sent to {0}").format(", ".join(sent)))
    return sent


def _invitation_context(interview, applicant):
    """What the invitation says: every key the template may name
    (interview_rules.INVITATION_KEYS), blank where there is nothing."""
    opening = frappe.db.get_value("Job Opening", interview.job_opening, ["company", "designation"], as_dict=True) \
        if interview.get("job_opening") else None
    opening = opening or frappe._dict()
    return {
        "applicant_name": applicant.get("applicant_name") or "",
        "designation": interview.get("designation") or opening.designation or "",
        "company": opening.company or "",
        "date": format_date(interview.scheduled_on, "EEEE d MMMM yyyy") if interview.get("scheduled_on") else "",
        "time": format_time(interview.from_time, "HH:mm") if interview.get("from_time") else "",
        "mode": interview.get("custom_mode") or rules.MODES[0],
        "venue": interview.get("custom_venue") or "",
        "meeting_link": interview.get("custom_meeting_link") or "",
        "what_to_bring": frappe.db.get_value("Interview Type", interview.interview_type, "custom_what_to_bring") or "",
        "interview": interview.name,
    }


def _send_panel_schedules(interviews):
    """Each panel member gets their slots of this booking in one email, with a
    link to each Interview, whose Candidate tab has the CV."""
    rows = frappe.get_all("Interview", filters={"name": ["in", interviews]},
                          fields=["name", "job_applicant", "interview_type", "scheduled_on", "from_time", "to_time",
                                  "custom_mode", "custom_venue"], order_by="scheduled_on asc, from_time asc")
    if not rows:
        return
    names = dict(frappe.get_all("Job Applicant", filters={"name": ["in", [row.job_applicant for row in rows]]},
                                fields=["name", "applicant_name"], as_list=True))
    sitting = {}
    for detail in frappe.get_all("Interview Detail", filters={"parent": ["in", interviews], "parenttype": "Interview"},
                                 fields=["parent", "interviewer"]):
        if detail.interviewer:
            sitting.setdefault(detail.interviewer, set()).add(detail.parent)
    header = "".join("<th>%s</th>" % _(label) for label in ("Date", "Time", "Candidate", "Where"))
    for user, mine in sitting.items():
        lines = "".join(
            "<tr><td>%s</td><td>%s to %s</td><td><a href=\"%s\">%s</a></td><td>%s</td></tr>" % (
                format_date(row.scheduled_on), format_time(row.from_time, "HH:mm"), format_time(row.to_time, "HH:mm"),
                get_url_to_form("Interview", row.name), escape_html(names.get(row.job_applicant) or row.job_applicant),
                escape_html(row.custom_venue or row.custom_mode or ""))
            for row in rows if row.name in mine)
        message = "<p>%s</p><table border=\"1\" cellpadding=\"4\" cellspacing=\"0\"><tr>%s</tr>%s</table>" % (
            _("You sit on these interviews. Each one's Candidate tab has the CV and the application."), header, lines)
        frappe.sendmail(recipients=[frappe.db.get_value("User", user, "email") or user],
                        subject=_("Your interviews: {0}").format(rows[0].interview_type), message=message,
                        sender=_hiring_sender(), reference_doctype="Interview Type", reference_name=rows[0].interview_type)


def regret_on_update(doc, method=None):
    """Job Applicant on_update: an applicant just turned down gets the regret
    email, where HR Settings says so."""
    if doc.get("status") == "Rejected" and doc.has_value_changed("status"):
        queue_regret(doc.name)


def queue_regret(applicant):
    """The regret email, after this transaction, where HR Settings says so."""
    if frappe.db.get_single_value("HR Settings", "custom_send_regret_emails"):
        frappe.enqueue("hrms_addon.hrms_addon.interviews.send_regret", applicant=applicant, enqueue_after_commit=True)


def send_regret(applicant):
    """Background: the regret email, once, to an applicant turned down who was
    never offered the job. Returns whether it went."""
    values = frappe.db.get_value("Job Applicant", applicant, ["applicant_name", "email_id", "status", "job_title",
                                                             "designation", "custom_regret_sent_on"], as_dict=True)
    template = frappe.db.get_single_value("HR Settings", "custom_regret_template")
    if not values or not template or not frappe.db.exists("Email Template", template):
        return False
    offered = frappe.db.exists("Job Offer", {"job_applicant": applicant, "docstatus": ["!=", 2]})
    if not rules.regret_due(values.status, values.custom_regret_sent_on, offered, values.email_id):
        return False
    company = frappe.db.get_value("Job Opening", values.job_title, "company") if values.job_title else ""
    subject, message = _render(template, {"applicant_name": values.applicant_name or "",
                                          "designation": values.designation or "", "company": company or ""})
    frappe.sendmail(recipients=[values.email_id], subject=subject, message=message, sender=_hiring_sender(),
                    reference_doctype="Job Applicant", reference_name=applicant)
    frappe.db.set_value("Job Applicant", applicant, "custom_regret_sent_on", now_datetime(), update_modified=False)
    return True


def mark_interviews_held():
    """Hourly: an interview whose slot has ended, and that nobody marked a
    no-show, is Under Review, so Frappe HR's daily reminder chases the panel
    members whose sheets are missing."""
    now = str(now_datetime())
    for row in frappe.get_all("Interview", filters={"docstatus": 0, "status": "Pending", "scheduled_on": ["<=", today()]},
                              fields=["name", "scheduled_on", "to_time", "custom_attendance"]):
        if row.custom_attendance not in rules.ABSENT and rules.slot_over(row.scheduled_on, row.to_time, now):
            frappe.db.set_value("Interview", row.name, "status", "Under Review", update_modified=False)


def seed_interview_letters():
    """The invitation and regret Email Templates, and HR Settings' interview
    day and letters where they are empty; once (a patch, and after_install)."""
    for name, subject, body in ((rules.INVITATION_TEMPLATE, rules.INVITATION_SUBJECT, rules.INVITATION_BODY),
                                (rules.REGRET_TEMPLATE, rules.REGRET_SUBJECT, rules.REGRET_BODY)):
        if not frappe.db.exists("Email Template", name):
            frappe.get_doc({"doctype": "Email Template", "name": name, "subject": subject, "use_html": 1,
                            "response_html": body}).insert(ignore_permissions=True)
    for field, value in (("custom_invitation_template", rules.INVITATION_TEMPLATE),
                         ("custom_regret_template", rules.REGRET_TEMPLATE), ("custom_interview_gap", 10),
                         ("custom_lunch_from", "13:00:00"), ("custom_lunch_to", "14:00:00"),
                         ("custom_interview_day_end", "17:00:00")):
        if not frappe.db.get_single_value("HR Settings", field):
            frappe.db.set_single_value("HR Settings", field, value)


def _render(template, context):
    """(subject, message) of an Email Template for this context."""
    doc = frappe.get_doc("Email Template", template)
    body = doc.response_html if doc.use_html else doc.response
    return frappe.render_template(doc.subject or "", context), frappe.render_template(body or "", context)


def _hiring_sender():
    return frappe.db.get_single_value("HR Settings", "hiring_sender_email") or None


def _quietly(function, *args):
    """A letter that cannot go is logged for HR, and the others still go."""
    try:
        function(*args)
    except Exception:
        frappe.log_error(title=_("Interview letter not sent"))


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
            if status == "Rejected":
                queue_regret(row.job_applicant)
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
    seed_interview_letters()


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
