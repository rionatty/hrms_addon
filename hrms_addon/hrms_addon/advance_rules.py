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

WHERE THE NUMBERS COME FROM

Luuka's own minutes — Human Resource, Reward and Compensation, 16 and 20
July 2026 — §4.4 for the leave advance and §4.9 for the salary advance;
LPL/HR/21 for the special advance. Every one of them is a setting on
Advance Settings rather than a constant here, because they are policy:
the day moves, the percentage moves, and neither should need a developer.
DEFAULTS below is what they are when nobody has changed them, and the
DocType's own defaults are checked against it (scripts/verify_salary_advance.py).

  Salary advance (§4.9)
    40% of gross, or a standard UGX 110,000 for the Per Meter category.
    Processed on the 15th; when that is a weekend or a public holiday, on
    the working day before. Only for regular employees who are not on
    leave, have not been absent more than three days, have no bank loan,
    and asked in time. The Payroll Officer checks the Off-Duty Forms so an
    approved off-duty day recorded as absent is not held against anyone.

  Leave advance (§4.4)
    60% of gross — for the Per Meter category, of the average gross over
    the previous two months. Only for regular employees with no bank or
    company loan, taking more than 19 days of leave.
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

# ── How gross is earned (minutes §4.6) ────────────────────────────────
# Per Meter and Per Piece pay on output, the other casuals by the hour, and
# everyone else a monthly salary.
MONTHLY, PER_METER, PER_PIECE, HOURLY = "Monthly", "Per Meter", "Per Piece", "Hourly"
PAY_CATEGORIES = (MONTHLY, PER_METER, PER_PIECE, HOURLY)

# the payroll period runs from the 26th of one month to the 25th of the next
CYCLE_START_DAY = 26
CYCLE_END_DAY = 25
# the bank does not process on a Saturday or a Sunday, whatever the factory does
WEEKEND = (5, 6)

# ── Advance Settings, as they stand when nobody has changed them ──────
DEFAULTS = {
    # §4.9 salary advance
    "salary_percent": 40.0,
    "per_meter_amount": 110000.0,
    "salary_processing_day": 15,
    "salary_move_before": 1,
    "salary_request_days_before": 3,
    "salary_hold_until_processing": 1,
    "salary_max_absent_days": 3,
    "salary_off_duty_not_absent": 1,
    "salary_not_on_leave": 1,
    "salary_no_bank_loan": 1,
    "salary_no_outstanding": 1,
    "salary_regular_only": 1,
    "salary_min_months": 0,
    "salary_instalments": 1,
    # §4.4 leave advance
    "leave_percent": 60.0,
    "leave_per_meter_months": 2,
    "leave_more_than_days": 19,
    "leave_regular_only": 1,
    "leave_no_loans": 1,
    # LPL/HR/21 special advance
    "special_percent": 50.0,
    "special_max_instalments": 3,
    "special_min_months": 3,
}

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


def settings_from(stored=None):
    """Advance Settings as the rules read them.

    What was saved stands; anything never saved takes its default. A saved
    nought is a nought — "no absence at all" is a real policy, and reading
    it as "unset" would quietly allow three days.
    """
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
    """What is wrong with Advance Settings, as messages."""
    s = _settings(settings)
    errors = []
    for key, what in (("salary_percent", "the salary advance"), ("leave_percent", "the leave advance"),
                      ("special_percent", "the special advance")):
        if not 0 < s[key] <= 100:
            errors.append("The percentage of gross for %s is more than 0 and no more than 100." % what)
    if not 1 <= s["salary_processing_day"] <= 28:
        errors.append("Salary advances are processed on a day from 1 to 28, so that every month has one.")
    if s["salary_request_days_before"] < 0:
        errors.append("Requests cannot close after the day they are processed.")
    if s["salary_max_absent_days"] < 0:
        errors.append("The days of absence allowed cannot be fewer than none.")
    for key, what in (("salary_instalments", "a salary advance"), ("special_max_instalments", "a special advance")):
        if s[key] < 1:
            errors.append("%s is recovered in at least one month." % _cap(what))
    if s["leave_per_meter_months"] < 1:
        errors.append("The Per Meter average is taken over at least one month.")
    if s["per_meter_amount"] < 0:
        errors.append("The Per Meter standard rate cannot be less than nothing.")
    return errors


