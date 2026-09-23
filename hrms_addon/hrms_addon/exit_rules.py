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


def clearance_errors(facts):
    """Problems with a Clearance Form, as user-facing messages.

    facts: "rows" of section, item, returned, cost; "sections" of section,
    signed_by; "employee".
    """
    errors = []
    rows = facts.get("rows") or []
    if not rows:
        errors.append("A clearance form has nothing on it. Draw up the ten boxes LPL/HR/22 prints.")
        return errors
    bad = sorted({row.get("section") for row in rows} - set(SECTION_CODES))
    if bad:
        errors.append("LPL/HR/22 has boxes A to J; %s is not one of them." % ", ".join(str(b) for b in bad))
    for row in rows:
        if not row.get("item"):
            errors.append("A row in box %s does not say what it is." % (row.get("section") or "?"))
        if not row.get("returned") and not _text(row.get("remarks")) and not _num(row.get("cost")):
            errors.append("%s is not returned: say what became of it, or what it costs."
                          % (row.get("item") or "An item"))
    return errors


def outstanding_cost(rows):
    """Box I of the form: what everything not returned comes to."""
    return round(sum(_num(row.get("cost")) for row in rows or [] if not row.get("returned")), 2)


def cleared_sections(rows, signatures):
    """Which of the ten boxes are done: every item accounted for and the
    box signed."""
    signed = {row.get("section") for row in signatures or [] if row.get("signed_by")}
    done = []
    for code in SECTION_CODES:
        items = [row for row in rows or [] if row.get("section") == code]
        if not items:
            continue
        accounted = all(row.get("returned") or _text(row.get("remarks")) or _num(row.get("cost"))
                        for row in items)
        if accounted and code in signed:
            done.append(code)
    return done


def clearance_complete(rows, signatures):
    """Every box that has anything in it is accounted for and signed."""
    used = sorted({row.get("section") for row in rows or [] if row.get("section") in SECTION_CODES})
    return used and cleared_sections(rows, signatures) == used


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
