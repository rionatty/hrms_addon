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

import calendar
import datetime
import math

# ── the five kinds LPL/HR/15 offers ───────────────────────────────────
ANNUAL = "Annual Leave"
MATERNITY = "Maternity Leave"
PATERNITY = "Paternity Leave"
SICK = "Sick Leave"
COMPASSIONATE = "Compassionate Leave"
UNPAID = "Leave Without Pay"
LEAVE_TYPES = (ANNUAL, MATERNITY, PATERNITY, SICK, COMPASSIONATE, UNPAID)
# sick leave past its sixty days: another 120 at half pay, on an official
# document from the hospital (minutes §4.3). Its own Leave Type, because
# that is how Frappe HR pays part of a day (Is Partially Paid Leave).
SICK_HALF_PAY = "Sick Leave (Half Pay)"
EXTRA_TYPES = (SICK_HALF_PAY,)
HALF_PAY_FRACTION = 0.5

# what the form asks for beside the dates
NEEDS_CERTIFICATE = (MATERNITY, PATERNITY, SICK, SICK_HALF_PAY)
NEEDS_REASON = (COMPASSIONATE,)
UNPAID_TYPES = (UNPAID,)

# Luuka's own leave, from the minutes of 16 and 20 July 2026 (Reward and
# Compensation, §4.3). What each Leave Type is set up with; what an
# employee is actually owed is still their Leave Allocation.
#
#   Annual           21 days, or 28 or 30 for the people Management names
#                    — and administration staff carry unused days forward
#                    with no maximum. Frappe HR refuses any allocation over
#                    a type's maximum and cuts carried-forward days back to
#                    it, so Annual Leave carries no maximum at all (0): a
#                    cap of 21 would block the 28 and 30 and eat the
#                    carry-forward.
#   Maternity        60 days
#   Paternity         4 days
#   Sick             60 days at full pay, and 120 more at half pay on an
#                    official document from the hospital
#   Compassionate     4 days
#   Without pay      at most 60 days, as the individual's situation allows
LEAVE_DAYS = {ANNUAL: 0, MATERNITY: 60, PATERNITY: 4, SICK: 60, SICK_HALF_PAY: 120,
              COMPASSIONATE: 4, UNPAID: 60}
ANNUAL_OPTIONS = (21, 28, 30)
# what the seed wrote before the minutes were read, so a migrate can tell a
# type nobody has touched from one Luuka set up themselves
FORMER_DAYS = {ANNUAL: 21, SICK: 30, COMPASSIONATE: 7, UNPAID: 0}

# ── the annual plan ───────────────────────────────────────────────────
PLAN_DRAFT, PLAN_PENDING_HOD, PLAN_PENDING_HR = "Draft", "Pending HOD", "Pending HR Officer"
PLAN_APPROVED, PLAN_CANCELLED = "Approved", "Cancelled"
PLAN_STATUSES = (PLAN_DRAFT, PLAN_PENDING_HOD, PLAN_PENDING_HR, PLAN_APPROVED, PLAN_CANCELLED)

# how long before a planned leave the employee and supervisor are told
DUE_HORIZONS = (30, 14, 7)
# what the plan row remembers once HR are told a leave was not applied for
NOT_APPLIED_TOLD = "not applied"

# where a planned leave stands
PLANNED, APPLIED, TAKEN, NOT_APPLIED = "Planned", "Applied", "Taken", "Not Applied"
ROW_STATUSES = (PLANNED, APPLIED, TAKEN, NOT_APPLIED)

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


def leave_days(start, end, holidays=(), include_holidays=False):
    """The days a leave takes from the balance, as Frappe HR's Leave
    Application counts them: both ends, less the holidays on the employee's
    list unless the leave type counts holidays as leave."""
    start, end = _date(start), _date(end)
    if not start or not end or end < start:
        return 0
    total = (end - start).days + 1
    if include_holidays:
        return total
    off = {day for day in (_date(value) for value in holidays or ()) if day and start <= day <= end}
    return total - len(off)


def end_after(start, days, holidays=(), include_holidays=False):
    """The last day of a leave of `days` leave days from `start`, the
    holidays passed over unless the leave type counts them."""
    start = _date(start)
    wanted = int(math.ceil(_num(days)))
    if not start or wanted < 1:
        return None
    off = set() if include_holidays else {day for day in (_date(value) for value in holidays or ()) if day}
    counted, day = 0, start
    for _step in range(wanted + 400):
        if day not in off:
            counted += 1
            if counted == wanted:
                return day
        day += datetime.timedelta(days=1)
    return None


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
    planned_to, planned_days, available_days. An employee may have more
    than one row: their leave split into parts, which must not overlap and
    together fit what they have available.
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
    parts = {}
    for index, row in enumerate(rows, 1):
        who = row.get("employee_name") or row.get("employee") or "row %d" % index
        if not row.get("employee"):
            errors.append("Row %d has no employee on it." % index)
            continue
        first, last = _date(row.get("planned_from")), _date(row.get("planned_to"))
        if not first or not last:
            errors.append("%s has no planned dates." % who)
            continue
        if last < first:
            errors.append("%s ends the leave before it starts." % who)
            continue
        if start and not (start <= first and last <= end):
            errors.append("%s is planned outside %s." % (who, year))
        parts.setdefault(row["employee"], []).append(
            (first, last, _num(row.get("planned_days")), who, _num(row.get("available_days"))))
    for employee in parts:
        spans = sorted(parts[employee])
        who = spans[0][3]
        for before, after in zip(spans, spans[1:]):
            if after[0] <= before[1]:
                errors.append("%s's planned leave overlaps: %s to %s and %s to %s."
                              % (who, _day(before[0]), _day(before[1]), _day(after[0]), _day(after[1])))
        planned = sum(span[2] for span in spans)
        available = max(span[4] for span in spans)
        if available and planned > available:
            errors.append("%s is planned for %g day(s), %g available." % (who, planned, available))
    return errors