def processing_date(year, month, settings=None, closed=()):
    """The day a month's salary advances are processed.

    The 15th by default; when that falls on a weekend or a public holiday,
    the working day before it (minutes §4.9). `closed` is the company's
    holiday list — its public holidays and whatever weekly offs it keeps.
    """
    s = _settings(settings)
    day = min(int(s["salary_processing_day"]), _days_in_month(int(year), int(month)))
    when = datetime.date(int(year), int(month), day)
    if int(s["salary_move_before"]):
        shut = {_date(value) for value in closed or ()}
        while when.weekday() in WEEKEND or when in shut:
            when -= datetime.timedelta(days=1)
    return when


def request_deadline(processed_on, settings=None):
    """The last day a request joins a run: "submitted the required Salary
    Advance Request Form in time" (minutes §4.9)."""
    s = _settings(settings)
    return _date(processed_on) - datetime.timedelta(days=int(s["salary_request_days_before"]))


def run_for(asked_on, settings=None, closed=()):
    """The processing date a request made on this day joins.

    This month's, if it came in before that run closed; otherwise the
    next one. A late request is not turned away — it waits for the next
    run, which is what happens to a late form on paper.
    """
    asked_on = _date(asked_on)
    year, month = asked_on.year, asked_on.month
    on = None
    for _ in range(3):
        on = processing_date(year, month, settings, closed)
        if asked_on <= request_deadline(on, settings):
            return on
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return on


def payroll_period(day):
    """(first day, last day) of the payroll period a day falls in: the
    26th of one month to the 25th of the next."""
    day = _date(day)
    if day.day >= CYCLE_START_DAY:
        start = datetime.date(day.year, day.month, CYCLE_START_DAY)
    else:
        back = add_months(datetime.date(day.year, day.month, 1), -1)
        start = datetime.date(back.year, back.month, min(CYCLE_START_DAY, _days_in_month(back.year, back.month)))
    forward = add_months(datetime.date(start.year, start.month, 1), 1)
    end = datetime.date(forward.year, forward.month, min(CYCLE_END_DAY, _days_in_month(forward.year, forward.month)))
    return start, end


def days_absent(absent, off_duty=(), settings=None):
    """The days of absence that count.

    An approved off-duty day recorded as absent is not an absence: the
    Payroll Officer checks the Off-Duty Forms for exactly this (§4.9).
    """
    s = _settings(settings)
    counted = {_date(day) for day in absent or () if _date(day)}
    if int(s["salary_off_duty_not_absent"]):
        counted -= {_date(day) for day in off_duty or () if _date(day)}
    return len(counted)


def entitled(kind, gross, pay_category=None, settings=None, average_gross=None):
    """The most an advance of this kind may be, by Luuka's own rule for it.

    None when there is nothing to work it out from — no gross on record —
    rather than nought, which would read as "nothing may be advanced".
    """
    s = _settings(settings)
    gross = _num(gross)
    if kind == SALARY_ADVANCE:
        if pay_category == PER_METER and _num(s["per_meter_amount"]) > 0:
            return round(_num(s["per_meter_amount"]), 2)
        return round(gross * _num(s["salary_percent"]) / 100.0, 2) if gross else None
    if kind == LEAVE_ADVANCE:
        base = _num(average_gross) if pay_category == PER_METER and _num(average_gross) else gross
        return round(base * _num(s["leave_percent"]) / 100.0, 2) if base else None
    return round(gross * _num(s["special_percent"]) / 100.0, 2) if gross else None


# ── The Salary Advance Request and the monthly run ────────────────────
# The employee applies once. The request stays active, month after month,
# until its last month or until it is stopped; each month's run picks it up
# and checks the conditions again for that month.
REQUEST_ACTIVE, REQUEST_STOPPED, REQUEST_ENDED = "Active", "Stopped", "Ended"
ASK_AMOUNT = "Say how much is being asked for."
NO_GROSS = "No gross pay on record."
NO_REQUEST = "No approved Salary Advance Request."
PAYMENT_METHODS = ("Cheque", "Bank Transfer", "Cash")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def request_errors(facts):
    """Problems with a request as it is sent for approval.

    facts: "employee", "first_month", "until_month", "amount", "today".
    """
    errors = []
    if not facts.get("employee"):
        errors.append("Select the employee.")
    first, until = _date(facts.get("first_month")), _date(facts.get("until_month"))
    now = _date(facts.get("today"))
    if not first:
        errors.append("Enter the month the advance starts.")
    elif until and (until.year, until.month) < (first.year, first.month):
        errors.append("The last month cannot be before the first month.")
    elif until and now and (until.year, until.month) < (now.year, now.month):
        errors.append("The last month has already passed.")
    if _num(facts.get("amount")) < 0:
        errors.append("The amount cannot be negative.")
    return errors


