# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Allowance Request rules (4.3). No Frappe import, like the other
*_rules.py modules, so scripts/verify_allowances.py exercises them without
a bench.

The process, from the revised flow chart 4.3 (Allowance Application):

  1. The employee creates the allowance request; the HR Officer is told.
  2. Qualified? No, and it ends there. Yes, and it is approved by the
     immediate Supervisor, then the HR Officer, then the General Manager;
     Accounts are told.
  3. Accounts process the payment.
  4. Accounts update the request to Paid, and the HR Officer is told.

What may be asked for, from the minutes (§4.7): field employees working out
in the field are paid lodging, a daily allowance (paid when they set off in
the morning), conveyance, labour charges and other expenses. That is the
Employee Travel Allowance form, LPL.HR.31: a line a kind with its days and
rate, a total, less any advance already taken, and the balance due to the
employee or refundable by them. Everyone may also have an airtime
allowance, a travel allowance, and an acting allowance for standing in for
someone on leave; acting allowances are paid through the payroll.

Each kind is an Allowance Type: whether it needs the trip (the dates and the
destination), whether its rate comes off the per-diem scale for the grade
and the destination (grade_rules.py), whether it names who is stood in for,
and whether Accounts pay it (a journal entry) or the payroll (an Additional
Salary).
"""

import calendar
import datetime

LODGING = "Lodging"
DAILY = "Daily Allowance"
CONVEYANCE = "Conveyance"
LABOUR = "Labour Charges"
OTHER = "Other Expenses"
AIRTIME = "Airtime Allowance"
TRAVEL = "Travel Allowance"
ACTING = "Acting Allowance"
# the lines LPL.HR.31 prints, in its order
FIELD_LINES = (LODGING, DAILY, CONVEYANCE, LABOUR, OTHER)

ACCOUNTS, PAYROLL = "Accounts", "Payroll"
PAID_THROUGH = (ACCOUNTS, PAYROLL)
# the per-diem scale's columns (Per Diem Rate: lodging, daily_allowance, conveyance)
PER_DIEM_COLUMNS = (LODGING, DAILY, CONVEYANCE)


def _type(name, needs_trip=0, per_diem_column="", needs_acting_for=0, paid_through=ACCOUNTS):
    return {"allowance_type": name, "needs_trip": needs_trip, "per_diem_column": per_diem_column,
            "needs_acting_for": needs_acting_for, "paid_through": paid_through}


# The types a site starts with. HR change them on the Allowance Type.
SEED_TYPES = (
    _type(LODGING, needs_trip=1, per_diem_column=LODGING),
    _type(DAILY, needs_trip=1, per_diem_column=DAILY),
    _type(CONVEYANCE, needs_trip=1, per_diem_column=CONVEYANCE),
    _type(LABOUR, needs_trip=1),
    _type(OTHER, needs_trip=1),
    _type(AIRTIME),
    _type(TRAVEL),
    _type(ACTING, needs_acting_for=1, paid_through=PAYROLL),
)

CASH = "Cash"
PAYMENT_METHODS = ("Bank Transfer", "Cheque", "Mobile Money", CASH)
# the payroll month closes on the 25th: an addition is dated that day
PAYROLL_DAY = 25


def line_amount(days, rate):
    """A line: its days times its rate. With no days the rate is the amount,
    as for a month's airtime or a labour charge."""
    days, rate = _num(days), _num(rate)
    return round(days * rate if days > 0 else rate, 2)


def trip_days(start, end):
    """The days the field work or travel covers, both ends counted."""
    start, end = _date(start), _date(end)
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def totals(lines, less_advance=0):
    """The foot of the form. The advance comes off what Accounts pay; what
    the payroll pays is apart. lines: "amount", "paid_through".

    Returns "total", "through_accounts", "through_payroll", "less_advance"
    and "balance": due to the employee, or, when negative, refundable by
    them."""
    total = round(sum(_num(row.get("amount")) for row in lines or ()), 2)
    through_payroll = round(sum(_num(row.get("amount")) for row in lines or ()
                                if row.get("paid_through") == PAYROLL), 2)
    through_accounts = round(total - through_payroll, 2)
    advance = round(_num(less_advance), 2)
    return {"total": total, "through_accounts": through_accounts, "through_payroll": through_payroll,
            "less_advance": advance, "balance": round(through_accounts - advance, 2)}


