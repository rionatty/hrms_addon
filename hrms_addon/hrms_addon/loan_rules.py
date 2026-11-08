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

Every figure a policy decides is a setting. Since 8 Nov 2026 the kinds of
loan are Luuka's own list, Employee Loan Type (review item 25: "the
company has different types of loan, for bank loan the company just
maintain the information but it doesn't process loan, for sacco is
executed by the company"), each with its own rules (TYPE_DEFAULTS). Loan
Settings keep what holds for every loan (DEFAULTS). Who lends decides how
a loan runs:

  Company   Luuka lend: Accounts pay it out and the payroll takes it back,
            on the Employee Loans account
  SACCO     the same, run by Luuka for the SACCO, on the SACCO Loans account
  Bank      the bank lends and takes it back. Luuka approve it, keep the
            record and give the bank a letter of undertaking; nothing is
            paid out or deducted here

What one earns decides what one may borrow (item 24): this loan's
instalment and those going to banks each month come to at most half the
net pay ("the instalment is at most 50% of net", Luuka, 5 Nov 2026).
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
# employee creates a loan request". Those three kinds are made from what
# Loan Settings held for them (seed_types), with a SACCO loan and a bank loan.
CAR_LOAN, STUDY_LOAN, OTHER_LOAN = "Car Loan", "Study Loan", "Other"
SACCO_LOAN, BANK_LOAN = "SACCO Loan", "Bank Loan"
LOAN_TYPES = (CAR_LOAN, STUDY_LOAN, OTHER_LOAN)
ADMINISTRATIVE = "Administrative"

# who lends
COMPANY, SACCO, BANK = "Company", "SACCO", "Bank"
PROCESSORS = (COMPANY, SACCO, BANK)

# a loan type's rules (Employee Loan Type); a figure never set takes these
TYPE_DEFAULTS = {
    "processed_by": COMPANY,
    "disabled": 0,
    "admin_only": 1,            # minutes §4.10
    "min_months": 6,
    "max_amount": 0.0,          # 0: no ceiling of its own
    "months_of_gross": 0.0,     # 0: not tied to the gross pay
    "course_fees": 0,           # at most what the course costs (a study loan)
    "max_instalments": 12,      # 0: as many months as the bank gives
    "share_of_net": 50.0,       # the instalments at most this share of the net pay; 0: no cap
    "default_rate": 0.0,
}
TYPE_INTEGERS = ("disabled", "admin_only", "min_months", "course_fees", "max_instalments")
TYPE_TEXT = ("processed_by",)

# what holds for every loan (Loan Settings)
DEFAULTS = {
    "missed_grace_days": 5,
    "payroll_day": 26,              # the day the payroll is processed: each repayment falls on it
}
INTEGERS = ("missed_grace_days", "payroll_day")

# what Loan Settings held for each kind before the types: seed_types makes
# the types from it, so nothing a site set is lost
LEGACY = {
    "admin_only": 1,
    "min_months": 6,
    "other_allowed": 1,
    "car_loan_max": 30000000.0,     # minutes §4.10
    "other_months_of_gross": 3.0,
    "car_max_instalments": 12,
    "study_max_instalments": 12,
    "other_max_instalments": 12,
    "default_rate": 0.0,
}

# the names this module has always had
MAX_MONTHS_OF_GROSS = LEGACY["other_months_of_gross"]
MAX_INSTALMENTS = LEGACY["other_max_instalments"]
DEFAULT_INSTALMENTS = 6
MIN_MONTHS_SERVED = LEGACY["min_months"]
DEFAULT_RATE = LEGACY["default_rate"]
CAR_LOAN_MAX = LEGACY["car_loan_max"]

# a line on the schedule that the payroll did not take
PAID_DIRECTLY, FINAL_SETTLEMENT = "Paid directly", "Final settlement"


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
    if s["missed_grace_days"] < 0:
        errors.append("A limit cannot be negative.")
    if not 1 <= int(s["payroll_day"]) <= 31:
        errors.append("The payroll day is a day of the month, 1 to 31.")
    return errors


