# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Penalty deductions (Reward and Compensation, §4.11).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_penalties.py exercises them without a bench.

The minutes of 16 and 20 July 2026:

  "Loans, housing, medical insurance, and penalties (such as property loss
  or damages) are treated as deductions in payroll processing. Before an
  employee receives a penalty, the immediate Supervisor reports the case
  to the Human Resource Officer, who calls a hearing with the employee and
  the Supervisor regarding the case. If the employee is found liable, an
  agreement on payment instalments is reached, and an Employee Deduction
  Consent Form is filled in and signed by the employee. The form is
  forwarded by the Human Resource Manager to the Executive Director for
  approval, and then sent back to the Human Resource Officer."

LPL/HR/39, the Employee Deduction Consent, is the form a staff loan is
recovered under too (loan_rules.py): the liability, the reason, the extent
of the deduction, and the declaration the employee signs, which also
agrees that whatever is still owed when they leave comes out of their
terminal benefits. The instalments are a loan's schedule with no interest.
"""

import datetime

LIABLE, NOT_LIABLE = "Liable", "Not Liable"
FINDINGS = (LIABLE, NOT_LIABLE)

# "penalties (such as property loss or damages)"
PROPERTY_LOSS, DAMAGE, OTHER = "Property Loss", "Damage", "Other"
KINDS = (PROPERTY_LOSS, DAMAGE, OTHER)

DRAFT = "Draft"
RECOVERING = "Recovering"
RECOVERED = "Recovered"
REJECTED = "Rejected"
CANCELLED = "Cancelled"
STATUSES = (DRAFT, RECOVERING, RECOVERED, NOT_LIABLE, REJECTED, CANCELLED)

COMPANY = "Luuka Plastics Ltd"


def report_errors(facts):
    """What the supervisor's report says before the HR Officer is asked to
    hear it.

    facts: "employee", "kind", "incident_date", "details", "today".
    """
    errors = []
    if not facts.get("employee"):
        errors.append("Say whose case it is.")
    if facts.get("kind") not in KINDS:
        errors.append("Say what the penalty is for: %s." % _either(KINDS).lower())
    day, today = _date(facts.get("incident_date")), _date(facts.get("today"))
    if not day:
        errors.append("Say when it happened.")
    elif today and day > today:
        errors.append("The date of the incident cannot be after today.")
    if not _text(facts.get("details")):
        errors.append("Say what was lost or damaged, and how.")
    return errors


def hearing_errors(facts):
    """The HR Officer's hearing, with the employee and the supervisor, and
    what it found.

    facts: "hearing_on", "hearing_record", "employee_heard",
    "supervisor_heard", "finding", and for a finding of Liable what was
    agreed: "amount", "instalments", "effective_from".
    """
    errors = []
    if not facts.get("hearing_on"):
        errors.append("Say when the hearing was held.")
    if not _text(_plain(facts.get("hearing_record"))):
        errors.append("Write what was said at the hearing.")
    finding = facts.get("finding")
    if finding not in FINDINGS:
        errors.append("Say whether the employee was found liable.")
    if finding == LIABLE:
        if not facts.get("employee_heard"):
            errors.append("An employee is heard before being found liable: the hearing is with them.")
        if not facts.get("supervisor_heard"):
            errors.append("The hearing is with the supervisor who reported the case as well.")
        errors += agreement_errors(facts)
    return errors


def agreement_errors(facts):
    """The instalments agreed at the hearing.

    facts: "amount", "instalments", "effective_from", "hearing_on".
    """
    errors = []
    if _num(facts.get("amount")) <= 0:
        errors.append("Say how much the employee is liable for.")
    if int(_num(facts.get("instalments"))) <= 0:
        errors.append("Say in how many equal instalments it is recovered.")
    starts, heard = _date(facts.get("effective_from")), _date(facts.get("hearing_on"))
    if not starts:
        errors.append("Say from when the deduction runs.")
    elif heard and starts < heard:
        errors.append("The deduction cannot run from before the hearing that agreed it.")
    return errors


def consent_errors(facts):
    """LPL/HR/39, signed by the employee.

    facts: "liability", "reason", "amount", "instalments",
    "effective_from", "consent", "by_employee" (the employee is the one
    signing on the screen) and "signed_form" (the paper they signed, for
    somebody whose consent HR record for them).
    """
    errors = []
    if not _text(facts.get("liability")):
        errors.append("Write what the employee is liable for (LPL/HR/39: Liability).")
    if not _text(facts.get("reason")):
        errors.append("Write the reason (LPL/HR/39: Reason).")
    errors += agreement_errors({key: facts.get(key) for key in ("amount", "instalments", "effective_from")})
    if not facts.get("consent"):
        errors.append("The employee signs the Employee Deduction Consent before it goes to the "
                      "HR Manager (LPL/HR/39).")
    elif not facts.get("by_employee") and not facts.get("signed_form"):
        errors.append("HR are recording the consent for the employee: attach the LPL/HR/39 they signed.")
    return errors


def declaration(facts):
    """The words the employee agrees to, as LPL/HR/39 has them.

    facts: "employee_name", "amount", "instalments", "effective_from",
    "liability", "year".
    """
    instalments = int(_num(facts.get("instalments")))
    day = _date(facts.get("effective_from"))
    return ("I, %s, do hereby agree to a salary deduction of %s in %d equal instalment(s) effective %s "
            "to cover my liability to %s in respect of %s in the year %s. In the event that I leave this "
            "company for any reason before full recovery of the amount unsettled, I agree that all "
            "outstanding balance be recovered in lump sum from my terminal benefits owed to me."
            % (_text(facts.get("employee_name")) or "the employee", _money(facts.get("amount")), instalments,
               day.strftime("%d %B %Y") if day else "(a date to be agreed)", COMPANY,
               _text(facts.get("liability")).rstrip(".") or "(the liability)",
               facts.get("year") or (day.year if day else "")))


def extent(amount, instalments):
    """LPL/HR/39's "Extent of Deduction", in words."""
    count = int(_num(instalments))
    if _num(amount) <= 0 or count <= 0:
        return None
    each = round(_num(amount) / count, 2)
    return "%s a month for %d month(s)" % (_money(each), count)


def outstanding(amount, recovered):
    return max(round(_num(amount) - _num(recovered), 2), 0.0)


def penalty_status(docstatus, finding, amount, recovered, rejected=False):
    if docstatus == 2:
        return CANCELLED
    if docstatus == 0:
        return DRAFT
    if rejected:
        return REJECTED
    if finding != LIABLE:
        return NOT_LIABLE
    return RECOVERED if not outstanding(amount, recovered) else RECOVERING


def age(born, on):
    born, on = _date(born), _date(on)
    if not (born and on):
        return None
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def _plain(value):
    """A Text Editor's HTML without its tags, so an empty paragraph is empty."""
    text, inside = [], False
    for char in str(value or ""):
        if char == "<":
            inside = True
        elif char == ">":
            inside = False
        elif not inside:
            text.append(char)
    return "".join(text).replace("&nbsp;", " ")


def _either(names):
    names = list(names)
    return names[0] if len(names) == 1 else "%s or %s" % (", ".join(names[:-1]), names[-1])


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    try:
        return datetime.date(*(int(part) for part in str(value)[:10].split("-")))
    except (ValueError, TypeError):
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
