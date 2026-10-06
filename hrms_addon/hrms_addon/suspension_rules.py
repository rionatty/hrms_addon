# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee suspension (Disciplinary Grievancy, test case 6, and Luuka's
Suspension Letter): an employee kept off duty for some days, without pay,
then back at work on the day the letter names.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_suspension.py exercises them without a bench.

THE LETTER (RE: SUSPENSION FROM DUTY)

  The date, the employee, their number, section and plant, and the
  offence. The days "without pay", from and to, and the day they report
  back to the Human Resource Office. Signed by the General Manager,
  acknowledged by the employee, witnessed by the HR Manager.

THE RECORD

  Raised by the HR Officer by hand, or from a Disciplinary Case decided at
  the ladder's Suspension rung, and signed as the letter is signed: the HR
  Manager, then the General Manager (suspension_approval.py). Approved, it
  is carried out:

  - each day it runs is marked on the employee's attendance as leave of
    the Suspension Without Pay leave type, which is unpaid (is_lwp), so the
    payroll takes the days off the pay as Frappe HR takes any unpaid leave,
    and leave is not earned on them; a suspension with pay is marked as
    Suspension With Pay, which is paid
  - the employee's status is Suspended from the first day, and Active
    again on the day they report back, when HR and the supervisor are told
"""

import datetime

# the two leave types the days are marked as, made on install
UNPAID_LEAVE = "Suspension Without Pay"
PAID_LEAVE = "Suspension With Pay"
LEAVE_TYPES = {
    UNPAID_LEAVE: {"is_lwp": 1, "max_leaves_allowed": 0, "include_holiday": 1},
    PAID_LEAVE: {"is_lwp": 0, "max_leaves_allowed": 0, "include_holiday": 1},
}
# the days the chart draws, and the most one letter may give
DEFAULT_DAYS = 3
MAX_DAYS = 30

# what the record says of itself: the workflow's states, then how far the
# suspension has run once approved
DRAFT, PENDING_HRM, PENDING_GM, APPROVED, CANCELLED = (
    "Draft", "Pending HR Manager", "Pending General Manager", "Approved", "Cancelled")
IN_PROGRESS, COMPLETED = "In Progress", "Completed"
STATUSES = (DRAFT, PENDING_HRM, PENDING_GM, APPROVED, IN_PROGRESS, COMPLETED, CANCELLED)

# Frappe's Employee statuses this moves between
ACTIVE, SUSPENDED = "Active", "Suspended"


def suspension_dates(start, days):
    """The suspension the letter prints: from, to, and the day they report
    back, both ends of the suspension counted (as discipline_rules counts
    the Disciplinary Case's)."""
    start = _date(start)
    days = _int(days)
    if not start or days < 1:
        return {"from": start, "to": None, "report_back": None}
    end = start + datetime.timedelta(days=days - 1)
    return {"from": start, "to": end, "report_back": end + datetime.timedelta(days=1)}


def days_between(first, last):
    """Every day from the first to the last, both in."""
    first, last = _date(first), _date(last)
    if not first or not last or last < first:
        return []
    return [first + datetime.timedelta(days=step) for step in range((last - first).days + 1)]


def overlaps(first, last, other_first, other_last):
    """Whether two runs of days share a day."""
    first, last, other_first, other_last = (_date(first), _date(last), _date(other_first), _date(other_last))
    if not (first and last and other_first and other_last):
        return False
    return first <= other_last and other_first <= last


def suspension_errors(facts):
    """What a suspension needs before it goes for signature. facts:
    "employee", "nature_of_offence", "days", "from_date", "date_of_joining",
    "relieving_date", "employee_status", "clashes" (the other suspensions
    of the employee its days fall on: names)."""
    errors = []
    if not facts.get("employee"):
        errors.append("Choose the employee.")
    if not _text(facts.get("nature_of_offence")):
        errors.append("Write the nature of the offence: the letter refers to it.")
    days = _int(facts.get("days"))
    if days < 1:
        errors.append("Say how many days the suspension runs.")
    elif days > MAX_DAYS:
        errors.append("A suspension runs for at most %d days." % MAX_DAYS)
    start = _date(facts.get("from_date"))
    if not start:
        errors.append("Say the day the suspension starts.")
    joined = _date(facts.get("date_of_joining"))
    if start and joined and start < joined:
        errors.append("The suspension cannot start before the employee joined.")
    relieved = _date(facts.get("relieving_date"))
    if start and relieved and start > relieved:
        errors.append("The employee leaves before the suspension would start.")
    if facts.get("employee_status") == "Left":
        errors.append("The employee has left.")
    clashes = [_text(name) for name in facts.get("clashes") or () if _text(name)]
    if clashes:
        errors.append("These days are already a suspension: %s." % ", ".join(clashes))
    return errors


def leave_type_for(without_pay):
    """The leave type a suspension's days are marked as."""
    return UNPAID_LEAVE if int(without_pay or 0) else PAID_LEAVE


def day_plan(days, marked):
    """What becomes of each day of the suspension on the attendance.

    days: the suspension's days; marked: {date: {"name", "docstatus",
    "status", "leave_type"}} the attendance already there. Returns
    {"create": [dates], "update": [names of drafts to mark], "kept": [(date,
    status)] submitted days left as they are (a day already marked stays
    marked: Absent is unpaid as it is, and a day worked was worked)}."""
    out = {"create": [], "update": [], "kept": []}
    for day in days:
        found = marked.get(_date(day))
        if not found:
            out["create"].append(_date(day))
        elif int(found.get("docstatus") or 0) == 0:
            out["update"].append(found.get("name"))
        elif found.get("leave_type") not in LEAVE_TYPES:
            out["kept"].append((_date(day), found.get("status")))
    return out


def running_status(today, from_date, report_back_on, current):
    """How far an approved suspension has run on `today`: Approved before
    the first day, In Progress from it, Completed from the day they report
    back. A Cancelled one stays Cancelled."""
    if current == CANCELLED:
        return CANCELLED
    today, start, back = _date(today), _date(from_date), _date(report_back_on)
    if back and today >= back:
        return COMPLETED
    if start and today >= start:
        return IN_PROGRESS
    return APPROVED


def employee_status_after(suspension_status, employee_status, others_running=False):
    """The employee's status once a suspension has moved: Suspended while
    one runs; Active again when it ends or is cancelled, but only from
    Suspended (someone who has left stays Left) and only when no other
    suspension still runs. None: leave it as it is."""
    if suspension_status == IN_PROGRESS:
        return SUSPENDED if employee_status == ACTIVE else None
    if suspension_status in (COMPLETED, CANCELLED) and employee_status == SUSPENDED and not others_running:
        return ACTIVE
    return None


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))
