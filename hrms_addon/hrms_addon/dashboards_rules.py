# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The desk home's dashboards: a tab for each HR module, and what is on it.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_home_dashboards.py checks it without a bench. dashboards.py
reads the site for it, and public/js/hrms_addon_home.js draws the tabs.
Luuka, 27 Oct 2026, of the ERPNext desk's tab of dashboards for each module:
"create such dashboards for every module be smart", "but for HR specific".

THE TABS

Overview, the home as it was, then a tab for each HR module in the order of
an employee's time with the company (home_rules.MODULES): People,
Recruitment, Attendance, Leave, Payroll, Loans, Expenses, Performance,
Training, Relations and Tenure, the exit last. Each has its figures across
the top, what needs attention in it, its charts and lists, and the reports a
decision is made from.

WHO HAS WHICH

A tab is on a desk only for the roles it is for (TABS: HR's and
management's, and Payroll, Loans and Expenses the payroll's too), where
Theme Settings show it, and where the user may read the documents it is
about. A figure, a chart or a report on documents they may not read is left
out, and a tab left with nothing is not there. Money is shown only to
MONEY_ROLES, and only as a company's or a plant's total: no tab shows
anybody's own pay.

MOST FIGURES ARE DECLARED, NOT WRITTEN

A count or a sum, a breakdown, six months of something or a list of what is
due is declared here (FIGURES, GROUPS, MONTHLY, LISTS) and read by one reader
for each kind in dashboards.py. Their filters may name the day (dates()):
"{today}", "{yesterday}", "{tomorrow}", "{week}" and "{in14}" and "{in30}"
ahead, "{ago7}" and "{ago30}" and "{since90}" back, "{month}" and
"{month_end}", "{year}", and "{cycle}", the first day of the pay period
today is in (the 26th). "company": True narrows one to the user's company.
What needs more than that is dashboards.py's own (CARDS, PANELS).

A day past which something is late is written as "between" EVER and
yesterday, not "<" today: Frappe reads an empty date as the year 1 for "<",
and would count everything with no date as late.

WHAT NEEDS ATTENTION

