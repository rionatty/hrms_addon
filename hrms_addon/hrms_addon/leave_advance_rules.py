# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Advance: part of the salary paid ahead of a leave, and taken back
from the payroll afterwards (minutes of 16 and 20 July 2026, §4.4).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_leave_advance.py exercises them without a bench.

The process, as the minutes give it:

  1. On the Leave Application Form the employee ticks the leave advance.
  2. Once the leave is approved, the HR Officer forwards the form to the
     Accounts Manager, who works out 60% of the employee's gross salary
     (for the Per Meter category, of the average gross of the previous two
     months) and records the amount on the form.
  3. The Payroll Officer prepares an Excel file of employee number, name,
     bank code, account number and amount, and forwards it to Finance.
  4. Finance pays. The advance is taken back from the payroll in the months
     agreed.

Only regular employees, with no bank or company loan, taking more than 19
days of accrued leave, qualify.

Here the Leave Advance is its own document, apart from the loans and the
other advances: it is raised from the approved leave, the Accounts Manager
approves it, the Leave Advance Processing is the Payroll Officer's file for
Finance and makes one bank entry, and when Finance submits that entry each
advance's deductions go onto the payroll for its months.

Every number is a setting (Leave Management Settings); DEFAULTS is what each
is until someone changes it.
"""

import calendar
import datetime

DEFAULTS = {
    "advance_percent": 60.0,
    "per_meter_months": 2,
    "more_than_days": 19,
    "regular_only": 1,
    "no_loans": 1,
    "instalments": 1,
    "max_instalments": 3,
    "raise_on_approval": 1,
}

MONTHLY, PER_METER = "Monthly", "Per Meter"
ACTIVE = "Active"

DRAFT = "Draft"
PENDING = "Pending Accounts Manager"
APPROVED = "Approved"
REJECTED = "Rejected"
PROCESSING = "In Processing"
PAID = "Paid"
RECOVERING = "Recovering"
RECOVERED = "Recovered"
CANCELLED = "Cancelled"
STATUSES = (DRAFT, PENDING, APPROVED, REJECTED, PROCESSING, PAID, RECOVERING, RECOVERED, CANCELLED)

RUN_DRAFT, RUN_SENT, RUN_PAID, RUN_CANCELLED = "Draft", "Sent to Finance", "Paid", "Cancelled"
RUN_STATUSES = (RUN_DRAFT, RUN_SENT, RUN_PAID, RUN_CANCELLED)

PAYMENT_METHODS = ("Bank Transfer", "Cheque", "Cash")
BANK = "Bank"
# the payroll month closes on the 25th: a deduction is dated that day
PAYROLL_DAY = 25
RECOVERY_COMPONENT = "Leave Advance Recovery"
RECOVERY_ABBR = "LAR"
ACCOUNT_NAME = "Leave Advances"

BANK_FILE_HEADER = ("Employee No", "Employee Name", "Bank Code", "Account Number", "Amount")


def settings_from(stored=None):
    """Leave Management Settings as the rules read them: what was saved
    stands, anything never saved takes its default, a saved nought is a
    nought."""
    stored = stored or {}
    merged = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        value = stored.get(key)
        if value is None or value == "":
            continue
        try:
            merged[key] = float(value) if isinstance(default, float) else int(float(value))
        except (TypeError, ValueError):
            continue
    merged["not_regular_types"] = [str(kind) for kind in stored.get("not_regular_types") or [] if kind]
    return merged


def settings_errors(settings):
    s = _settings(settings)
    errors = []
    if not 0 < s["advance_percent"] <= 100:
        errors.append("The leave advance is more than 0% and no more than 100% of gross.")
    if s["per_meter_months"] < 1:
        errors.append("The Per Meter average is taken over at least one month.")
    if s["more_than_days"] < 0:
        errors.append("The days of leave a leave advance needs cannot be fewer than none.")
    if s["instalments"] < 1 or s["max_instalments"] < 1:
        errors.append("A leave advance is recovered in at least one month.")
    elif s["instalments"] > s["max_instalments"]:
        errors.append("The usual number of months cannot be more than the most allowed.")
    return errors


def gross_basis(pay_category, monthly_gross, recent_gross=(), months=2):
    """(gross, how it was worked out). A Per Meter employee's pay follows
    their output, so their gross is the average of the last months' paid
    gross (recent_gross, the latest first); everyone else's is the monthly
    gross the salary structure works out. None when there is nothing to
    work it out from."""
    months = max(int(months or 1), 1)
    recent = [_num(value) for value in (recent_gross or ())][:months]
    if pay_category == PER_METER and recent:
        average = round(sum(recent) / len(recent), 2)
        return average, "the average gross of the last %d month(s), %s" % (len(recent), _money(average))
    if _num(monthly_gross) > 0:
        note = "the monthly gross from the salary structure, %s" % _money(monthly_gross)
        if pay_category == PER_METER:
            note += " (no payslip yet to average)"
        return round(_num(monthly_gross), 2), note
    return None, None


def allowed(gross, settings=None):
    """The most that may be advanced: the percentage of gross."""
    s = _settings(settings)
    if gross is None or _num(gross) <= 0:
        return None
    return round(_num(gross) * s["advance_percent"] / 100.0, 2)


def eligibility_errors(facts, settings=None):
    """Why this employee may not have this leave advance, as user-facing
    messages; none means they qualify.

    facts: "status", "employment_type", "bank_loan", "company_loan" (still
    owed), "leave_type", "earned_leave" (the type is accrued leave),
    "leave_days", "outstanding" (still owed on earlier leave advances),
    "allowed", "amount", "instalments".
    """
    s = _settings(settings)
    errors = []
    if facts.get("status") and facts["status"] != ACTIVE:
        errors.append("Only an active employee may be advanced; this one is %s." % facts["status"])
    kind = facts.get("employment_type")
    if int(s["regular_only"]) and kind and kind in s["not_regular_types"]:
        errors.append("A leave advance is for regular employees; %s staff do not qualify." % kind)
    if int(s["no_loans"]):
        if facts.get("bank_loan"):
            errors.append("Has a bank loan, and a leave advance is not given alongside one.")
        if _num(facts.get("company_loan")) > 0:
            errors.append("%s is still owed on a company loan." % _money(facts.get("company_loan")))
    if not facts.get("earned_leave"):
        errors.append("A leave advance is for accrued leave; %s is not." % (facts.get("leave_type") or "this leave"))
    elif _num(facts.get("leave_days")) <= int(s["more_than_days"]):
        errors.append("A leave advance is for more than %d days of accrued leave; this leave is %g."
                      % (int(s["more_than_days"]), _num(facts.get("leave_days"))))
    if _num(facts.get("outstanding")) > 0:
        errors.append("%s is still owed on an earlier leave advance." % _money(facts.get("outstanding")))
    ceiling = facts.get("allowed")
    if ceiling is None:
        errors.append("No salary in force to work the advance out from.")
    amount = _num(facts.get("amount"))
    if ceiling is not None and amount <= 0:
        errors.append("Say how much is advanced.")
    elif ceiling is not None and amount > _num(ceiling) + 0.005:
        errors.append("The most that may be advanced is %s, %g%% of gross." % (_money(ceiling), s["advance_percent"]))
    instalments = int(_num(facts.get("instalments")))
    if not 1 <= instalments <= int(s["max_instalments"]):
        errors.append("A leave advance is recovered in 1 to %d month(s)." % int(s["max_instalments"]))
    return errors


def payroll_date(day):
    """The payroll month a day's deduction falls in: its closing day, the
    25th on or after it."""
    day = _date(day)
    if not day:
        return None
    if day.day <= PAYROLL_DAY:
        return datetime.date(day.year, day.month, PAYROLL_DAY)
    return add_months(datetime.date(day.year, day.month, PAYROLL_DAY), 1)


def first_deduction(leave_ends):
    """The first month taken back, when nobody has agreed another: the
    payroll month the leave ends in."""
    return payroll_date(leave_ends)


def recovery_schedule(amount, instalments, first_month):
    """[(payroll date, amount)]: equal instalments, the rounding on the last
    one so the parts add back to the whole."""
    amount = round(_num(amount), 2)
    instalments = max(1, int(_num(instalments) or 1))
    first = payroll_date(first_month)
    if not first or amount <= 0:
        return []
    each = round(amount / instalments, 2)
    rows, taken = [], 0.0
    for n in range(instalments):
        due = each if n < instalments - 1 else round(amount - taken, 2)
        taken = round(taken + due, 2)
        rows.append((add_months(first, n), due))
    return rows


def outstanding(amount, recovered):
    return round(max(_num(amount) - _num(recovered), 0), 2)


def advance_status(docstatus, workflow_state, on_run=False, paid=False, amount=0, recovered=0):
    """Where a leave advance stands."""
    if docstatus == 2:
        return CANCELLED
    if docstatus == 0:
        return workflow_state if workflow_state in (DRAFT, PENDING, REJECTED) else DRAFT
    if workflow_state == REJECTED:
        return REJECTED
    if paid:
        left = outstanding(amount, recovered)
        if not left:
            return RECOVERED
        return RECOVERING if _num(recovered) > 0 else PAID
    return PROCESSING if on_run else APPROVED


def run_errors(facts):
    """Why the Leave Advance Processing cannot go to Finance yet.

    facts: "included" (lines to pay), "bank_account", "payment_method",
    "reference_no", "reference_date", "no_account" (names paid by bank with
    no account number), "not_approved" (advances no longer waiting to be
    paid).
    """
    errors = []
    if not int(facts.get("included") or 0):
        errors.append("Nobody in this run is included for payment.")
    if not facts.get("bank_account"):
        errors.append("Select the bank or cash account the advances are paid from.")
    method = facts.get("payment_method")
    if method not in PAYMENT_METHODS:
        errors.append("Select the payment method: %s." % ", ".join(PAYMENT_METHODS))
    elif method != "Cash" and not (facts.get("reference_no") and facts.get("reference_date")):
        errors.append("Enter the cheque or reference number and its date.")
    missing = list(facts.get("no_account") or ())
    if missing:
        errors.append("No bank account number for: %s. Add it on the employee or take them out of the run."
                      % ", ".join(missing))
    stale = list(facts.get("not_approved") or ())
    if stale:
        errors.append("No longer waiting to be paid: %s. Take them out of the run." % ", ".join(stale))
    return errors


def bank_file_rows(lines):
    """The file the Payroll Officer sends Finance: the minutes' five columns,
    for each line paid."""
    rows = [list(BANK_FILE_HEADER)]
    for line in lines or ():
        if not int(line.get("include") or 0):
            continue
        rows.append([line.get("employee") or "", line.get("employee_name") or "", line.get("bank_code") or "",
                     line.get("bank_ac_no") or "", round(_num(line.get("amount")), 2)])
    return rows


def add_months(day, months):
    day = _date(day)
    if not day:
        return None
    month = day.month - 1 + int(months)
    year = day.year + month // 12
    month = month % 12 + 1
    return datetime.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _settings(settings):
    if settings and "not_regular_types" in settings and all(key in settings for key in DEFAULTS):
        return settings
    return settings_from(settings)


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


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
