# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The safety module's rules (Luuka's review list of 5 Nov 2026, items 11 to
17): what an incident must say, and where the employee stands after it.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_safety.py exercises them without a bench. Who signs what is in
safety_approval.py; safety.py reads and writes the site.

The safety chart ends in two places this module has to name: a sick leave
for the day off, and a separation on medical grounds.
"""

SICK_LEAVE = "Sick Leave"

# where the employee stands after the accident: the incident's Status
DRAFT, RECORDED, ON_SICK_LEAVE, BACK, SEPARATED, CANCELLED = (
    "Draft", "Recorded", "On Sick Leave", "Back at Work", "Separated", "Cancelled")


def incident_errors(facts):
    """Problems with a safety incident, as user-facing messages."""
    errors = []
    if not facts.get("employee"):
        errors.append("Say who the accident happened to.")
    if not facts.get("incident_on"):
        errors.append("Say when it happened.")
    if not _text(facts.get("nature")):
        errors.append("Write what happened; the EHS Officer's report is the record of it.")
    if not facts.get("manageable") and not _text(facts.get("hospital")):
        errors.append("The employee was taken to hospital: say which one.")
    if facts.get("day_off_required"):
        if not facts.get("sick_from"):
            errors.append("Say when the sick leave starts.")
        if not int(facts.get("sick_days") or 0):
            errors.append("Say how many days of sick leave the doctor gave.")
    if facts.get("compensation_required") and not _num(facts.get("compensation_amount")):
        errors.append("Say how much compensation is being followed up.")
    return errors


def incident_status(docstatus, day_off, sick_leave, persists, separation):
    """Where the employee stands, from what has followed the accident."""
    if docstatus == 2:
        return CANCELLED
    if docstatus == 0:
        return DRAFT
    if separation or persists:
        return SEPARATED if separation else ON_SICK_LEAVE
    if day_off and sick_leave:
        return ON_SICK_LEAVE
    return RECORDED if day_off else BACK


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()