Each check (ATTENTION) counts what waits for a decision, or is late, in one
module, as the list it opens shows it. A module's tab lists its own; the
overview lists every tab's, and the tab bar says how many each tab has, in
the colour of the most pressing.
"""

import calendar
import datetime

# the same roles as home_panels_rules (scripts/verify_home_dashboards.py holds them equal)
HR_ROLES = ("HR Manager", "HR User", "System Manager")
# the company's management: the read-only management view and the two who sign for the company
EXECUTIVE_ROLES = ("Executive Director", "General Manager", "Management Viewer")
PAYROLL_ROLES = ("HR Manager", "Payroll Officer", "System Manager")
# money as a plant's or the company's total, never a person's
MONEY_ROLES = ("HR Manager", "Payroll Officer", "System Manager", "Executive Director", "General Manager")
PEOPLE_ROLES = HR_ROLES + EXECUTIVE_ROLES
# the tabs about money paid to people: HR's, the payroll's and management's
PAID_ROLES = tuple(dict.fromkeys(HR_ROLES + PAYROLL_ROLES + EXECUTIVE_ROLES))

COUNT, MONEY, HOURS, PERCENT = "count", "money", "hours", "percent"
WIDE, NORMAL = "wide", "normal"
OVERDUE, TODAY, SOON, LATER, NONE, GOOD = "overdue", "today", "soon", "later", "none", "good"
# the most pressing first
SEVERITY = (OVERDUE, TODAY, SOON, LATER, NONE, GOOD)
# how many rows a list or a breakdown shows
SHOWN = 6
# how long a part's figures are kept for a user before they are read again
CACHE_SECONDS = 300
OVERVIEW = "overview"
# where a panel of the overview goes: across the top, in place of a section, in the rows under what waits
TOP, SECTIONS, ROW = "top", "sections", "row"
# Payroll Readiness is on the overview, on top, from the 18th to the 25th: the week before the pay period closes
TOP_FROM, TOP_TO = 18, 25
HR_VIEW = "hr"
# the first day a "between" reaches back to (the docstring says why)
EVER = "2000-01-01"

# ── What each module's documents say ─────────────────────────────────
STAFF = ("Active", "Suspended")
CONTRACT_UNDECIDED = ("Active", "Expiring Soon", "Expired")
DECIDED_PROBATION = ("Confirmed", "Not Confirmed")
APPLYING = ("Open", "Replied", "Hold", "Shortlisted")
OFFER_LIVE = "Awaiting Response"
# Attendance that is a day at work, and an approved Overtime Request's hours
PRESENT = ("Present", "Work From Home", "Half Day")
OVERTIME_WAITING = ("Requested", "Authorised")
OVERTIME_COUNTED = ("Costed", "Sent to Payroll")
OFF_DUTY_WAITING = ("Pending Supervisor", "Pending Section Manager", "Pending HR Manager")
UNPLACED_PUNCHES = ("Failed", "Unknown Employee")
# leave: the application's own workflow status (custom_leave_status), the plan's and the change's
LEAVE_WAITING = ("Pending Supervisor", "Pending HOD", "Pending HR Officer")
PLAN_WAITING = ("Pending HOD", "Pending HR Officer")
PLAN_CHANGE_WAITING = ("Pending Supervisor", "Pending HOD")
# a Leave Encashment approved still waits for HR to send it to Accounts
ENCASHMENT_WAITING = ("Pending Supervisor", "Pending HR", "Pending General Manager", "Pending Executive Director",
                      "Approved", "Pending Accounts")
# every approval workflow of loans, advances, penalties, claims and allowances names its waiting states "Pending ..."
PENDING = ["like", "Pending%"]
GONE = ("Rejected", "Cancelled")
# performance
PIP_OPEN = ("Draft", "Agreed", "In Progress")
REVIEW_WAITING = ("Pending General Manager", "Pending Executive Director")
# training
REQUISITION_OPEN = ("Submitted", "In Assessment")
ASSESSMENT_WAITING = ("Pending HR Manager", "Pending General Manager")
# relations: the open stages of a disciplinary case, and of a grievance by its workflow state (its status says
# Resolved both while the employee has still to accept and once it is closed)
CASE_OPEN = ("Under Investigation", "Charge Issued", "Hearing Scheduled")
GRIEVANCE_OPEN = ("Open", "Under Review", "Resolved", "Appealed")
SUSPENSION_WAITING = ("Pending HR Manager", "Pending General Manager")
SUSPENDED = "In Progress"
# tenure
SETTLEMENT_WAITING = "Pending Payroll"
ONBOARDING_OPEN = ("Pending", "In Process")

# ── The tabs ──────────────────────────────────────────────────────────
# Each module's tab: what it is called, its picture, the roles it is for, the documents that make it the module
# it is (a tab is offered only to someone who may read one of them), the module pages whose Dashboard button opens
# it, the module its heading opens, its figures, its panels, its reports and the pages beside them.
TABS = (
    {
        "key": "people", "title": "People", "icon": "employees", "roles": PEOPLE_ROLES,
        "anchors": ("Employee",), "workspaces": ("HR Setup",), "opens": "HR Setup",
        "cards": ("headcount", "joined_month", "left_month", "contracts_ending"),
        "panels": ("attention", "movement", "departments", "plants_headcount", "employment_types", "data_health"),
        "reports": ("Monthly Manpower and Headcount", "Employee Analytics", "Document Expiry", "Contract Expiry Status"),
        "pages": (),
    },
    {
        "key": "recruitment", "title": "Recruitment", "icon": "recruitment", "roles": PEOPLE_ROLES,
        "anchors": ("Job Opening", "Job Applicant", "Job Requisition"), "workspaces": ("Recruitment",),
        "opens": "Recruitment",
        "cards": ("vacancies", "requisitions_waiting", "applicants", "offers_out"),
        "panels": ("attention", "recruitment", "applications_trend", "applicant_sources"),
        "reports": ("Applicant Screening", "Time to Hire", "Time to Fill", "Interview Pass Rate", "Interviewer Calibration",
                    "Recruitment Analytics"),
        "pages": (),
    },
    {
        "key": "attendance", "title": "Attendance", "icon": "attendance", "roles": PEOPLE_ROLES,
        "anchors": ("Attendance", "Employee Checkin"), "workspaces": ("Shift & Attendance",), "opens": "Shift & Attendance",
        "cards": ("present_today", "absent_today", "overtime_hours", "overtime_waiting"),
        "panels": ("attention", "plants", "attendance_trend", "late_by_department", "overtime_by_plant"),
        "reports": ("Monthly Attendance Sheet", "Shift Attendance", "Employees working on a holiday"),
        "pages": (("attendance-board", "Attendance Board"),),
    },
    {
        "key": "leave", "title": "Leave", "icon": "leave", "roles": PEOPLE_ROLES,
        "anchors": ("Leave Application",), "workspaces": ("Leaves",), "opens": "Leaves",
        "cards": ("on_leave_today", "leave_waiting", "leave_starting", "leave_days_month"),
        "panels": ("attention", "leave_trend", "leave_types", "leave_coming", "leave_waiting_list"),
        "reports": ("Employee Leave Balance", "Employee Leave Balance Summary", "Leave Schedule", "Leave Plan Adherence",
                    "Leave Accrual"),
        "pages": (("leave-overview", "Leave Overview"),),
    },
    {
        "key": "payroll", "title": "Payroll", "icon": "payroll", "roles": MONEY_ROLES,
        "anchors": ("Salary Slip", "Payroll Entry"), "workspaces": ("Payroll", "Tax & Benefits"), "opens": "Payroll",
        "cards": ("gross_pay", "net_pay", "paid_people", "slips_draft"),
        "panels": ("attention", "payroll", "payroll_trend", "output", "gross_by_department"),
        "reports": ("Salary Register", "Bank Remittance", "Salary Payments Based On Payment Mode"),
        "pages": (),
    },
    {
        "key": "loans", "title": "Loans", "icon": "loans", "roles": PAID_ROLES,
        "anchors": ("Employee Loan", "Salary Advance Request", "Employee Advance"), "workspaces": ("Loans",),
        "opens": "Loans",
        "cards": ("loans_running", "loans_owed", "loans_waiting", "advances_active"),
        "panels": ("attention", "lending_trend", "loan_types", "loans_waiting_list"),
        "reports": ("Loan Register", "Loan Statement", "Advance Payment Report", "Employee Advance Summary"),
        "pages": (),
    },
    {
        "key": "expenses", "title": "Expenses", "icon": "expenses", "roles": PAID_ROLES,
        "anchors": ("Expense Claim", "Allowance Request"), "workspaces": ("Expenses",), "opens": "Expenses",
        "cards": ("claims_waiting", "claimed_month", "allowances_waiting", "allowances_month"),
        "panels": ("attention", "claims_trend", "claim_occasions", "claims_waiting_list"),
        "reports": (),
        "pages": (),
    },
    {
        "key": "performance", "title": "Performance", "icon": "performance", "roles": PEOPLE_ROLES,
        "anchors": ("Appraisal",), "workspaces": ("Performance",), "opens": "Performance",
        "cards": ("appraisals_open", "appraisals_done", "average_score", "pips_open"),
        "panels": ("attention", "appraisal_steps", "rating_bands", "score_by_department", "nine_box", "pips_due"),
        "reports": ("Appraisal Results", "Performance Analytics", "Nine-Box Distribution", "Succession Coverage",
                    "Top Talent and Flight Risk", "Appraisal Overview"),
        "pages": (("talent-board", "Talent Board"),),
    },
    {
        # on Frappe HR's Tenure page, whose Dashboard button opens the Tenure tab
        "key": "training", "title": "Training", "icon": "training", "roles": PEOPLE_ROLES,
        "anchors": ("Training Event", "Training Requisition"), "workspaces": (), "opens": "Tenure",
        "cards": ("trainings_month", "trainings_held", "requisitions_open", "evaluation_score"),
        "panels": ("attention", "training_trend", "trainings_coming", "training_types"),
        "reports": ("Training Report", "Programme Effectiveness", "Development Plan Tracker"),
        "pages": (("hr-calendar", "HR Calendar"),),
    },
    {
        # discipline, grievances and safety, on the Tenure page too
        "key": "relations", "title": "Relations", "icon": "relations", "roles": PEOPLE_ROLES,
        "anchors": ("Disciplinary Case", "Employee Grievance"), "workspaces": (), "opens": "Tenure",
        "cards": ("grievances_open", "cases_open", "suspended_now", "incidents_month"),
        "panels": ("attention", "relations_trend", "case_stages", "grievance_types", "hearings"),
        "reports": (),
        "pages": (),
    },
    {
        "key": "tenure", "title": "Tenure", "icon": "tenure", "roles": PEOPLE_ROLES,
        "anchors": ("Employee Separation", "Employee Onboarding"), "workspaces": ("Tenure",), "opens": "Tenure",
        "cards": ("onboarding", "probations_due", "leaving", "settlements"),
        "panels": ("attention", "deadlines", "exits_trend", "exit_reasons", "onboarding_list"),
        "reports": ("Serving Notice", "Contract Expiry Status", "Employee Exits"),
        "pages": (),
    },
)
TAB_KEYS = tuple(tab["key"] for tab in TABS)
TAB_TITLES = dict({OVERVIEW: "Overview"}, **{tab["key"]: tab["title"] for tab in TABS})
# each tab's switch in Theme Settings
SWITCHES = tuple("dash_" + key for key in TAB_KEYS)

# The doctype each report is about: a report is offered to those Frappe lets open it, or, where that cannot be
# said, to those who may read its doctype.
REPORT_DOCTYPES = {
    "Monthly Manpower and Headcount": "Employee",
    "Employee Analytics": "Employee",
    "Recruitment Analytics": "Staffing Plan",
    "Employee Exits": "Exit Interview",
    "Document Expiry": "Employee",
    "Contract Expiry Status": "Employee Contract",
    "Applicant Screening": "Job Applicant",
    "Time to Hire": "Job Offer",
    "Time to Fill": "Job Requisition",
    "Interview Pass Rate": "Interview",
    "Interviewer Calibration": "Interview Feedback",
    "Monthly Attendance Sheet": "Attendance",
    "Shift Attendance": "Attendance",
    "Employees working on a holiday": "Attendance",
    "Employee Leave Balance": "Employee",
    "Employee Leave Balance Summary": "Employee",
    "Leave Schedule": "Annual Leave Plan",
    "Leave Plan Adherence": "Annual Leave Plan",
    "Leave Accrual": "Leave Application",
    "Salary Register": "Salary Slip",
    "Bank Remittance": "Payroll Entry",
    "Salary Payments Based On Payment Mode": "Salary Slip",
    "Loan Register": "Employee Loan",
    "Loan Statement": "Employee Loan",
    "Advance Payment Report": "Salary Advance Processing",
    "Employee Advance Summary": "Employee Advance",
    "Appraisal Results": "Performance Review",
    "Performance Analytics": "Appraisal",
    "Nine-Box Distribution": "Talent Placement",
    "Succession Coverage": "Succession Position",
    "Top Talent and Flight Risk": "Talent Placement",
    "Appraisal Overview": "Appraisal",
    "Training Report": "Training Event",
    "Programme Effectiveness": "Talent Program",
    "Development Plan Tracker": "Talent Program",
    "Serving Notice": "Employee Separation",
}

# ── Figures, declared ─────────────────────────────────────────────────
# figure: {"label", "kind", "icon", "doctype", "function" (COUNT or SUM), "field" (for SUM), "filters", "company",
# "note" (said under it), "late" (filters added to count how many of it are late, said instead of the note),
# "late_words", "tone", "quiet" (the tone where it is none at all), "money" (shown only to MONEY_ROLES)}
FIGURES = {
    # people
    "headcount": {
        "label": "Active Employees", "kind": COUNT, "icon": "employees", "doctype": "Employee", "function": "COUNT",
        "filters": {"status": ["in", list(STAFF)]}, "company": True, "note": "On the staff today, the suspended too",
    },
    "joined_month": {
        "label": "Joined This Month", "kind": COUNT, "icon": "movement", "doctype": "Employee", "function": "COUNT",
        "filters": {"date_of_joining": ["between", ["{month}", "{today}"]]}, "company": True, "note": "Since the 1st",
        "tone": "green",
    },
    "left_month": {
        "label": "Left This Month", "kind": COUNT, "icon": "tenure", "doctype": "Employee", "function": "COUNT",
        "filters": {"relieving_date": ["between", ["{month}", "{today}"]]}, "company": True, "note": "Since the 1st",
        "tone": "rose", "quiet": "green",
    },
    "contracts_ending": {
        "label": "Contracts Ending", "kind": COUNT, "icon": "contracts", "doctype": "Employee Contract",
        "function": "COUNT",
        "filters": {"docstatus": 1, "status": ["in", list(CONTRACT_UNDECIDED)], "end_date": ["between", ["{today}", "{in30}"]]},
        "company": True, "note": "In the next 30 days", "tone": "amber", "quiet": "green",
    },
    # recruitment
    "vacancies": {
        "label": "Open Vacancies", "kind": COUNT, "icon": "recruitment", "doctype": "Job Opening", "function": "COUNT",
        "filters": {"status": "Open"}, "company": True,
        "soon": {"closes_on": ["between", ["{today}", "{week}"]]}, "soon_words": "closing this week",
        "note": "None closing this week",
    },
    "requisitions_waiting": {
        "label": "Requisitions Waiting", "kind": COUNT, "icon": "contracts", "doctype": "Job Requisition",
        "function": "COUNT", "filters": {"status": "Pending"}, "company": True, "note": "For approval",
        "tone": "amber", "quiet": "green",
    },
    "applicants": {
        "label": "Applicants in Process", "kind": COUNT, "icon": "employees", "doctype": "Job Applicant",
        "function": "COUNT", "filters": {"status": ["in", list(APPLYING)]}, "note": "Applied, replied to or shortlisted",
        "tone": "blue",
    },
    "offers_out": {
        "label": "Offers Awaiting Reply", "kind": COUNT, "icon": "waiting", "doctype": "Job Offer", "function": "COUNT",
        "filters": {"status": OFFER_LIVE, "docstatus": ["<", 2]}, "company": True,
        "late": {"offer_date": ["between", [EVER, "{ago7}"]]}, "late_words": "unanswered for a week",
        "note": "None unanswered for a week", "tone": "amber", "quiet": "green",
    },
    # attendance
    "absent_today": {
        "label": "Absent Today", "kind": COUNT, "icon": "attendance", "doctype": "Attendance", "function": "COUNT",
        "filters": {"docstatus": 1, "attendance_date": "{today}", "status": "Absent"}, "company": True,
        "note": "Marked absent", "tone": "rose", "quiet": "green",
    },
    "overtime_hours": {
        "label": "Overtime This Period", "kind": HOURS, "icon": "clock", "doctype": "Overtime Request",
        "function": "SUM", "field": "total_hours",
        "filters": {"status": ["in", list(OVERTIME_COUNTED)], "overtime_date": ["between", ["{cycle}", "{today}"]]},
        "note": "Approved since the 26th", "tone": "blue",
    },
    "overtime_waiting": {
        "label": "Overtime Waiting", "kind": COUNT, "icon": "waiting", "doctype": "Overtime Request",
        "function": "COUNT", "filters": {"docstatus": 0, "status": ["in", list(OVERTIME_WAITING)]},
        "note": "For approval", "tone": "amber", "quiet": "green",
    },
    # leave
    "on_leave_today": {
        "label": "On Leave Today", "kind": COUNT, "icon": "on_leave", "doctype": "Leave Application",
        "function": "COUNT",
        "filters": {"docstatus": 1, "status": "Approved", "from_date": ["<=", "{today}"], "to_date": [">=", "{today}"]},
        "company": True, "note": "On approved leave", "tone": "blue",
    },
    "leave_waiting": {
        "label": "Waiting for Approval", "kind": COUNT, "icon": "waiting", "doctype": "Leave Application",
        "function": "COUNT", "filters": {"docstatus": 0, "custom_leave_status": ["in", list(LEAVE_WAITING)]},
        "company": True, "late": {"from_date": ["<=", "{today}"]}, "late_words": "already started",
        "note": "None started yet", "tone": "amber", "quiet": "green",
    },
    "leave_starting": {
        "label": "Starting This Week", "kind": COUNT, "icon": "calendar", "doctype": "Leave Application",
        "function": "COUNT",
        "filters": {"docstatus": 1, "status": "Approved", "from_date": ["between", ["{tomorrow}", "{week}"]]},
        "company": True, "note": "Approved, in the next 7 days",
    },
    "leave_days_month": {
        "label": "Leave Days This Month", "kind": COUNT, "icon": "leave", "doctype": "Leave Application",
        "function": "SUM", "field": "total_leave_days",
        "filters": {"docstatus": 1, "status": "Approved", "from_date": ["between", ["{month}", "{month_end}"]]},
        "company": True, "note": "Approved, starting this month",
    },
    # payroll
    "slips_draft": {
        "label": "Slips in Draft", "kind": COUNT, "icon": "payroll", "doctype": "Salary Slip", "function": "COUNT",
        "filters": {"docstatus": 0}, "company": True, "note": "Not submitted yet", "tone": "amber", "quiet": "green",
    },
    # loans
    "loans_running": {
        "label": "Loans Running", "kind": COUNT, "icon": "loans", "doctype": "Employee Loan", "function": "COUNT",
        "filters": {"docstatus": 1, "status": "Running"}, "company": True, "note": "Being recovered from pay",
    },
    "loans_owed": {
        "label": "Owed on Loans", "kind": MONEY, "icon": "money", "doctype": "Employee Loan", "function": "SUM",
        "field": "outstanding", "filters": {"docstatus": 1, "status": "Running"}, "company": True,
        "note": "Still to be recovered", "tone": "green", "money": True,
    },
    "loans_waiting": {
        "label": "Loans Waiting", "kind": COUNT, "icon": "waiting", "doctype": "Employee Loan", "function": "COUNT",
        "filters": {"docstatus": 0, "approval_status": PENDING}, "company": True, "note": "For approval",
        "tone": "amber", "quiet": "green",
    },
    "advances_active": {
        "label": "Salary Advances Active", "kind": COUNT, "icon": "money", "doctype": "Salary Advance Request",
        "function": "COUNT", "filters": {"docstatus": 1, "status": "Active"}, "company": True,
        "note": "Paid each month", "tone": "blue",
    },
    # expenses
    "claims_waiting": {
        "label": "Claims Waiting", "kind": COUNT, "icon": "waiting", "doctype": "Expense Claim", "function": "COUNT",
        "filters": {"docstatus": 0, "custom_claim_status": PENDING}, "company": True, "note": "For approval",
        "tone": "amber", "quiet": "green",
    },
    "claimed_month": {
        "label": "Claimed This Month", "kind": MONEY, "icon": "expenses", "doctype": "Expense Claim",
        "function": "SUM", "field": "base_total_claimed_amount",
        "filters": {"docstatus": ["<", 2], "custom_claim_status": ["not in", list(GONE)],
                    "posting_date": ["between", ["{month}", "{today}"]]},
        "company": True, "note": "Since the 1st, not rejected", "tone": "blue", "money": True,
    },
    "allowances_waiting": {
        "label": "Allowances Waiting", "kind": COUNT, "icon": "waiting", "doctype": "Allowance Request",
        "function": "COUNT", "filters": {"docstatus": 0, "status": PENDING}, "company": True, "note": "For approval",
        "tone": "amber", "quiet": "green",
    },
    "allowances_month": {
        "label": "Allowances This Month", "kind": MONEY, "icon": "money", "doctype": "Allowance Request",
        "function": "SUM", "field": "total",
        "filters": {"docstatus": ["<", 2], "status": ["not in", list(GONE)], "posting_date": ["between", ["{month}", "{today}"]]},
        "company": True, "note": "Since the 1st, not rejected", "tone": "blue", "money": True,
    },
    # performance
    "appraisals_open": {
        "label": "Appraisals Under Way", "kind": COUNT, "icon": "performance", "doctype": "Appraisal",
        "function": "COUNT", "filters": {"docstatus": 0}, "company": True,
        "late": {"end_date": ["between", [EVER, "{yesterday}"]]}, "late_words": "past their cycle's end",
        "note": "None past their cycle's end",
    },
    "appraisals_done": {
        "label": "Completed This Year", "kind": COUNT, "icon": "done", "doctype": "Appraisal", "function": "COUNT",
        "filters": {"docstatus": 1, "end_date": [">=", "{year}"]}, "company": True, "note": "Signed off",
        "tone": "green",
    },
    "pips_open": {
        "label": "On an Improvement Plan", "kind": COUNT, "icon": "performance",
        "doctype": "Performance Improvement Plan", "function": "COUNT",
        "filters": {"docstatus": 0, "status": ["in", list(PIP_OPEN)]}, "note": "Plans not yet closed",
        "tone": "amber", "quiet": "green",
    },
    # training
    "trainings_month": {
        "label": "Trainings This Month", "kind": COUNT, "icon": "training", "doctype": "Training Event",
        "function": "COUNT",
        "filters": {"event_status": ["!=", "Cancelled"], "start_time": ["between", ["{month}", "{month_end}"]]},
        "company": True, "note": "Held or booked", "tone": "blue",
    },
    "trainings_held": {
        "label": "Held This Year", "kind": COUNT, "icon": "done", "doctype": "Training Event", "function": "COUNT",
        "filters": {"docstatus": 1, "start_time": [">=", "{year}"]}, "company": True, "note": "Since 1 January",
        "tone": "green",
    },
    "requisitions_open": {
        "label": "Requisitions Open", "kind": COUNT, "icon": "contracts", "doctype": "Training Requisition",
        "function": "COUNT", "filters": {"status": ["in", list(REQUISITION_OPEN)]},
        "note": "Waiting to be scheduled", "tone": "amber", "quiet": "green",
    },
    # relations
    "grievances_open": {
        "label": "Open Grievances", "kind": COUNT, "icon": "relations", "doctype": "Employee Grievance",
        "function": "COUNT", "filters": {"docstatus": 0, "workflow_state": ["in", list(GRIEVANCE_OPEN)]},
        "late": {"custom_overdue": 1}, "late_words": "past their timeline", "note": "None past their timeline",
    },
    "cases_open": {
        "label": "Disciplinary Cases Open", "kind": COUNT, "icon": "relations", "doctype": "Disciplinary Case",
        "function": "COUNT", "filters": {"docstatus": 0, "status": ["in", list(CASE_OPEN)]}, "company": True,
        "note": "Investigated, charged or at a hearing", "tone": "amber", "quiet": "green",
    },
    "suspended_now": {
        "label": "Suspended Now", "kind": COUNT, "icon": "deadlines", "doctype": "Employee Suspension",
        "function": "COUNT", "filters": {"docstatus": 1, "status": SUSPENDED}, "company": True,
        "note": "Back on their report-back day", "tone": "rose", "quiet": "green",
    },
    "incidents_month": {
        "label": "Safety Incidents This Month", "kind": COUNT, "icon": "attention", "doctype": "Safety Incident",
        "function": "COUNT", "filters": {"docstatus": 1, "incident_on": [">=", "{month}"]}, "company": True,
        "note": "Since the 1st", "tone": "amber", "quiet": "green",
    },
    # tenure
    "onboarding": {
        "label": "Being Onboarded", "kind": COUNT, "icon": "employees", "doctype": "Employee Onboarding",
        "function": "COUNT", "filters": {"docstatus": ["<", 2], "boarding_status": ["in", list(ONBOARDING_OPEN)]},
        "company": True, "note": "Activities still open", "tone": "blue",
    },
    "leaving": {
        "label": "Leaving in 30 Days", "kind": COUNT, "icon": "tenure", "doctype": "Employee Separation",
        "function": "COUNT", "filters": {"docstatus": 1, "custom_relieving_date": ["between", ["{today}", "{in30}"]]},
        "company": True, "note": "Their last day is coming", "tone": "amber", "quiet": "green",
    },
    "settlements": {
        "label": "Settlements Waiting", "kind": COUNT, "icon": "money", "doctype": "Full and Final Statement",
        "function": "COUNT", "filters": {"docstatus": 0, "custom_settlement_status": SETTLEMENT_WAITING},
        "company": True, "note": "For the payroll", "tone": "rose", "quiet": "green",
    },
}

# The figures dashboards.py works out itself: (label, kind, the doctypes it needs, picture, money)
CARDS = {
    "present_today": ("Present Today", COUNT, ("Attendance",), "on_site", False),
    "gross_pay": ("Gross Pay", MONEY, ("Salary Slip",), "payroll", True),
    "net_pay": ("Net Pay", MONEY, ("Salary Slip",), "money", True),
    "paid_people": ("Employees Paid", COUNT, ("Salary Slip",), "employees", False),
    "average_score": ("Average Score This Year", PERCENT, ("Appraisal",), "performance", False),
    "evaluation_score": ("Average Evaluation", PERCENT, ("Training Event",), "training", False),
    "probations_due": ("Probations Ending", COUNT, ("Employee",), "deadlines", False),
}
for _key, _spec in FIGURES.items():
    CARDS[_key] = (_spec["label"], _spec["kind"], (_spec["doctype"],), _spec["icon"], bool(_spec.get("money")))

# ── Breakdowns, declared ──────────────────────────────────────────────
# breakdown: {"title", "icon", "doctype", "by" (the field), "function", "field", "filters", "company", "draw" ("bars"
# or "donut"), "money", "hours", "none" (what a blank is called), "bands" ({value: band}), "empty", "note"}
GROUPS = {
    "departments": {
        "title": "Headcount by Department", "icon": "employees", "doctype": "Employee", "by": "department",
        "function": "COUNT", "filters": {"status": ["in", list(STAFF)]}, "company": True, "draw": "bars",
        "none": "No department", "empty": "Nobody on the staff", "note": "Active employees",
    },
    "plants_headcount": {
        "title": "Headcount by Plant", "icon": "plants", "doctype": "Employee", "by": "branch", "function": "COUNT",
        "filters": {"status": ["in", list(STAFF)]}, "company": True, "draw": "donut", "none": "No plant",
        "empty": "Nobody on the staff", "note": "Active employees",
    },
    "employment_types": {
        "title": "By Employment Type", "icon": "contracts", "doctype": "Employee", "by": "employment_type",
        "function": "COUNT", "filters": {"status": ["in", list(STAFF)]}, "company": True, "draw": "donut",
        "none": "Not set", "empty": "Nobody on the staff", "note": "Active employees",
    },
    "applicant_sources": {
        "title": "Where Applicants Came From", "icon": "ring", "doctype": "Job Applicant", "by": "source",
        "function": "COUNT", "filters": {"creation": [">=", "{since90}"]}, "draw": "donut", "none": "Not given",
        "empty": "No applicants in the last 90 days", "note": "Last 90 days",
    },
    "late_by_department": {
        "title": "Late Arrivals This Month", "icon": "clock", "doctype": "Attendance", "by": "department",
        "function": "COUNT", "filters": {"docstatus": 1, "late_entry": 1, "attendance_date": [">=", "{month}"]},
        "company": True, "draw": "bars", "none": "No department", "empty": "Nobody came late this month",
        "note": "Days late, by department",
    },
    "overtime_by_plant": {
        "title": "Overtime This Period by Plant", "icon": "plants", "doctype": "Overtime Request", "by": "branch",
        "function": "SUM", "field": "total_hours",
        "filters": {"status": ["in", list(OVERTIME_COUNTED)], "overtime_date": ["between", ["{cycle}", "{today}"]]},
        "draw": "bars", "hours": 1, "none": "No plant", "empty": "No overtime approved this period",
        "note": "Approved hours",
    },
    "leave_types": {
        "title": "Leave Taken This Year", "icon": "ring", "doctype": "Leave Application", "by": "leave_type",
        "function": "SUM", "field": "total_leave_days",
        "filters": {"docstatus": 1, "status": "Approved", "from_date": [">=", "{year}"]}, "company": True,
        "draw": "donut", "none": "No type", "empty": "No leave taken this year", "note": "Days, by type",
    },
    "loan_types": {
        "title": "Owed by Loan Type", "icon": "ring", "doctype": "Employee Loan", "by": "loan_type",
        "function": "SUM", "field": "outstanding", "filters": {"docstatus": 1, "status": "Running"},
        "company": True, "draw": "donut", "money": 1, "none": "Not set", "empty": "No loans running",
        "note": "Still to be recovered",
    },
    "claim_occasions": {
        "title": "Claims This Year by Occasion", "icon": "ring", "doctype": "Expense Claim",
        "by": "custom_occasion", "function": "COUNT",
        "filters": {"docstatus": ["<", 2], "custom_claim_status": ["not in", list(GONE)], "posting_date": [">=", "{year}"]},
        "company": True, "draw": "donut", "none": "Not given", "empty": "No claims this year", "note": "How many",
    },
    "appraisal_steps": {
        "title": "Appraisals Under Way, by Step", "icon": "performance", "doctype": "Appraisal",
        "by": "custom_appraisal_status", "function": "COUNT", "filters": {"docstatus": 0}, "company": True,
        "draw": "bars", "none": "Draft", "empty": "No appraisal under way", "note": "Who each waits for",
    },
    "rating_bands": {
        "title": "Ratings This Year", "icon": "ring", "doctype": "Appraisal", "by": "custom_band",
        "function": "COUNT", "filters": {"docstatus": 1, "end_date": [">=", "{year}"]}, "company": True,
        "draw": "donut", "none": "No rating", "empty": "No appraisal completed this year", "note": "Completed appraisals",
    },
    "nine_box": {
        "title": "Nine-Box Placements", "icon": "performance", "doctype": "Talent Placement", "by": "box_name",
        "function": "COUNT", "filters": {"docstatus": 1}, "company": True, "draw": "bars", "none": "Not placed",
        "empty": "No placement finalised", "note": "Finalised placements",
        "bands": {"Star": "good", "High Performer": "good", "High Potential": "good", "Risk": "overdue"},
    },
    "training_types": {
        "title": "Trainings This Year by Type", "icon": "ring", "doctype": "Training Event", "by": "type",
        "function": "COUNT", "filters": {"docstatus": 1, "start_time": [">=", "{year}"]}, "company": True,
        "draw": "donut", "none": "Not set", "empty": "No training held this year", "note": "Held",
    },
    "case_stages": {
        "title": "Open Cases by Stage", "icon": "relations", "doctype": "Disciplinary Case", "by": "status",
        "function": "COUNT", "filters": {"docstatus": 0, "status": ["in", list(CASE_OPEN)]}, "company": True,
        "draw": "bars", "bands": {"Hearing Scheduled": "today"}, "empty": "No case open", "note": "How many at each stage",
    },
    "exit_reasons": {
        "title": "Why People Left This Year", "icon": "ring", "doctype": "Employee Separation", "by": "custom_reason",
        "function": "COUNT", "filters": {"docstatus": 1, "custom_relieving_date": [">=", "{year}"]}, "company": True,
        "draw": "donut", "none": "No reason given", "empty": "Nobody left this year", "note": "Separations",
    },
    "grievance_types": {
        "title": "Grievances This Year by Type", "icon": "ring", "doctype": "Employee Grievance",
        "by": "grievance_type", "function": "COUNT", "filters": {"docstatus": ["<", 2], "date": [">=", "{year}"]},
        "draw": "donut", "none": "No type", "empty": "No grievance raised this year", "note": "Raised",
    },
}

# ── Six months of something, declared ─────────────────────────────────
# months: {"title", "icon", "series": [{"key", "label", "band", "doctype", "day" (its date field), "function",
# "field", "filters"}], "company", "money", "hours", "note"}
MONTHLY = {
    "applications_trend": {
        "title": "Applications and Hires by Month", "icon": "trend",
        "series": (
            {"key": "applied", "label": "Applied", "band": "soon", "doctype": "Job Applicant", "day": "creation",
             "function": "COUNT", "filters": {}},
            {"key": "hired", "label": "Joined", "band": "good", "doctype": "Employee", "day": "date_of_joining",
             "function": "COUNT", "filters": {}},
        ),
        "company": False, "note": "Last 6 months",
    },
    "attendance_trend": {
        "title": "Attendance by Month", "icon": "trend",
        "series": (
            {"key": "present", "label": "Present", "band": "good", "doctype": "Attendance", "day": "attendance_date",
             "function": "COUNT", "filters": {"docstatus": 1, "status": ["in", list(PRESENT)]}},
            {"key": "absent", "label": "Absent", "band": "overdue", "doctype": "Attendance", "day": "attendance_date",
             "function": "COUNT", "filters": {"docstatus": 1, "status": "Absent"}},
            {"key": "leave", "label": "On leave", "band": "soon", "doctype": "Attendance", "day": "attendance_date",
             "function": "COUNT", "filters": {"docstatus": 1, "status": "On Leave"}},
        ),
        "company": True, "note": "Days marked",
    },
    "leave_trend": {
        "title": "Leave Days by Month", "icon": "trend",
        "series": (
            {"key": "days", "label": "Days", "band": "soon", "doctype": "Leave Application", "day": "from_date",
             "function": "SUM", "field": "total_leave_days", "filters": {"docstatus": 1, "status": "Approved"}},
        ),
        "company": True, "note": "Approved leave, by the day it starts",
    },
    "payroll_trend": {
        "title": "Gross and Net Pay by Month", "icon": "trend",
        "series": (
            {"key": "gross", "label": "Gross", "band": "soon", "doctype": "Salary Slip", "day": "end_date",
             "function": "SUM", "field": "base_gross_pay", "filters": {"docstatus": 1}},
            {"key": "net", "label": "Net", "band": "good", "doctype": "Salary Slip", "day": "end_date",
             "function": "SUM", "field": "base_net_pay", "filters": {"docstatus": 1}},
        ),
        "company": True, "money": 1, "note": "Submitted slips, by the period's last day",
    },
    "lending_trend": {
        "title": "Lent by Month", "icon": "trend",
        "series": (
            {"key": "loans", "label": "Loans", "band": "soon", "doctype": "Employee Loan", "day": "disbursed_on",
             "function": "SUM", "field": "approved_amount", "filters": {"docstatus": 1, "status": ["not in", list(GONE)]}},
            {"key": "advances", "label": "Salary advances", "band": "today", "doctype": "Salary Advance Processing",
             "day": "processing_date", "function": "SUM", "field": "total_amount", "filters": {"docstatus": 1}},
        ),
        "company": True, "money": 1, "note": "Paid out",
    },
    "claims_trend": {
        "title": "Claims and Allowances by Month", "icon": "trend",
        "series": (
            {"key": "claims", "label": "Claims", "band": "soon", "doctype": "Expense Claim", "day": "posting_date",
             "function": "SUM", "field": "base_total_claimed_amount",
             "filters": {"docstatus": ["<", 2], "custom_claim_status": ["not in", list(GONE)]}},
            {"key": "allowances", "label": "Allowances", "band": "today", "doctype": "Allowance Request",
             "day": "posting_date", "function": "SUM", "field": "total",
             "filters": {"docstatus": ["<", 2], "status": ["not in", list(GONE)]}},
        ),
        "company": True, "money": 1, "note": "Not rejected",
    },
    "training_trend": {
        "title": "Trainings Held by Month", "icon": "trend",
        "series": (
            {"key": "held", "label": "Held", "band": "good", "doctype": "Training Event", "day": "start_time",
             "function": "COUNT", "filters": {"docstatus": 1}},
        ),
        "company": True, "note": "Last 6 months",
    },
    "relations_trend": {
        "title": "Cases by Month", "icon": "trend",
        "series": (
            {"key": "grievances", "label": "Grievances", "band": "soon", "doctype": "Employee Grievance", "day": "date",
             "function": "COUNT", "filters": {"docstatus": ["<", 2]}},
            {"key": "discipline", "label": "Disciplinary", "band": "overdue", "doctype": "Disciplinary Case",
             "day": "incident_date", "function": "COUNT", "filters": {"docstatus": ["<", 2]}},
            {"key": "safety", "label": "Safety incidents", "band": "today", "doctype": "Safety Incident",
             "day": "incident_on", "function": "COUNT", "filters": {"docstatus": 1}},
        ),
        "company": False, "note": "Raised, by the day it happened",
    },
    "exits_trend": {
        "title": "Exits by Month", "icon": "trend",
        "series": (
            {"key": "exits", "label": "Last days", "band": "overdue", "doctype": "Employee Separation",
             "day": "custom_relieving_date", "function": "COUNT", "filters": {"docstatus": 1}},
        ),
        "company": True, "note": "Separations, by the last day",
    },
}

# ── Lists, declared ───────────────────────────────────────────────────
# list: {"title", "icon", "doctype", "filters", "company", "fields", "title_field", and either "due" (the date it is
# due by, the soonest first) or "opened" (the date it was opened, the longest open first), "empty"}
LISTS = {
    "leave_coming": {
        "title": "Leave Coming Up", "icon": "calendar", "doctype": "Leave Application",
        "filters": {"docstatus": 1, "status": "Approved", "from_date": ["between", ["{today}", "{in14}"]]},
        "company": True, "fields": ("name", "employee_name", "from_date"), "title_field": "employee_name",
        "due": "from_date", "empty": "Nobody goes on leave in the next two weeks",
    },
    "leave_waiting_list": {
        "title": "Leave Waiting for Approval", "icon": "waiting", "doctype": "Leave Application",
        "filters": {"docstatus": 0, "custom_leave_status": ["in", list(LEAVE_WAITING)]}, "company": True,
        "fields": ("name", "employee_name", "from_date"), "title_field": "employee_name", "due": "from_date",
        "empty": "No leave waits for approval",
    },
    "loans_waiting_list": {
        "title": "Loans Waiting for Approval", "icon": "waiting", "doctype": "Employee Loan",
        "filters": {"docstatus": 0, "approval_status": PENDING}, "company": True,
        "fields": ("name", "employee_name", "posting_date"), "title_field": "employee_name", "opened": "posting_date",
        "empty": "No loan waits for approval",
    },
    "claims_waiting_list": {
        "title": "Claims Waiting for Approval", "icon": "waiting", "doctype": "Expense Claim",
        "filters": {"docstatus": 0, "custom_claim_status": PENDING}, "company": True,
        "fields": ("name", "employee_name", "posting_date"), "title_field": "employee_name", "opened": "posting_date",
        "empty": "No claim waits for approval",
    },
    "pips_due": {
        "title": "Improvement Plans Due", "icon": "deadlines", "doctype": "Performance Improvement Plan",
        "filters": {"docstatus": 0, "status": ["in", list(PIP_OPEN)]},
        "fields": ("name", "employee_name", "end_date"), "title_field": "employee_name", "due": "end_date",
        "empty": "No improvement plan open",
    },
    "trainings_coming": {
        "title": "Trainings Coming Up", "icon": "calendar", "doctype": "Training Event",
        "filters": {"docstatus": 0, "event_status": "Scheduled", "start_time": [">=", "{today}"]}, "company": True,
        "fields": ("name", "event_name", "start_time"), "title_field": "event_name", "due": "start_time",
        "empty": "No training booked ahead",
    },
    "hearings": {
        "title": "Hearings Coming Up", "icon": "calendar", "doctype": "Disciplinary Case",
        "filters": {"docstatus": 0, "status": "Hearing Scheduled"}, "company": True,
        "fields": ("name", "employee_name", "hearing_on"), "title_field": "employee_name", "due": "hearing_on",
        "empty": "No hearing scheduled",
    },
    "onboarding_list": {
        "title": "Onboarding Under Way", "icon": "employees", "doctype": "Employee Onboarding",
        "filters": {"docstatus": ["<", 2], "boarding_status": ["in", list(ONBOARDING_OPEN)]}, "company": True,
        "fields": ("name", "employee_name", "date_of_joining"), "title_field": "employee_name",
        "due": "date_of_joining", "empty": "Nobody is being onboarded",
    },
}

# ── The panels: those dashboards.py works out itself, then the declared ──
# panel: (title, size, the doctypes it is read from (any one of the sets will do; none means it decides for itself),
# picture, the roles it is for (None: everybody the tab is for), money)
PANELS = {
    "attention": ("Needs Attention", NORMAL, (), "attention", None, False),
    # the panels of the desk home before the tabs (home_panels.py reads them)
    "payroll": ("Payroll Readiness", WIDE, (("Payroll Entry",), ("Salary Slip",)), "payroll", PAYROLL_ROLES, False),
    "plants": ("Plants at a Glance", WIDE, (("Employee",),), "plants", PEOPLE_ROLES, False),
    "output": ("Output and Labour Cost", WIDE, (("Daily Production Report",), ("Overtime Request",)), "output",
               PAYROLL_ROLES + EXECUTIVE_ROLES, False),
    "movement": ("Workforce Movement", WIDE, (("Employee",),), "movement", PEOPLE_ROLES, False),
    "deadlines": ("Deadlines", NORMAL, (("Employee",),), "deadlines", HR_ROLES, False),
    "recruitment": ("Recruitment Pipeline", NORMAL, (("Job Opening",),), "recruitment", PEOPLE_ROLES, False),
    "data_health": ("Data Health", NORMAL, (("Employee",),), "data_health", HR_ROLES, False),
    # worked out here
    "gross_by_department": ("Gross Pay by Department", NORMAL, (("Salary Slip",),), "payroll", MONEY_ROLES, True),
    "score_by_department": ("Average Score by Department", NORMAL, (("Appraisal",),), "performance", None, False),
}
for _key, _spec in GROUPS.items():
    PANELS[_key] = (_spec["title"], NORMAL, ((_spec["doctype"],),), _spec["icon"], None, bool(_spec.get("money")))
for _key, _spec in MONTHLY.items():
    PANELS[_key] = (_spec["title"], WIDE, tuple((series["doctype"],) for series in _spec["series"]), _spec["icon"],
                    None, bool(_spec.get("money")))
for _key, _spec in LISTS.items():
    PANELS[_key] = (_spec["title"], NORMAL, ((_spec["doctype"],),), _spec["icon"], None, False)

# The overview's panels, where each goes, and the tab it belongs to, whose switch takes it off the overview too:
# (key, place, tab). Payroll Readiness on top in its week, Plants at a Glance in Today's place on HR's desk, what
# needs attention across the tabs and the deadlines in the rows.
OVERVIEW_PANELS = (("payroll", TOP, "payroll"), ("plants", SECTIONS, "attendance"), ("attention", ROW, None),
                   ("deadlines", ROW, "tenure"))

# ── What needs attention ──────────────────────────────────────────────
# (key, what one is called, what several are, the doctype counted, its tab, band), the most pressing band first and
# the most pressing first within each: the order they are listed in (scripts/verify_home_dashboards.py keeps it)
ATTENTION = (
    ("punches_unplaced", "Punch the clock could not place", "Punches the clock could not place", "Attendance Device Log",
     "attendance", OVERDUE),
    ("leave_started_waiting", "Leave started before it was approved", "Leaves started before they were approved",
     "Leave Application", "leave", OVERDUE),
    ("entries_failed", "Payroll entry that failed", "Payroll entries that failed", "Payroll Entry", "payroll", OVERDUE),
    ("appraisals_overdue", "Appraisal past its cycle's end", "Appraisals past their cycle's end", "Appraisal",
     "performance", OVERDUE),
    ("pips_overdue", "Improvement plan past its end date", "Improvement plans past their end date",
     "Performance Improvement Plan", "performance", OVERDUE),
    ("grievances_overdue", "Grievance past its timeline", "Grievances past their timeline", "Employee Grievance",
     "relations", OVERDUE),
    ("documents_expired", "Employee document expired", "Employee documents expired", "Employee", "people", OVERDUE),
    ("clearances_late", "Clearance not signed off by the last day", "Clearances not signed off by the last day",
     "Clearance Form", "tenure", OVERDUE),
    ("requisitions_waiting", "Job requisition waiting for approval", "Job requisitions waiting for approval",
     "Job Requisition", "recruitment", TODAY),
    ("interviews_unscored", "Interview waiting for the panel's feedback", "Interviews waiting for the panel's feedback",
     "Interview", "recruitment", TODAY),
    ("data_changes_waiting", "Change of details waiting for HR", "Changes of details waiting for HR",
     "Employee Data Change Request", "people", TODAY),
    ("overtime_waiting", "Overtime request waiting for approval", "Overtime requests waiting for approval",
     "Overtime Request", "attendance", TODAY),
    ("off_duty_waiting", "Off duty request waiting for approval", "Off duty requests waiting for approval",
     "Off Duty Request", "attendance", TODAY),
    ("passes_not_returned", "Gate pass not returned", "Gate passes not returned", "Gate Pass", "attendance", TODAY),
    ("leave_waiting", "Leave waiting for approval", "Leaves waiting for approval", "Leave Application", "leave", TODAY),
    ("slips_draft", "Salary slip of a past period in draft", "Salary slips of a past period in draft", "Salary Slip",
     "payroll", TODAY),
    ("entries_open", "Payroll entry not submitted", "Payroll entries not submitted", "Payroll Entry", "payroll", TODAY),
    ("loans_waiting", "Loan waiting for approval", "Loans waiting for approval", "Employee Loan", "loans", TODAY),
    ("advance_requests_waiting", "Salary advance request waiting", "Salary advance requests waiting",
     "Salary Advance Request", "loans", TODAY),
    ("claims_waiting", "Expense claim waiting for approval", "Expense claims waiting for approval", "Expense Claim",
     "expenses", TODAY),
    ("allowances_waiting", "Allowance request waiting for approval", "Allowance requests waiting for approval",
     "Allowance Request", "expenses", TODAY),
    ("hearings_week", "Disciplinary hearing this week", "Disciplinary hearings this week", "Disciplinary Case",
     "relations", TODAY),
    ("suspensions_waiting", "Suspension waiting for approval", "Suspensions waiting for approval",
     "Employee Suspension", "relations", TODAY),
    ("settlements_waiting", "Final settlement waiting for the payroll", "Final settlements waiting for the payroll",
     "Full and Final Statement", "tenure", TODAY),
    ("evaluations_due", "Probation evaluation due", "Probation evaluations due", "Probation Evaluation", "tenure",
     TODAY),
    ("openings_closing", "Job opening closing this week", "Job openings closing this week", "Job Opening",
     "recruitment", SOON),
    ("offers_unanswered", "Offer unanswered for a week", "Offers unanswered for a week", "Job Offer", "recruitment",
     SOON),
    ("attendance_requests", "Attendance request waiting", "Attendance requests waiting", "Attendance Request",
     "attendance", SOON),
    ("shift_requests", "Shift request waiting", "Shift requests waiting", "Shift Request", "attendance", SOON),
    ("late_notices", "Late arrival notice waiting", "Late arrival notices waiting", "Late Arrival Notice",
     "attendance", SOON),
    ("uploads_with_problems", "Attendance upload with rows not marked", "Attendance uploads with rows not marked",
     "Upload Attendance", "attendance", SOON),
    ("plans_waiting", "Annual leave plan waiting for approval", "Annual leave plans waiting for approval",
     "Annual Leave Plan", "leave", SOON),
    ("plan_changes_waiting", "Leave plan change waiting", "Leave plan changes waiting", "Leave Plan Change", "leave",
     SOON),
    ("leave_advances_waiting", "Leave advance waiting", "Leave advances waiting", "Leave Advance", "leave", SOON),
    ("encashments_waiting", "Leave encashment waiting", "Leave encashments waiting", "Leave Encashment", "leave", SOON),
    ("additional_draft", "Additional salary in draft", "Additional salaries in draft", "Additional Salary", "payroll",
     SOON),
    ("output_runs_draft", "Output pay run in draft", "Output pay runs in draft", "Output Pay Run", "payroll", SOON),
    ("advance_runs_draft", "Salary advance run not processed", "Salary advance runs not processed",
     "Salary Advance Processing", "loans", SOON),
    ("employee_advances_waiting", "Advance waiting for approval", "Advances waiting for approval", "Employee Advance",
     "loans", SOON),
    ("penalties_waiting", "Penalty waiting for a decision", "Penalties waiting for a decision", "Employee Penalty",
     "loans", SOON),
    ("reviews_waiting", "Performance review waiting for sign-off", "Performance reviews waiting for sign-off",
     "Performance Review", "performance", SOON),
    ("requisitions_to_assess", "Training requisition to assess", "Training requisitions to assess",
     "Training Requisition", "training", SOON),
    ("trainings_not_closed", "Training held but not closed", "Trainings held but not closed", "Training Event",
     "training", SOON),
    ("assessments_waiting", "Training needs assessment waiting", "Training needs assessments waiting",
     "Training Needs Assessment", "training", SOON),
    ("suspensions_ending", "Suspension ending this week", "Suspensions ending this week", "Employee Suspension",
     "relations", SOON),
    ("reviews_due", "Onboarding review due", "Onboarding reviews due", "Onboarding Review", "tenure", SOON),
    ("exit_interviews_waiting", "Exit interview waiting", "Exit interviews waiting", "Exit Interview", "tenure", SOON),
    ("position_changes_waiting", "Position change waiting for approval", "Position changes waiting for approval",
     "Employee Position Change", "tenure", SOON),
)
ATTENTION_DOCTYPE = {key: doctype for key, _one, _many, doctype, _tab, _band in ATTENTION}
ATTENTION_TAB = {key: tab for key, _one, _many, _doctype, tab, _band in ATTENTION}
# the checks dashboards.py counts itself
COUNTED = ("documents_expired", "pips_overdue")
# a check that opens a report rather than its doctype's list
ATTENTION_ROUTES = {"documents_expired": ["query-report", "Document Expiry"]}
# the checks narrowed to the user's company: those of doctypes that always carry one
ATTENTION_COMPANY = {
    "leave_started_waiting", "entries_failed", "appraisals_overdue", "requisitions_waiting", "leave_waiting",
    "slips_draft", "entries_open", "loans_waiting", "advance_requests_waiting", "claims_waiting", "allowances_waiting",
    "hearings_week", "suspensions_waiting", "settlements_waiting", "openings_closing", "offers_unanswered",
    "attendance_requests", "shift_requests", "late_notices", "uploads_with_problems", "plans_waiting",
    "encashments_waiting", "additional_draft", "output_runs_draft", "advance_runs_draft", "employee_advances_waiting",
    "penalties_waiting", "reviews_waiting", "trainings_not_closed", "suspensions_ending", "documents_expired",
    "exit_interviews_waiting",
}


def attention_filters(key, day_of, company=None):
    """What each check counts, as a list filter, on the day dates() gives, narrowed to the user's company where its
    doctype always carries one: the same filter opens the list."""
    filters = {
        "punches_unplaced": {"status": ["in", list(UNPLACED_PUNCHES)], "punch_time": [">=", "{ago30}"]},
        "leave_started_waiting": {"docstatus": 0, "custom_leave_status": ["in", list(LEAVE_WAITING)],
                                  "from_date": ["<=", "{today}"]},
        "entries_failed": {"status": "Failed"},
        "appraisals_overdue": {"docstatus": 0, "end_date": ["between", [EVER, "{yesterday}"]]},
        "grievances_overdue": {"docstatus": 0, "custom_overdue": 1},
        "requisitions_waiting": {"status": "Pending"},
        "interviews_unscored": {"docstatus": 0, "status": "Under Review"},
        "data_changes_waiting": {"docstatus": 1, "status": "Pending HR"},
        "overtime_waiting": {"docstatus": 0, "status": ["in", list(OVERTIME_WAITING)]},
        "off_duty_waiting": {"docstatus": 0, "status": ["in", list(OFF_DUTY_WAITING)]},
        "passes_not_returned": {"status": "Not Returned", "pass_date": [">=", "{ago30}"]},
        "leave_waiting": {"docstatus": 0, "custom_leave_status": ["in", list(LEAVE_WAITING)], "from_date": [">", "{today}"]},
        "slips_draft": {"docstatus": 0, "end_date": ["between", [EVER, "{yesterday}"]]},
        "entries_open": {"docstatus": 0, "status": ["!=", "Failed"]},
        "loans_waiting": {"docstatus": 0, "approval_status": PENDING},
        "advance_requests_waiting": {"docstatus": 0, "approval_status": PENDING},
        "claims_waiting": {"docstatus": 0, "custom_claim_status": PENDING},
        "allowances_waiting": {"docstatus": 0, "status": PENDING},
        "hearings_week": {"docstatus": 0, "status": "Hearing Scheduled", "hearing_on": ["between", ["{today}", "{week}"]]},
        "suspensions_waiting": {"docstatus": 0, "status": ["in", list(SUSPENSION_WAITING)]},
        "settlements_waiting": {"docstatus": 0, "custom_settlement_status": SETTLEMENT_WAITING},
        "openings_closing": {"status": "Open", "closes_on": ["between", ["{today}", "{week}"]]},
        "offers_unanswered": {"docstatus": ["<", 2], "status": OFFER_LIVE, "offer_date": ["between", [EVER, "{ago7}"]]},
        "attendance_requests": {"docstatus": 0},
        "shift_requests": {"docstatus": 0, "status": "Draft"},
        "late_notices": {"docstatus": 0, "status": "Pending Supervisor"},
        "uploads_with_problems": {"status": "Done with Problems", "imported_on": [">=", "{ago30}"]},
        "plans_waiting": {"docstatus": 0, "status": ["in", list(PLAN_WAITING)]},
        "plan_changes_waiting": {"docstatus": 0, "approval_status": ["in", list(PLAN_CHANGE_WAITING)]},
        "leave_advances_waiting": {"docstatus": 0, "approval_status": "Pending Accounts Manager"},
        "encashments_waiting": {"docstatus": 0, "custom_encashment_status": ["in", list(ENCASHMENT_WAITING)]},
        "additional_draft": {"docstatus": 0},
        "output_runs_draft": {"docstatus": 0},
        "advance_runs_draft": {"docstatus": 0},
        "employee_advances_waiting": {"docstatus": 0, "custom_advance_status": PENDING},
        "penalties_waiting": {"docstatus": 0, "approval_status": PENDING},
        "reviews_waiting": {"docstatus": 0, "status": ["in", list(REVIEW_WAITING)]},
        "requisitions_to_assess": {"docstatus": 1, "status": "Submitted"},
        "trainings_not_closed": {"docstatus": 0, "event_status": "Scheduled", "end_time": ["between", [EVER, "{yesterday}"]]},
        "assessments_waiting": {"docstatus": 0, "status": ["in", list(ASSESSMENT_WAITING)]},
        "suspensions_ending": {"docstatus": 1, "status": SUSPENDED, "report_back_on": ["between", ["{today}", "{week}"]]},
        "clearances_late": {"docstatus": 0, "leaving_date": ["between", [EVER, "{yesterday}"]]},
        "evaluations_due": {"docstatus": 0, "end_of_probation": ["between", [EVER, "{week}"]]},
        "reviews_due": {"docstatus": 0, "due_date": ["between", [EVER, "{today}"]]},
        "exit_interviews_waiting": {"docstatus": 0, "custom_exit_status": PENDING},
        "position_changes_waiting": {"docstatus": 0, "status": PENDING},
        # counted by dashboards.py itself; these open the list they are drawn from
        "documents_expired": {"status": ["in", list(STAFF)]},
        "pips_overdue": {"docstatus": 0, "status": ["in", list(PIP_OPEN)]},
    }
    found = fill(filters[key], day_of)
    if company and key in ATTENTION_COMPANY:
        found["company"] = company
    return found


def attention_in(tab, readable):
    """The checks shown on one module's tab, whose doctype the user may read."""
    readable = set(readable or ())
    return [key for key, *_rest in ATTENTION if ATTENTION_TAB[key] == tab and ATTENTION_DOCTYPE[key] in readable]


