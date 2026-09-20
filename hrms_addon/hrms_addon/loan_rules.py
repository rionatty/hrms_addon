# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Loans Application rules (4.4).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_loans.py exercises them without a bench.

The process, from the revised flow chart and the test script:

  1. The employee creates a loan request; the Head of Department is told.
  2. It is approved by the HOD, then the Executive Director, then the
     General Manager. Not approved, and it goes back to the employee.
  3. Accounts set the terms actually discussed with the employee — the
     amount, the rate and how many months — and the HR Officer is told.
  4. The employee consents to the deduction (LPL/HR/39), and the HR
     Officer and the accountant are told.
  5. The HR or Payroll Officer runs the loan: the repayment schedule
     becomes a monthly deduction on the payroll.
  6. The system watches the loan's life and tells the HR Officer and the
     employee about the payments.

Luuka's staff loans carry no interest by default; where a rate is set it
is flat — the whole term's interest worked out once and spread evenly —
because that is how the Special Advance Form's recovery lines read.
"""

import datetime

DRAFT = "Draft"
RUNNING = "Running"
REPAID = "Repaid"
WRITTEN_OFF = "Written Off"
CANCELLED = "Cancelled"
STATUSES = (DRAFT, RUNNING, REPAID, WRITTEN_OFF, CANCELLED)

# Luuka's policy: a loan of at most three months' gross, recovered over at
# most a year, and only once an earlier loan is cleared.
MAX_MONTHS_OF_GROSS = 3
MAX_INSTALMENTS = 12
DEFAULT_INSTALMENTS = 6
MIN_MONTHS_SERVED = 6
DEFAULT_RATE = 0.0


def limit_for(gross, months=MAX_MONTHS_OF_GROSS):
    return round(_num(gross) * float(months), 2)


def months_served(joined, today):
    joined, today = _date(joined), _date(today)
    if not joined or not today or today < joined:
        return 0
    months = (today.year - joined.year) * 12 + (today.month - joined.month)
    return months - 1 if today.day < joined.day else months


def eligibility_errors(facts):
    """Why this employee may not take a loan, as user-facing messages. An
    empty list means they qualify — the chart's "Approved?" rests on it.

    facts: "status", "date_of_joining", "today", "gross_pay", "amount",
    "outstanding", "instalments", "purpose".
    """
    errors = []
    if facts.get("status") and facts["status"] != "Active":
        errors.append("Only an active employee may take a loan; this one is %s." % facts["status"])
    served = months_served(facts.get("date_of_joining"), facts.get("today"))
    minimum = facts.get("min_months")
    minimum = MIN_MONTHS_SERVED if minimum is None else int(minimum)
    if minimum and served < minimum:
        errors.append("A loan is given after %d month(s) of service; this employee has served %d."
                      % (minimum, served))
    amount = _num(facts.get("amount"))
    if amount <= 0:
        errors.append("Say how much is being asked for.")
    gross = _num(facts.get("gross_pay"))
    if gross:
        ceiling = limit_for(gross, facts.get("max_months") or MAX_MONTHS_OF_GROSS)
        if amount > ceiling:
            errors.append("The most that may be lent is %s, being %d month(s) of a gross of %s."
                          % (_money(ceiling), facts.get("max_months") or MAX_MONTHS_OF_GROSS, _money(gross)))
    outstanding = _num(facts.get("outstanding"))
    if outstanding > 0:
        errors.append("%s is still owed on an earlier loan. It is cleared before another is given."
                      % _money(outstanding))
    instalments = int(facts.get("instalments") or 0)
    if instalments > MAX_INSTALMENTS:
        errors.append("A loan is recovered over at most %d month(s)." % MAX_INSTALMENTS)
    if not _text(facts.get("purpose")):
        errors.append("Say what the loan is for.")
    return errors


def interest_for(principal, rate, instalments):
    """Flat interest over the whole term."""
    if not _num(rate) or not int(instalments or 0):
        return 0.0
    return round(_num(principal) * _num(rate) / 100.0 * (int(instalments) / 12.0), 2)


def repayment_schedule(principal, rate, instalments, first_month):
    """[(month, principal, interest, total)] — equal instalments, the
    rounding on the last one so the parts add back to the whole."""
    principal = round(_num(principal), 2)
    instalments = max(1, int(instalments or DEFAULT_INSTALMENTS))
    month = _date(first_month)
    if not month or principal <= 0:
        return []
    interest = interest_for(principal, rate, instalments)
    each_principal = round(principal / instalments, 2)
    each_interest = round(interest / instalments, 2)
    rows, taken_p, taken_i = [], 0.0, 0.0
    for n in range(instalments):
        last = n == instalments - 1
        due_p = round(principal - taken_p, 2) if last else each_principal
        due_i = round(interest - taken_i, 2) if last else each_interest
        taken_p, taken_i = round(taken_p + due_p, 2), round(taken_i + due_i, 2)
        rows.append((add_months(month, n), due_p, due_i, round(due_p + due_i, 2)))
    return rows


def monthly_instalment(principal, rate, instalments):
    """Nothing until the months are settled: a loan with no term has no
    monthly instalment, and guessing one puts a wrong figure on the
    consent form."""
    if not int(instalments or 0):
        return 0.0
    schedule = repayment_schedule(principal, rate, instalments, "2000-01-31")
    return schedule[0][3] if schedule else 0.0


def outstanding(amount, recovered):
    return round(max(_num(amount) - _num(recovered), 0), 2)


def loan_status(docstatus, amount, recovered, written_off=False):
    if docstatus == 2:
        return CANCELLED
    if docstatus == 0:
        return DRAFT
    if written_off:
        return WRITTEN_OFF
    return REPAID if not outstanding(amount, recovered) else RUNNING


def consent_errors(facts):
    """LPL/HR/39, the Employee Deduction Consent: it says what the
    liability is, how much comes off, in how many instalments and from
    when, and it is the employee who agrees to it."""
    errors = []
    if not _text(facts.get("liability")):
        errors.append("Write what the deduction is for (LPL/HR/39: Liability).")
    if _num(facts.get("amount")) <= 0:
        errors.append("The consent must say how much is deducted.")
    if int(facts.get("instalments") or 0) <= 0:
        errors.append("The consent must say in how many equal instalments.")
    if not facts.get("effective_from"):
        errors.append("The consent must say from when the deduction runs.")
    if not facts.get("consent"):
        errors.append("The employee consents to the deduction before the loan runs (LPL/HR/39).")
    return errors


def terms_errors(facts):
    """What Accounts settled with the employee, checked against what was
    asked for."""
    errors = []
    asked = _num(facts.get("amount"))
    approved = _num(facts.get("approved_amount"))
    if approved and asked and approved > asked:
        errors.append("%s is being lent but only %s was asked for." % (_money(approved), _money(asked)))
    if approved <= 0:
        errors.append("Set the amount actually being lent.")
    if int(facts.get("instalments") or 0) <= 0:
        errors.append("Say in how many months the loan is recovered.")
    if not facts.get("first_repayment"):
        errors.append("Say which month the first repayment comes off.")
    if _num(facts.get("rate")) < 0:
        errors.append("A rate cannot be negative.")
    return errors


def add_months(day, months):
    day = _date(day)
    if not day:
        return None
    month = day.month - 1 + int(months)
    year = day.year + month // 12
    month = month % 12 + 1
    return datetime.date(year, month, min(day.day, _days_in_month(year, month)))


def _days_in_month(year, month):
    if month == 12:
        return 31
    return (datetime.date(year + month // 12, month % 12 + 1, 1) - datetime.timedelta(days=1)).day


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