def joins_run(request, processed_on, settings=None):
    """Whether a request is paid in the run processed on this date, and if
    not, why.

    request: "status", "approved_on", "first_month", "until_month".
    A request approved after the run's closing day waits for the next one.
    """
    processed_on = _date(processed_on)
    month = (processed_on.year, processed_on.month)
    if request.get("status") != REQUEST_ACTIVE:
        return False, "The request is %s." % (request.get("status") or "not active").lower()
    first, until = _date(request.get("first_month")), _date(request.get("until_month"))
    if first and (first.year, first.month) > month:
        return False, "The request starts in %s %d." % (MONTHS[first.month - 1], first.year)
    if until and (until.year, until.month) < month:
        return False, "The request ended in %s %d." % (MONTHS[until.month - 1], until.year)
    approved = _date(request.get("approved_on"))
    deadline = request_deadline(processed_on, settings)
    if not approved or approved > deadline:
        return False, "Approved after requests closed on %s." % _day(deadline)
    return True, None


def line_amount(entitlement, requested):
    """What is paid: the amount asked for, up to what is allowed; the full
    amount allowed when nothing in particular was asked for; nothing when
    the allowance cannot be worked out."""
    entitlement, requested = _num(entitlement), _num(requested)
    if 0 < requested < entitlement:
        return round(requested, 2)
    return round(entitlement, 2)


def run_errors(facts, settings=None):
    """Why the month's run cannot be submitted yet.

    facts: "processing_date", "today", "unconfirmed" (plants not yet
    confirmed), "included" (lines to pay), "bank_account",
    "payment_method", "reference_no", "reference_date".
    """
    errors = []
    held = held_until(facts.get("processing_date"), facts.get("today"), settings)
    if held:
        errors.append(held)
    unconfirmed = list(facts.get("unconfirmed") or ())
    if unconfirmed:
        errors.append("Attendance and leave are not yet confirmed for: %s." % ", ".join(unconfirmed))
    if not int(facts.get("included") or 0):
        errors.append("Nobody in this run is included for payment.")
    if not facts.get("bank_account"):
        errors.append("Select the bank or cash account the advances are paid from.")
    method = facts.get("payment_method")
    if method not in PAYMENT_METHODS:
        errors.append("Select the payment method: %s." % ", ".join(PAYMENT_METHODS))
    elif method != "Cash" and not (facts.get("reference_no") and facts.get("reference_date")):
        errors.append("Enter the cheque or reference number and its date.")
    return errors


def held_until(processed_on, today, settings=None):
    """Why a salary advance may not go to Finance yet, or None.

    It is processed on the day, not before: that is what the date is for,
    and the absences are only final on it.
    """
    s = _settings(settings)
    processed_on, today = _date(processed_on), _date(today)
    if not int(s["salary_hold_until_processing"]) or not processed_on or not today:
        return None
    if today < processed_on:
        return ("Salary advances are processed on %s; this one can go to Finance from that day."
                % _day(processed_on))
    return None


def eligibility_errors(facts, settings=None):
    """Why this employee may not take this advance, as user-facing
    messages. An empty list means they qualify — the charts' "Qualify for
    advance?".

    facts: "advance_type", "status", "employment_type", "pay_category",
    "date_of_joining", "today", "gross_pay", "average_gross", "amount",
    "outstanding", "instalments", and for a salary advance
    "processing_date", "window_start", "days_absent", "on_leave",
    "bank_loan"; for a leave advance "bank_loan", "company_loan",
    "leave_days".
    """
    s = _settings(settings)
    kind = facts.get("advance_type") or SALARY_ADVANCE
    if kind not in ADVANCE_TYPES:
        return ["%r is not a valid advance type." % kind]
    errors = []
    if facts.get("status") and facts["status"] != ACTIVE:
        errors.append("Only an active employee may be advanced; this one is %s." % facts["status"])
    if kind == SALARY_ADVANCE:
        errors += _salary_errors(facts, s)
    elif kind == LEAVE_ADVANCE:
        errors += _leave_errors(facts, s)
    else:
        errors += _special_errors(facts, s)
    amount = _num(facts.get("amount"))
    if amount <= 0:
        errors.append(ASK_AMOUNT)
    ceiling = entitled(kind, facts.get("gross_pay"), facts.get("pay_category"), s, facts.get("average_gross"))
    if ceiling is not None and amount > ceiling:
        errors.append("The most that may be advanced is %s, %s." % (_money(ceiling), _because(kind, facts, s)))
    return errors


