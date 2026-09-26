# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Requisition — Frappe side of the approval workflow.

The definition (states, transitions, which fields each signature fills)
lives in requisition_approval.py, which has no Frappe import so it can be
tested without a bench. This module only applies it:

  setup_on_migrate()  after_migrate: roles, permissions, Workflow States,
                      Workflow Actions and the Workflow itself, built by
                      workflows.py (which says why that is Python, not fixtures)
  before_validate()   defaults Requested By to the logged-in employee, an
                      empty Job Description tab to the Job Title's JD, and an
                      empty Department to the JD's
  validate()          the reason and a mode of recruitment while it is
                      written; fills the Approvals tab as approvers act
  get_job_description()
                      the Job Description tab for a Job Title, which the form
                      fills in when the Job Title is picked
  get_jd_department() the Job Title's department, which the form takes too

To change who approves, change requisition_approval.py, not the Workflow in
the desk — a desk edit is overwritten on the next deploy.
"""

import frappe
from frappe import _
from frappe.utils import strip_html, today

from hrms_addon.hrms_addon import careers, jd_rules
from hrms_addon.hrms_addon import requisition_approval as rules
from hrms_addon.hrms_addon import workflows

# The requisition's Job Description tab: Responsibilities, Reporting Line of
# the New Employee and Subordinates of the New Employee
JD_FIELDS = ("description", "custom_reporting_line", "custom_subordinates")

# ── Doc events ───────────────────────────────────────────────────────


def before_validate(doc, method=None):
    """A new requisition's defaults, before the mandatory check: Requested By
    = the logged-in user's employee record, and an empty Job Description tab
    = the Job Title's JD. The Department, when there is none, is the Job
    Title's JD's.

    The form does these itself (job_requisition.js); this is the server-side
    net for everything that is not the form, such as an API call or import.
    """
    if doc.is_new() and not doc.get("requested_by"):
        employee = _employee_for(frappe.session.user)
        if employee:
            doc.requested_by = employee
    if doc.is_new() and doc.get("designation") and not any(_has_content(doc.get(field)) for field in JD_FIELDS):
        doc.update(job_description_for(doc.designation))
    if doc.get("designation") and not doc.get("department"):
        department = jd_department(doc.designation)
        if department:
            doc.department = department


def validate(doc, method=None):
    before = doc.get_doc_before_save()
    old_state = before.get(rules.STATE_FIELD) if before else None
    new_state = doc.get(rules.STATE_FIELD)

    errors = rules.request_errors(old_state, new_state,
                                  {field: doc.get(field) for field in (rules.REASON_FIELD, *rules.MODE_FIELDS)})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Job Requisition"))

    if rules.recommended_salary_missing(old_state, new_state, doc.get("expected_compensation")):
        frappe.throw(
            _("Enter the Recommended Salary and save before authorizing this requisition."),
            title=_("Recommended Salary Required"),
        )

    current = {field: before.get(field) for field in rules.ALL_STAMP_FIELDS} if before else {}
    stamped = rules.compute_stamp_values(old_state, new_state, frappe.session.user, today(), current)
    for field, value in stamped.items():
        doc.set(field, value)


@frappe.whitelist()
def get_session_employee():
    """Active employee linked to the logged-in user — for the form default.

    Server-side on purpose: the Employee role can only read its own
    employee record through user permissions, which is enough here but
    not something the browser should have to rely on.
    """
    return _employee_for(frappe.session.user)


def _employee_for(user):
    """The user's active employee record: by the login linked to it, else by
    the user's email on it (a record not yet linked to the login)."""
    if not user or user in ("Guest", "Administrator"):
        return None
    for field in ("user_id", "company_email", "prefered_email", "personal_email"):
        employee = frappe.db.get_value("Employee", {field: user, "status": "Active"}, "name")
        if employee:
            return employee
    return None


@frappe.whitelist()
def get_job_description(designation: str) -> dict:
    """The Job Description tab for this Job Title, for the form to fill in
    when the Job Title is picked.

    For whoever writes requisitions: the requesting roles may only pick Job
    Titles, not open them, so the Designation is read here on their behalf.
    """
    frappe.has_permission("Job Requisition", "write", throw=True)
    return job_description_for(designation)


def job_description_for(designation):
    """{field: value} for a requisition's Job Description tab, from the Job
    Title's JD: its candidate-facing parts as the Responsibilities (HRMS copies
    them onto the Job Opening, whose page is public), Reports To as the
    Reporting Line, and the Reporting Relationships as the Subordinates.
    All blank when the Job Title has no JD.
    """
    values = dict.fromkeys(JD_FIELDS, "")
    if not designation or not frappe.db.exists("Designation", designation):
        return values
    jd = frappe.get_doc("Designation", designation)
    values["description"] = jd_rules.requisition_description(careers.posting_details_of(jd))
    values["custom_reporting_line"] = jd.get("custom_jd_reports_to") or ""
    values["custom_subordinates"] = jd_rules.requisition_subordinates(
        jd.get("custom_jd_reporting_lines"),
        frappe.get_all("JD Relationship Type", order_by="creation asc", pluck="name"),
    )
    return values


@frappe.whitelist()
def get_jd_department(designation: str) -> str | None:
    """The Job Title's department, from its JD, for the form to take when the
    Job Title is picked; read on behalf of whoever writes requisitions."""
    frappe.has_permission("Job Requisition", "write", throw=True)
    return jd_department(designation)


def jd_department(designation):
    """The Department on the Job Title's JD, or None."""
    return frappe.db.get_value("Designation", designation, "custom_jd_department") if designation else None


def _has_content(value):
    """Text, or a pasted image: the editor's empty "<p><br></p>" is not content."""
    value = str(value or "")
    return bool(strip_html(value).strip()) or "<img" in value.lower()


# ── Setup (after_migrate) ────────────────────────────────────────────


def setup_on_migrate():
    """after_migrate hook: the approval workflow, never failing the deploy."""
    workflows.setup_on_migrate(rules, "Job Requisition approval")
