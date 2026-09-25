# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Loans Application rules (4.4).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_loans.py exercises them without a bench.

The process, from the revised flow chart and the test script:

  1. The employee creates a loan request; the first approver is told.
  2. It is approved as the Employee Loan workflow says (set up in the desk:
     the test script asks for the HOD and then the Executive Director).
     Not approved, and it goes back to the employee, or is refused.
  3. Accounts set the terms actually discussed with the employee — the
     amount, the rate and how many months — and the HR Officer is told.
  4. The employee consents to the deduction (LPL/HR/39), and the HR
     Officer and the accountant are told. Accounts pay the loan out.
  5. The HR or Payroll Officer runs the loan: the repayment schedule
     becomes a monthly deduction on the payroll.
  6. The system watches the loan's life and tells the HR Officer and the
     employee about the payments, and about a month the payroll missed.

Luuka's staff loans carry no interest by default; where a rate is set it
is flat — the whole term's interest worked out once and spread evenly —
because that is how the Special Advance Form's recovery lines read.

Every figure a policy decides is a setting (Loan Settings); DEFAULTS are
what the minutes set and what this module assumed before Luuka set it.
"""

import datetime

DRAFT = "Draft"
RUNNING = "Running"
REPAID = "Repaid"
WRITTEN_OFF = "Written Off"
REJECTED = "Rejected"
CANCELLED = "Cancelled"
STATUSES = (DRAFT, RUNNING, REPAID, WRITTEN_OFF, REJECTED, CANCELLED)

# What the minutes add (§4.10): "a car loan of a maximum of UGX 30
# million and a study loan whose amount depends on the selected course of
# study ... Loans are applicable only to administration team members with no
# existing loans." The test script's first case says the same: "an admin
# employee creates a loan request".
CAR_LOAN, STUDY_LOAN, OTHER_LOAN = "Car Loan", "Study Loan", "Other"
LOAN_TYPES = (CAR_LOAN, STUDY_LOAN, OTHER_LOAN)
ADMINISTRATIVE = "Administrative"

DEFAULTS = {
    "admin_only": 1,                # minutes §4.10
    "min_months": 6,
    "other_allowed": 1,
    "car_loan_max": 30000000.0,     # minutes §4.10
    "other_months_of_gross": 3.0,
    "car_max_instalments": 12,
    "study_max_instalments": 12,
    "other_max_instalments": 12,
    "max_share_of_gross": 0.0,      # 0: no cap on the monthly instalment
    "default_rate": 0.0,
    "missed_grace_days": 5,
}
INTEGERS = ("admin_only", "min_months", "other_allowed", "car_max_instalments", "study_max_instalments",
            "other_max_instalments", "missed_grace_days")

# the names this module has always had
MAX_MONTHS_OF_GROSS = DEFAULTS["other_months_of_gross"]
MAX_INSTALMENTS = DEFAULTS["other_max_instalments"]
DEFAULT_INSTALMENTS = 6
MIN_MONTHS_SERVED = DEFAULTS["min_months"]
DEFAULT_RATE = DEFAULTS["default_rate"]
CAR_LOAN_MAX = DEFAULTS["car_loan_max"]

# a line on the schedule that the payroll did not take
PAID_DIRECTLY, FINAL_SETTLEMENT = "Paid directly", "Final settlement"

# Luuka's payroll period runs from the 26th to the 25th
# (advance_rules.payroll_period); a deduction falls on its close
PERIOD_CLOSES_ON = 25


def settings_from(stored):
    """Loan Settings merged over DEFAULTS: a stored nought stays a nought,
    anything never saved takes its default."""
    out = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        value = (stored or {}).get(key)
        if value in (None, ""):
            continue
        out[key] = int(_num(value)) if key in INTEGERS else _num(value)
    return out


def settings_errors(settings):
    errors = []
    s = settings_from(settings)
    for key in ("car_max_instalments", "study_max_instalments", "other_max_instalments"):
        if int(s[key]) < 1:
            errors.append("A loan is recovered over at least one month.")
            break
    if s["car_loan_max"] < 0 or s["other_months_of_gross"] < 0 or s["min_months"] < 0 \
            or s["missed_grace_days"] < 0:
        errors.append("A limit cannot be negative.")
    if not 0 <= s["max_share_of_gross"] <= 100:
        errors.append("The share of the gross pay is between 0 and 100%.")
    if s["default_rate"] < 0:
        errors.append("A rate cannot be negative.")
    return errors


def max_instalments(loan_type, settings=None):
    s = settings_from(settings)
    return int({CAR_LOAN: s["car_max_instalments"], STUDY_LOAN: s["study_max_instalments"]}.get(
        loan_type, s["other_max_instalments"]))


def limit_for(gross, months=MAX_MONTHS_OF_GROSS):
    return round(_num(gross) * float(months), 2)


def limit_for_type(loan_type, gross, months=None, settings=None):
    """The most a loan of this kind may be.

    A car loan, the settings' ceiling whatever the gross. A study loan, what
    the course costs — shown on its fee structure, so no figure here (None).
    Anything else, so many months of the gross.
    """
    s = settings_from(settings)
    if loan_type == CAR_LOAN:
        return s["car_loan_max"]
    if loan_type == STUDY_LOAN:
        return None
    return limit_for(gross, s["other_months_of_gross"] if months is None else months)


def months_served(joined, today):
    joined, today = _date(joined), _date(today)
    if not joined or not today or today < joined:
        return 0
    months = (today.year - joined.year) * 12 + (today.month - joined.month)
    return months - 1 if today.day < joined.day else months


def eligibility_errors(facts, settings=None):
    """Why this employee may not take a loan, as user-facing messages. An
    empty list means they qualify — the chart's "Approved?" rests on it.

    facts: "status", "date_of_joining", "today", "gross_pay", "amount",
    "outstanding" (still owed on running loans), "waiting" (another request
    of theirs waiting for approval), "instalments", "rate", "purpose",
    "loan_type", "category" (the employee's department: Administrative or
    not), "fee_structure".
    """
    s = settings_from(settings)
    errors = []
    if facts.get("status") and facts["status"] != "Active":
        errors.append("Only an active employee may take a loan; this one is %s." % facts["status"])
    loan_type = facts.get("loan_type") or OTHER_LOAN
    if loan_type not in LOAN_TYPES:
        errors.append("%r is not a valid loan type." % loan_type)
    elif loan_type == OTHER_LOAN and not s["other_allowed"]:
        errors.append("Only car and study loans are given.")
    if s["admin_only"] and facts.get("category") != ADMINISTRATIVE:
        errors.append("Loans are only for the administration team. This employee's "
                      "department is %s." % (facts.get("category") or "not marked Administrative"))
    served = months_served(facts.get("date_of_joining"), facts.get("today"))
    minimum = facts.get("min_months")
    minimum = s["min_months"] if minimum is None else int(minimum)
    if minimum and served < minimum:
        errors.append("A loan is given after %d month(s) of service; this employee has served %d."
                      % (minimum, served))
    amount = _num(facts.get("amount"))
    if amount <= 0:
        errors.append("Say how much is being asked for.")
    gross = _num(facts.get("gross_pay"))
    if loan_type == CAR_LOAN:
        if amount > s["car_loan_max"]:
            errors.append("A car loan is at most %s." % _money(s["car_loan_max"]))
    elif loan_type == STUDY_LOAN:
        if not facts.get("fee_structure"):
            errors.append("A study loan is what the course costs: attach the course's fee structure.")
    elif not gross:
        errors.append("This employee has no gross pay on record, so the most that may be lent cannot be "
                      "worked out.")
    else:
        months = facts.get("max_months") or s["other_months_of_gross"]
        ceiling = limit_for(gross, months)
        if amount > ceiling:
            errors.append("The most that may be lent is %s, being %g month(s) of a gross of %s."
                          % (_money(ceiling), _num(months), _money(gross)))
    outstanding = _num(facts.get("outstanding"))
    if outstanding > 0:
        errors.append("%s is still owed on an earlier loan. It is cleared before another is given."
                      % _money(outstanding))
    if facts.get("waiting"):
        errors.append("Another loan request, %s, is waiting for approval. One is dealt with before "
                      "another is made." % facts["waiting"])
    instalments = int(facts.get("instalments") or 0)
    most = max_instalments(loan_type, s)
    if instalments > most:
        errors.append("A %s is recovered over at most %d month(s)." % (
            loan_type.lower() if loan_type != OTHER_LOAN else "loan", most))
    over = over_share(amount, facts.get("rate"), instalments, gross, s["max_share_of_gross"])
    if over:
        errors.append(over)
    if not _text(facts.get("purpose")):
        errors.append("Say what the loan is for.")
    return errors


def over_share(amount, rate, instalments, gross, share):
    """Why the monthly instalment is too much: more than `share`% of the
    gross pay. None when it is not, or when no cap is set."""
    share, gross = _num(share), _num(gross)
    if not (share and gross and _num(amount) > 0 and int(instalments or 0) > 0):
        return None
    monthly = monthly_instalment(amount, rate, instalments)
    if monthly > round(gross * share / 100.0, 2):
        return "A monthly instalment of %s is more than %g%% of the gross pay of %s." % (
            _money(monthly), share, _money(gross))
    return None


def interest_for(principal, rate, instalments):
    """Flat interest over the whole term."""
    if not _num(rate) or not int(instalments or 0):
        return 0.0
    return round(_num(principal) * _num(rate) / 100.0 * (int(instalments) / 12.0), 2)


def spread(principal, interest, months, first_month, day=None):
    """[(month, principal, interest, total)]: equal instalments from the
    first month, on `day` of each month where given (the loan's own day),
    the rounding on the last one so the parts add back to the whole."""
    principal, interest = round(_num(principal), 2), round(_num(interest), 2)
    months = max(1, int(months or 1))
    month = _date(first_month)
    if not month or principal + interest <= 0:
        return []
    each_principal = round(principal / months, 2)
    each_interest = round(interest / months, 2)
    rows, taken_p, taken_i = [], 0.0, 0.0
    for n in range(months):
        last = n == months - 1
        due_p = round(principal - taken_p, 2) if last else each_principal
        due_i = round(interest - taken_i, 2) if last else each_interest
        taken_p, taken_i = round(taken_p + due_p, 2), round(taken_i + due_i, 2)
        rows.append((on_day(add_months(month, n), day), due_p, due_i, round(due_p + due_i, 2)))
    return rows


def repayment_schedule(principal, rate, instalments, first_month):
    """[(month, principal, interest, total)] — equal instalments, the
    rounding on the last one so the parts add back to the whole."""
    principal = round(_num(principal), 2)
    instalments = max(1, int(instalments or DEFAULT_INSTALMENTS))
    if principal <= 0:
        return []
    return spread(principal, interest_for(principal, rate, instalments), instalments, first_month)


def monthly_instalment(principal, rate, instalments):
    """Nothing until the months are settled: a loan with no term has no
    monthly instalment, and guessing one puts a wrong figure on the
    consent form."""
    if not int(instalments or 0):
        return 0.0
    schedule = repayment_schedule(principal, rate, instalments, "2000-01-31")
    return schedule[0][3] if schedule else 0.0


def left(principal, interest, rows):
    """(principal, interest) still owed after the lines recovered so far.
    rows: principal, interest, recovered."""
    taken_p = sum(_num(row.get("principal")) for row in rows if row.get("recovered"))
    taken_i = sum(_num(row.get("interest")) for row in rows if row.get("recovered"))
    return max(round(_num(principal) - taken_p, 2), 0.0), max(round(_num(interest) - taken_i, 2), 0.0)


def split(amount, principal_left, interest_left):
    """A payment's (principal, interest), in proportion to what is left of
    each; never more than is left."""
    amount = min(round(_num(amount), 2), round(_num(principal_left) + _num(interest_left), 2))
    whole = _num(principal_left) + _num(interest_left)
    if whole <= 0:
        return 0.0, 0.0
    interest = round(amount * _num(interest_left) / whole, 2)
    return round(amount - interest, 2), interest


def outstanding(amount, recovered):
    return round(max(_num(amount) - _num(recovered), 0), 2)


def loan_status(docstatus, amount, recovered, written_off=False, state=None):
    """Where the loan stands. A request refused is Rejected whatever its
    docstatus: nothing was lent and nothing is owed."""
    if state == REJECTED:
        return REJECTED
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


def run_errors(facts):
    """What must stand before the payroll starts taking the loan back: the
    consent, and the loan paid out (chart step 3)."""
    errors = consent_errors(facts)
    if not facts.get("paid"):
        errors.append("Accounts record the payment of the loan first (Record Payment).")
    return errors


def terms_errors(facts):
    """What Accounts settled with the employee, checked against what was
    asked for, the months the payroll has already paid and the cap on the
    instalment ("gross_pay", "max_share")."""
    errors = []
    asked = _num(facts.get("amount"))
    approved = _num(facts.get("approved_amount"))
    if approved and asked and approved > asked:
        errors.append("%s is being lent but only %s was asked for." % (_money(approved), _money(asked)))
    if approved <= 0:
        errors.append("Set the amount actually being lent.")
    instalments = int(facts.get("instalments") or 0)
    if instalments <= 0:
        errors.append("Say in how many months the loan is recovered.")
    elif facts.get("max_instalments") and instalments > int(facts["max_instalments"]):
        errors.append("It is recovered over at most %d month(s)." % int(facts["max_instalments"]))
    over = over_share(approved, facts.get("rate"), instalments, facts.get("gross_pay"), facts.get("max_share"))
    if over:
        errors.append(over)
    first = _date(facts.get("first_repayment"))
    if not first:
        errors.append("Say which month the first repayment comes off.")
    paid_through = _date(facts.get("paid_through"))
    if first and paid_through and first <= paid_through:
        errors.append("The payroll is already paid up to %s. The first repayment comes after it."
                      % _day(paid_through))
    if _num(facts.get("rate")) < 0:
        errors.append("A rate cannot be negative.")
    return errors


def missed(rows, today, grace_days=DEFAULTS["missed_grace_days"]):
    """The lines whose month has passed, and some days more, with nothing
    taken and nobody told. rows: payroll_date, recovered, missed_told."""
    today = _date(today)
    grace = datetime.timedelta(days=int(grace_days or 0))
    out = []
    for row in rows or ():
        day = _date(row.get("payroll_date"))
        if day and today and not row.get("recovered") and not row.get("missed_told") and day + grace < today:
            out.append(row)
    return out


def resume_from(last, today, day=None):
    """The month a schedule drawn again picks up: the one after `last`, on
    the loan's own day of the month where given, never a month gone by.
    Each month is counted from `last` itself, so a short month does not
    pull the day down for the months after it."""
    today, last = _date(today), _date(last)
    if not last:
        return on_day(today, day)
    months = 1
    while True:
        found = on_day(add_months(last, months), day)
        if not today or (found.year, found.month) >= (today.year, today.month):
            return found
        months += 1


def period_close(day):
    """The last day of the payroll period a day falls in: the 25th of its
    month, or from the 26th on, of the next."""
    day = _date(day)
    if not day:
        return None
    month = datetime.date(day.year, day.month, 1)
    if day.day > PERIOD_CLOSES_ON:
        month = add_months(month, 1)
    return datetime.date(month.year, month.month, min(PERIOD_CLOSES_ON, _days_in_month(month.year, month.month)))


def first_month(asked_on, paid_through=None):
    """Where a request's schedule starts until Accounts settle the terms:
    the close of the payroll period after the one it was asked in, never a
    period the payroll has already paid."""
    asked = _date(asked_on)
    if not asked:
        return None
    first = period_close(period_close(asked) + datetime.timedelta(days=1))
    paid = _date(paid_through)
    if paid and first <= paid:
        first = period_close(paid + datetime.timedelta(days=1))
    return first


def on_day(value, day=None):
    """The date in the same month on `day` (the month's last day where it
    has fewer); the date itself without one."""
    value = _date(value)
    if not value or not day:
        return value
    return datetime.date(value.year, value.month, min(int(day), _days_in_month(value.year, value.month)))


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


def _day(value):
    value = _date(value)
    return "%d %s %d" % (value.day, value.strftime("%b"), value.year) if value else ""


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