def type_from(stored):
    """A loan type's rules over TYPE_DEFAULTS: a stored nought stays a
    nought, anything never set takes its default. None for no type."""
    if stored is None:
        return None
    out = dict(TYPE_DEFAULTS)
    for key in TYPE_DEFAULTS:
        value = stored.get(key)
        if value in (None, ""):
            continue
        out[key] = value if key in TYPE_TEXT else int(_num(value)) if key in TYPE_INTEGERS else _num(value)
    out["name"] = stored.get("loan_type_name") or stored.get("name") or ""
    return out


def type_errors(loan_type):
    """What is wrong with a loan type as Luuka set it."""
    t = type_from(loan_type or {})
    errors = []
    if t["processed_by"] not in PROCESSORS:
        errors.append("Say who lends: the Company, the SACCO or a Bank.")
    if min(t["max_amount"], t["months_of_gross"], t["min_months"], t["max_instalments"]) < 0:
        errors.append("A limit cannot be negative.")
    if not 0 <= t["share_of_net"] <= 100:
        errors.append("The share of the net pay is between 0 and 100%.")
    if t["default_rate"] < 0:
        errors.append("A rate cannot be negative.")
    if t["processed_by"] in (COMPANY, SACCO) and t["max_instalments"] < 1:
        errors.append("A loan the payroll takes back is recovered within a set number of months.")
    return errors


def seed_types(stored=None):
    """The types a site starts with, from what Loan Settings held for each
    kind (LEGACY): a car loan up to its ceiling, a study loan up to the
    course fees, any other loan up to so many months of the gross; and a
    SACCO loan and a bank loan, which the whole staff may ask for."""
    s = dict(LEGACY)
    for key, value in (stored or {}).items():
        if key in LEGACY and value not in (None, ""):
            s[key] = _num(value)
    common = {"admin_only": int(s["admin_only"]), "min_months": int(s["min_months"]),
              "default_rate": s["default_rate"], "share_of_net": TYPE_DEFAULTS["share_of_net"]}
    return [
        dict(common, loan_type_name=CAR_LOAN, processed_by=COMPANY, max_amount=s["car_loan_max"],
             max_instalments=int(s["car_max_instalments"])),
        dict(common, loan_type_name=STUDY_LOAN, processed_by=COMPANY, course_fees=1,
             max_instalments=int(s["study_max_instalments"])),
        dict(common, loan_type_name=OTHER_LOAN, processed_by=COMPANY, months_of_gross=s["other_months_of_gross"],
             max_instalments=int(s["other_max_instalments"]), disabled=0 if int(s["other_allowed"]) else 1),
        dict(common, loan_type_name=SACCO_LOAN, processed_by=SACCO, admin_only=0, default_rate=0.0,
             max_instalments=TYPE_DEFAULTS["max_instalments"]),
        dict(common, loan_type_name=BANK_LOAN, processed_by=BANK, admin_only=0, default_rate=0.0,
             max_instalments=0),
    ]


def max_instalments(loan_type):
    """The most months a loan of this type is recovered over; 0, as many as
    the bank gives."""
    return int(type_from(loan_type or {})["max_instalments"])


def limit_for(gross, months=MAX_MONTHS_OF_GROSS):
    return round(_num(gross) * float(months), 2)


def limit_for_type(loan_type, gross, course_fee=None):
    """The most a loan of this type may be: what the course costs for one
    lent up to the course fees (None until they are typed), else the lower
    of its own ceiling and so many months of the gross. None where the
    type sets neither."""
    t = type_from(loan_type or {})
    if t["course_fees"]:
        return _num(course_fee) or None
    ceilings = []
    if t["max_amount"] > 0:
        ceilings.append(t["max_amount"])
    if t["months_of_gross"] > 0:
        ceilings.append(limit_for(gross, t["months_of_gross"]))
    return min(ceilings) if ceilings else None


def months_served(joined, today):
    joined, today = _date(joined), _date(today)
    if not joined or not today or today < joined:
        return 0
    months = (today.year - joined.year) * 12 + (today.month - joined.month)
    return months - 1 if today.day < joined.day else months