def clashes(rows, most_off):
    """Where more of one department than `most_off` are planned off on the
    same days: [{"department", "from", "to", "most", "names"}], earliest
    first. rows: employee, employee_name, department, planned_from,
    planned_to."""
    most_off = int(_num(most_off))
    if most_off < 1:
        return []
    off = {}
    for row in rows or ():
        first, last = _date(row.get("planned_from")), _date(row.get("planned_to"))
        if not row.get("employee") or not first or not last or last < first:
            continue
        name = row.get("employee_name") or row.get("employee")
        day = first
        while day <= last:
            off.setdefault((row.get("department") or "", day), set()).add(name)
            day += datetime.timedelta(days=1)
    found = []
    for department in sorted({key[0] for key in off}):
        run = []
        for day in sorted(key[1] for key in off if key[0] == department and len(off[key]) > most_off):
            if run and day != run[-1] + datetime.timedelta(days=1):
                found.append(_clash(department, run, off))
                run = []
            run.append(day)
        if run:
            found.append(_clash(department, run, off))
    return sorted(found, key=lambda clash: (clash["from"], clash["department"]))


def _clash(department, run, off):
    return {"department": department, "from": run[0], "to": run[-1],
            "most": max(len(off[(department, day)]) for day in run),
            "names": sorted(set().union(*(off[(department, day)] for day in run)))}


def clash_lines(found, most_off):
    """The clashes as the plan shows them."""
    return ["%s: %d off %s, more than %d (%s)."
            % (clash["department"] or "No department", clash["most"],
               ("on %s" % _day(clash["from"])) if clash["from"] == clash["to"]
               else "from %s to %s" % (_day(clash["from"]), _day(clash["to"])),
               int(_num(most_off)), ", ".join(clash["names"])) for clash in found]


def plan_row_status(planned_from, today, application=None):
    """Where a planned leave stands: Taken, Applied, Not Applied (its first
    day has passed with nothing applied for) or Planned.

    application: "docstatus", "status" and "to_date" of the leave applied
    for, if any."""
    today = _date(today)
    if application and application.get("docstatus") in (0, 1) and \
            application.get("status") not in ("Rejected", "Cancelled"):
        ended = _date(application.get("to_date"))
        if application.get("docstatus") == 1 and application.get("status") == "Approved" and ended \
                and today and ended < today:
            return TAKEN
        return APPLIED
    first = _date(planned_from)
    if first and today and first < today:
        return NOT_APPLIED
    return PLANNED


def month_days(first, last, year, holidays=(), include_holidays=False):
    """The leave days of a planned leave in each month of the year:
    {month number: days}."""
    first, last = _date(first), _date(last)
    out = {}
    if not first or not last or not year:
        return out
    year = int(year)
    for month in range(1, 13):
        start = max(first, datetime.date(year, month, 1))
        end = min(last, datetime.date(year, month, calendar.monthrange(year, month)[1]))
        if start <= end:
            days = leave_days(start, end, holidays, include_holidays)
            if days:
                out[month] = days
    return out


def adherence(rows):
    """How a plan was kept to, by department: {department: {"planned",
    TAKEN, APPLIED, NOT_APPLIED, PLANNED, "moved"}}. rows: department,
    leave_status, moved."""
    out = {}
    for row in rows or ():
        counts = out.setdefault(row.get("department") or "", dict({"planned": 0, "moved": 0},
                                                                  **{status: 0 for status in ROW_STATUSES}))
        counts["planned"] += 1
        counts[row.get("leave_status") if row.get("leave_status") in ROW_STATUSES else PLANNED] += 1
        counts["moved"] += 1 if row.get("moved") else 0
    return out


def change_errors(facts):
    """Problems with moving one planned leave, as user-facing messages.

    facts: "year", "new_from", "new_to", "new_days", "available", "others"
    (the employee's other planned parts, as (from, to, days)), "applied"
    (a leave is already applied for on this row), "reason".
    """
    errors = []
    first, last = _date(facts.get("new_from")), _date(facts.get("new_to"))
    if not first or not last:
        errors.append("Give the new dates.")
        return errors
    if last < first:
        errors.append("The leave ends before it starts.")
        return errors
    if facts.get("year"):
        start, end = year_window(facts["year"])
        if not (start <= first and last <= end):
            errors.append("The new dates must fall in %s." % facts["year"])
    for other_first, other_last, _days in facts.get("others") or ():
        other_first, other_last = _date(other_first), _date(other_last)
        if other_first and other_last and first <= other_last and other_first <= last:
            errors.append("The new dates overlap the leave planned from %s to %s."
                          % (_day(other_first), _day(other_last)))
    total = _num(facts.get("new_days")) + sum(_num(days) for _first, _last, days in facts.get("others") or ())
    if _num(facts.get("available")) and total > _num(facts.get("available")):
        errors.append("That makes %g day(s) planned, %g available." % (total, _num(facts.get("available"))))
    if facts.get("applied"):
        errors.append("A leave is already applied for on these dates. Cancel that application first.")
    if not _text(facts.get("reason")):
        errors.append("Say why the leave is moving.")
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


def _day(value):
    value = _date(value)
    return value.strftime("%d %b %Y").lstrip("0") if value else ""


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