def attention_overview(tabs, readable):
    """The checks on the overview: those of every module tab the user has."""
    tabs = set(tabs or ())
    readable = set(readable or ())
    return [key for key, *_rest in ATTENTION if ATTENTION_TAB[key] in tabs and ATTENTION_DOCTYPE[key] in readable]


def attention_rows(counts, day_of, modules=False, company=None):
    """What needs attention, the most pressing first, as ATTENTION is declared: only what there is some of.
    counts: {key: how many}. Each row opens the list of them, or the report it is read in: {"key", "label", "value",
    "band", "route", "filters"}, and, on the overview (modules), the module it is in."""
    rows = []
    for key, one, many, doctype, tab, band in ATTENTION:
        value = int(_number((counts or {}).get(key)))
        if value <= 0:
            continue
        row = {"key": key, "label": one if value == 1 else many, "value": value, "band": band}
        if key in ATTENTION_ROUTES:
            row["route"] = list(ATTENTION_ROUTES[key])
        else:
            row.update(route=["List", doctype], filters=attention_filters(key, day_of, company))
        if modules:
            row["module"] = TAB_TITLES[tab]
        rows.append(row)
    return rows


def badges(rows):
    """How much needs attention on each tab, for the tab bar, from attention_rows' rows in any order:
    {tab: {"value": how many in all, "band": the most pressing}}."""
    out = {}
    for row in rows or ():
        tab = ATTENTION_TAB.get(row["key"])
        if not tab:
            continue
        found = out.setdefault(tab, {"value": 0, "band": row["band"]})
        found["value"] += row["value"]
        if SEVERITY.index(row["band"]) < SEVERITY.index(found["band"]):
            found["band"] = row["band"]
    return out


