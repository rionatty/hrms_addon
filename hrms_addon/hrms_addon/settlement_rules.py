# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Cessation Benefits rules (4.9): the Full and Final Settlement
Agreement, LPL/HR/20.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_exits.py exercises them without a bench.

The process, from the revised flow chart:

  1. The employee serves a notice. Served as required or not, the process
     goes on; what differs is what comes off the final pay.
  2. The system makes the employee inactive and takes them off the payroll.
  3. Accounts work out the benefits due and the deductions to be made.
  4. The employee confirms and signs the severance / full and final pay.
  5. The Executive Director approves the benefits and the deductions.
  6. The Payroll Officer schedules the payment in the next payroll run.

LPL/HR/20 names what the settlement is made of: "my final salary, leave
encashment, notice pay, severance pay and any net claims ... less any
statutory deductions (NSSF, PAYE, Local Service Tax)".

The formulas here are the Employment Act minima and common Luuka practice.
They are defaults the Payroll Officer may overwrite on the statement, not
a rule this module enforces: what an employee is owed is what their
contract and the law say.
"""

import datetime

# what LPL/HR/20 lists, in its own order
FINAL_SALARY = "Final Salary"
LEAVE_ENCASHMENT = "Leave Encashment"
NOTICE_PAY = "Notice Pay"
SEVERANCE_PAY = "Severance Pay"
NET_CLAIMS = "Net Claims"
PAYABLES = (FINAL_SALARY, LEAVE_ENCASHMENT, NOTICE_PAY, SEVERANCE_PAY, NET_CLAIMS)

# and what comes off it
NOTICE_SHORTFALL = "Notice Not Served"
ADVANCES = "Advances Outstanding"
LOANS = "Loans Outstanding"
UNRETURNED = "Items Not Returned"
NSSF = "NSSF"
PAYE = "PAYE"
LST = "Local Service Tax"
RECEIVABLES = (NOTICE_SHORTFALL, ADVANCES, LOANS, UNRETURNED)
STATUTORY = (NSSF, PAYE, LST)

# Luuka's working month, the same one the attendance register counts by
WORKING_DAYS_A_MONTH = 26
# a month's pay for each year served, pro-rated for part of a year
SEVERANCE_MONTHS_A_YEAR = 1.0
# severance is earned after six months of continuous service
SEVERANCE_AFTER_MONTHS = 6

DRAFT, PENDING, APPROVED, SCHEDULED, PAID, CANCELLED = (
    "Draft", "Pending", "Approved", "Scheduled", "Paid", "Cancelled")


def daily_rate(gross, working_days=WORKING_DAYS_A_MONTH):
    return round(_num(gross) / float(working_days or WORKING_DAYS_A_MONTH), 2)


def final_salary(gross, days_worked_in_month, working_days=WORKING_DAYS_A_MONTH):
    """The part-month worked up to the last day of service."""
    return round(daily_rate(gross, working_days) * _num(days_worked_in_month), 2)


def leave_encashment(gross, days, working_days=WORKING_DAYS_A_MONTH):
    """What the untaken leave days are worth."""
    return round(daily_rate(gross, working_days) * _num(days), 2)


def notice_pay(gross, days_short, working_days=WORKING_DAYS_A_MONTH):
    """Pay in lieu where the company cut the notice short."""
    return round(daily_rate(gross, working_days) * _num(days_short), 2)


def severance_pay(gross, months_of_service, months_a_year=SEVERANCE_MONTHS_A_YEAR):
    """A month's pay for each year served, pro-rated, once six months of
    continuous service are behind them."""
    months = int(months_of_service or 0)
    if months < SEVERANCE_AFTER_MONTHS:
        return 0.0
    return round(_num(gross) * float(months_a_year) * (months / 12.0), 2)


def totals(payables, receivables):
    """The foot of the computation: what is due, what comes off, and the
    net the employee signs for."""
    due = round(sum(_num(row.get("amount")) for row in payables or []), 2)
    off = round(sum(_num(row.get("amount")) for row in receivables or []), 2)
    return {"payable": due, "receivable": off, "net": round(due - off, 2)}


def suggest(facts):
    """What Accounts would normally work out, as two lists of rows. The
    Payroll Officer may change any of it on the statement.

    facts: "gross_pay", "days_worked_in_month", "leave_balance",
    "months_served", "notice_short_days", "notice_cut_days",
    "advances_outstanding", "loans_outstanding", "unreturned_cost",
    "net_claims".
    """
    gross = _num(facts.get("gross_pay"))
    payables = [
        {"component": FINAL_SALARY,
         "amount": final_salary(gross, facts.get("days_worked_in_month"))},
        {"component": LEAVE_ENCASHMENT,
         "amount": leave_encashment(gross, facts.get("leave_balance"))},
        {"component": NOTICE_PAY, "amount": notice_pay(gross, facts.get("notice_cut_days"))},
        {"component": SEVERANCE_PAY, "amount": severance_pay(gross, facts.get("months_served"))},
        {"component": NET_CLAIMS, "amount": _num(facts.get("net_claims"))},
    ]
    receivables = [
        {"component": NOTICE_SHORTFALL, "amount": notice_pay(gross, facts.get("notice_short_days"))},
        {"component": ADVANCES, "amount": _num(facts.get("advances_outstanding"))},
        {"component": LOANS, "amount": _num(facts.get("loans_outstanding"))},
        {"component": UNRETURNED, "amount": _num(facts.get("unreturned_cost"))},
    ]
    return {"payables": [row for row in payables if row["amount"]],
            "receivables": [row for row in receivables if row["amount"]]}


def settlement_errors(facts):
    """Problems with a settlement, as user-facing messages.

    facts: "relieving_date", "date_of_joining", "payables", "receivables",
    "net", "clearance", "account_name", "bank_name", "account_number".
    """
    errors = []
    if not facts.get("relieving_date"):
        errors.append("Say the last day of service.")
    payables = facts.get("payables") or []
    if not payables:
        errors.append("A settlement with nothing due on it is not a settlement.")
    for row in payables + (facts.get("receivables") or []):
        if not row.get("component"):
            errors.append("A line of the computation does not say what it is for.")
        if _num(row.get("amount")) < 0:
            errors.append("%s is a negative amount; put it on the other side instead."
                          % (row.get("component") or "A line"))
    figures = totals(payables, facts.get("receivables"))
    if figures["net"] < 0:
        errors.append("The deductions come to more than is due: %s is owed to the company, "
                      "which is not a full and final settlement."
                      % _money(-figures["net"]))
    if not facts.get("clearance"):
        errors.append("The Clearance Form comes first (LPL/HR/22): it says what is still outstanding.")
    return errors


def payment_errors(facts):
    """LPL/HR/20: the money is remitted to the employee's own account, so
    the account must be on the agreement before it is approved."""
    errors = []
    for field, label in (("account_name", "Account Name"), ("bank_name", "Bank Name"),
                         ("account_number", "Account Number")):
        if not _text(facts.get(field)):
            errors.append("LPL/HR/20 remits to the employee's account: give the %s." % label)
    if not facts.get("employee_signed"):
        errors.append("The employee confirms and signs the computation before it goes to the "
                      "Executive Director (step 4).")
    return errors


def schedule_errors(facts):
    errors = []
    if not facts.get("payroll_date"):
        errors.append("Say which payroll run the settlement is paid in.")
    if not facts.get("approved"):
        errors.append("The Executive Director approves the benefits and deductions before they are "
                      "scheduled (step 5).")
    return errors


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