def _salary_errors(facts, s):
    """§4.9: regular, not on leave, not absent more than three days, no
    bank loan — and nothing still owed on an earlier advance (test case 2)."""
    errors = []
    kind = facts.get("employment_type")
    if int(s["salary_regular_only"]) and kind and kind in s["not_regular_types"]:
        errors.append("A salary advance is for regular employees; %s staff do not qualify." % kind)
    errors += _served(facts, s["salary_min_months"])
    if int(s["salary_not_on_leave"]) and facts.get("on_leave"):
        errors.append("On leave on %s, the day salary advances are processed."
                      % _day(facts.get("processing_date")))
    absent = int(_num(facts.get("days_absent")))
    allowed = int(s["salary_max_absent_days"])
    if absent > allowed:
        errors.append("Absent %d day(s) since %s; a salary advance allows no more than %d."
                      % (absent, _day(facts.get("window_start")), allowed))
    if int(s["salary_no_bank_loan"]) and facts.get("bank_loan"):
        errors.append("Has a bank loan, and a salary advance is not given alongside one.")
    if int(s["salary_no_outstanding"]) and _num(facts.get("outstanding")) > 0:
        errors.append("%s is still owed on an earlier advance. It is recovered before another is given."
                      % _money(facts.get("outstanding")))
    if int(facts.get("instalments") or 0) > int(s["salary_instalments"]):
        errors.append("A salary advance is recovered in %d month(s)." % int(s["salary_instalments"]))
    return errors


def _leave_errors(facts, s):
    """§4.4: regular, no bank or company loan, more than 19 days of leave."""
    errors = []
    kind = facts.get("employment_type")
    if int(s["leave_regular_only"]) and kind and kind in s["not_regular_types"]:
        errors.append("A leave advance is for regular employees; %s staff do not qualify." % kind)
    if int(s["leave_no_loans"]):
        if facts.get("bank_loan"):
            errors.append("Has a bank loan, and a leave advance is not given alongside one.")
        if _num(facts.get("company_loan")) > 0:
            errors.append("%s is still owed on a company loan." % _money(facts.get("company_loan")))
    days = facts.get("leave_days")
    if days is not None and _num(days) <= int(s["leave_more_than_days"]):
        errors.append("A leave advance is for leave of more than %d days; this leave is %g."
                      % (int(s["leave_more_than_days"]), _num(days)))
    if _num(facts.get("outstanding")) > 0:
        errors.append("%s is still owed on an earlier advance. It is recovered before another is given."
                      % _money(facts.get("outstanding")))
    if int(facts.get("instalments") or 0) > MAX_INSTALMENTS:
        errors.append("An advance is recovered in at most %d month(s)." % MAX_INSTALMENTS)
    return errors


def _special_errors(facts, s):
    """LPL/HR/21: after three months' service, recovered in at most three."""
    errors = _served(facts, s["special_min_months"])
    if _num(facts.get("outstanding")) > 0:
        errors.append("%s is still owed on an earlier advance. It is recovered before another is given."
                      % _money(facts.get("outstanding")))
    if int(facts.get("instalments") or 0) > int(s["special_max_instalments"]):
        errors.append("An advance is recovered in at most %d month(s)." % int(s["special_max_instalments"]))
    return errors


def _served(facts, minimum):
    minimum = int(minimum or 0)
    if not minimum:
        return []
    served = months_served(facts.get("date_of_joining"), facts.get("processing_date") or facts.get("today"))
    if served < minimum:
        return ["An advance is given after %d month(s) of service; this employee has served %d."
                % (minimum, served)]
    return []


def _because(kind, facts, s):
    if kind == SALARY_ADVANCE:
        if facts.get("pay_category") == PER_METER and _num(s["per_meter_amount"]) > 0:
            return "the standard rate for the Per Meter category"
        return "being %g%% of a gross of %s" % (s["salary_percent"], _money(facts.get("gross_pay")))
    if kind == LEAVE_ADVANCE:
        if facts.get("pay_category") == PER_METER and _num(facts.get("average_gross")):
            return "being %g%% of the average gross over the last %d month(s), %s" % (
                s["leave_percent"], int(s["leave_per_meter_months"]), _money(facts.get("average_gross")))
        return "being %g%% of a gross of %s" % (s["leave_percent"], _money(facts.get("gross_pay")))
    return "being %g%% of a gross of %s" % (s["special_percent"], _money(facts.get("gross_pay")))


def _settings(settings):
    """Settings already merged are used as they are; anything else — a raw
    stored dict, or nothing at all — is merged with the defaults first."""
    if settings and "not_regular_types" in settings and all(key in settings for key in DEFAULTS):
        return settings
    return settings_from(settings)


def _cap(text):
    return text[:1].upper() + text[1:]


def _day(value):
    value = _date(value)
    return value.strftime("%d %b %Y").lstrip("0") if value else "the processing date"


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
