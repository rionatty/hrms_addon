# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Benefits Administration rules (4.7): the Employees Claim Form
(LPL/HR/27), and the two things the test script asks for beside it.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_benefits.py exercises them without a bench.

The process, from the revised flow chart and the test script:

  1. The employee raises a claim in the system.
  2. It is approved by the immediate Supervisor, the Head of Department,
     the HR Officer or Manager, and last the General Manager; Accounts are
     then told.
  3. Accounts process the payment and set the claim to Paid, and the HR
     Officer is told.

The chart draws three approvers (HOD, HRM, GM); the test script written
after it adds the immediate supervisor first. The script is the later word
and the fuller one, so the chain here is Supervisor, HOD, HR, GM — the
chart's three are all in it, in their order.

Two recommendations came with the script and are rules here:

  * "Wedding gifts and claims that are standard especially for production
    can be updated on the system" — a claim type may carry a standard
    amount, and a standard claim is checked against it.
  * "System should be able to track birthdays and send notifications" —
    whose birthday falls on a day, counting the 29th of February on the
    28th in a year that has no 29th.
"""

import datetime

DRAFT, PENDING_SUPERVISOR, PENDING_HOD = "Draft", "Pending Supervisor", "Pending HOD"
PENDING_HR, PENDING_GM, PENDING_ACCOUNTS = "Pending HR", "Pending General Manager", "Pending Accounts"
PAID, REJECTED, CANCELLED = "Paid", "Rejected", "Cancelled"

# the occasions Luuka pay a standard claim for
WEDDING = "Wedding"
BEREAVEMENT = "Bereavement"
BIRTH = "Birth"
SICKNESS = "Sickness"
OTHER = "Other"
OCCASIONS = (WEDDING, BEREAVEMENT, BIRTH, SICKNESS, OTHER)

# how many days before a birthday the reminder goes out
BIRTHDAY_HORIZONS = (7, 0)


def claim_errors(facts):
    """Problems with a claim, as user-facing messages.

    facts: "claim_details", "reason", "amount", "claim_type",
    "standard_amount", "is_standard", "requires_evidence", "evidence".
    """
    errors = []
    if not _text(facts.get("claim_details")):
        errors.append("Write what is being claimed and when (LPL/HR/27: Claimed details/date).")
    if not _text(facts.get("reason")):
        errors.append("Write the reason for the claim.")
    amount = _num(facts.get("amount"))
    if amount <= 0:
        errors.append("A claim needs an amount.")
    if facts.get("is_standard"):
        standard = _num(facts.get("standard_amount"))
        if standard and round(amount, 2) > round(standard, 2):
            errors.append("%s is a standard claim of %s; %s is being claimed."
                          % (facts.get("claim_type") or "This", _money(standard), _money(amount)))
    if facts.get("requires_evidence") and not facts.get("evidence"):
        errors.append("%s is paid on evidence: attach it." % (facts.get("claim_type") or "This claim"))
    return errors


def standard_amount(claim_type, types):
    """What a standard claim is worth, or None where it is not standard."""
    row = (types or {}).get(claim_type) or {}
    return _num(row.get("standard_amount")) if row.get("is_standard") else None


def genuine_errors(facts):
    """The line LPL/HR/27 calls "Genuine-to be paid or not approved": the
    supervisor says so before anyone above them signs."""
    if facts.get("genuine") is None:
        return ["Say whether the claim is genuine before passing it on (LPL/HR/27)."]
    if not facts.get("genuine") and not _text(facts.get("supervisor_remarks")):
        return ["A claim found not genuine needs the supervisor's remarks saying why."]
    return []


def payment_errors(facts):
    errors = []
    sanctioned = _num(facts.get("sanctioned_amount")) or _num(facts.get("amount"))
    paid = _num(facts.get("paid_amount"))
    if paid and sanctioned and round(paid, 2) > round(sanctioned, 2):
        errors.append("%s is being paid but only %s was approved." % (_money(paid), _money(sanctioned)))
    if paid and not facts.get("paid_on"):
        errors.append("Say when the claim was paid.")
    return errors


def birthday_on(date_of_birth, day):
    """Is this the employee's birthday? Someone born on the 29th of
    February has it on the 28th in a year that has no 29th."""
    born, day = _date(date_of_birth), _date(day)
    if not born or not day:
        return False
    if born.month == day.month and born.day == day.day:
        return True
    if born.month == 2 and born.day == 29 and day.month == 2 and day.day == 28:
        return not _is_leap(day.year)
    return False


def birthdays_due(employees, day, horizons=BIRTHDAY_HORIZONS):
    """[(employee, days away)] for the birthdays a horizon away from `day`.

    employees: rows of "name" and "date_of_birth".
    """
    day = _date(day)
    if not day:
        return []
    out = []
    for row in employees or []:
        for ahead in horizons:
            if birthday_on(row.get("date_of_birth"), day + datetime.timedelta(days=int(ahead))):
                out.append((row.get("name"), int(ahead)))
                break
    return out


def age_on(date_of_birth, day):
    born, day = _date(date_of_birth), _date(day)
    if not born or not day:
        return None
    years = day.year - born.year
    if (day.month, day.day) < (born.month, born.day):
        years -= 1
    return years


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


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


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
