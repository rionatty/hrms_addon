# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Exit rules: voluntary (4.5) and involuntary (4.6), and the Clearance
Form (LPL/HR/22) both of them end in.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_exits.py exercises them without a bench.

Voluntary, from the revised flow chart:

  1. The employee gives the HR Officer a resignation letter.
  2. The HR Officer calls them for an exit interview.
  3. The employee fills it in.
  4. It is approved by the Supervisor, the HOD and the HR Officer.
  5. The employee serves the notice period.
  6. The HR Officer calls them to hand over the tools of work.
  7. The employee fills the Clearance Form.
  8. It is approved by the HR Officer/Manager, Finance and the General
     Manager.
  9. The cessation of employment follows (settlement_rules.py).

Involuntary:

  1. The HR Officer draws up the termination letter.
  2-4. The employee is summoned, shown it and signs it.
  5. The employee hands company property to the HOD.
  6. The employee fills and signs the Clearance Form.
  7. The HR Officer updates their status; the Payroll Officer is told.
  8. It is approved by the General Manager, Accounts and the HR Manager.
  9. The termination process follows.

The notice periods are Luuka's own, from the minutes of 16 and 20 July
2026 (Reward and Compensation, §4.13), which sit at or above the
Employment Act's: 0 to 6 months of service, 7 days; 6 to 12 months, 14;
1 to 5 years, a month; 5 to 10 years, two; above 10 years, three. What the
employee is actually owed is still what their contract says.
"""

import datetime

VOLUNTARY = "Voluntary"
INVOLUNTARY = "Involuntary"
EXIT_TYPES = (VOLUNTARY, INVOLUNTARY)

# why someone leaves
RESIGNATION = "Resignation"
RETIREMENT = "Retirement"
END_OF_CONTRACT = "End of Contract"
DISMISSAL = "Dismissal"
REDUNDANCY = "Redundancy"
DESERTION = "Desertion"
MEDICAL = "Medical Grounds"
DEATH = "Death"
REASONS = {
    VOLUNTARY: (RESIGNATION, RETIREMENT, END_OF_CONTRACT),
    INVOLUNTARY: (DISMISSAL, REDUNDANCY, DESERTION, MEDICAL, END_OF_CONTRACT, DEATH),
}

# minutes §4.13: months served -> days of notice
NOTICE_PERIODS = ((120, 90), (60, 60), (12, 30), (6, 14), (0, 7))

# the ten boxes LPL/HR/22 prints, in its own order
SECTIONS = (
    ("A", "Own Department", ("Locker keys", "Company Documents/Files", "Handover report")),
    ("B", "Information Technology", ("Computer", "Laptop", "Cell phone", "Password closed",
                                     "Email closed", "System Account closed", "Outstanding items")),
    ("C", "Immigration", ("Passport", "Visa")),
    ("D", "Company Loan / Advance", ("Outstanding Debts", "Other Items")),
    ("E", "Library", ("Drawings", "Manuals", "Reference Books", "Plans", "Other Company Documents")),
    ("F", "Stores", ("All stocks reconciled", "Fuel card", "Others", "Outstanding items")),
    ("G", "Safety Department", ("Uniform", "Other", "Outstanding items")),
    ("H", "Human Resources", ("Staff ID Pass", "Locker keys", "Coupons", "Leave balance",
                              "T&A card returned", "Misc. deductions", "Removed from TA", "NSSF")),
    ("I", "Audit", ("Total cost of all items not returned and loans",)),
    ("J", "Accounts / Salaries", ("Creditors informed", "Suppliers", "Bankers informed", "Co. Loans",
                                  "Cost of items not returned")),
)
SECTION_CODES = tuple(code for code, _name, _items in SECTIONS)
SECTION_NAMES = {code: name for code, name, _items in SECTIONS}

# Who signs each box. On the paper every department initials its own box.
# On the site a box is signed by somebody who holds one of its roles, or by
# HR on the department's behalf from the signed paper, which is what keeps
# a department with nobody on the system from holding an exit up.
BOX_ROLES = {
    "A": ("Head of Department", "Supervisor"),
    "B": ("System Manager",),
    "C": ("HR User", "HR Manager"),
    "D": ("Accounts User", "Accounts Manager", "Finance Officer"),
    "E": ("HR User", "HR Manager"),
    "F": (),
    "G": (),
    "H": ("HR User", "HR Manager"),
    "I": ("Auditor", "Accounts Manager"),
    "J": ("Accounts User", "Accounts Manager", "Finance Officer", "Payroll Officer"),
}
# and the Tool Provider whose Responsible Role signs it as well, where the
# box is a department that issues tools of work (onboarding_rules.PROVIDERS)
BOX_PROVIDERS = {"A": "Department", "B": "IT", "F": "Stores", "G": "EHS", "H": "HR"}
ON_BEHALF = ("HR User", "HR Manager")

DRAFT, PENDING, CLEARED, CANCELLED = "Draft", "Pending", "Cleared", "Cancelled"


def reasons_for(exit_type):
    return REASONS.get(exit_type or VOLUNTARY, REASONS[VOLUNTARY])


def notice_days(months_served):
    """The notice Luuka asks for at this length of service (minutes §4.13)."""
    months = int(months_served or 0)
    for threshold, days in NOTICE_PERIODS:
        if months >= threshold:
            return days
    return 0


def months_served(joined, until):
    joined, until = _date(joined), _date(until)
    if not joined or not until or until < joined:
        return 0
    months = (until.year - joined.year) * 12 + (until.month - joined.month)
    return months - 1 if until.day < joined.day else months


def days_worked(joined, last_day):
    joined, last_day = _date(joined), _date(last_day)
    if not joined or not last_day or last_day < joined:
        return 0
    return (last_day - joined).days + 1


def last_working_day(notice_given, days):
    """The last day of the notice period, both ends counted."""
    given = _date(notice_given)
    if not given or not int(days or 0):
        return given
    return given + datetime.timedelta(days=int(days) - 1)


def notice_served(notice_given, last_day, required_days):
    """The chart's "Notice served as required?" — and by how many days it
    falls short, which is what is deducted from the final pay."""
    given, last = _date(notice_given), _date(last_day)
    required = int(required_days or 0)
    if not given or not last:
        return {"served": not required, "days": 0, "short": required}
    served = (last - given).days + 1
    return {"served": served >= required, "days": max(served, 0),
            "short": max(required - served, 0)}


def separation_errors(facts):
    """Problems with a separation, as user-facing messages.

    facts: "exit_type", "reason", "notice_given", "relieving_date",
    "date_of_joining", "termination_date", "letter_signed_on".
    """
    errors = []
    exit_type = facts.get("exit_type") or VOLUNTARY
    if exit_type not in EXIT_TYPES:
        errors.append("%r is neither a voluntary nor an involuntary exit." % exit_type)
        return errors
    reason = facts.get("reason")
    if not reason:
        errors.append("Say why the employee is leaving.")
    elif reason not in reasons_for(exit_type):
        errors.append("%s is not a reason for %s exit." % (reason, exit_type.lower()))
    joined = _date(facts.get("date_of_joining"))
    leaving = _date(facts.get("relieving_date"))
    if not leaving:
        errors.append("Say the last day of service.")
    elif joined and leaving < joined:
        errors.append("The last day of service is before the day they joined.")
    if exit_type == VOLUNTARY:
        given = _date(facts.get("notice_given"))
        if not given:
            errors.append("Record the date the resignation letter was given.")
        elif leaving and leaving < given:
            errors.append("The last day of service is before the notice was given.")
    else:
        if not facts.get("termination_date"):
            errors.append("Say the date of termination the letter carries.")
        if facts.get("letter_signed_on") and _date(facts["letter_signed_on"]) and leaving \
                and _date(facts["letter_signed_on"]) > leaving:
            errors.append("The letter cannot be signed after the last day of service.")
    return errors


def box_label(code):
    """A box as the form names it: "B Information Technology"."""
    return ("%s %s" % (code or "", SECTION_NAMES.get(code) or "")).strip()


def accounted(row):
    """An item is accounted for once it is returned, marked as not
    applying to this employee, or said to be missing with a remark or a
    cost. The remark the form was drawn up with (a tool's serial number,
    who takes the work over) is not somebody saying what became of it."""
    said = _text(row.get("remarks"))
    return bool(row.get("returned") or row.get("not_applicable") or _num(row.get("cost"))
                or (said and said != _text(row.get("drawn_remarks"))))


def used_sections(rows):
    """The boxes that have anything in them, in the form's own order."""
    have = {row.get("section") for row in rows or []}
    return [code for code in SECTION_CODES if code in have]