def eligibility_errors(facts):
    """Why the request cannot go forward, as user-facing messages: the
    chart's "Qualified?". None means it qualifies.

    facts: "status" (the employee's), "employee", "purpose", "lines" (each
    "allowance_type", "days", "amount", "needs_trip", "needs_acting_for",
    "paid_through", "salary_component", "disabled"), "start_date",
    "end_date", "acting_for", "acting_from", "acting_to", "less_advance",
    "advance" (the Employee Advance it comes off), "advance_employee" (whose
    the advance is) and "advance_left" (what is still to settle on it).
    """
    errors = []
    status = facts.get("status")
    if status and status != "Active":
        errors.append("Only an active employee may have an allowance; this one is %s." % status)
    if not _text(facts.get("purpose")):
        errors.append("Say what the allowance is for.")
    lines = list(facts.get("lines") or ())
    if not lines:
        errors.append("Add at least one allowance.")
    covered = 0
    if any(row.get("needs_trip") for row in lines):
        start, end = _date(facts.get("start_date")), _date(facts.get("end_date"))
        if not start or not end:
            errors.append("Give the dates the field work or travel starts and ends.")
        elif end < start:
            errors.append("The travel ends before it starts.")
        else:
            covered = trip_days(start, end)
    for index, row in enumerate(lines, 1):
        what = row.get("allowance_type")
        if not what:
            errors.append("Line %d does not say which allowance it is." % index)
            continue
        if row.get("disabled"):
            errors.append("%s is no longer paid." % what)
        if _num(row.get("amount")) <= 0:
            errors.append("%s comes to nothing: give its rate, and its days where it is paid by the day." % what)
        if row.get("needs_trip") and covered and _num(row.get("days")) > covered:
            errors.append("%s is asked for %g day(s) but the travel covers %d." % (what, _num(row.get("days")),
                                                                                  covered))
        if row.get("paid_through") == PAYROLL and not row.get("salary_component"):
            errors.append("%s is paid through the payroll: set its salary component on the Allowance Type." % what)
    if any(row.get("needs_acting_for") for row in lines):
        if not facts.get("acting_for"):
            errors.append("Say whom the employee stands in for.")
        elif facts.get("acting_for") == facts.get("employee"):
            errors.append("An employee cannot stand in for themselves.")
        acting_from, acting_to = _date(facts.get("acting_from")), _date(facts.get("acting_to"))
        if not acting_from or not acting_to:
            errors.append("Give the days the employee acts from and to.")
        elif acting_to < acting_from:
            errors.append("The acting ends before it starts.")
    advance = _num(facts.get("less_advance"))
    if advance < 0:
        errors.append("The advance taken off cannot be less than nothing.")
    elif advance > 0:
        if not facts.get("advance"):
            errors.append("Pick the advance the amount comes off (Advance Taken).")
        elif facts.get("advance_employee") and facts.get("advance_employee") != facts.get("employee"):
            errors.append("The advance is another employee's.")
        left = facts.get("advance_left")
        if left is not None and advance > _num(left) + 0.005:
            errors.append("Only %s of the advance is left to settle." % _money(left))
    return errors


