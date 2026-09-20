# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Allowance Application rules (4.3): LPL.HR.31, the travel allowance.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_benefits.py exercises them without a bench.

The process, from the revised flow chart:

  1. The employee creates the allowance request, saying which allowance;
     the HR Officer is told.
  2. Qualified? No, and it ends there. Yes, and it is approved by the
     immediate Supervisor, then the HR Officer, then the General Manager;
     Accounts are told to pay.
  3. Accounts process the payment.
  4. Accounts set the request to Paid, and the HR Officer is told.

The paper is LPL.HR.31: a line per kind of expense, each with the number
of days, the rate and what that comes to, a total, less any advance
already taken, and the balance due to the employee or refundable by them.
"""

import datetime

# The lines LPL.HR.31 prints, which are Expense Claim Types on the site so
# the claim form (benefits_rules.py) shares them.
LODGING = "Lodging"
DAILY = "Daily Allowance"
CONVEYANCE = "Conveyance"
LABOUR = "Labour Charges"
OTHER = "Other Expenses"
ALLOWANCE_LINES = (LODGING, DAILY, CONVEYANCE, LABOUR, OTHER)

DRAFT, PENDING_SUPERVISOR, PENDING_HR, PENDING_GM = (
    "Draft", "Pending Supervisor", "Pending HR Officer", "Pending General Manager")
PENDING_ACCOUNTS, PAID, REJECTED, CANCELLED = "Pending Accounts", "Paid", "Rejected", "Cancelled"

# an employee must be in service, and a request is for days actually spent
MIN_MONTHS_SERVED = 0


def line_amount(days, rate):
    """One line of LPL.HR.31: the days times the rate."""
    return round(_num(days) * _num(rate), 2)


def totals(lines, less_advance=0):
    """The three figures at the foot of the form: the total, what was
    already advanced, and the balance due to the employee (negative means
    they refund it)."""
    total = round(sum(line_amount(row.get("days"), row.get("rate")) or _num(row.get("amount"))
                      for row in lines or []), 2)
    advance = _num(less_advance)
    return {"total": total, "less_advance": advance, "balance": round(total - advance, 2)}


def days_between(start, end):
    """Whole days a trip covers, both ends counted, as the form counts them."""
    start, end = _date(start), _date(end)
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def eligibility_errors(facts):
    """Why this request may not go forward — the chart's "Qualified?".

    facts: "status", "purpose", "start_date", "end_date", "lines",
    "date_of_joining", "today".
    """
    errors = []
    if facts.get("status") and facts["status"] != "Active":
        errors.append("Only an active employee may claim an allowance; this one is %s." % facts["status"])
    if not _text(facts.get("purpose")):
        errors.append("Say what the travel is for (LPL.HR.31: Purpose of Travel).")
    start, end = _date(facts.get("start_date")), _date(facts.get("end_date"))
    if not start or not end:
        errors.append("Give the dates the travel starts and ends.")
    elif end < start:
        errors.append("The travel ends before it starts.")
    lines = facts.get("lines") or []
    if not lines:
        errors.append("An allowance request needs at least one line (lodging, daily allowance, and so on).")
    for index, row in enumerate(lines, 1):
        what = row.get("expense_type") or "line %d" % index
        if not row.get("expense_type"):
            errors.append("Line %d does not say what it is for." % index)
        if line_amount(row.get("days"), row.get("rate")) <= 0 and _num(row.get("amount")) <= 0:
            errors.append("%s comes to nothing: give the days and the rate." % what)
    covered = days_between(start, end) if (start and end) else 0
    if covered and lines:
        # only worth saying once the dates themselves make sense
        for row in lines:
            if _num(row.get("days")) > covered:
                errors.append("%s is claimed for %g day(s) but the travel covers %d."
                              % (row.get("expense_type") or "A line", _num(row.get("days")), covered))
    return errors


def payment_errors(facts):
    """Problems with what Accounts are paying."""
    errors = []
    balance = _num(facts.get("balance"))
    paid = _num(facts.get("paid_amount"))
    if paid and balance and round(paid, 2) > round(balance, 2):
        errors.append("%s is being paid but only %s is due." % (_money(paid), _money(balance)))
    if paid and not facts.get("paid_on"):
        errors.append("Say when the allowance was paid.")
    return errors


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
