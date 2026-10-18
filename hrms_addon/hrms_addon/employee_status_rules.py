# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What an employee's status is, and what Frappe goes by.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_employee_status.py checks it without a bench.
employee_status.py reads and writes the site; the Employee form and list
show it. Luuka, 18 Oct 2026: "on the employee status edit the standard
field to accommodate all the status the customer provided ... have a place
for defining new one too and include the one client shared".

Luuka's statuses are Employee Status records, and an employee's Status is
one of them. Frappe's own field (System Status on the form) stays one of its
four, because payroll, leave, attendance and the login are written against
those four: Payroll Entry leaves out only an employee who is Inactive, the
monthly earned leave skips only one who is Left, a salary slip refuses one
relieved before the month unless they are Left, and the login is disabled
for anyone not Active. So each status says which of the four it counts as,
and the System Status is kept to it: an employee who Resigned is Left to
Frappe, with Left's rules (a relieving date), and one On Hold is Inactive,
off the payroll.

  BASE         Frappe's four, each a status of its own that counts as itself
  LUUKA        the statuses Luuka's records use, and what each counts as
  settle       an employee's (System Status, Status) after a change to either
  drift        the employees whose two have come apart, and the Status each takes
  exit_status  the status an exit for this reason leaves the employee in
  status_errors  what stops an Employee Status being saved
"""

ACTIVE, INACTIVE, SUSPENDED, LEFT = "Active", "Inactive", "Suspended", "Left"
BASE = (ACTIVE, INACTIVE, SUSPENDED, LEFT)
# Luuka's Ebisframe statuses (the Employee sheet of 18 Oct 2026), beside Active and Inactive
LUUKA = (
    ("On Hold", INACTIVE),
    ("Separated", LEFT),
    ("Resigned", LEFT),
    ("Terminated", LEFT),
    ("Deceased", LEFT),
    ("Retired", LEFT),
)
# the reason an Employee Separation gives (custom_reason) -> the status the exit leaves
EXIT_STATUSES = {
    "Resignation": "Resigned",
    "Retirement": "Retired",
    "Death": "Deceased",
    "Dismissal": "Terminated",
    "Desertion": "Terminated",
    "End of Contract": "Separated",
    "Redundancy": "Separated",
    "Medical Grounds": "Separated",
}
# the colour Frappe's list gives each of its four (erpnext employee_list.js)
COLOURS = {ACTIVE: "green", INACTIVE: "red", SUSPENDED: "orange", LEFT: "gray"}
INDICATORS = ("green", "blue", "orange", "yellow", "red", "gray", "purple", "pink", "cyan")


def settle(status, chosen, before, counts):
    """(System Status, Status) as the employee is to be saved.

    status, chosen: the System Status and the Status now; before: the two as
    last saved, or None for a new employee; counts: each Employee Status and
    what it counts as. A Status picked (or changed) decides the System
    Status. Otherwise the System Status, which only Frappe and the app move
    (a suspension, an exit, Frappe HR's transfer, a reinstatement), keeps the
    Status if it still counts as it, and names its own if not. An employee
    with no Status takes their System Status's. Without any statuses on the
    site, nothing is touched."""
    if not counts:
        return status, chosen
    if chosen and chosen in counts:
        if before is None or chosen != before[1]:
            return counts[chosen], chosen
        if counts[chosen] == status:
            return status, chosen
    return status, (status if status in counts else chosen)


def drift(rows, counts):
    """[(employee, Status)]: those whose Status is empty or no longer counts as
    their System Status (one set without a save), with the Status to give them."""
    if not counts:
        return []
    out = []
    for row in rows or ():
        chosen, status = row.get("custom_employee_status"), row.get("status")
        if counts.get(chosen) != status and status in counts:
            out.append((row.get("name"), status))
    return out


def moved(chosen, status, counts):
    """The Status of an employee whose System Status is set to `status`
    without a save: kept while it counts as it, else the System Status's own."""
    return chosen if counts.get(chosen) == status else status


def exit_status(reason, counts, disabled=()):
    """The status an exit for this reason leaves the employee in: Luuka's own
    where it is on the site, still used and counts as Left, else Left."""
    name = EXIT_STATUSES.get(reason or "")
    if name and (counts or {}).get(name) == LEFT and name not in (disabled or ()):
        return name
    return LEFT


def colour_of(name, counts, colours=None):
    """The status's colour in the Employee list: its own, else the one Frappe
    gives what it counts as."""
    own = (colours or {}).get(name)
    return own if own in INDICATORS else COLOURS.get((counts or {}).get(name), "gray")


def status_errors(name, counts_as, is_standard, in_use, before):
    """What stops an Employee Status being saved. before: (counts_as,
    is_standard) as last saved, or None for a new one; in_use: how many
    employees have it."""
    errors = []
    name = (name or "").strip()
    if not name:
        errors.append("The status needs a name.")
    if counts_as not in BASE:
        errors.append("Counts As must be one of the system statuses: %s." % ", ".join(BASE))
    if before is None and is_standard and name not in BASE:
        errors.append("Only the system statuses are built in: %s." % ", ".join(BASE))
    if before is not None and bool(before[1]) != bool(is_standard):
        errors.append("Whether a status is built in cannot be changed.")
    if is_standard and name in BASE and counts_as != name:
        errors.append("%s is a system status and counts as itself." % name)
    if before is not None and before[0] and before[0] != counts_as and in_use:
        errors.append("%d employee(s) have the status %s, which counts as %s: give them another status before it "
                      "counts as %s." % (in_use, name, before[0], counts_as))
    return errors