# ── Whose tabs ────────────────────────────────────────────────────────
def switched_on(stored):
    """Each tab's switch as on or off. stored: the settings as saved; a switch never saved is on, as its field's
    default says."""
    stored = stored or {}
    out = {}
    for switch in SWITCHES:
        value = stored.get(switch)
        if value is None or value == "":
            out[switch] = True
            continue
        try:
            out[switch] = bool(int(value))
        except (TypeError, ValueError):
            out[switch] = True
    return out


def money_for(roles):
    """Whether money is shown to the user at all."""
    return bool(set(roles or ()) & set(MONEY_ROLES))


def available(needs, readable):
    """Whether the user may read one of the sets of doctypes a part is read from."""
    readable = set(readable or ())
    return not needs or any(all(doctype in readable for doctype in group) for group in needs)


def panel_for(key, roles, readable):
    """Whether a panel is on a user's tab: theirs by role, money only for those who see it, and read from what
    they may read."""
    _title, _size, needs, _icon, allowed, money = PANELS[key]
    roles = set(roles or ())
    if allowed is not None and not roles & set(allowed):
        return False
    if money and not money_for(roles):
        return False
    return available(needs, readable)


def card_for(key, roles, readable):
    """Whether a figure is on a user's tab: money only for those who see it, read from what they may read."""
    _label, _kind, needs, _icon, money = CARDS[key]
    if money and not money_for(roles):
        return False
    return all(doctype in set(readable or ()) for doctype in needs)


