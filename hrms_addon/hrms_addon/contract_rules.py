# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Contract rules: Luuka's To-Be contract management.

No Frappe import, like the other *_rules.py modules, so scripts/verify_contracts.py
exercises them without a bench.

  1. The HR Officer prepares the contract; the employee signs it (outside
     the system) and HR records the signed copy, which submits it.
  2. The system watches the contract and tells the HR Officer as its end
     comes near: a year, a quarter and a month before (Onboarding Settings,
     contract_alert_days).
  3. The HR Officer decides: renew (a new contract from the day after, for
     the Employment Type's usual length, one year by default) or not (the
     termination process follows, with the Expiry of Contract letter).
"""

import datetime
import re

DRAFT, ACTIVE, EXPIRING, EXPIRED = "Draft", "Active", "Expiring Soon", "Expired"
RENEWED, NOT_RENEWED, CANCELLED = "Renewed", "Not Renewed", "Cancelled"
STATUSES = (DRAFT, ACTIVE, EXPIRING, EXPIRED, RENEWED, NOT_RENEWED, CANCELLED)
# "Expiring Soon" from a quarter before the end
EXPIRING_DAYS = 90
DEFAULT_ALERT_DAYS = (365, 90, 30)
# A renewal runs one year unless the Employment Type says otherwise (the
# Contract Renewal letter: "renewing your contract for one year")
DEFAULT_RENEWAL_MONTHS = 12


def parse_alert_days(text):
    """"365, 90, 30" -> (365, 90, 30): whole positive days, largest first,
    each once; the default when nothing usable is given."""
    days = sorted({int(n) for n in re.findall(r"-?\d+", str(text or "")) if int(n) > 0}, reverse=True)
    return tuple(days) or DEFAULT_ALERT_DAYS


def days_left(end, today):
    return (_date(end) - _date(today)).days


def contract_status(docstatus, end, today, renewed=False, not_renewed=False):
    """Where a contract stands on `today`."""
    if docstatus == 0:
        return DRAFT
    if docstatus == 2:
        return CANCELLED
    if renewed:
        return RENEWED
    if not_renewed:
        return NOT_RENEWED
    if not end:
        return ACTIVE  # open-ended
    left = days_left(end, today)
    if left < 0:
        return EXPIRED
    return EXPIRING if left <= EXPIRING_DAYS else ACTIVE


def alerts_due(end, today, alert_days, sent):
    """The alert thresholds reached and not yet sent, largest first. A
    contract first seen inside several thresholds (a job that did not run,
    a contract entered late) gets one alert covering them all."""
    if not end:
        return []
    left = days_left(end, today)
    if left < 0:
        return []
    sent = {int(n) for n in re.findall(r"\d+", str(sent or ""))}
    thresholds = parse_alert_days(alert_days) if isinstance(alert_days, str) else sorted(set(alert_days), reverse=True)
    return [threshold for threshold in thresholds if left <= threshold and threshold not in sent]


def record_alerts(sent, thresholds):
    """The alerts_sent field after sending `thresholds`."""
    days = {int(n) for n in re.findall(r"\d+", str(sent or ""))} | set(thresholds)
    return ", ".join(str(n) for n in sorted(days, reverse=True))


def add_months(day, months):
    day = _date(day)
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    last = (datetime.date(year + month // 12, month % 12 + 1, 1) - datetime.timedelta(days=1)).day
    return datetime.date(year, month, min(day.day, last))


def end_for(start, months):
    """The last day of a contract of `months` months from `start` (None for
    an open-ended one, months 0 or blank)."""
    if not months:
        return None
    return add_months(start, months) - datetime.timedelta(days=1)


def renewal_dates(end, months):
    """(start, end) of the contract renewing one that ends on `end`."""
    start = _date(end) + datetime.timedelta(days=1)
    return start, end_for(start, months or DEFAULT_RENEWAL_MONTHS)


def contract_errors(facts, today):
    """Problems with a contract, as user-facing messages.

    facts: "start_date", "end_date", "open_ended" (the Employment Type has
    no usual length), "submitting", "signed_on", "signed_contract",
    "overlaps" ([names of the employee's other live contracts covering these
    dates]).
    """
    errors = []
    start, end = facts.get("start_date"), facts.get("end_date")
    if start and end and _date(end) < _date(start):
        errors.append("The contract cannot end before it starts.")
    if not end and not facts.get("open_ended"):
        errors.append("Set the End Date: this Employment Type is not open-ended (it has a usual contract length).")
    if facts.get("overlaps"):
        errors.append("The employee already has a contract for these dates: %s. Renew it instead, or cancel it first."
                      % ", ".join(facts["overlaps"]))
    if facts.get("submitting"):
        if not facts.get("signed_on"):
            errors.append("Record the date the employee signed the contract before submitting it.")
        elif _date(facts["signed_on"]) > _date(today):
            errors.append("The date signed cannot be in the future.")
        if not facts.get("signed_contract"):
            errors.append("Attach the signed contract before submitting it.")
    return errors


def overlaps(start, end, others):
    """The contracts in `others` ([{"name", "start_date", "end_date"}], live
    ones) whose dates meet [start, end]; an open end runs forever."""
    start = _date(start)
    stop = _date(end) if end else datetime.date.max
    hits = []
    for other in others:
        other_start = _date(other["start_date"])
        other_stop = _date(other["end_date"]) if other.get("end_date") else datetime.date.max
        if other_start <= stop and start <= other_stop:
            hits.append(other["name"])
    return hits


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
