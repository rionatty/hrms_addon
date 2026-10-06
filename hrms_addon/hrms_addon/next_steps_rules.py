# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Where each document's process goes next: the documents it raised, or
that followed it, opened from the Next Steps buttons on its form
(next_steps.py, public/js/hrms_addon_next_steps.js). Luuka, 7 Oct 2026:
"there is no button to link it to the next module ... this should apply to
all the modules".

No Frappe import, like the other *_rules.py modules, so
scripts/verify_next_steps.py checks every step against the doctypes
without a bench.

Each step is (the next doctype, how this document reaches it[, label]):

  field:<f>               a link on this document
  rows:<table>.<f>        the links in one of this document's tables
  back:<f>                documents of the next doctype whose <f> names this one
  back_rows:<table>.<f>   documents of the next doctype with a row in their
                          <table> whose <f> names this one
  via:<own>=<theirs>      documents of the next doctype whose <theirs> is
                          this document's <own>

The steps are in the order the process takes them. Only documents that
exist, are not cancelled and the user may read are shown; making the next
document stays with the buttons each form already has.
"""

STEPS = {
    # ── recruitment ───────────────────────────────────────────────────
    "Staffing Plan": (
        ("Job Requisition", "back:custom_staffing_plan"),
        ("Job Opening", "back:staffing_plan"),
    ),
    "Job Requisition": (
        ("Job Opening", "back:job_requisition"),
    ),
    "Job Opening": (
        ("Job Applicant", "back:job_title"),
        ("Interview Shortlist", "back:job_opening"),
        ("Interview", "back:job_opening"),
        ("Interview Report", "back:job_opening"),
    ),
    "Employee Referral": (
        ("Job Applicant", "back:employee_referral"),
    ),
    "Job Applicant": (
        ("Interview", "back:job_applicant"),
        ("Job Offer", "back:job_applicant"),
        ("Appointment Letter", "back:job_applicant"),
        ("Employee Onboarding", "back:job_applicant"),
        ("Graduate Trainee Program", "back:job_applicant"),
    ),
    "Interview Shortlist": (
        ("Interview", "rows:candidates.interview"),
        ("Interview Report", "via:job_opening=job_opening"),
    ),
    "Interview": (
        ("Interview Feedback", "back:interview"),
        ("Interview Report", "back_rows:candidates.interview"),
    ),
    "Interview Report": (
        ("Job Offer", "rows:candidates.job_offer"),
    ),
    "Job Offer": (
        ("Appointment Letter", "back:custom_job_offer"),
        ("Employee Onboarding", "back:job_offer"),
        ("Employee Transfer", "back:custom_job_offer"),
        ("Employee Position Change", "back:job_offer"),
    ),
    "Appointment Letter": (
        ("Employee Onboarding", "via:job_applicant=job_applicant"),
    ),
    # ── joining, probation and contracts ──────────────────────────────
    "Employee Onboarding": (
        ("Salary Structure Assignment", "field:custom_salary_structure_assignment"),
        ("Training Event", "rows:custom_trainings.training_event"),
        ("Onboarding Review", "back:onboarding"),
        ("Probation Evaluation", "back:onboarding"),
        ("Employee Contract", "back:onboarding"),
        ("Graduate Trainee Program", "back:employee_onboarding"),
    ),
    "Onboarding Review": (
        ("Probation Evaluation", "via:onboarding=onboarding"),
    ),
    "Probation Evaluation": (
        ("Employee Contract", "via:onboarding=onboarding"),
    ),
    "Employee Contract": (
        ("Employee Contract", "field:renewed_by", "Renewal"),
        ("Employee Position Change", "back:contract"),
        ("Employee Separation", "field:separation"),
    ),
    "Employee Position Change": (
        ("Employee Contract", "field:new_contract", "New Contract"),
        ("Salary Structure Assignment", "field:salary_structure_assignment"),
    ),
    # ── performance and talent ────────────────────────────────────────
    "Appraisal Plan": (
        ("Appraisal Cycle", "rows:quarters.appraisal_cycle"),
        ("Appraisal", "back:custom_plan"),
        ("Performance Review", "back:plan"),
        ("Talent Review", "back:appraisal_plan"),
    ),
    "Appraisal Cycle": (
        ("Appraisal", "back:appraisal_cycle"),
        ("Performance Review", "back:appraisal_cycle"),
        ("Talent Review", "back:appraisal_cycle"),
    ),
    "Appraisal": (
        ("Performance Review", "field:custom_performance_review"),
        ("Performance Improvement Plan", "back:appraisal"),
        ("Talent Placement", "back:appraisal"),
    ),
    "Performance Review": (
        ("Employee Position Change", "rows:employees.position_change"),
        ("Performance Improvement Plan", "rows:employees.improvement_plan"),
    ),
    "Performance Improvement Plan": (
        ("Disciplinary Case", "back:performance_review"),
    ),
    "Talent Review": (
        ("Talent Placement", "back:talent_review"),
        ("Talent Program", "back:talent_review"),
    ),
    "Talent Placement": (
        ("Talent Program", "field:development_plan"),
        ("Training Requisition", "rows:themes.training_requisition"),
        ("Succession Position", "back_rows:candidates.placement"),
    ),
    "Talent Program": (
        ("Training Requisition", "field:training_requisition"),
        ("Training Event", "rows:trainings.training_event"),
        ("Employee Position Change", "back:talent_program"),
        ("Job Requisition", "back:custom_talent_program"),
    ),
    "Succession Position": (
        ("Talent Program", "rows:candidates.development_plan"),
        ("Training Requisition", "rows:candidates.training_requisition"),
        ("Employee Position Change", "back:succession_position"),
        ("Job Requisition", "back:custom_succession_position"),
        ("Job Opening", "field:job_opening"),
    ),
    "Graduate Trainee Program": (
        ("Employee Onboarding", "field:employee_onboarding"),
        ("Appraisal", "rows:milestones.appraisal"),
        ("Talent Placement", "field:placement"),
        ("Employee Separation", "field:separation"),
    ),
    # ── training ──────────────────────────────────────────────────────
    "Training Needs Form": (
        ("Training Requisition", "field:requisition"),
    ),
    "Training Requisition": (
        ("Training Needs Assessment", "field:assessment"),
        ("Training Event", "field:training_event"),
    ),
    "Training Needs Assessment": (
        ("Training Calendar", "field:calendar"),
    ),
    "Training Calendar": (
        ("Monthly Training Schedule", "back:training_calendar"),
    ),
    "Monthly Training Schedule": (
        ("Training Event", "back:custom_schedule"),
    ),
    "Training Event": (
        ("Training Feedback", "back:training_event"),
        ("Training Result", "back:training_event"),
    ),
    # ── leave ─────────────────────────────────────────────────────────
    "Annual Leave Plan": (
        ("Leave Application", "back:custom_plan"),
        ("Leave Plan Change", "back:plan"),
    ),
    "Leave Application": (
        ("Leave Advance", "field:custom_leave_advance"),
        ("Employee Advance", "field:custom_advance"),
        ("Allowance Request", "back:leave_application"),
        ("Leave Encashment", "back:custom_leave_application"),
    ),
    "Leave Advance": (
        ("Leave Advance Processing", "field:processing"),
        ("Journal Entry", "field:journal_entry"),
    ),
    "Leave Advance Processing": (
        ("Leave Advance", "rows:employees.leave_advance"),
        ("Journal Entry", "field:journal_entry"),
    ),
    "Leave Encashment": (
        ("Additional Salary", "field:additional_salary"),
    ),
    "Compensatory Leave Request": (
        ("Leave Allocation", "field:leave_allocation"),
    ),
    # ── advances, loans, allowances, penalties and output pay ─────────
    "Salary Advance Request": (
        ("Salary Advance Processing", "back_rows:employees.request"),
        ("Employee Advance", "back:custom_salary_advance_request"),
    ),
    "Salary Advance Processing": (
        ("Employee Advance", "rows:employees.employee_advance"),
        ("Journal Entry", "field:journal_entry"),
    ),
    "Employee Advance": (
        ("Additional Salary", "rows:custom_recoveries.additional_salary", "Recoveries"),
    ),
    "Employee Loan": (
        ("Journal Entry", "field:disbursement_entry", "Disbursement"),
        ("Additional Salary", "rows:repayments.additional_salary", "Repayments"),
        ("Journal Entry", "field:write_off_entry", "Write-off"),
    ),
    "Employee Penalty": (
        ("Additional Salary", "rows:repayments.additional_salary", "Deductions"),
    ),
    "Allowance Request": (
        ("Employee Advance", "field:advance"),
        ("Journal Entry", "field:journal_entry"),
        ("Additional Salary", "rows:lines.additional_salary"),
    ),
    "Shift Allowance": (
        ("Additional Salary", "field:additional_salary"),
    ),
    "Daily Production Report": (
        ("Output Pay Run", "field:output_pay_run"),
    ),
    "Output Pay Run": (
        ("Additional Salary", "rows:employees.additional_salary"),
    ),
    # ── exits ─────────────────────────────────────────────────────────
    "Employee Separation": (
        ("Exit Interview", "field:custom_exit_interview"),
        ("Clearance Form", "field:custom_clearance"),
        ("Full and Final Statement", "field:custom_settlement"),
    ),
    "Exit Interview": (
        ("Clearance Form", "via:custom_separation=separation"),
    ),
    "Clearance Form": (
        ("Full and Final Statement", "back:custom_clearance"),
    ),
    "Full and Final Statement": (
        ("Additional Salary", "field:custom_additional_salary"),
    ),
    # ── employee relations ────────────────────────────────────────────
    "Disciplinary Case": (
        ("Employee Suspension", "field:employee_suspension"),
        ("Employee Separation", "field:separation"),
        ("Employee Penalty", "back:disciplinary_case"),
        ("Training Needs Form", "field:training_need"),
    ),
    "Safety Incident": (
        ("Leave Application", "field:sick_leave", "Sick Leave"),
        ("Employee Separation", "field:separation"),
    ),
    # ── attendance ────────────────────────────────────────────────────
    "Attendance Request": (
        ("Attendance", "back:attendance_request"),
    ),
    "Off Duty Request": (
        ("Attendance", "field:attendance"),
    ),
    "Late Arrival Notice": (
        ("Attendance", "field:attendance"),
    ),
    "Shift Request": (
        ("Shift Assignment", "back:shift_request"),
    ),
}

KINDS = ("field", "rows", "back", "back_rows", "via")
# the most names one step returns; more open as a filtered list
LIMIT = 50


def parse(relation):
    """(kind, parts) of a step's relation: field -> (f,), rows and
    back_rows -> (table, f), back -> (f,), via -> (own, theirs)."""
    kind, _sep, spec = (relation or "").partition(":")
    if kind not in KINDS or not spec:
        raise ValueError("not a relation: %r" % relation)
    if kind in ("rows", "back_rows"):
        table, _dot, field = spec.partition(".")
        if not (table and field):
            raise ValueError("a table and a field: %r" % relation)
        return kind, (table, field)
    if kind == "via":
        own, _eq, theirs = spec.partition("=")
        if not (own and theirs):
            raise ValueError("own=theirs: %r" % relation)
        return kind, (own, theirs)
    return kind, (spec,)


def label_of(step):
    """What the button says: the step's own label, else the next doctype."""
    return step[2] if len(step) > 2 and step[2] else step[0]


def unique(values):
    """The values once each, in their order, blanks left out."""
    seen, out = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
