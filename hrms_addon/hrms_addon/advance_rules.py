# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Advances: leave advance (4.2), salary advance (4.10) and the special
advance the paper calls a loan (LPL/HR/21).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_leave.py exercises them without a bench.

All three are one document — Frappe HR's own Employee Advance — because
all three are the same thing: money paid before it is earned and recovered
from the payroll afterwards. What differs is why it is asked for and who
signs, so the Advance Type says which, and the workflow carries all three
chains (advance_approval.py).

  Leave Advance     the HR Officer raises it from the employee's leave form,
                    the Accounts Manager approves, the Payroll Officer
                    processes it and Accounts/Finance pays.
  Salary Advance    the employee asks; the system checks they qualify; the
                    HR Officer confirms attendance and leave; the Payroll
                    Officer sets the amount approved and Finance pays.
  Special Advance   LPL/HR/21, sanctioned by the Section Head and then the
                    Executive Director, recovered over up to three months.

The recovery is what makes an advance an advance: an amount, the number of
equal instalments and the month the first one is taken.
"""

import datetime

LEAVE_ADVANCE = "Leave Advance"
SALARY_ADVANCE = "Salary Advance"
SPECIAL_ADVANCE = "Special Advance"
ADVANCE_TYPES = (LEAVE_ADVANCE, SALARY_ADVANCE, SPECIAL_ADVANCE)

# Luuka's policy, as the Special Advance Form works it: no more than half
# a month's gross, recovered in at most three months, and nothing while an
# advance of the same kind is still being recovered.
DEFAULT_LIMIT_FRACTION = 0.5
MAX_INSTALMENTS = 3
DEFAULT_INSTALMENTS = 1
# a new employee is not advanced against a salary they have not yet earned
MIN_MONTHS_SERVED = 3

ACTIVE = "Active"

# where an advance stands
DRAFT, PENDING, APPROVED, PAID, RECOVERING, RECOVERED, REJECTED = (
    "Draft", "Pending", "Approved", "Paid", "Recovering", "Recovered", "Rejected")


def months_served(joined, today):
    joined, today = _date(joined), _date(today)
    if not joined or not today or today < joined:
        return 0
    months = (today.year - joined.year) * 12 + (today.month - joined.month)
    return months - 1 if today.day < joined.day else months


def limit_for(gross, fraction=DEFAULT_LIMIT_FRACTION):
    """The most this employee may be advanced at once."""
    return round(_num(gross) * float(fraction), 2)


def eligibility_errors(facts):
    """Why this employee may not take an advance, as user-facing messages.
    An empty list means they qualify — the chart's "Qualify for advance?".

    facts: "advance_type", "status", "date_of_joining", "today",
    "gross_pay", "amount", "outstanding", "instalments",
    "limit_fraction", "min_months".
    """
    errors = []
    kind = facts.get("advance_type") or SALARY_ADVANCE
    if facts.get("status") and facts["status"] != ACTIVE:
        errors.append("Only an active employee may be advanced; this one is %s." % facts["status"])
    minimum = facts.get("min_months")
    minimum = MIN_MONTHS_SERVED if minimum is None else int(minimum)
    served = months_served(facts.get("date_of_joining"), facts.get("today"))
    if minimum and served < minimum:
        errors.append("An advance is given after %d month(s) of service; this employee has served %d."
                      % (minimum, served))
    amount = _num(facts.get("amount"))
    if amount <= 0:
        errors.append("Say how much is being asked for.")
    gross = _num(facts.get("gross_pay"))
    if gross:
        ceiling = limit_for(gross, facts.get("limit_fraction") or DEFAULT_LIMIT_FRACTION)
        if amount > ceiling:
            errors.append("The most that may be advanced is %s, being %g%% of a gross of %s."
                          % (_money(ceiling), float(facts.get("limit_fraction") or DEFAULT_LIMIT_FRACTION) * 100,
                             _money(gross)))
    outstanding = _num(facts.get("outstanding"))
    if outstanding > 0:
        errors.append("%s is still owed on an earlier advance. It is recovered before another is given."
                      % _money(outstanding))
    instalments = int(facts.get("instalments") or 0)
    if instalments > MAX_INSTALMENTS:
        errors.append("An advance is recovered in at most %d month(s)." % MAX_INSTALMENTS)
    if kind not in ADVANCE_TYPES:
        errors.append("%r is not one of Luuka's advances." % kind)
    return errors


def recovery_schedule(amount, instalments, first_month):
    """[(month, amount)] — equal instalments, the rounding on the last one
    so the parts add back to the whole."""
    amount = round(_num(amount), 2)
    instalments = max(1, int(instalments or DEFAULT_INSTALMENTS))
    month = _date(first_month)
    if not month or amount <= 0:
        return []
    each = round(amount / instalments, 2)
    rows, taken = [], 0.0
    for n in range(instalments):
        due = each if n < instalments - 1 else round(amount - taken, 2)
        taken = round(taken + due, 2)
        rows.append((add_months(month, n), due))
    return rows


def outstanding(amount, recovered):
    return round(max(_num(amount) - _num(recovered), 0), 2)


def advance_status(docstatus, paid, amount, recovered, rejected=False):
    """Where an advance stands, from what has been paid and recovered."""
    if docstatus == 2:
        return REJECTED if rejected else DRAFT
    if docstatus == 0:
        return DRAFT
    if rejected:
        return REJECTED
    if not _num(paid):
        return APPROVED
    left = outstanding(amount, recovered)
    if not left:
        return RECOVERED
    return RECOVERING if _num(recovered) else PAID


def sanctioned(section_head, executive_director, asked):
    """LPL/HR/21: two people write an amount sanctioned. The lower of the
    two stands, and neither may sanction more than was asked for."""
    amounts = [_num(value) for value in (section_head, executive_director) if _num(value) > 0]
    if not amounts:
        return _num(asked)
    return round(min(min(amounts), _num(asked) or min(amounts)), 2)


def sanction_errors(facts):
    """Problems with what was sanctioned."""
    errors = []
    asked = _num(facts.get("amount"))
    for field, who in (("section_head_amount", "Section Head"), ("ed_amount", "Executive Director")):
        value = _num(facts.get(field))
        if value and asked and value > asked:
            errors.append("The %s sanctioned more than the %s asked for." % (who, _money(asked)))
    paid = _num(facts.get("paid_amount"))
    allowed = sanctioned(facts.get("section_head_amount"), facts.get("ed_amount"), asked)
    if paid and allowed and paid > allowed:
        errors.append("%s is being paid but only %s was sanctioned." % (_money(paid), _money(allowed)))
    return errors


def add_months(day, months):
    day = _date(day)
    if not day:
        return None
    month = day.month - 1 + int(months)
    year = day.year + month // 12
    month = month % 12 + 1
    last = _days_in_month(year, month)
    return datetime.date(year, month, min(day.day, last))


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


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