def unaccounted(rows):
    """{box: [items]} still to be accounted for, in the form's own order."""
    out = {}
    for code in SECTION_CODES:
        items = [row.get("item") or "An item" for row in rows or []
                 if row.get("section") == code and not accounted(row)]
        if items:
            out[code] = items
    return out


def clearance_errors(facts):
    """What stops a Clearance Form being sent for approval, as user-facing
    messages: the items the employee has not accounted for.

    facts: "rows" of section, item, returned, not_applicable, cost, remarks.
    """
    errors = []
    rows = facts.get("rows") or []
    if not rows:
        errors.append("The form has no items. Use Draw Up Clearance Form on the Employee Separation.")
        return errors
    bad = sorted({str(row.get("section")) for row in rows} - set(SECTION_CODES))
    if bad:
        errors.append("The boxes are A to J. %s is not one of them." % ", ".join(bad))
    if any(not row.get("item") for row in rows):
        errors.append("Every row needs an item.")
    waiting = unaccounted([row for row in rows if row.get("item")])
    for code, items in waiting.items():
        errors.append("%s: %s." % (box_label(code), ", ".join(items)))
    if waiting:
        errors.append("Tick Returned or Not Applicable for each item above, or enter a remark or a cost.")
    return errors


def outstanding_cost(rows):
    """Box I of the form: what everything not returned comes to."""
    return round(sum(_num(row.get("cost")) for row in rows or []
                     if not row.get("returned") and not row.get("not_applicable")), 2)