def card_frame(key):
    """A figure of a tab before it is read."""
    label, kind, _needs, icon, _money = CARDS[key]
    return {"key": key, "label": label, "kind": kind, "icon": icon, "frame": 1}


def panel_frame(key):
    """A panel of a tab before it is read."""
    title, size, _needs, icon, _allowed, _money = PANELS[key]
    return {"key": key, "title": title, "size": size, "icon": icon}


def tabs_for(roles, readable, switches=None, reports=None, pages=()):
    """The tabs of a user's desk: Overview, then each module's tab that is theirs. A module's tab is there only for
    the roles it is for, where the settings show it and something on it is theirs to read. Each: {"key", "title",
    "icon", "workspaces", "opens", "cards" (frames), "panels" (frames), "reports" [{"label", "route"}]}.

    reports: the reports the user may open, or None where that cannot be said, when a report is offered to
    whoever may read what it reports on. pages: the pages the user may open."""
    roles = set(roles or ())
    readable = set(readable or ())
    switches = switches if switches is not None else switched_on({})
    pages = set(pages or ())
    tabs = []
    for tab in TABS:
        if not roles & set(tab["roles"]) or not switches.get("dash_" + tab["key"], True):
            continue
        if not any(doctype in readable for doctype in tab["anchors"]):
            continue
        cards = [key for key in tab["cards"] if card_for(key, roles, readable)]
        panels = [key for key in tab["panels"] if key != "attention" and panel_for(key, roles, readable)]
        if not cards and not panels:
            continue
        if "attention" in tab["panels"] and attention_in(tab["key"], readable):
            panels.insert(0, "attention")
        offered = [{"label": name, "route": ["query-report", name]} for name in tab["reports"]
                   if (name in reports if reports is not None else REPORT_DOCTYPES.get(name) in readable)]
        offered += [{"label": label, "route": [page]} for page, label in tab["pages"] if page in pages]
        tabs.append({
            "key": tab["key"], "title": tab["title"], "icon": tab["icon"], "workspaces": list(tab["workspaces"]),
            "opens": tab["opens"], "cards": [card_frame(key) for key in cards],
            "panels": [panel_frame(key) for key in panels], "reports": offered,
        })
    overview = {"key": OVERVIEW, "title": TAB_TITLES[OVERVIEW], "icon": "overview", "workspaces": [], "opens": None,
                "cards": [], "panels": [], "reports": []}
    return [overview] + tabs


