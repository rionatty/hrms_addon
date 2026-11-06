# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The safety module's rules (Luuka's review list of 5 Nov 2026, items 11 to
17): what an incident must say, the doctor's reports and the rest each one
gives, and where the employee stands after the accident.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_safety.py exercises them without a bench. Who signs what is in
safety_approval.py; safety.py reads and writes the site.

The doctor's reports are rows on the incident (item 14: "the doctor's report
is more than one. Need a provision for multiple reports and rest days"), each
with what the doctor recommends:

  Rest            days off from a day: a sick leave of their own
  Light Duty      back on the light work the doctor allows, told to whoever
                  the employee works under (item 17: "light work is
                  sometimes recommended if sickness persists")
  Fit to Work     back at work
  Unfit for Work  the doctor's recommendation a separation on medical
                  grounds rests on (item 17: "Termination comes on doctor's
                  recommendation"), which the HR Manager then decides

The latest report says where the employee stands. A report that gave a sick
leave stays as it was: the leave was made from it.
"""

import datetime

SICK_LEAVE = "Sick Leave"
HRM = "HR Manager"

# what a doctor's report recommends
REST, LIGHT_DUTY, FIT, UNFIT = "Rest", "Light Duty", "Fit to Work", "Unfit for Work"
RECOMMENDATIONS = (REST, LIGHT_DUTY, FIT, UNFIT)

# where the employee stands after the accident: the incident's Status
DRAFT, RECORDED, ON_SICK_LEAVE, ON_LIGHT_DUTY, BACK, UNFIT_FOR_WORK, SEPARATED, CANCELLED = (
    "Draft", "Recorded", "On Sick Leave", "On Light Duty", "Back at Work", "Unfit for Work", "Separated", "Cancelled")
STATUSES = (DRAFT, RECORDED, ON_SICK_LEAVE, ON_LIGHT_DUTY, BACK, UNFIT_FOR_WORK, SEPARATED, CANCELLED)
STANDING = {REST: ON_SICK_LEAVE, LIGHT_DUTY: ON_LIGHT_DUTY, FIT: BACK, UNFIT: UNFIT_FOR_WORK}
# what a report that gave a sick leave keeps as it was
FIXED_FIELDS = ("recommendation", "rest_from", "rest_days", "leave_application")


# ── the accident ──────────────────────────────────────────────────────
def incident_errors(facts):
    """Problems with a safety incident, as user-facing messages."""
    errors = []
    if not facts.get("employee"):
        errors.append("Say who the accident happened to.")
    if not facts.get("incident_on"):
        errors.append("Say when it happened.")
    if not _text(facts.get("nature")):
        errors.append("Write what happened; the EHS Officer's report is the record of it.")
    if not facts.get("manageable") and not _text(facts.get("hospital")):
        errors.append("The employee was taken to hospital: say which one.")
    return errors


def incident_status(docstatus, rows, manageable, separation):
    """Where the employee stands: by the doctor's latest report, else on
    site or still to be seen by a doctor."""
    if docstatus == 2:
        return CANCELLED
    if docstatus == 0:
        return DRAFT
    if separation:
        return SEPARATED
    latest = latest_report(rows)
    if latest is not None:
        return STANDING.get(latest.get("recommendation"), RECORDED)
    return BACK if manageable else RECORDED


# ── the doctor's reports ──────────────────────────────────────────────
def rest_to(rest_from, days):
    """The last day of a rest: both ends counted."""
    start, days = _date(rest_from), _int(days)
    if not start or days <= 0:
        return None
    return start + datetime.timedelta(days=days - 1)


def latest_report(rows):
    """The doctor's latest report: the last dated, and of two on one day the
    later row."""
    latest = None
    for row in rows or ():
        day = _date(row.get("report_date"))
        if day and (latest is None or day >= _date(latest.get("report_date"))):
            latest = row
    return latest


def report_errors(rows, incident_on):
    """Problems with the doctor's reports, as user-facing messages."""
    day = _date(incident_on)
    errors, rests = [], []
    for index, row in enumerate(rows or (), 1):
        label = "Doctor's report %s" % (row.get("idx") or index)
        on = _date(row.get("report_date"))
        if not on:
            errors.append("%s: say when the doctor gave it." % label)
        elif day and on < day:
            errors.append("%s is dated before the accident." % label)
        recommendation = row.get("recommendation")
        if recommendation not in RECOMMENDATIONS:
            errors.append("%s: say what the doctor recommends." % label)
        elif recommendation == REST:
            start, end = _date(row.get("rest_from")), rest_to(row.get("rest_from"), row.get("rest_days"))
            if not end:
                errors.append("%s: say from when, and for how many days, the doctor gives rest." % label)
            elif day and start < day:
                errors.append("%s: the rest starts before the accident." % label)
            else:
                rests.append((start, end, label))
        elif recommendation == LIGHT_DUTY and not _text(row.get("light_duties")):
            errors.append("%s: say what light work the doctor allows." % label)
    rests.sort()
    for (_start, first_end, first), (second_start, _end, second) in zip(rests, rests[1:]):
        if second_start <= first_end:
            errors.append("%s gives rest while %s's still runs: one sick leave at a time." % (second, first))
    return errors


def fixed_row_errors(before_rows, rows):
    """A report that gave a sick leave stays on the incident as it was."""
    now = {row.get("name"): row for row in rows or () if row.get("name")}
    errors = []
    for old in before_rows or ():
        leave = old.get("leave_application")
        if not leave:
            continue
        label = "The doctor's report of %s" % (_date(old.get("report_date")) or "")
        new = now.get(old.get("name"))
        if new is None:
            errors.append("%s gave the sick leave %s: it stays on the incident." % (label, leave))
        elif any(_kept(field, old.get(field)) != _kept(field, new.get(field)) for field in FIXED_FIELDS):
            errors.append("%s gave the sick leave %s, which was made from it: change the leave itself, or add the "
                          "doctor's next report." % (label, leave))
    return errors


def rest_ended(rows, today):
    """The day a rest ended, where it ended yesterday and the doctor has not
    reported since: the doctor's next word is due."""
    latest = latest_report(rows)
    if latest is None or latest.get("recommendation") != REST:
        return None
    end, day = rest_to(latest.get("rest_from"), latest.get("rest_days")), _date(today)
    return end if end and day and end == day - datetime.timedelta(days=1) else None


# ── the separation, on the doctor's recommendation ────────────────────
def separation_errors(docstatus, rows, separation, roles):
    """Whether the HR Manager may separate the employee on medical grounds
    from this incident now."""
    errors = []
    if HRM not in set(roles or ()):
        errors.append("Only the HR Manager separates an employee on medical grounds.")
    if docstatus != 1:
        errors.append("Record the incident first.")
    if separation:
        errors.append("The employee is already being separated: %s." % separation)
    latest = latest_report(rows)
    if latest is None or latest.get("recommendation") != UNFIT:
        errors.append("An employee is separated on medical grounds only on the doctor's recommendation: the latest "
                      "doctor's report must find them unfit for work.")
    return errors


def last_day_of_work(rows, today):
    """The last day of work a separation on medical grounds names unless
    HR say otherwise: the end of the last rest the doctor gave, or the day of
    the report that found the employee unfit, whichever is later."""
    days = [rest_to(row.get("rest_from"), row.get("rest_days")) for row in rows or ()
            if row.get("recommendation") == REST]
    latest = latest_report(rows)
    if latest is not None:
        days.append(_date(latest.get("report_date")))
    days = [day for day in days if day]
    return max(days) if days else _date(today)


# ── the medical treatment order (item 11) ─────────────────────────────
def order_errors(facts):
    """Problems with a treatment order, as user-facing messages. facts:
    "employee", "hospital", "complaint", "transport_required",
    "transport_amount", "incident_employee" (the employee of the incident
    it names, if it names one)."""
    errors = []
    if not facts.get("employee"):
        errors.append("Say who the order is for.")
    if not _text(facts.get("hospital")):
        errors.append("Say which hospital the order is for.")
    if not _text(facts.get("complaint")):
        errors.append("Say what the employee is to be treated for.")
    if facts.get("transport_required") and _num(facts.get("transport_amount")) <= 0:
        errors.append("Say how much the transport to the hospital costs.")
    if facts.get("incident_employee") and facts.get("incident_employee") != facts.get("employee"):
        errors.append("The safety incident it names happened to someone else.")
    return errors


# ── the transport, paid in cash by the plant's accountant (item 15) ───
ACCOUNTANTS = ("Accounts User", "Accounts Manager")


def transport_errors(facts):
    """Whether the transport to the hospital may be paid now. facts:
    "docstatus", "transport_required", "transport_amount", "transport_entry",
    "account" (Safety Settings' transport account, if it is the order's
    company's), "cash_account" (the company's default), "roles"."""
    errors = []
    if not set(facts.get("roles") or ()) & set(ACCOUNTANTS):
        errors.append("The plant's accountant pays the transport.")
    if facts.get("docstatus") != 1:
        errors.append("The transport is paid once the order is issued.")
    if not facts.get("transport_required"):
        errors.append("The order needs no transport.")
    elif _num(facts.get("transport_amount")) <= 0:
        errors.append("Say how much the transport is.")
    if facts.get("transport_entry"):
        errors.append("The transport is paid already: %s." % facts["transport_entry"])
    if not facts.get("account"):
        errors.append("Set the Transport to Hospital Account in Safety Settings, an account of the order's company.")
    if not facts.get("cash_account"):
        errors.append("Set the company's Default Cash Account.")
    return errors


def transport_paid(rows, account):
    """What an entry pays toward the transport: its debits on the transport
    account, less its credits there."""
    if not account:
        return 0.0
    return round(sum(_num(row.get("debit_in_account_currency")) - _num(row.get("credit_in_account_currency"))
                     for row in rows or () if row.get("account") == account), 2)


# ── the compensation, claimed on the insurance (item 15) ──────────────
NOT_LODGED, LODGED, APPROVED, REJECTED, PAID = "Not Lodged", "Lodged", "Approved", "Rejected", "Paid"
CLAIM_STATUSES = (NOT_LODGED, LODGED, APPROVED, REJECTED, PAID)


def compensation_errors(facts):
    """The compensation claimed on the insurance, which the insurer pays to
    the employee (the user, 5 Nov 2026: "insuranecy pays the employee not
    the company"): Luuka follow the claim and book nothing. facts:
    "compensation_required", "compensation_amount", "insurance_policy",
    "policy_from", "policy_to", "incident_on", "claim_status",
    "claim_number", "claim_lodged_on", "insurer_paid_amount",
    "insurer_paid_on"."""
    if not facts.get("compensation_required"):
        return []
    errors = []
    if _num(facts.get("compensation_amount")) <= 0:
        errors.append("Say how much compensation is being claimed.")
    status = facts.get("claim_status") or NOT_LODGED
    if status != NOT_LODGED:
        if not facts.get("insurance_policy"):
            errors.append("Say which insurance policy the claim is made on.")
        if not _text(facts.get("claim_number")):
            errors.append("Give the insurer's claim number.")
        if not _date(facts.get("claim_lodged_on")):
            errors.append("Say when the claim was lodged.")
    if status == PAID:
        if _num(facts.get("insurer_paid_amount")) <= 0:
            errors.append("Say how much the insurer paid the employee.")
        if not _date(facts.get("insurer_paid_on")):
            errors.append("Say when the insurer paid the employee.")
    day, start, end = _date(facts.get("incident_on")), _date(facts.get("policy_from")), _date(facts.get("policy_to"))
    if facts.get("insurance_policy") and day and ((start and day < start) or (end and day > end)):
        errors.append("The policy %s does not cover the accident of %s: it runs from %s to %s."
                      % (facts["insurance_policy"], day, start or "its start", end or "its end"))
    return errors


def _kept(field, value):
    if field == "rest_from":
        return _date(value)
    if field == "rest_days":
        return _int(value)
    return _text(value)


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


def _int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return str(value or "").strip()