def payment_errors(facts):
    """What Accounts must give before the request is paid.

    facts: "balance" (what the bank pays, negative when the employee
    refunds), "through_accounts", "payment_account", "payment_method",
    "reference_no", "reference_date", "paid_on", "no_account" (the
    allowances with no expense account for the company), "foreign" (the
    request is in another currency than the company's), "exchange_rate",
    "account_ok" (False when the account is not a bank or cash account of
    the company), "account_currency_ok" (False when it is not in the
    company's currency).
    """
    errors = []
    if not facts.get("paid_on"):
        errors.append("Say when the allowance was paid.")
    if _num(facts.get("through_accounts")) > 0:
        missing = list(facts.get("no_account") or ())
        if missing:
            errors.append("Set the expense account for %s on the Allowance Type." % ", ".join(missing))
    if round(_num(facts.get("balance")), 2) != 0:
        if not facts.get("payment_account"):
            errors.append("Select the bank or cash account the allowance is paid from.")
        elif facts.get("account_ok") is False:
            errors.append("Pay from a bank or cash account of the company.")
        elif facts.get("account_currency_ok") is False:
            errors.append("Pay from an account in the company's currency.")
        method = facts.get("payment_method")
        if method not in PAYMENT_METHODS:
            errors.append("Select the payment method: %s." % ", ".join(PAYMENT_METHODS))
        elif method != CASH and not (facts.get("reference_no") and facts.get("reference_date")):
            errors.append("Enter the payment's reference number and its date.")
    if facts.get("foreign") and _num(facts.get("exchange_rate")) <= 0:
        errors.append("Give the exchange rate the allowance is paid at.")
    return errors


def journal_rows(lines, less_advance=0, rate=1):
    """The payment's journal entry, in the company's currency: each expense
    account debited with its lines, the advance credited with what it
    settles, and the bank credited with the rest (debited, when the
    employee refunds). lines: "expense_account", "amount", "paid_through".

    Returns {"expenses": [(account, amount)], "advance": amount,
    "bank": amount}, the bank figure making the entry balance."""
    rate = _num(rate) or 1.0
    by_account = {}
    for row in lines or ():
        if row.get("paid_through") == PAYROLL:
            continue
        account = row.get("expense_account")
        by_account[account] = by_account.get(account, 0.0) + _num(row.get("amount"))
    expenses = [(account, round(amount * rate, 2)) for account, amount in by_account.items()
                if round(amount * rate, 2)]
    advance = round(_num(less_advance) * rate, 2)
    bank = round(sum(amount for _account, amount in expenses) - advance, 2)
    return {"expenses": expenses, "advance": advance, "bank": bank}


def advance_left(paid, claimed=0, returned=0):
    """What an Employee Advance still has to settle: what was paid out, less
    what was claimed against it and what came back."""
    return round(max(_num(paid) - _num(claimed) - _num(returned), 0.0), 2)


def type_errors(facts):
    """What is wrong with an Allowance Type, as user-facing messages.

    facts: "paid_through", "salary_component", "component_type" (Earning or
    Deduction), "accounts" (each "company", "account", "account_company",
    "is_group").
    """
    errors = []
    if facts.get("paid_through") not in PAID_THROUGH:
        errors.append("Say whether Accounts or the payroll pay it.")
    if facts.get("paid_through") == PAYROLL:
        if not facts.get("salary_component"):
            errors.append("An allowance the payroll pays needs its salary component.")
        elif facts.get("component_type") and facts["component_type"] != "Earning":
            errors.append("%s is not an earning." % facts["salary_component"])
    seen = set()
    for row in facts.get("accounts") or ():
        company = row.get("company")
        if company in seen:
            errors.append("%s has two expense accounts." % company)
        seen.add(company)
        if row.get("account_company") and row["account_company"] != company:
            errors.append("%s is not an account of %s." % (row.get("account"), company))
        elif row.get("is_group"):
            errors.append("%s is a group account." % row.get("account"))
    return errors


def payroll_date(day):
    """The payroll month a day falls in: its closing day, the 25th on or
    after it."""
    day = _date(day)
    if not day:
        return None
    if day.day <= PAYROLL_DAY:
        return datetime.date(day.year, day.month, PAYROLL_DAY)
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return datetime.date(year, month, min(PAYROLL_DAY, calendar.monthrange(year, month)[1]))


def status_for(docstatus, workflow_state):
    """Where a request stands, for the list."""
    if int(docstatus or 0) == 2:
        return "Cancelled"
    return workflow_state or "Draft"


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
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
