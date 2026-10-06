# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Where everything this app adds is reached from in the desk.

No Frappe import, like the other *_rules.py modules, so scripts/verify_navigation.py
exercises them without a bench.

Frappe HR's own workspaces are the place people already work, so each thing
is put beside the standard documents it belongs with — Recruitment,
Tenure and HR Setup — rather than on a page of its own that has to be
remembered. Two lists carry it:

  CARDS    the cards on the workspace page: a card is a Card Break in the
           Workspace's `links` plus a `card` block in its `content`
  SIDEBAR  the entries in the left sidebar (a Workspace Sidebar's `items`),
           either at the top or under one of its sections

Both are added to what Frappe HR ships, never in place of it: an upstream
update rewrites those records and navigation.py puts these back on the next
migrate, so anything of theirs that moved or was renamed survives.
"""

import json
import os

DOCTYPE, REPORT, WORKSPACE = "DocType", "Report", "Workspace"
PAGE = "Page"
# A page of ours belongs to this app, not to Frappe HR's. That is not
# cosmetic: remove_orphan_entities() looks for the file behind a record in
# the app the record NAMES, and deletes it where there is none. Putting
# Frappe HR's name on our records would send it looking in their app and
# find nothing. Which grid the tile lands on is settled by the Desktop
# Icon's parent_icon, not by this.
OWN_APP, MODULE = "hrms_addon", "HRMS Addon"

# Pages this app makes of its own, where Frappe HR has none to add to.
# Lending is the only one: everything else Luuka do has a page already.
# A page is made once and then left alone — what goes on it is merged in
# like any other page, so a card someone adds by hand survives a migrate.
#
# A page is three records, not one. The Workspace is the page, the
# Workspace Sidebar is its left-hand list, and the Desktop Icon is what
# puts it on the launcher grid: get_desktop_icons() reads those rows and
# nothing else, so a page without one exists, opens by name, and appears
# on no grid at all (apps_screen.py has the whole story).
# All three are shipped as files — hrms_addon/workspace/<name>/,
# workspace_sidebar/ and desktop_icon/ — because Frappe imports those
# folders on every migrate and sweeps away any such record that has no
# file behind it. The sweep runs BEFORE after_migrate, so a record only a
# hook of ours creates is deleted at the start of the next deploy.
#   label, icon (a desk icon name), sequence_id (where it sits: 8 falls
#   between Performance and Payroll, among the money pages), sections (the
#   sidebar headers it starts with), under (the app tile it sits in)
PAGES = (
    {"label": "Loans", "icon": "loan", "sequence_id": 8.0, "sections": ("Reports", "Setup"),
     "under": "Frappe HR"},
)
PAGE_LABELS = tuple(page["label"] for page in PAGES)

# The HR home: the HR Overview page (page/hr_overview) has a launcher tile and
# a sidebar of its own, shipped as files (desktop_icon/hr_overview.json,
# workspace_sidebar/hr_overview.json), and no Workspace, so the page keeps its
# own address, /app/hr-overview. The tile opens the sidebar's first link, the
# page, and shows only to those the page's roles let in: a link tile is on
# the grid only while its sidebar has a link the user may open.
HOME = "HR Overview"

# Our tiles, for the desktops people have arranged themselves. Frappe shows a
# saved desktop (Desktop Layout) instead of the shared tiles, so a tile made
# after it was saved never appears on it unless it is added: (label, where)
OWN_TILES = ((HOME, "first"),) + tuple((label, "last") for label in PAGE_LABELS)

# the icon each standard sidebar section header carries
SECTION_ICONS = {"Reports": "notepad-text", "Setup": "database", "Settings": "settings"}

# workspace -> [(card, [(label, what it opens, kind)])]. A card that Frappe
# HR already has (Reports, Onboarding) is added to, not replaced.
CARDS = {
    "Recruitment": [
        ("Shortlisting", [
            ("Interview Shortlist", "Interview Shortlist", DOCTYPE),
            ("Interview Report", "Interview Report", DOCTYPE),
        ]),
        ("Score Sheet Setup", [
            ("Interview Criterion", "Interview Criterion", DOCTYPE),
            ("Interview Criteria Group", "Interview Criteria Group", DOCTYPE),
        ]),
        ("Candidate Lists", [
            ("Qualification Type", "Qualification Type", DOCTYPE),
            ("Examination Level", "Examination Level", DOCTYPE),
            ("District", "District", DOCTYPE),
            ("Relationship", "Relationship", DOCTYPE),
        ]),
        # how the applicants screen (cv_screening.py), how the panels score,
        # how each round goes, how long a hire and a requisition take
        # (interview_analytics_rules.py)
        ("Reports", [
            ("Applicant Screening", "Applicant Screening", REPORT),
            ("Interviewer Calibration", "Interviewer Calibration", REPORT),
            ("Interview Pass Rate", "Interview Pass Rate", REPORT),
            ("Time to Hire", "Time to Hire", REPORT),
            ("Time to Fill", "Time to Fill", REPORT),
        ]),
    ],
    "Tenure": [
        ("Probation and Contracts", [
            ("Onboarding Review", "Onboarding Review", DOCTYPE),
            ("Probation Evaluation", "Probation Evaluation", DOCTYPE),
            ("Employee Contract", "Employee Contract", DOCTYPE),
            ("Contract Expiry Status", "Contract Expiry Status", REPORT),
        ]),
        # promotions, changes of designation and salary reviews, and the
        # employee's own records (positions.py, employee_data.py)
        ("Position and Pay Changes", [
            ("Employee Position Change", "Employee Position Change", DOCTYPE),
            ("Employee Data Change Request", "Employee Data Change Request", DOCTYPE),
            ("Intern Placement", "Intern Placement", DOCTYPE),
        ]),
        # Employee relations and welfare: the disciplinary case (5.3), the
        # safety incident, and the two lists they are judged by. The
        # non-disciplinary concern is Frappe HR's own Employee Grievance,
        # already on their Grievance card (discipline.py)
        ("Discipline and Safety", [
            ("Disciplinary Case", "Disciplinary Case", DOCTYPE),
            ("Safety Incident", "Safety Incident", DOCTYPE),
            ("Misconduct Type", "Misconduct Type", DOCTYPE),
            ("Disciplinary Action Type", "Disciplinary Action Type", DOCTYPE),
        ]),
        # Frappe HR's Tenure page carries onboarding, grievances and
        # training but nothing about leaving, though their sidebar lists
        # the Employee Separation. Both exits run on their documents; the
        # clearance form is the one they do not have (exits.py)
        ("Leaving", [
            ("Employee Separation", "Employee Separation", DOCTYPE),
            ("Exit Interview", "Exit Interview", DOCTYPE),
            ("Clearance Form", "Clearance Form", DOCTYPE),
            ("Full and Final Statement", "Full and Final Statement", DOCTYPE),
        ]),
        ("Onboarding Setup", [
            ("Onboarding Settings", "Onboarding Settings", DOCTYPE),
            ("Tool of Work", "Tool of Work", DOCTYPE),
            ("Tool Provider", "Tool Provider", DOCTYPE),
            ("Probation Factor", "Probation Factor", DOCTYPE),
        ]),
        # Frappe HR's own Training card gains the steps before a session and
        # what is made of it after (training.py)
        ("Training", [
            ("Training Needs Form", "Training Needs Form", DOCTYPE),
            ("Training Requisition", "Training Requisition", DOCTYPE),
            ("Training Needs Assessment", "Training Needs Assessment", DOCTYPE),
            ("Training Calendar", "Training Calendar", DOCTYPE),
            ("Monthly Training Schedule", "Monthly Training Schedule", DOCTYPE),
            ("HR Calendar", "hr-calendar", PAGE),
            # what the evaluations add up to, downloaded by HR (case 10)
            ("Training Report", "Training Report", REPORT),
            ("Training Evaluation Item", "Training Evaluation Item", DOCTYPE),
            ("Meeting Record", "Meeting Record", DOCTYPE),
        ]),
    ],
    # Frappe HR ships the Performance page with its Appraisal Overview chart
    # and nothing else — no cards, no links — so it reads as an empty page
    # until someone knows to use the sidebar. These are the documents the
    # appraisal round runs on, and what an appraisal ends in (positions.py).
    "Performance": [
        ("Appraisal", [
            ("Appraisal Cycle", "Appraisal Cycle", DOCTYPE),
            ("Appraisal", "Appraisal", DOCTYPE),
            ("Employee Performance Feedback", "Employee Performance Feedback", DOCTYPE),
            ("Goal", "Goal", DOCTYPE),
        ]),
        # Luuka's own round: the plan, the report to management and what
        # happens to anyone below the pass mark (appraisals.py, pips.py)
        ("The Appraisal Round", [
            ("Appraisal Plan", "Appraisal Plan", DOCTYPE),
            ("Performance Review", "Performance Review", DOCTYPE),
            # the results with what is to become of each employee, and the
            # review they go to management on (6 Oct 2026)
            ("Appraisal Results", "Appraisal Results", REPORT),
            ("Performance Improvement Plan", "Performance Improvement Plan", DOCTYPE),
        ]),
        ("After the Appraisal", [
            ("Employee Position Change", "Employee Position Change", DOCTYPE),
            ("Employee Promotion", "Employee Promotion", DOCTYPE),
        ]),
        # Talent management reads the appraisal and never re-enters it, so
        # it belongs on the page the appraisal is run from (talent.py).
        ("Talent Management", [
            ("Talent Board", "talent-board", PAGE),
            ("Talent Review", "Talent Review", DOCTYPE),
            ("Talent Placement", "Talent Placement", DOCTYPE),
            ("Talent Program", "Talent Program", DOCTYPE),
            ("Succession Position", "Succession Position", DOCTYPE),
            ("Graduate Trainee Program", "Graduate Trainee Program", DOCTYPE),
            ("Succession Coverage", "Succession Coverage", REPORT),
            ("Performance Analytics", "Performance Analytics", REPORT),
        ]),
        # what talent comes to, month by month and person by person (5 Oct 2026)
        ("Talent Reports", [
            ("Monthly Talent Report", "Monthly Talent Report", REPORT),
            ("Nine-Box Distribution", "Nine-Box Distribution", REPORT),
            ("Top Talent and Flight Risk", "Top Talent and Flight Risk", REPORT),
            ("Calibration Movers", "Calibration Movers", REPORT),
            ("Development Plan Tracker", "Development Plan Tracker", REPORT),
            ("Programme Effectiveness", "Programme Effectiveness", REPORT),
            ("Graduate Trainee Progress", "Graduate Trainee Progress", REPORT),
        ]),
        # The role's balanced scorecard is carried on Frappe HR's own
        # Appraisal Template (bsc.py), so there is one template document,
        # not two: their page never listed it, and this puts it on the page.
        ("Appraisal Setup", [
            ("Appraisal Template", "Appraisal Template", DOCTYPE),
            ("Appraisal Settings", "Appraisal Settings", DOCTYPE),
            ("BSC Competency", "BSC Competency", DOCTYPE),
            ("Appraisal Factor (LPL/HR/18)", "Appraisal Factor", DOCTYPE),
            ("Employee Feedback Criteria", "Employee Feedback Criteria", DOCTYPE),
            ("KRA", "KRA", DOCTYPE),
        ]),
    ],
    # Luuka's staff loans are a process of their own (4.4) and Frappe HR
    # has no page for lending, so this app makes one (PAGES). The advance
    # is listed here too, because LPL/HR/21 calls it a loan and it is
    # recovered like one; their Expenses page keeps its own entry.
    "Loans": [
        ("Loans", [
            ("Employee Loan", "Employee Loan", DOCTYPE),
            ("Loan Statement", "Loan Statement", REPORT),
            ("Loan Register", "Loan Register", REPORT),
            ("Loan Settings", "Loan Settings", DOCTYPE),
        ]),
        ("Advances", [
            ("Salary Advance Request", "Salary Advance Request", DOCTYPE),
            ("Salary Advance Processing", "Salary Advance Processing", DOCTYPE),
            ("Advance Payment Report", "Advance Payment Report", REPORT),
            ("Employee Advance", "Employee Advance", DOCTYPE),
            # the minutes' rules for all three advances (advances.py)
            ("Advance Settings", "Advance Settings", DOCTYPE),
        ]),
        # a penalty for property lost or damaged, recovered under the same
        # LPL/HR/39 as a loan (penalties.py, minutes §4.11)
        ("Penalties", [
            ("Employee Penalty", "Employee Penalty", DOCTYPE),
        ]),
        ("Setup", [
            ("Salary Component", "Salary Component", DOCTYPE),
        ]),
    ],
    # Frappe HR's own leave page gains the plan the year is drawn up on:
    # the application itself is theirs, carrying LPL/HR/15 (leave.py)
    "Leaves": [
        ("Application", [
            ("Annual Leave Plan", "Annual Leave Plan", DOCTYPE),
            ("Leave Plan Change", "Leave Plan Change", DOCTYPE),
            ("HR Calendar", "hr-calendar", PAGE),
        ]),
        # the leave advance, its own document apart from the loans
        # (leave_advances.py, minutes §4.4)
        ("Leave Advance", [
            ("Leave Advance", "Leave Advance", DOCTYPE),
            ("Leave Advance Processing", "Leave Advance Processing", DOCTYPE),
        ]),
        ("Reports", [
            ("Leave Schedule", "Leave Schedule", REPORT),
            ("Leave Plan Adherence", "Leave Plan Adherence", REPORT),
            # leave earned by the days worked (leave_accrual.py)
            ("Leave Accrual", "Leave Accrual", REPORT),
        ]),
        ("Leave Settings", [
            ("Leave Management Settings", "Leave Management Settings", DOCTYPE),
        ]),
    ],
    # Frappe HR's own attendance page gains Luuka's three forms and the
    # machines they are reconciled against (attendance.py, devices.py)
    "Shift & Attendance": [
        # LPL/HR/07 on screen, filled from the punches (attendance_board.py)
        ("The Floor", [
            ("Attendance Board", "attendance-board", PAGE),
        ]),
        ("Attendance Forms", [
            ("Off Duty Request", "Off Duty Request", DOCTYPE),
            ("Overtime Request", "Overtime Request", DOCTYPE),
            ("Shift Rotation", "Shift Rotation", DOCTYPE),
            ("Shift Allowance", "Shift Allowance", DOCTYPE),
            ("Gate Pass", "Gate Pass", DOCTYPE),
            # the minutes' recommendation: late, said in advance, a full day
            ("Late Arrival Notice", "Late Arrival Notice", DOCTYPE),
        ]),
        ("Clocking Machines", [
            ("BioTime Server", "BioTime Server", DOCTYPE),
            ("Attendance Device", "Attendance Device", DOCTYPE),
            ("Attendance Device Log", "Attendance Device Log", DOCTYPE),
        ]),
    ],
    # Frappe HR's own payroll page gains the output-pay sheets: the daily
    # report, the month's run, and each size with its Work Unit (output_pay.py)
    "Payroll": [
        ("Output Pay", [
            ("Daily Production Report", "Daily Production Report", DOCTYPE),
            ("Output Pay Run", "Output Pay Run", DOCTYPE),
            ("Sizes and Work Units", "Output Rate", DOCTYPE),
            ("Output Pay Settings", "Output Pay Settings", DOCTYPE),
        ]),
    ],
    "HR Setup": [
        # The scale the travel form reads its rates off (grades.py). The
        # Gradar band and its steps are custom fields on Frappe HR's own
        # Employee Grade, which is already on this page and is left where
        # they put it.
        ("Travel Allowance Scale", [
            ("Travel Destination", "Travel Destination", DOCTYPE),
            ("Per Diem Rate", "Per Diem Rate", DOCTYPE),
        ]),
        # who may see what, and the matrix that says so (security.py)
        ("Access", [
            ("Role and Access Matrix", "Role and Access Matrix", REPORT),
        ]),
        # the report that replaces the manual extract, and the dashboard
        # the plants are read from
        ("Manpower", [
            ("Monthly Manpower and Headcount", "Monthly Manpower and Headcount", REPORT),
        ]),
        # the specimen on file and the signatures given (signatures.py)
        ("Signatures", [
            ("Employee Signature", "Employee Signature", DOCTYPE),
            ("Signature Log", "Signature Log", DOCTYPE),
        ]),
        # what an employee has to hold, and what is running out
        # (documents.py)
        ("Employee Documents", [
            ("Employee Document Type", "Employee Document Type", DOCTYPE),
            ("Document Expiry", "Document Expiry", REPORT),
        ]),
        ("Job Description Lists", [
            ("KRA Perspective", "KRA Perspective", DOCTYPE),
            ("KRA Level", "KRA Level", DOCTYPE),
            ("KRA Unit", "KRA Unit", DOCTYPE),
            ("KRA Data Source", "KRA Data Source", DOCTYPE),
            ("KRA Review Frequency", "KRA Review Frequency", DOCTYPE),
            ("JD Relationship Type", "JD Relationship Type", DOCTYPE),
            ("JD Stakeholder Type", "JD Stakeholder Type", DOCTYPE),
            ("JD Authority Level", "JD Authority Level", DOCTYPE),
            ("JD Horizon", "JD Horizon", DOCTYPE),
            ("JD ISO Standard", "JD ISO Standard", DOCTYPE),
            ("JD Specification Type", "JD Specification Type", DOCTYPE),
            ("JD Requirement Priority", "JD Requirement Priority", DOCTYPE),
            ("JD Competency Category", "JD Competency Category", DOCTYPE),
        ]),
    ],
    # The Allowance Request (4.3) is a document of its own, beside the claim
    # and the advance on Frappe HR's page for money paid to employees
    # (allowances.py); its types and the per-diem scale with it.
    "Expenses": [
        ("Allowances", [
            ("Allowance Request", "Allowance Request", DOCTYPE),
            ("Allowance Type", "Allowance Type", DOCTYPE),
            ("Per Diem Rate", "Per Diem Rate", DOCTYPE),
            ("Travel Destination", "Travel Destination", DOCTYPE),
        ]),
    ],
}

# The desk routes a Report link by its kind: a Script or Query Report opens
# as a query report, a Report Builder one on its doctype's list. Written
# with the flag off, a script report opened the list instead (Sep 2026).
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")
QUERY_REPORT_TYPES = ("Query Report", "Script Report", "Custom Report")


def report_facts(name):
    """(report_type, ref_doctype) of a report this app ships, from its file;
    (None, None) for one it does not."""
    # the folder Frappe makes of the name (frappe.scrub): a hyphen is an
    # underscore too, as in Nine-Box Distribution
    folder = name.replace(" ", "_").replace("-", "_").lower()
    path = os.path.join(REPORTS_DIR, folder, folder + ".json")
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as handle:
        spec = json.load(handle)
    return spec.get("report_type"), spec.get("ref_doctype")

# workspace -> [(label, what it opens, kind, section, after)]
#   section: the sidebar section it goes under ("Setup", "Reports"), or None
#            for the top level
#   after:   the entry it follows, where it matters; otherwise it goes last
#            in its part of the list
SIDEBAR = {
    "Recruitment": [
        ("Interview Shortlist", "Interview Shortlist", DOCTYPE, None, "Job Applicant"),
        ("Interview Report", "Interview Report", DOCTYPE, None, "Interview"),
        ("Interview Criterion", "Interview Criterion", DOCTYPE, "Setup", None),
        ("Interview Criteria Group", "Interview Criteria Group", DOCTYPE, "Setup", None),
        ("Qualification Type", "Qualification Type", DOCTYPE, "Setup", None),
        ("Applicant Screening", "Applicant Screening", REPORT, "Reports", None),
        ("Interviewer Calibration", "Interviewer Calibration", REPORT, "Reports", None),
        ("Interview Pass Rate", "Interview Pass Rate", REPORT, "Reports", None),
        ("Time to Hire", "Time to Hire", REPORT, "Reports", None),
        ("Time to Fill", "Time to Fill", REPORT, "Reports", None),
    ],
    # a promotion follows an appraisal, so it is reachable from here too
    "Performance": [
        ("Appraisal Plan", "Appraisal Plan", DOCTYPE, None, "Goal"),
        ("Performance Review", "Performance Review", DOCTYPE, None, "Appraisal"),
        ("Appraisal Results", "Appraisal Results", REPORT, None, "Performance Review"),
        ("Performance Improvement Plan", "Performance Improvement Plan", DOCTYPE, None, "Appraisal Results"),
        ("Employee Position Change", "Employee Position Change", DOCTYPE, None, "Employee Promotion"),
        # the review on one grid (page/talent_board), first of the talent entries
        ("Talent Board", "talent-board", PAGE, None, None),
        ("Talent Review", "Talent Review", DOCTYPE, None, "Employee Position Change"),
        ("Talent Placement", "Talent Placement", DOCTYPE, None, "Talent Review"),
        ("Talent Program", "Talent Program", DOCTYPE, None, "Talent Placement"),
        ("Succession Position", "Succession Position", DOCTYPE, None, "Talent Program"),
        ("Graduate Trainee Program", "Graduate Trainee Program", DOCTYPE, None,
         "Succession Position"),
        ("Succession Coverage", "Succession Coverage", REPORT, "Reports", None),
        ("Performance Analytics", "Performance Analytics", REPORT, "Reports", None),
        # talent, linked with the appraisal (5 Oct 2026): the month first,
        # since it is what HR and the council are sent each month
        ("Monthly Talent Report", "Monthly Talent Report", REPORT, "Reports", None),
        ("Nine-Box Distribution", "Nine-Box Distribution", REPORT, "Reports", None),
        ("Top Talent and Flight Risk", "Top Talent and Flight Risk", REPORT, "Reports", None),
        ("Calibration Movers", "Calibration Movers", REPORT, "Reports", None),
        ("Development Plan Tracker", "Development Plan Tracker", REPORT, "Reports", None),
        ("Programme Effectiveness", "Programme Effectiveness", REPORT, "Reports", None),
        ("Graduate Trainee Progress", "Graduate Trainee Progress", REPORT, "Reports", None),
        # Appraisal Template is Frappe HR's own entry, already under Setup,
        # and the scorecard is built on it: it is left exactly where it is
        ("BSC Competency", "BSC Competency", DOCTYPE, "Setup", None),
        ("Appraisal Factor", "Appraisal Factor", DOCTYPE, "Setup", None),
        ("Appraisal Settings", "Appraisal Settings", DOCTYPE, "Setup", None),
    ],
    "Loans": [
        ("Employee Loan", "Employee Loan", DOCTYPE, None, None),
        ("Loan Statement", "Loan Statement", REPORT, "Reports", None),
        ("Loan Register", "Loan Register", REPORT, "Reports", None),
        ("Loan Settings", "Loan Settings", DOCTYPE, "Setup", None),
        ("Salary Advance Request", "Salary Advance Request", DOCTYPE, None, "Employee Loan"),
        ("Salary Advance Processing", "Salary Advance Processing", DOCTYPE, None, "Salary Advance Request"),
        ("Employee Advance", "Employee Advance", DOCTYPE, None, "Salary Advance Processing"),
        ("Advance Payment Report", "Advance Payment Report", REPORT, "Reports", None),
        ("Employee Penalty", "Employee Penalty", DOCTYPE, None, "Employee Advance"),
        ("Advance Settings", "Advance Settings", DOCTYPE, "Setup", None),
        ("Salary Component", "Salary Component", DOCTYPE, "Setup", None),
    ],
    "Leaves": [
        ("Annual Leave Plan", "Annual Leave Plan", DOCTYPE, None, "Leave Application"),
        ("Leave Plan Change", "Leave Plan Change", DOCTYPE, None, "Annual Leave Plan"),
        ("HR Calendar", "hr-calendar", PAGE, None, "Leave Plan Change"),
        ("Leave Advance", "Leave Advance", DOCTYPE, None, "hr-calendar"),
        ("Leave Advance Processing", "Leave Advance Processing", DOCTYPE, None, "Leave Advance"),
        ("Leave Schedule", "Leave Schedule", REPORT, "Reports", None),
        ("Leave Plan Adherence", "Leave Plan Adherence", REPORT, "Reports", None),
        ("Leave Accrual", "Leave Accrual", REPORT, "Reports", None),
        ("Leave Management Settings", "Leave Management Settings", DOCTYPE, "Setup", None),
    ],
    "Shift & Attendance": [
        ("Attendance Board", "attendance-board", PAGE, None, None),
        ("Off Duty Request", "Off Duty Request", DOCTYPE, None, "Attendance"),
        ("Overtime Request", "Overtime Request", DOCTYPE, None, "Off Duty Request"),
        ("Gate Pass", "Gate Pass", DOCTYPE, None, "Overtime Request"),
        ("Late Arrival Notice", "Late Arrival Notice", DOCTYPE, None, "Gate Pass"),
        ("Shift Rotation", "Shift Rotation", DOCTYPE, None, "Late Arrival Notice"),
        ("Shift Allowance", "Shift Allowance", DOCTYPE, None, "Shift Rotation"),
        ("Travel Destination", "Travel Destination", DOCTYPE, "Setup", None),
        ("Per Diem Rate", "Per Diem Rate", DOCTYPE, "Setup", None),
        ("BioTime Server", "BioTime Server", DOCTYPE, "Setup", None),
        ("Attendance Device", "Attendance Device", DOCTYPE, "Setup", None),
        ("Attendance Device Log", "Attendance Device Log", DOCTYPE, "Setup", None),
    ],
    "Payroll": [
        ("Daily Production Report", "Daily Production Report", DOCTYPE, None, "Additional Salary"),
        ("Output Pay Run", "Output Pay Run", DOCTYPE, None, "Daily Production Report"),
        ("Sizes and Work Units", "Output Rate", DOCTYPE, "Setup", None),
        ("Output Pay Settings", "Output Pay Settings", DOCTYPE, "Setup", None),
    ],
    "Tenure": [
        ("Onboarding Review", "Onboarding Review", DOCTYPE, None, "Employee Onboarding"),
        ("Probation Evaluation", "Probation Evaluation", DOCTYPE, None, "Onboarding Review"),
        # Employee Separation is their own sidebar entry: it stays where
        # they put it, and the rest of the exit follows it
        ("Exit Interview", "Exit Interview", DOCTYPE, None, "Employee Separation"),
        ("Clearance Form", "Clearance Form", DOCTYPE, None, "Exit Interview"),
        ("Full and Final Statement", "Full and Final Statement", DOCTYPE, None, "Clearance Form"),
        ("Employee Contract", "Employee Contract", DOCTYPE, None, "Probation Evaluation"),
        # what follows the contract: a promotion, a change of designation or a
        # salary review, where the pay is sent, and internship placements
        ("Employee Position Change", "Employee Position Change", DOCTYPE, None, "Employee Contract"),
        ("Employee Data Change Request", "Employee Data Change Request", DOCTYPE, None, "Employee Position Change"),
        ("Intern Placement", "Intern Placement", DOCTYPE, None, "Employee Data Change Request"),
        ("Contract Expiry Status", "Contract Expiry Status", REPORT, "Reports", None),
        # the training process, in the order it runs
        ("Training Requisition", "Training Requisition", DOCTYPE, None, "Intern Placement"),
        ("Training Needs Assessment", "Training Needs Assessment", DOCTYPE, None, "Training Requisition"),
        ("Training Calendar", "Training Calendar", DOCTYPE, None, "Training Needs Assessment"),
        ("Monthly Training Schedule", "Monthly Training Schedule", DOCTYPE, None, "Training Calendar"),
        ("HR Calendar", "hr-calendar", PAGE, None, "Monthly Training Schedule"),
        ("Training Report", "Training Report", REPORT, "Reports", None),
        ("Training Needs Form", "Training Needs Form", DOCTYPE, "Setup", None),
        ("Training Evaluation Item", "Training Evaluation Item", DOCTYPE, "Setup", None),
        ("Meeting Record", "Meeting Record", DOCTYPE, "Setup", None),
        ("Disciplinary Case", "Disciplinary Case", DOCTYPE, None, "Employee Grievance"),
        ("Safety Incident", "Safety Incident", DOCTYPE, None, "Disciplinary Case"),
        ("Misconduct Type", "Misconduct Type", DOCTYPE, "Setup", None),
        ("Disciplinary Action Type", "Disciplinary Action Type", DOCTYPE, "Setup", None),
        ("Onboarding Settings", "Onboarding Settings", DOCTYPE, "Setup", None),
        ("Tool of Work", "Tool of Work", DOCTYPE, "Setup", None),
        ("Tool Provider", "Tool Provider", DOCTYPE, "Setup", None),
        ("Probation Factor", "Probation Factor", DOCTYPE, "Setup", None),
    ],
    "Expenses": [
        ("Allowance Request", "Allowance Request", DOCTYPE, None, "Expense Claim"),
        ("Allowance Type", "Allowance Type", DOCTYPE, "Setup", None),
    ],
}

# How each sidebar is laid out (Luuka, 5 Oct 2026: "the menu is not
# appealing"). Added one by one, the entries made one long list, and every
# one of ours carried Frappe's stand-in "list" icon. Now every entry, ours
# and Frappe HR's alike, sits under a heading for the part of the process it
# serves, drawn open with its own icon; the entries at the top keep theirs,
# and Reports, Setup and Frappe HR's other sections stay below, folded, as
# they ship. A group named like one of their sections (Planning, Overtime,
# Travel) takes it over, and whatever else they keep in it follows.
#   workspace -> [(group, icon, [what each entry opens, in order])]
GROUPS = {
    "Recruitment": [
        ("Planning", "clipboard-list", ["Job Requisition", "Staffing Plan", "Employee Referral"]),
        ("Hiring", "briefcase", ["Job Opening", "Job Applicant", "Interview Shortlist", "Interview",
                                 "Interview Report"]),
        ("Offers", "handshake", ["Job Offer", "Appointment Letter"]),
    ],
    "Performance": [
        ("Appraisals", "star", ["Appraisal Plan", "Appraisal Cycle", "Appraisal", "Performance Review",
                                "Appraisal Results", "Performance Improvement Plan"]),
        ("Goals and Feedback", "target", ["Goal", "Employee Performance Feedback"]),
        ("Promotions", "trending-up", ["Employee Promotion", "Employee Position Change"]),
        ("Talent", "award", ["talent-board", "Talent Review", "Talent Placement", "Talent Program",
                             "Succession Position", "Graduate Trainee Program"]),
    ],
    "Loans": [
        ("Loans", "hand-coins", ["Employee Loan"]),
        ("Advances", "coins", ["Salary Advance Request", "Salary Advance Processing", "Employee Advance"]),
        ("Penalties", "gavel", ["Employee Penalty"]),
    ],
    "Leaves": [
        ("Requests", "clipboard-pen", ["Leave Application", "Leave Encashment"]),
        ("Leave Advances", "wallet", ["Leave Advance", "Leave Advance Processing"]),
        ("Planning", "calendar-days", ["Annual Leave Plan", "Leave Plan Change"]),
        ("Allocation", "layers", ["Leave Control Panel", "Leave Policy Assignment", "Leave Allocation"]),
    ],
    "Shift & Attendance": [
        ("Attendance", "clock", ["Employee Checkin", "Employee Attendance Tool", "Attendance Request",
                                 "Late Arrival Notice", "Gate Pass", "Off Duty Request"]),
        ("Shifts", "repeat", ["Shift Request", "Shift Rotation", "Shift Allowance"]),
        ("Overtime", "calendar-clock", ["Overtime Request", "Overtime Slip"]),
    ],
    "Payroll": [
        ("Payroll", "banknote", ["Payroll Entry", "Salary Structure Assignment", "Salary Slip", "Additional Salary",
                                 "Salary Withholding"]),
        ("Output Pay", "factory", ["Daily Production Report", "Output Pay Run"]),
    ],
    "Tenure": [
        ("Joining", "user-plus", ["Employee Onboarding", "Onboarding Review", "Probation Evaluation",
                                  "Intern Placement"]),
        ("Contracts", "file-text", ["Employee Contract", "Employee Position Change",
                                    "Employee Data Change Request"]),
        ("Training", "graduation-cap", ["Training Requisition", "Training Needs Assessment", "Training Calendar",
                                        "Monthly Training Schedule"]),
        ("Employee Relations", "scale", ["Employee Grievance", "Disciplinary Case", "Safety Incident"]),
        ("Exit", "log-out", ["Employee Separation", "Exit Interview", "Clearance Form", "Full and Final Statement"]),
    ],
    "Expenses": [
        ("Claims", "receipt", ["Expense Claim", "Employee Advance", "Allowance Request"]),
        ("Travel", "plane", ["Travel Request", "Vehicle Log"]),
    ],
}

# the shorter name an entry carries under its group's heading, which says
# the rest: what it opens -> its name there. It opens the same document.
SHORT_LABELS = {
    "Employee Referral": "Referral",
    "Interview Shortlist": "Shortlist",
    "Performance Improvement Plan": "Improvement Plan",
    "Employee Performance Feedback": "Feedback",
    "Employee Promotion": "Promotion",
    "Employee Position Change": "Position Change",
    "Talent Placement": "Placement",
    "Talent Program": "Program",
    "Succession Position": "Succession",
    "Graduate Trainee Program": "Graduate Trainees",
    "Salary Advance Request": "Advance Request",
    "Salary Advance Processing": "Advance Processing",
    "Employee Penalty": "Penalty",
    "Leave Encashment": "Encashment",
    "Leave Advance Processing": "Advance Processing",
    "Annual Leave Plan": "Annual Plan",
    "Leave Plan Change": "Plan Change",
    "Leave Control Panel": "Control Panel",
    "Leave Policy Assignment": "Policy Assignment",
    "Leave Allocation": "Allocation",
    "Employee Checkin": "Checkin",
    "Employee Attendance Tool": "Attendance Tool",
    "Salary Structure Assignment": "Salary Assignment",
    "Salary Withholding": "Withholding",
    "Daily Production Report": "Daily Production",
    "Employee Onboarding": "Onboarding",
    "Employee Data Change Request": "Data Change Request",
    "Training Needs Assessment": "Needs Assessment",
    "Monthly Training Schedule": "Monthly Schedule",
    "Employee Grievance": "Grievance",
    "Employee Separation": "Separation",
    "Full and Final Statement": "Final Settlement",
}

# the icon of an entry of ours that stays at the top of a sidebar, above
# the groups: what it opens -> icon
TOP_ICONS = {"hr-calendar": "calendar", "attendance-board": "layout-grid"}

CARD_BREAK, LINK, SECTION = "Card Break", "Link", "Section Break"


def link_row(label, link_to, kind):
    """A Workspace Link row for one thing to open."""
    report_type, ref_doctype = report_facts(link_to) if kind == REPORT else (None, None)
    return {
        "type": LINK,
        "label": label,
        "link_type": kind,
        "link_to": link_to,
        "hidden": 0,
        "onboard": 0,
        "link_count": 0,
        "is_query_report": 1 if report_type in QUERY_REPORT_TYPES else 0,
        "report_ref_doctype": ref_doctype,
    }


def card_row(label):
    return {"type": CARD_BREAK, "label": label, "link_type": None, "link_to": None, "hidden": 0, "onboard": 0,
            "link_count": 0, "is_query_report": 0}


def merge_links(rows, cards):
    """The Workspace's `links` with our cards in it. What Frappe HR ships is
    never rewritten: a card it already has is added to, a card it does not
    have is appended. Each link of ours ends up once, at the end of its own
    card, in our order, wherever a copy of it was found: one sitting in
    another card, or a second one, is what a faulty write leaves behind
    (numbered()), and is cleared away here. Every Card Break's link_count is
    worked out again at the end, which is what the page counts by."""
    ours = {link[1] for _card, links in cards for link in links}
    rows = [dict(row) for row in rows if not (row.get("type") == LINK and row.get("link_to") in ours)]
    for card, links in cards:
        start = next((i for i, row in enumerate(rows) if row.get("type") == CARD_BREAK and row.get("label") == card), None)
        if start is None:
            rows.append(card_row(card))
            start = len(rows) - 1
        end = next((i for i in range(start + 1, len(rows)) if rows[i].get("type") == CARD_BREAK), len(rows))
        rows[end:end] = [link_row(*link) for link in links]
    return count_links(rows)


def numbered(rows):
    """The rows as they must be written: numbered 1, 2, 3... in `idx`, the
    order Frappe reads them back in.

    A row taken from the database brings its old number with it, and Frappe
    keeps a number it is given (only a row without one gets its place in the
    list). So without this, a row put in the middle shares its number with
    the one it pushed down and the two come back in either order: in
    September 2026 the Training links landed in the cards after theirs, were
    not found in their own on the next migrate, and were added again."""
    return [dict(row, idx=number) for number, row in enumerate(rows, 1)]


def count_links(rows):
    """Each Card Break counts the links that follow it."""
    rows = [dict(row) for row in rows]
    card = None
    for row in rows:
        if row.get("type") == CARD_BREAK:
            card, row["link_count"] = row, 0
        elif card is not None:
            card["link_count"] += 1
    return rows


def block_id(card):
    """The id of a card's block in the page's content. Ours is worked out
    from the card's name, not random like Frappe's, so running this again
    finds the block it wrote last time instead of adding another."""
    return "ha" + "".join(word.capitalize() for word in "".join(c if c.isalnum() else " " for c in card).split())


def merge_content(blocks, cards):
    """The page's content with a block for each of our cards, added once."""
    blocks = [dict(block) for block in blocks]
    have = {(block.get("data") or {}).get("card_name") for block in blocks if block.get("type") == "card"}
    for card, _ in cards:
        if card not in have:
            blocks.append({"id": block_id(card), "type": "card", "data": {"card_name": card, "col": 4}})
    return blocks


def new_sidebar(label, sections=()):
    """The sidebar a page of ours starts with: Home, and a header for each
    section its entries are seated under. Without the headers `_seat` has
    nothing to put a Setup entry beneath and it would land at the end."""
    rows = [dict(sidebar_row("Home", label, WORKSPACE), icon="home")]
    for name in sections:
        rows.append({"type": SECTION, "label": name, "link_type": None, "link_to": None,
                     "icon": SECTION_ICONS.get(name, "database"), "child": 0, "indent": 1,
                     "collapsible": 1, "keep_closed": 1, "show_arrow": 0})
    return numbered(rows)


def with_tiles(layout, tiles):
    """A saved desktop with each of our tiles it lacks added, first or last,
    or None when it has them all. What else it holds stays as it was.

    layout: the list of tiles Frappe saved for the user.
    tiles: [(the tile as get_desktop_icons() gives it, "first" or "last")]."""
    if not isinstance(layout, list):
        return None
    have = {icon.get("label") for icon in layout if isinstance(icon, dict)}
    out, added = list(layout), False
    for tile, where in tiles:
        if not tile or tile.get("label") in have:
            continue
        if where == "first":
            out.insert(0, tile)
        else:
            out.append(tile)
        have.add(tile.get("label"))
        added = True
    return out if added else None


def sidebar_row(label, link_to, kind, child=0):
    return {"type": LINK, "label": label, "link_type": kind, "link_to": link_to, "icon": "", "child": child,
            "indent": 0, "collapsible": 1, "keep_closed": 0, "show_arrow": 0}


def merge_sidebar(items, entries):
    """The sidebar's items with ours among them: under the section each names
    where there is one, else after the entry it follows, else before the
    first section. Ours are always seated afresh, in our order, so one found
    out of place (numbered()) goes back where it belongs; Frappe HR's own
    stay exactly as they are."""
    ours = {entry[1] for entry in entries}
    items = [dict(item) for item in items if not (item.get("type") == LINK and item.get("link_to") in ours)]
    for label, link_to, kind, section, after in entries:
        at = _seat(items, section, after)
        items.insert(at, sidebar_row(label, link_to, kind, child=1 if section else 0))
    return items


def arrange_sidebar(items, groups):
    """The sidebar's items laid out in its groups (GROUPS): each group a
    heading drawn open, its entries beneath it in the order given and under
    their SHORT_LABELS names, placed after the entries at the top and before
    the sections still there, which stay as they were. A group named like a
    section already there takes it over: what else that section holds
    follows the group's own entries. An entry of ours left at the top gets
    its TOP_ICONS icon. Entries no group names, theirs or ours, stay where
    they are; a group none of whose entries is there is left out. Run on
    its own result, it changes nothing."""
    items = [dict(item) for item in items]
    if not groups:
        return items
    names = {name for name, _icon, _entries in groups}
    placed = {link_to for _name, _icon, entries in groups for link_to in entries}
    found, heads, leftovers, rest = {}, {}, {name: [] for name in names}, []
    section = None
    for item in items:
        if item.get("type") == SECTION:
            section = item.get("label")
            if section in names:
                heads.setdefault(section, item)
            else:
                rest.append(item)
        elif item.get("type") == LINK and item.get("link_to") in placed:
            found.setdefault(item["link_to"], item)
        elif section in names and item.get("child"):
            leftovers[section].append(item)
        else:
            rest.append(item)
    block = []
    for name, icon, entries in groups:
        # an entry is drawn without an icon under its heading, as Frappe
        # draws the entries of its own sections
        rows = [dict(found[link_to], child=1, icon="", label=SHORT_LABELS.get(link_to, found[link_to].get("label")))
                for link_to in entries if link_to in found] + leftovers[name]
        if rows:
            block.append(dict(heads.get(name) or {}, type=SECTION, label=name, link_type=None, link_to=None,
                              icon=icon, child=0, indent=1, collapsible=1, keep_closed=0, show_arrow=0))
            block += rows
    at = next((i for i, item in enumerate(rest) if item.get("type") == SECTION), len(rest))
    for item in rest[:at]:
        if item.get("type") == LINK and not item.get("icon") and item.get("link_to") in TOP_ICONS:
            item["icon"] = TOP_ICONS[item["link_to"]]
    return rest[:at] + block + rest[at:]


def _seat(items, section, after):
    if section:
        start = next((i for i, item in enumerate(items)
                      if item.get("type") == SECTION and item.get("label") == section), None)
        if start is not None:
            end = next((i for i in range(start + 1, len(items)) if items[i].get("type") == SECTION), len(items))
            # the section's own rows are the ones marked as its children
            while end > start + 1 and not items[end - 1].get("child"):
                end -= 1
            return end
        return len(items)
    if after:
        at = next((i for i, item in enumerate(items) if item.get("label") == after), None)
        if at is not None:
            return at + 1
    first_section = next((i for i, item in enumerate(items) if item.get("type") == SECTION), None)
    return len(items) if first_section is None else first_section
