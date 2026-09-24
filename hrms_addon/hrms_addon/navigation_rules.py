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
            ("Spoken Language", "Spoken Language", DOCTYPE),
            ("Relationship", "Relationship", DOCTYPE),
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
            ("Performance Improvement Plan", "Performance Improvement Plan", DOCTYPE),
        ]),
        ("After the Appraisal", [
            ("Employee Position Change", "Employee Position Change", DOCTYPE),
            ("Employee Promotion", "Employee Promotion", DOCTYPE),
        ]),
        # Talent management reads the appraisal and never re-enters it, so
        # it belongs on the page the appraisal is run from (talent.py).
        ("Talent Management", [
            ("Talent Review", "Talent Review", DOCTYPE),
            ("Talent Placement", "Talent Placement", DOCTYPE),
            ("Talent Program", "Talent Program", DOCTYPE),
            ("Succession Position", "Succession Position", DOCTYPE),
            ("Graduate Trainee Program", "Graduate Trainee Program", DOCTYPE),
            ("Succession Coverage", "Succession Coverage", REPORT),
            ("Performance Analytics", "Performance Analytics", REPORT),
        ]),
        # The role's balanced scorecard is carried on Frappe HR's own
        # Appraisal Template (bsc.py), so there is one template document,
        # not two: their page never listed it, and this puts it on the page.
        ("Appraisal Setup", [
            ("Appraisal Template", "Appraisal Template", DOCTYPE),
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
        ]),
        ("Reports", [
            ("Leave Schedule", "Leave Schedule", REPORT),
            ("Leave Plan Adherence", "Leave Plan Adherence", REPORT),
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
    # Frappe HR's own payroll page gains the output-pay sheets: the machines
    # and their rates, the daily report, and the month's run (output_pay.py)
    "Payroll": [
        ("Output Pay", [
            ("Daily Production Report", "Daily Production Report", DOCTYPE),
            ("Output Pay Run", "Output Pay Run", DOCTYPE),
            ("Production Machine", "Production Machine", DOCTYPE),
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
}

# The desk routes a Report link by its kind: a Script or Query Report opens
# as a query report, a Report Builder one on its doctype's list. Written
# with the flag off, a script report opened the list instead (Sep 2026).
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")
QUERY_REPORT_TYPES = ("Query Report", "Script Report", "Custom Report")


def report_facts(name):
    """(report_type, ref_doctype) of a report this app ships, from its file;
    (None, None) for one it does not."""
    folder = name.lower().replace(" ", "_")
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
    ],
    # a promotion follows an appraisal, so it is reachable from here too
    "Performance": [
        ("Appraisal Plan", "Appraisal Plan", DOCTYPE, None, "Goal"),
        ("Performance Review", "Performance Review", DOCTYPE, None, "Appraisal"),
        ("Performance Improvement Plan", "Performance Improvement Plan", DOCTYPE, None, "Performance Review"),
        ("Employee Position Change", "Employee Position Change", DOCTYPE, None, "Employee Promotion"),
        ("Talent Review", "Talent Review", DOCTYPE, None, "Employee Position Change"),
        ("Talent Placement", "Talent Placement", DOCTYPE, None, "Talent Review"),
        ("Talent Program", "Talent Program", DOCTYPE, None, "Talent Placement"),
        ("Succession Position", "Succession Position", DOCTYPE, None, "Talent Program"),
        ("Graduate Trainee Program", "Graduate Trainee Program", DOCTYPE, None,
         "Succession Position"),
        ("Succession Coverage", "Succession Coverage", REPORT, "Reports", None),
        ("Performance Analytics", "Performance Analytics", REPORT, "Reports", None),
        # Appraisal Template is Frappe HR's own entry, already under Setup,
        # and the scorecard is built on it: it is left exactly where it is
        ("BSC Competency", "BSC Competency", DOCTYPE, "Setup", None),
        ("Appraisal Factor", "Appraisal Factor", DOCTYPE, "Setup", None),
    ],
    "Loans": [
        ("Employee Loan", "Employee Loan", DOCTYPE, None, None),
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
        ("Leave Schedule", "Leave Schedule", REPORT, "Reports", None),
        ("Leave Plan Adherence", "Leave Plan Adherence", REPORT, "Reports", None),
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
        ("Production Machine", "Production Machine", DOCTYPE, "Setup", None),
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
}

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
