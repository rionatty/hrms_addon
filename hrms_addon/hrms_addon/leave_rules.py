# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Management rules: Luuka's To-Be leave process (4.1).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_leave.py exercises them without a bench.

The process, from the revised flow chart:

  1. The HR Officer draws up the Annual Leave Plan at the end of a year for
     the year coming, from what each department can spare.
  2. The HODs approve the plan for their own people.
  3. The HR Officer tells each employee their dates.
  4. The system watches: when a planned leave comes due, or enough leave has
     accrued, the employee and the immediate supervisor are told.
  5. The employee applies (LPL/HR/15).
  6. It is approved by the Immediate Supervisor, then the HOD, then the HR
     Officer.
  7. Leave advance wanted? Then the Leave Advance process (advance_rules.py);
     otherwise the employee goes on leave.
  8. The employee reports back and the leave closes.

LPL/HR/15 is the paper: Part 1 the applicant's, Part 2 the HR Officer's
balances, Part 3 the three signatures, Part 4 what Accounts advanced.
"""

import datetime

# ── the five kinds LPL/HR/15 offers ───────────────────────────────────
ANNUAL = "Annual Leave"
MATERNITY = "Maternity Leave"
PATERNITY = "Paternity Leave"
SICK = "Sick Leave"
COMPASSIONATE = "Compassionate Leave"
UNPAID = "Leave Without Pay"
LEAVE_TYPES = (ANNUAL, MATERNITY, PATERNITY, SICK, COMPASSIONATE, UNPAID)

# what the form asks for beside the dates
NEEDS_CERTIFICATE = (MATERNITY, PATERNITY, SICK)
NEEDS_REASON = (COMPASSIONATE,)
UNPAID_TYPES = (UNPAID,)

# The Employment Act (Uganda) minima Luuka's leave types are set up from.
# They are defaults for the seed, not a rule the module enforces: what an
# employee is actually owed is the Leave Allocation on the site.
STATUTORY_DAYS = {ANNUAL: 21, MATERNITY: 60, PATERNITY: 4, SICK: 30, COMPASSIONATE: 7, UNPAID: 0}

# ── the annual plan ───────────────────────────────────────────────────
PLAN_DRAFT, PLAN_PENDING_HOD, PLAN_PENDING_HR = "Draft", "Pending HOD", "Pending HR Officer"
PLAN_APPROVED, PLAN_CANCELLED = "Approved", "Cancelled"
PLAN_STATUSES = (PLAN_DRAFT, PLAN_PENDING_HOD, PLAN_PENDING_HR, PLAN_APPROVED, PLAN_CANCELLED)

# how long before a planned leave the employee and supervisor are told
DUE_HORIZONS = (30, 14, 7)

# ── an application ────────────────────────────────────────────────────
APPLIED, ON_LEAVE, REPORTED_BACK = "Applied", "On Leave", "Reported Back"


def year_window(year):
    """The plan year: 1 January to 31 December."""
    year = int(year)
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def days_between(start, end):
    """Whole days a leave covers, both ends counted, as LPL/HR/15 does."""
    start, end = _date(start), _date(end)
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def end_for(start, days):
    """The last day of a leave of `days` starting on `start`."""
    start = _date(start)
    if not start or not days or int(days) < 1:
        return None
    return start + datetime.timedelta(days=int(days) - 1)


def balance_after(before, days):
    """The balance Part 2 of the form writes for after the leave."""
    return round(_num(before) - _num(days), 2)


def needs_certificate(leave_type):
    return leave_type in NEEDS_CERTIFICATE


def needs_reason(leave_type):
    return leave_type in NEEDS_REASON


def plan_errors(facts):
    """Problems with an Annual Leave Plan, as user-facing messages.

    facts: "year", "rows" of employee, employee_name, planned_from,
    planned_to, planned_days, entitlement_days.
    """
    errors = []
    year = facts.get("year")
    if not year:
        errors.append("Say which year the plan is for.")
    rows = facts.get("rows") or []
    if not rows:
        errors.append("A leave plan needs at least one employee on it.")
    start = end = None
    if year:
        start, end = year_window(year)
    seen = set()
    for index, row in enumerate(rows, 1):
        who = row.get("employee_name") or row.get("employee") or "row %d" % index
        if not row.get("employee"):
            errors.append("Row %d has no employee on it." % index)
        elif row["employee"] in seen:
            errors.append("%s is on the plan twice. One planned leave each per year." % who)
        else:
            seen.add(row["employee"])
        first, last = _date(row.get("planned_from")), _date(row.get("planned_to"))
        if not first or not last:
            errors.append("%s has no planned dates." % who)
            continue
        if last < first:
            errors.append("%s ends the leave before it starts." % who)
            continue
        if start and not (start <= first and last <= end):
            errors.append("%s is planned outside %s." % (who, year))
        planned = _num(row.get("planned_days"))
        counted = days_between(first, last)
        if planned and round(planned, 2) != counted:
            errors.append("%s is planned for %g day(s) but the dates cover %d." % (who, planned, counted))
        entitlement = _num(row.get("entitlement_days"))
        if entitlement and (planned or counted) > entitlement:
            errors.append("%s is planned for more days than the %g they are entitled to." % (who, entitlement))
    return errors


def application_errors(facts):
    """Problems with a Leave Application, as user-facing messages.

    facts: "leave_type", "from_date", "to_date", "total_leave_days",
    "certificate", "reason", "balance_before".
    """
    errors = []
    leave_type = facts.get("leave_type")
    first, last = _date(facts.get("from_date")), _date(facts.get("to_date"))
    if first and last and last < first:
        errors.append("The leave ends before it starts.")
    if needs_certificate(leave_type) and not facts.get("certificate"):
        errors.append("%s needs a medical certificate attached (LPL/HR/15)." % leave_type)
    if needs_reason(leave_type) and not _text(facts.get("reason")):
        errors.append("Compassionate Leave needs the precise reason written on the form.")
    days = _num(facts.get("total_leave_days")) or (days_between(first, last) if first and last else 0)
    balance = facts.get("balance_before")
    if leave_type not in UNPAID_TYPES and balance is not None and days > _num(balance):
        errors.append("%g day(s) applied for, %g left. Apply for Leave Without Pay for the rest."
                      % (days, _num(balance)))
    return errors


def due_alerts(planned_from, today, horizons=DUE_HORIZONS, sent=None):
    """The horizons reached and not yet told, nearest first.

    An employee first seen inside several horizons — a job that did not run,
    a plan approved late — gets one notice covering them all, like the
    contract alerts (contract_rules.alerts_due).
    """
    planned_from = _date(planned_from)
    today = _date(today)
    if not planned_from or not today:
        return []
    left = (planned_from - today).days
    if left < 0:
        return []
    told = set(record_split(sent))
    return sorted((h for h in horizons if left <= h and h not in told), reverse=True)


def record_alerts(sent, horizons):
    """What the plan row remembers after telling someone."""
    return ",".join(str(h) for h in sorted(set(record_split(sent)) | set(horizons), reverse=True))


def record_split(sent):
    return [int(part) for part in str(sent or "").replace(" ", "").split(",") if part.isdigit()]


def advance_wanted(facts):
    """Step 7 of the chart: the form's "Salary Requested in Advance"."""
    return bool(facts.get("salary_requested_in_advance"))


def leave_stage(docstatus, from_date, to_date, today, reported_back=False):
    """Where a submitted leave stands, for the report-back step."""
    if docstatus != 1:
        return None
    if reported_back:
        return REPORTED_BACK
    first, last = _date(from_date), _date(to_date)
    today = _date(today)
    if not first or not last or not today:
        return APPLIED
    if today < first:
        return APPLIED
    if today <= last:
        return ON_LEAVE
    return REPORTED_BACK


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