def eligibility_errors(facts, loan_type=None):
    """Why this employee may not take a loan of this type, as user-facing
    messages. An empty list means they qualify — the chart's "Approved?"
    rests on it.

    loan_type: the type's rules (Employee Loan Type); None where the loan
    names no type there is.
    facts: "status", "date_of_joining", "today", "gross_pay", "net_pay"
    (the last salary slip's; None where there is none), "committed" (what
    goes to bank loans each month, which the slip does not show), "amount",
    "monthly" (this loan's instalment), "outstanding" (still owed to the
    same lender on loans running now), "waiting" (another request of theirs
    waiting for approval), "instalments", "purpose", "loan_type" (its
    name), "category" (the employee's department: Administrative or not),
    "fee_structure", "course_fee" (the fees it shows).
    """
    errors = []
    if facts.get("status") and facts["status"] != "Active":
        errors.append("Only an active employee may take a loan; this one is %s." % facts["status"])
    name = facts.get("loan_type") or ""
    t = type_from(loan_type)
    if t is None:
        errors.append("%s is not a kind of loan Luuka give." % name if name else "Choose the kind of loan.")
        t = type_from({})
    elif t["disabled"]:
        errors.append("%s are no longer given." % _kinds(name))
    if t["admin_only"] and facts.get("category") != ADMINISTRATIVE:
        errors.append("Loans are only for the administration team. This employee's "
                      "department is %s." % (facts.get("category") or "not marked Administrative"))
    served = months_served(facts.get("date_of_joining"), facts.get("today"))
    minimum = int(t["min_months"])
    if minimum and served < minimum:
        errors.append("A loan is given after %d month(s) of service; this employee has served %d."
                      % (minimum, served))
    amount = _num(facts.get("amount"))
    if amount <= 0:
        errors.append("Say how much is being asked for.")
    gross = _num(facts.get("gross_pay"))
    if t["course_fees"]:
        fee = _num(facts.get("course_fee"))
        if not facts.get("fee_structure"):
            errors.append("%s is what the course costs: attach the course's fee structure." % _a_kind(name))
        if fee <= 0:
            errors.append("Enter the Course Fees shown on the fee structure.")
        elif amount > fee:
            errors.append("%s is at most the course fees, %s." % (_a_kind(name), _money(fee)))
    else:
        if t["max_amount"] > 0 and amount > t["max_amount"]:
            errors.append("%s is at most %s." % (_a_kind(name), _money(t["max_amount"])))
        if t["months_of_gross"] > 0:
            if not gross:
                errors.append("This employee has no gross pay on record, so the most that may be lent cannot be "
                              "worked out.")
            else:
                ceiling = limit_for(gross, t["months_of_gross"])
                if amount > ceiling:
                    errors.append("The most that may be lent is %s, being %g month(s) of a gross of %s."
                                  % (_money(ceiling), t["months_of_gross"], _money(gross)))
    outstanding = _num(facts.get("outstanding"))
    if outstanding > 0:
        errors.append("%s is still owed on an earlier loan. It is cleared before another is given."
                      % _money(outstanding))
    if facts.get("waiting"):
        errors.append("Another loan request, %s, is waiting for approval. One is dealt with before "
                      "another is made." % facts["waiting"])
    instalments = int(facts.get("instalments") or 0)
    most = int(t["max_instalments"])
    if most and instalments > most:
        errors.append("%s is recovered over at most %d month(s)." % (_a_kind(name), most))
    over = over_net(facts.get("monthly"), facts.get("net_pay"), facts.get("committed"), t["share_of_net"])
    if over:
        errors.append(over)
    if not _text(facts.get("purpose")):
        errors.append("Say what the loan is for.")
    return errors


def over_net(monthly, net, committed, share):
    """Why the instalment is too much: more than `share`% of the net pay
    once what already goes to banks each month is taken off it. None when
    it fits, or when the type sets no cap.

    net: the last salary slip's net pay (what the payroll already takes,
    loans with it, is off it); None where there is no slip to read."""
    share, monthly, committed = _num(share), _num(monthly), _num(committed)
    if not share or monthly <= 0:
        return None
    if net is None:
        return ("There is no salary slip for this employee yet, so the net pay the instalment is measured "
                "against is not known.")
    room = round(_num(net) * share / 100.0 - committed, 2)
    if monthly <= room:
        return None
    said = "A monthly instalment of %s is more than %g%% of the net pay of %s" % (
        _money(monthly), share, _money(net))
    if committed > 0:
        said += ", once the %s a month going to bank loans is taken off" % _money(committed)
    return said + "."


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
        errors.append("Fill in Liability: what the deduction is for.")
    if _num(facts.get("amount")) <= 0:
        errors.append("Set the amount lent.")
    if int(facts.get("instalments") or 0) <= 0:
        errors.append("Set how many months the loan is repaid over.")
    if not facts.get("effective_from"):
        errors.append("Set the first repayment: the deduction starts on it.")
    if not facts.get("consent"):
        errors.append("The employee has not consented yet: they tick Employee Consents.")
    return errors


