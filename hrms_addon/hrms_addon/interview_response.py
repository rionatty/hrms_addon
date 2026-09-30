# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The candidate's answer to an interview invitation, at /interview-response
(www/interview-response.html).

The invitation links here with the Interview's own key (interviews.response_link).
The candidate sees their interview and confirms they will attend, or asks for
another time with a note on when they could come. The answer is kept on the
Interview with the slot it was given for (interview_rules.slot_of), so it
stops standing once the interview moves (interviews.clear_moved_response).
Asking for another time tells whoever booked the interview.

  page_context   what the page shows for a key
  respond        the candidate's answer (a guest may send it; rate limited)
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import escape_html, format_date, format_time, now_datetime

from hrms_addon.hrms_addon import interview_rules as rules

FIELDS = ["name", "docstatus", "status", "job_applicant", "job_opening", "designation", "scheduled_on", "from_time",
          "to_time", "custom_mode", "custom_venue", "custom_meeting_link", "custom_candidate_response",
          "custom_responded_on", "custom_response_slot", "owner"]


def _interview(key):
    """The Interview a key opens, or None. A key is 32 characters, made when
    the invitation is sent."""
    key = str(key or "").strip()
    if len(key) < 20:
        return None
    return frappe.db.get_value("Interview", {"custom_response_key": key}, FIELDS, as_dict=True)


def page_context(key):
    """What /interview-response shows: the interview, what the candidate may
    do with it, and their answer for its slot as it is now."""
    row = _interview(key)
    if not row:
        return frappe._dict(valid=0)
    applicant = frappe.db.get_value("Job Applicant", row.job_applicant, "applicant_name") or ""
    company = frappe.db.get_value("Job Opening", row.job_opening, "company") if row.job_opening else ""
    answer = rules.response_for_slot(row.custom_candidate_response, row.custom_response_slot, row.scheduled_on,
                                     row.from_time)
    return frappe._dict(
        valid=1, key=str(key).strip(), first_name=(applicant.split() or [""])[0], designation=row.designation or "",
        company=company or "", date=format_date(row.scheduled_on, "EEEE d MMMM yyyy") if row.scheduled_on else "",
        time=format_time(row.from_time, "HH:mm") if row.from_time else "", mode=row.custom_mode or rules.MODES[0],
        venue=row.custom_venue or company or "", meeting_link=row.custom_meeting_link or "",
        state=rules.response_page_state(row.docstatus, row.status, row.scheduled_on, row.to_time, str(now_datetime())),
        answer=answer, answered_on=format_date(row.custom_responded_on) if answer and row.custom_responded_on else "",
        confirmed=rules.CONFIRMED, another_time=rules.ANOTHER_TIME, note_max=rules.NOTE_MAX)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60)
def respond(key: str, answer: str, note: str | None = None) -> dict:
    """The candidate's answer: Confirmed, or Asked for Another Time with a
    note. Refused for a key that opens nothing, an interview cancelled or
    already held, and an answer that is not whole."""
    row = _interview(key)
    if not row:
        frappe.throw(_("This link is not valid. Please use the link in your invitation email."))
    state = rules.response_page_state(row.docstatus, row.status, row.scheduled_on, row.to_time, str(now_datetime()))
    if state == "cancelled":
        frappe.throw(_("This interview has been cancelled."))
    if state == "over":
        frappe.throw(_("This interview has already taken place."))
    errors = rules.response_errors(answer, note)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors))
    note = str(note or "").strip() if answer == rules.ANOTHER_TIME else ""
    frappe.db.set_value("Interview", row.name, {
        "custom_candidate_response": answer, "custom_responded_on": now_datetime(),
        "custom_response_note": note or None,
        "custom_response_slot": rules.slot_of(row.scheduled_on, row.from_time)}, update_modified=False)
    doc = frappe.get_doc("Interview", row.name)
    if answer == rules.CONFIRMED:
        doc.add_comment("Info", _("The candidate confirmed they will attend."))
    else:
        doc.add_comment("Info", _("The candidate asked for another time: {0}").format(escape_html(note)))
        _tell_whoever_booked(row, note)
    return {"answer": answer}


def _tell_whoever_booked(row, note):
    """Whoever booked the interview hears that the candidate asked to move it."""
    if not row.owner or row.owner == "Guest":
        return
    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

    applicant = frappe.db.get_value("Job Applicant", row.job_applicant, "applicant_name") or row.job_applicant
    enqueue_create_notification([row.owner], {
        "type": "Alert", "document_type": "Interview", "document_name": row.name,
        "subject": _("{0} asked for another time for their interview on {1}").format(
            escape_html(applicant), format_date(row.scheduled_on)),
        "email_content": escape_html(note)})
