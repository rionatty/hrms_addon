# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a module's page shows above Frappe's own cards.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_module_pages.py checks it without a bench. module_pages.py
reads the site and public/js/hrms_addon_module_pages.js draws the page.
Luuka, 14 Oct 2026, seeing the desk home and then a module opened from it:
"extend the UI acuteness to the inner modules when opened".

  page_of   Executive, or Standard where Theme Settings say so
  ACTIONS   the one document a module's header offers to make
  doctypes  the documents a module's page and menu open, each once
  mine_in   the user's own alerts about those documents

A module's page opens under a header of its own: its picture and name, the
groups of its menu, where it falls in an employee's time with the company
(home_rules.MODULES), what waits for the user in it, and the document most
often made there. Frappe's charts, lists and cards follow, drawn as the desk
home draws its panels.
"""

EXECUTIVE, STANDARD = "Executive", "Standard"
PAGES = (EXECUTIVE, STANDARD)
# how many rows the panel of what waits lists; the rest are in My Alerts
SHOWN = 5
# The document most often made in each module, offered beside its name to
# somebody who may make it: where the module's work starts. Tax & Benefits
# has none: its documents are made from payroll and the employee's record.
ACTIONS = {
    "Recruitment": "Job Requisition",
    "HR Setup": "Employee",
    "Shift & Attendance": "Attendance Request",
    "Leaves": "Leave Application",
    "Payroll": "Payroll Entry",
    "Loans": "Employee Loan",
    "Expenses": "Expense Claim",
    "Performance": "Appraisal",
    "Tenure": "Employee Onboarding",
}


def page_of(value):
    """Executive unless Theme Settings say Standard: a setting nobody has
    touched is the module pages' own look."""
    return STANDARD if str(value or "").strip() == STANDARD else EXECUTIVE


def doctypes(names):
    """Each doctype once, in the order first named, blanks left out."""
    seen, found = set(), []
    for name in names or ():
        name = str(name or "").strip()
        if name and name not in seen:
            seen.add(name)
            found.append(name)
    return found


def mine_in(alerts, names):
    """The user's alerts about documents of the doctypes named, in the order
    given: what waits for them in one module."""
    wanted = set(names or ())
    return [alert for alert in alerts or [] if alert.get("doctype") in wanted]