def tab_of_workspace(tabs, workspace):
    """The tab a module page is the dashboard of, among a user's tabs."""
    for tab in tabs or ():
        if workspace in (tab.get("workspaces") or ()):
            return tab["key"]
    return None


def payroll_on_top(today):
    """Payroll Readiness sits on top of the overview from the 18th to the 25th."""
    return TOP_FROM <= today.day <= TOP_TO


def overview_places(roles, view, today, tabs, readable):
    """The overview's panels and where each goes: [{"key", "title", "icon", "place"}]. Payroll Readiness on top in
    its week, Plants at a Glance in Today's place on HR's desk, what needs attention across the user's tabs and the
    deadlines in the rows; management's Plants at a Glance in the rows too. tabs: the user's module tabs; a panel
    of a tab they do not have, or one switched off, is not on their overview either."""
    out = []
    for key, place, tab in OVERVIEW_PANELS:
        if tab and tab not in tabs:
            continue
        if key == "payroll" and not payroll_on_top(today):
            continue
        if key == "plants" and view != HR_VIEW:
            place = ROW
        if key == "attention":
            if not attention_overview(tabs, readable):
                continue
        elif not panel_for(key, roles, readable):
            continue
        out.append(dict(panel_frame(key), place=place))
    return out


# ── Dates ─────────────────────────────────────────────────────────────
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
TREND_MONTHS = 6