def cleared_sections(rows, signatures):
    """Which of the ten boxes are done: every item accounted for and the
    box signed."""
    signed = {row.get("section") for row in signatures or [] if row.get("signed_by")}
    waiting = unaccounted(rows)
    return [code for code in used_sections(rows) if code in signed and code not in waiting]


def unsigned_sections(rows, signatures):
    """The boxes in use that nobody has signed yet."""
    signed = {row.get("section") for row in signatures or [] if row.get("signed_by")}
    return [code for code in used_sections(rows) if code not in signed]


def clearance_complete(rows, signatures):
    """Every box that has anything in it is accounted for and signed."""
    used = used_sections(rows)
    return bool(used) and cleared_sections(rows, signatures) == used


def may_sign(code, roles, box_roles=None):
    """Whether the holder of `roles` signs box `code`: one of the box's own
    roles, or HR on the department's behalf."""
    wanted = set(BOX_ROLES.get(code, ()) if box_roles is None else box_roles) | set(ON_BEHALF)
    return bool(wanted & set(roles or ()))


def sign_errors(facts):
    """What stops a box being signed, as user-facing messages.

    facts: "section", "docstatus", "roles" (the user's), "box_roles" (who
    signs this box), "own_form" (the user is the employee leaving),
    "signed" (already), "in_use", "waiting" (its items not accounted for).
    """
    code = facts.get("section")
    label = box_label(code)
    if int(facts.get("docstatus") or 0) != 0:
        return ["The form is closed. No box can be signed."]
    if code not in SECTION_CODES or not facts.get("in_use"):
        return ["%s is not on this form." % (label or "That box")]
    if facts.get("own_form"):
        return ["Nobody signs a box on their own clearance."]
    if not may_sign(code, facts.get("roles"), facts.get("box_roles")):
        return ["%s is signed by its own department or by HR." % label]
    if facts.get("signed"):
        return ["%s is already signed." % label]
    if facts.get("waiting"):
        return ["%s: %s. Tick Returned or Not Applicable for each, or enter a remark or a cost."
                % (label, ", ".join(facts["waiting"]))]
    return []


def unsign_errors(facts):
    """What stops a signature being taken off a box.

    facts: "section", "docstatus", "roles", "signed", "is_signer", "open"
    (HR has not yet approved the form).
    """
    label = box_label(facts.get("section"))
    if int(facts.get("docstatus") or 0) != 0 or not facts.get("open"):
        return ["HR has approved the form. Its signatures stay."]
    if not facts.get("signed"):
        return ["%s is not signed." % label]
    if not (facts.get("is_signer") or set(ON_BEHALF) & set(facts.get("roles") or ())):
        return ["Only HR or whoever signed %s can remove the signature." % label]
    return []


def default_rows(exit_type=None):
    """The ten boxes as LPL/HR/22 prints them, ready to tick."""
    return [{"section": code, "section_name": name, "item": item, "returned": 0}
            for code, name, items in SECTIONS for item in items]


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.date(*(int(part) for part in text.split("-")))
    except (ValueError, TypeError):
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()


# ── Reinstatement (minutes §6.2) ──────────────────────────────────────
# "Accidentally terminated workers cannot be reinstated; permission rests
# only with the Executive Director." Ebizframe could not do it at all; here
# the Executive Director can, and nobody else.
REINSTATER = "Executive Director"
LEFT = "Left"


def reinstatement_errors(facts):
    """Problems with reinstating an employee.

    facts: "status" (the employee's), "roles" (the user's), "reason".
    """
    errors = []
    if facts.get("status") != LEFT:
        errors.append("Only an employee who has left can be reinstated; this one is %s."
                      % (facts.get("status") or "not marked"))
    if REINSTATER not in (facts.get("roles") or ()):
        errors.append("Only the Executive Director can reinstate an employee who has left.")
    if not (facts.get("reason") or "").strip():
        errors.append("Say why the employee is reinstated.")
    return errors


def status_change_errors(old_status, new_status, reinstating=False):
    """An employee who has left comes back only through the Executive
    Director's reinstatement, never by editing the record."""
    if old_status == LEFT and new_status != LEFT and not reinstating:
        return ["Only the Executive Director can reinstate an employee who has left. Use Reinstate on "
                "the employee record."]
    return []
