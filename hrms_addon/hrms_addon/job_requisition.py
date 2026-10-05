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
  headcount_values()  the Headcount section: the job title's staffing plan,
                      the people it has, the positions already being filled
                      and the gap (staffing_rules.py); drawn on every save
                      until the requisition is approved or refused, and by
                      the form as the job title or the number changes
                      (get_headcount)

To change who approves, change requisition_approval.py, not the Workflow in
the desk — a desk edit is overwritten on the next deploy.
"""

import frappe
from frappe import _
from frappe.utils import strip_html, today

from hrms_addon.hrms_addon import careers, jd_rules
from hrms_addon.hrms_addon import requisition_approval as rules
from hrms_addon.hrms_addon import staffing_rules
from hrms_addon.hrms_addon import workflows

# The requisition's Job Description tab: Responsibilities, Reporting Line of
# the New Employee and Subordinates of the New Employee
JD_FIELDS = ("description", "custom_reporting_line", "custom_subordinates")
# The Headcount section
HEADCOUNT_FIELDS = ("custom_staffing_plan", "custom_planned_positions", "custom_current_headcount",
                    "custom_positions_filling", "custom_headcount_gap", "custom_against_plan")

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
    if doc.flags.get("drafted_by_talent"):
        # one a succession plan or a talent programme drafts (talent.py)
        # leaves how to recruit to HR, who are asked for it when they save it
        errors = []
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

    # the figures the approvers acted on stay once the requisition is decided
    if new_state not in (rules.APPROVED, rules.REJECTED) or old_state not in (rules.APPROVED, rules.REJECTED):
        values = headcount_values(doc.get("designation"), doc.get("company"), doc.get("no_of_positions"),
                                  doc.get("posting_date"), doc.name)
        doc.update({field: values[field] for field in HEADCOUNT_FIELDS})


# ── The headcount against the staffing plan ─────────────────────────


@frappe.whitelist()
def get_headcount(designation: str, company: str, no_of_positions: int | None = None,
                  posting_date: str | None = None, requisition: str | None = None) -> dict:
    """The Headcount section for the form, read on behalf of whoever writes
    requisitions: they may not read staffing plans or employees."""
    frappe.has_permission("Job Requisition", "write", throw=True)
    return headcount_values(designation, company, no_of_positions, posting_date, requisition)


def headcount_values(designation, company, requested, day=None, requisition=None):
    """{field: value} for the Headcount section, and "over_by": how many the
    requisition asks beyond the plan (staffing_rules.headcount)."""
    values = dict.fromkeys(HEADCOUNT_FIELDS)
    values["over_by"] = 0
    if not designation or not company:
        return values
    companies = _companies(company)
    plan = _staffing_plan(designation, company, day or today())
    current = frappe.db.count("Employee", {"designation": designation, "status": "Active",
                                           "company": ["in", companies]})
    openings = frappe.get_all("Job Opening", filters={"designation": designation, "status": "Open",
                                                      "company": ["in", companies]},
                              fields=["vacancies", "job_requisition"])
    filters = {"designation": designation, "company": ["in", companies],
               "status": ["in", list(staffing_rules.LIVE_STATUSES)], "name": ["!=", requisition or ""]}
    if frappe.get_meta("Job Requisition").has_field(rules.STATE_FIELD):
        filters[rules.STATE_FIELD] = ["not in", [rules.DRAFT, rules.REJECTED]]
    others = frappe.get_all("Job Requisition", filters=filters, fields=["name", "no_of_positions"])
    filling = staffing_rules.being_filled(openings, others, requisition)
    planned = plan.get("number_of_positions") if plan else 0
    result = staffing_rules.headcount(planned, current, filling, requested, bool(plan))
    values.update({
        "custom_staffing_plan": plan.get("name") if plan else None,
        "custom_planned_positions": planned,
        "custom_current_headcount": current,
        "custom_positions_filling": filling,
        "custom_headcount_gap": result["gap"],
        "custom_against_plan": result["verdict"],
        "over_by": result["over_by"],
    })
    return values


def _staffing_plan(designation, company, day):
    """The submitted staffing plan covering the day with a line for the job
    title: the company's own, else its parent company's, as Frappe HR looks
    (staffing_plan.get_active_staffing_plan_details)."""
    seen = set()
    while company and company not in seen:
        seen.add(company)
        plans = frappe.get_all("Staffing Plan", filters={"company": company, "docstatus": 1},
                               fields=["name", "from_date", "to_date"])
        if plans:
            lines = {row.parent: row.number_of_positions for row in frappe.get_all(
                "Staffing Plan Detail",
                filters={"parent": ["in", [plan.name for plan in plans]], "parenttype": "Staffing Plan",
                         "designation": designation},
                fields=["parent", "number_of_positions"])}
            found = staffing_rules.plan_for(
                [dict(plan, number_of_positions=lines[plan.name]) for plan in plans if plan.name in lines], day)
            if found:
                return found
        company = frappe.db.get_value("Company", company, "parent_company")
    return None


def _companies(company):
    """The company and the companies under it, as Frappe HR counts people
    (staffing_plan.get_designation_counts)."""
    try:
        from frappe.utils.nestedset import get_descendants_of

        return [company, *get_descendants_of("Company", company)]
    except Exception:
        return [company]


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