def run_errors(facts):
    """What must stand before the payroll starts taking the loan back: the
    consent, and the loan paid out (chart step 3). A bank loan is only put
    on record: the bank pays it and takes it back (bank_errors)."""
    if facts.get("processed_by") == BANK:
        return bank_errors(facts)
    errors = consent_errors(facts)
    if not facts.get("paid"):
        errors.append("The loan has not been paid out: Accounts click Record Payment and submit the Journal "
                      "Entry.")
    return errors


def bank_errors(facts):
    """A bank loan on record: the bank, the account the salary keeps going
    to, and the bank's own terms, which the letter of undertaking gives."""
    errors = []
    if not _text(facts.get("bank")):
        errors.append("Say which bank is lending.")
    if not _text(facts.get("account_no")):
        errors.append("Give the account at that bank the salary is paid into.")
    if _num(facts.get("amount")) <= 0:
        errors.append("Set the amount the bank lends.")
    if int(facts.get("instalments") or 0) <= 0:
        errors.append("Set how many months the bank is repaid over.")
    if _num(facts.get("monthly")) <= 0:
        errors.append("Set the monthly instalment the bank takes.")
    if not _date(facts.get("first_repayment")):
        errors.append("Set the first repayment to the bank.")
    return errors


def runs_until(first, months):
    """The month of a bank loan's last instalment: the first one's day, so
    many months on."""
    first = _date(first)
    if not first or int(months or 0) < 1:
        return None
    return add_months(first, int(months) - 1)


def bank_loan_ended(until, today):
    """A bank loan whose last instalment has gone by."""
    until, today = _date(until), _date(today)
    return bool(until and today and until < today)


def terms_errors(facts):
    """What Accounts settled with the employee, checked against what was
    asked for, the months the payroll has already paid and the cap on the
    instalment ("monthly", "net_pay", "committed", "share"). A bank loan's
    first month is the bank's: the payroll takes nothing."""
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
    over = over_net(facts.get("monthly"), facts.get("net_pay"), facts.get("committed"), facts.get("share"))
    if over:
        errors.append(over)
    first = _date(facts.get("first_repayment"))
    if not first:
        errors.append("Say which month the first repayment comes off.")
    paid_through = None if facts.get("processed_by") == BANK else _date(facts.get("paid_through"))
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


def first_month(asked_on, paid_through=None, day=DEFAULTS["payroll_day"]):
    """Where a request's schedule starts until Accounts settle the terms:
    the payroll day of the month after it was asked, never a day the payroll
    has already paid."""
    asked = _date(asked_on)
    if not asked:
        return None
    first = on_day(add_months(datetime.date(asked.year, asked.month, 1), 1), day)
    paid = _date(paid_through)
    while paid and first <= paid:
        first = on_day(add_months(datetime.date(first.year, first.month, 1), 1), day)
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


def _kind(name):
    """A type's name in a sentence: "car loan", "SACCO loan", and "loan"
    for Other."""
    text = (name or "").strip()
    if not text or text == OTHER_LOAN:
        return "loan"
    words = [word if word.isupper() and len(word) > 1 else word.lower() for word in text.split()]
    return " ".join(words) if words[-1].lower() == "loan" else " ".join(words + ["loan"])


def _a_kind(name):
    """"A car loan", "An emergency loan", "A loan" for Other."""
    kind = _kind(name)
    return ("An " if kind[:1].lower() in "aeiou" else "A ") + kind


def _kinds(name):
    """A type's name, plural, opening a sentence: "Car loans", "SACCO
    loans", "Other loans"."""
    if (name or "").strip() == OTHER_LOAN:
        return "Other loans"
    kind = _kind(name)
    return kind[:1].upper() + kind[1:] + "s"


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()


def _money(value):
    return "UGX {:,.0f}".format(_num(value))