def dates(today, cycle_start=None):
    """What the placeholders in the filters stand for, on a given day. cycle_start: the first day of the pay period
    today is in (attendance_rules.cycle_window), the 1st of the month where none is given."""
    day = datetime.timedelta(days=1)
    first = today.replace(day=1)
    last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    return {
        "{today}": str(today),
        "{yesterday}": str(today - day),
        "{tomorrow}": str(today + day),
        "{week}": str(today + 7 * day),
        "{in14}": str(today + 14 * day),
        "{in30}": str(today + 30 * day),
        "{ago7}": str(today - 7 * day),
        "{ago30}": str(today - 30 * day),
        "{since90}": str(today - 90 * day),
        "{month}": str(first),
        "{month_end}": str(last),
        "{year}": str(today.replace(month=1, day=1)),
        "{cycle}": str(cycle_start or first),
    }


def fill(value, day_of):
    """The filters with their placeholders put in: day_of is dates() for the day."""
    if isinstance(value, str):
        return day_of.get(value, value)
    if isinstance(value, dict):
        return {key: fill(item, day_of) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [fill(item, day_of) for item in value]
    return value


def months(today, count=TREND_MONTHS):
    """The last `count` months to today, the oldest first, this one running to today: [{"label", "from", "to"}]."""
    year, month = today.year, today.month
    out = []
    for _ in range(count):
        start = datetime.date(year, month, 1)
        end = min(datetime.date(year, month, calendar.monthrange(year, month)[1]), today)
        out.append({"label": MONTHS[month - 1], "from": str(start), "to": str(end)})
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return list(reversed(out))


def by_month(rows, months_, day="day", value="total"):
    """Each month's total of rows that are one per day or moment ({day: date, value: x})."""
    sums = [0.0] * len(months_)
    for row in rows or ():
        on = _day(row.get(day))
        if not on:
            continue
        for index, month in enumerate(months_):
            if month["from"] <= str(on) <= month["to"]:
                sums[index] += _number(row.get(value))
                break
    return [round(total, 2) for total in sums]


def change(now, before):
    """How a figure moved against the one before: {"percent", "direction"}, or None where there is nothing before
    to compare it with."""
    now, before = _number(now), _number(before)
    if not before:
        return None
    percent = round(100.0 * (now - before) / abs(before))
    return {"percent": abs(percent), "direction": "up" if percent > 0 else "down" if percent < 0 else "same"}


# ── The panels' rows ──────────────────────────────────────────────────
def card(key, value, note="", tone="navy", change_=None, route=None, filters=None, options=None, currency=None):
    """A figure, read: {"key", "label", "kind", "icon", "value", "note", "tone", "change", "route", "filters",
    "options", "currency"}."""
    label, kind, _needs, icon, _money = CARDS[key]
    out = {"key": key, "label": label, "kind": kind, "icon": icon, "value": _number(value), "note": note, "tone": tone}
    if change_:
        out["change"] = change_
    if route:
        out["route"] = list(route)
    if filters:
        out["filters"] = dict(filters)
    if options:
        out["options"] = dict(options)
    if currency and kind == MONEY:
        out["currency"] = currency
    return out


def ranked(rows, label, value, shown=SHOWN):
    """The largest first, as bars: [{"label", "value", "key"}], where key is the value the bars are of."""
    ordered = sorted((row for row in rows or () if _number(row.get(value)) > 0),
                     key=lambda row: (-_number(row.get(value)), str(row.get(label) or "")))
    return [{"label": row.get(label) or "", "value": round(_number(row.get(value)), 2), "key": row.get("key")}
            for row in ordered[:shown]]


def slices(rows, label, value, shown=5, other="Everything else"):
    """The largest parts of a whole as they are, and the rest as one, for a ring: [{"label", "value", "key"}], the
    largest first, the rest marked "rest". A part of nothing is left out."""
    ordered = sorted((row for row in rows or () if _number(row.get(value)) > 0),
                     key=lambda row: (-_number(row.get(value)), str(row.get(label) or "")))
    out = [{"label": row.get(label) or "", "value": round(_number(row.get(value)), 2), "key": row.get("key")}
           for row in ordered[:shown]]
    rest = sum(_number(row.get(value)) for row in ordered[shown:])
    if rest > 0:
        out.append({"label": other, "value": round(rest, 2), "key": None, "rest": 1})
    return out


def due_rows(rows, today, doctype, title, due, when, urgency, shown=SHOWN):
    """Open documents the soonest due first, those without a date last: rows the home lists, each opening its
    document. title and due name the fields; when and urgency say how far off a day is (alerts_rules)."""
    ordered = sorted(rows or (), key=lambda row: (_day(row.get(due)) or datetime.date.max, str(row.get("name") or "")))
    out = []
    for row in ordered[:shown]:
        on = _day(row.get(due))
        out.append({"title": row.get(title) or row.get("name") or "", "doctype": doctype, "docname": row.get("name"),
                    "when": when(on, today) if on else "no date set", "band": urgency(on, today) if on else NONE})
    return out


def open_for(rows, today, doctype, title, opened, shown=SHOWN):
    """Open documents, the longest open first: rows the home lists. Open more than a week is late; more than two
    days, due today."""
    ordered = sorted(rows or (), key=lambda row: (_day(row.get(opened)) or today, str(row.get("name") or "")))
    out = []
    for row in ordered[:shown]:
        age = max(0, (today - (_day(row.get(opened)) or today)).days)
        out.append({"title": row.get(title) or row.get("name") or "", "doctype": doctype, "docname": row.get("name"),
                    "when": "opened today" if age == 0 else "open for %d %s" % (age, "day" if age == 1 else "days"),
                    "band": OVERDUE if age > 7 else TODAY if age > 2 else SOON})
    return out


def average(rows, by, total="total", how_many="count", shown=SHOWN, none="Not set"):
    """Each value of `by` with its average, the highest first, from rows of a sum and a count for each:
    [{"label", "value", "key"}]."""
    out = []
    for row in rows or ():
        count = _number(row.get(how_many))
        if count > 0:
            out.append({"label": row.get(by) or none, "value": round(_number(row.get(total)) / count, 1),
                        "key": row.get(by)})
    out.sort(key=lambda row: (-row["value"], str(row["label"])))
    return out[:shown]


def open_probation(row, decided=DECIDED_PROBATION):
    """Whether an employee's probation is still to be decided."""
    return (row.get("custom_probation_status") or "") not in decided


def period_note(end):
    """What is said under the pay of the latest period: the day it ended."""
    end = _day(end)
    return "Period ending %s %s" % (end.day, MONTHS[end.month - 1]) if end else "No period paid yet"


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
