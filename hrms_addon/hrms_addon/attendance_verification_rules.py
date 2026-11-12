# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Each branch's attendance, verified before payroll pays it.

No Frappe import (scripts/verify_attendance_verification.py); the site's side
is attendance_verification.py, the steps attendance_verification_approval.py.

  THE SHEET      one per branch per payroll: a Monthly one for a payroll month
                 (the 26th to the 25th), a Weekly one for the casuals' days.
                 Everyone active in the branch paid that way, each with
                 the Attendance Board's letters counted (person_figures)
  WHAT STOPS IT  a day nobody marked, a day the clock saw and nobody marked,
                 and a request still on its way that would change a day:
                 leave, an attendance request, overtime, off duty, a late
                 arrival notice (person_issues, the glue's requests)
  THE PAYROLL    pays nobody for a day that no verified sheet of theirs
                 covers (payroll_gaps): a monthly payroll every day of its
                 month, a weekly one each day it pays
  THE LOCK       a verified day of somebody on the sheet changes no more
                 until the sheet is reopened (held)
"""

import datetime

MONTHLY, WEEKLY = "Monthly", "Weekly"
KINDS = (MONTHLY, WEEKLY)
# Employee custom_pay_category of the casuals the weekly payroll pays: by the hour (weekly_pay_rules.WEEKLY), and by
# the piece (weekly_pay_rules.PER_PIECE), who are paid for their pieces and have no hours
WEEKLY_CATEGORY = "Weekly"
PER_PIECE_CATEGORY = "Per Piece"
CASUAL_CATEGORIES = (WEEKLY_CATEGORY, PER_PIECE_CATEGORY)
MAX_WEEKLY_DAYS = 31
# the system status of those verified; Luuka's own statuses each count as one of the four
ACTIVE = "Active"

# the Attendance Board's letters (attendance_rules.py)
DAY_SHIFT, NIGHT_SHIFT, ABSENT, SICK, WEEKLY_OFF, LEAVE, OFF_DUTY = "M", "N", "A", "S", "WO", "L", "O"
WORKED_CODES = (DAY_SHIFT, NIGHT_SHIFT)
LEAVE_CODES = (LEAVE, SICK)
OFF_CODES = (WEEKLY_OFF, OFF_DUTY)
HALF_DAY = "Half Day"

# a line of the sheet, in the order the table shows it
FIGURES = ("worked", "half_day", "absent", "leave", "off", "not_marked", "overtime_hours", "hours_worked")

NOT_MARKED = "Not marked"
CLOCKED = "Clocked in, not marked"
LEAVE_WAITING = "Leave waiting for approval"
ATTENDANCE_REQUEST_WAITING = "Attendance request waiting for approval"
OVERTIME_WAITING = "Overtime waiting for approval"
OVERTIME_NOT_SENT = "Overtime approved, not yet on the attendance"
OFF_DUTY_WAITING = "Off-duty request waiting for approval"
LATE_NOTICE_WAITING = "Late arrival notice waiting for the supervisor"
# a sheet keeps this many lines of what to put right, and counts the rest
ISSUE_ROWS = 500

# Payroll Settings: whether payroll waits for each branch's sheet (on until it is unticked)
SETTING = "custom_branches_verify_attendance"

VERIFIED_STATE = "Verified"
WAITING_TEXT = {None: "not started", "": "not started", "Draft": "with HR",
                "Pending General Manager": "waiting for the General Manager"}
NAMES_SHOWN = 5


# ── The sheet ─────────────────────────────────────────────────────────
def sheet_errors(sheet):
    """What a sheet lacks to be saved. sheet: company, branch, pay_kind, from_date, to_date, period_name (the payroll
    month its dates make, if they make one) and clashes (other live sheets of the branch on these days)."""
    errors = []
    if not sheet.get("company"):
        errors.append("Pick the company.")
    if not sheet.get("branch"):
        errors.append("Pick the branch.")
    kind = sheet.get("pay_kind")
    if kind not in KINDS:
        errors.append("Payroll is Monthly or Weekly.")
    first, last = _date(sheet.get("from_date")), _date(sheet.get("to_date"))
    if not first or not last:
        errors.append("Give the From and To dates.")
    elif last < first:
        errors.append("To comes before From.")
    elif kind == MONTHLY and not sheet.get("period_name"):
        errors.append("A monthly sheet is one payroll month, the 26th to the 25th.")
    elif kind == WEEKLY and (last - first).days + 1 > MAX_WEEKLY_DAYS:
        errors.append("A weekly sheet is at most %d days." % MAX_WEEKLY_DAYS)
    clashes = [name for name in sheet.get("clashes") or () if name]
    if clashes:
        errors.append("These days of the branch are on %s already." % ", ".join(clashes))
    return errors


def ready_errors(to_date, today):
    """A sheet is sent and verified once its last day is over."""
    last, today = _date(to_date), _date(today)
    if last and today and last >= today:
        return ["The sheet runs to %s. Send it once that day is over." % show(last)]
    return []


def title_for(branch, kind, period_name, from_date, to_date):
    if kind == MONTHLY and period_name:
        return "%s, %s" % (branch or "", period_name)
    return "%s, casuals %s to %s" % (branch or "", show(from_date), show(to_date))


def on_sheet(person, kind, from_date, to_date):
    """Whether somebody is on a branch's sheet: active, on the books for some of its days, and paid the way it pays.
    Only the active are verified (Luuka, 8 Nov 2026): somebody who has left, is suspended or inactive is not on it,
    and no payroll waits for them (payroll_people). On a monthly sheet, nor is somebody with no salary structure
    assigned by its last day (Luuka, 8 Nov 2026): the monthly payroll pays nobody else, so nobody else holds the sheet
    up. A weekly sheet is every active weekly casual (Luuka, 11 Nov 2026: "the employee should be weekly casuals"):
    the weekly payroll gives a casual the weekly structure itself when it pays them (weekly_pay.assign_people). The
    Per Piece casuals are on it too, as the weekly payroll pays them, with no hours (Luuka, 12 Nov 2026: "for per
    piece pay hour is 0 but attendance verification should cater for this"); never on a monthly sheet, though the
    weekly structure is assigned to them. person: status (the system status, which each of Luuka's statuses counts
    as), salary_structure (whether one is assigned by the sheet's last day), date_of_joining, relieving_date,
    custom_pay_category."""
    if (person.get("status") or "") != ACTIVE:
        return False
    if kind != WEEKLY and not person.get("salary_structure"):
        return False
    joined, left = _date(person.get("date_of_joining")), _date(person.get("relieving_date"))
    first, last = _date(from_date), _date(to_date)
    if joined and last and joined > last:
        return False
    if left and first and left < first:
        return False
    casual = (person.get("custom_pay_category") or "") in CASUAL_CATEGORIES
    return casual if kind == WEEKLY else not casual


def fed_by_sheets(days, plant_days):
    """Whether a weekly sheet's casuals by the hour are fed by its plant's Casual Hours Sheets: they give every one of
    its days (casual_hours.for_verification)."""
    return bool(days) and set(days) <= set(plant_days or ())


def is_casual(person):
    """Whether somebody is a casual the weekly payroll pays, by the hour or by the piece: their days nobody marked are
    skipped on a weekly sheet, not put right."""
    return (person.get("custom_pay_category") or "") in CASUAL_CATEGORIES


def by_the_hour(person):
    """Whether a casual is paid for the hours they work: a Per Piece casual is paid for their pieces, and their Hours
    Worked are nought however many days they worked."""
    return (person.get("custom_pay_category") or "") == WEEKLY_CATEGORY


def employed(person, day):
    """Whether the day is one the person was on the books for."""
    day = _date(day)
    joined, left = _date(person.get("date_of_joining")), _date(person.get("relieving_date"))
    return bool(day) and not (joined and day < joined) and not (left and day > left)


def person_figures(person, codes, clock, statuses, overtime_hours, days, hours=None, standard=None):
    """A person's line: the Board's letters, counted over the days they were on the books.

    codes: {date: letter} (attendance_rules.register_code); clock: the dates the clock saw them and nobody has marked
    (the Board shows those as worked, drawn lighter); statuses: {date: Attendance status}, for the half days;
    overtime_hours: what the attendance carries. hours: {date: the Working Hours marked}, on a weekly sheet only: its
    Hours Worked are the hours the weekly payroll pays for the days worked (day_hours; Luuka, 12 Nov 2026: "for weekly
    add no of hours worked"); standard: a full day's hours."""
    row = dict.fromkeys(FIGURES, 0)
    codes = {_date(day): code for day, code in (codes or {}).items()}
    clock = {_date(day) for day in clock or ()}
    statuses = {_date(day): status for day, status in (statuses or {}).items()}
    for day in days or ():
        day = _date(day)
        if not employed(person, day):
            continue
        code = codes.get(day) or ""
        if day in clock or not code:
            row["not_marked"] += 1
        elif code in WORKED_CODES:
            row["worked"] += 1
            if statuses.get(day) == HALF_DAY:
                row["half_day"] += 1
            if hours is not None:
                row["hours_worked"] += day_hours(statuses.get(day), hours.get(day), standard)
        elif code == ABSENT:
            row["absent"] += 1
        elif code in LEAVE_CODES:
            row["leave"] += 1
        elif code in OFF_CODES:
            row["off"] += 1
    row["overtime_hours"] = round(_num(overtime_hours), 2)
    row["hours_worked"] = round(row["hours_worked"], 2)
    return row


def day_hours(status, worked, standard):
    """The hours a day worked pays a casual by the hour, as the weekly payroll counts them (weekly_pay_rules.day_hours,
    held to the same answers by scripts/verify_attendance_verification.py): those marked, up to a full day; a day
    marked with none is a full day, a half day half of one."""
    day, hours = _num(standard), _num(worked)
    if hours > 0:
        return round(min(hours, day), 2)
    return round(day / 2.0 if status == HALF_DAY else day, 2)


def person_issues(person, codes, clock, days):
    """The days on a person's line that stop the sheet, a run of days at a time: not marked, or seen by the clock and
    not marked. [{"employee", "employee_name", "from_date", "to_date", "days", "issue"}]"""
    codes = {_date(day): code for day, code in (codes or {}).items()}
    clock = {_date(day) for day in clock or ()}
    found = {CLOCKED: [], NOT_MARKED: []}
    for day in days or ():
        day = _date(day)
        if not employed(person, day):
            continue
        if day in clock:
            found[CLOCKED].append(day)
        elif not codes.get(day):
            found[NOT_MARKED].append(day)
    out = []
    for issue, dates in found.items():
        for first, last in runs(dates):
            out.append(issue_row(person, first, last, issue))
    out.sort(key=lambda row: row["from_date"])
    return out


# a Casual Hours Sheet over the sheet's days that the plant's General Manager has not approved yet (casual_hours.py)
HOURS_SHEET_DRAFT = "Casual hours not yet sent to the General Manager"
HOURS_SHEET_WAITING = "Casual hours waiting for the General Manager"
HOURS_SHEET = "Casual Hours Sheet"


def with_hours_sheet(figures, inside, sheet, counted=None):
    """A casual's line where Casual Hours Sheets give some of its days, as the weekly payroll pays them (Luuka,
    12 Nov 2026: "i have uploaded casual hours but it pull different data also it doesnt show the overtime hours").

    figures: the line over the days no sheet gives, as the attendance has them; inside: the days a sheet gives, as
    the attendance has them; sheet: what the sheets give on this verification ({"hours", "overtime", "days"});
    counted: the attendance over those of the days whose sheet leaves its Days Worked blank. The hours and
    overtime are the sheets'; the days worked are those the sheets give, and the attendance's where a sheet gives
    none, each day counted once however the weeks fall; leave, absences and days off are the attendance's; a day a
    sheet gives is never "not marked"."""
    out = dict(figures)
    for key in ("absent", "leave", "off"):
        out[key] = out.get(key, 0) + inside.get(key, 0)
    out["worked"] = out.get("worked", 0) + int(round(_num(sheet.get("days")))) + (counted or {}).get("worked", 0)
    out["half_day"] = out.get("half_day", 0) + (counted or {}).get("half_day", 0)
    out["hours_worked"] = round(_num(out.get("hours_worked")) + _num(sheet.get("hours")), 2)
    out["overtime_hours"] = round(_num(out.get("overtime_hours")) + _num(sheet.get("overtime")), 2)
    return out


def hours_sheet_issue(name, sheet, first, last):
    """The line of what to put right for a Casual Hours Sheet over the sheet's days that its General Manager has not
    approved: its figures are on the sheet, and are not yet what the payroll pays. None for an approved one.
    sheet: {"from_date", "to_date", "state", "people"} (casual_hours.for_verification)."""
    state = sheet.get("state") or "Draft"
    if state == "Approved":
        return None
    start, end = max(_date(sheet.get("from_date")), _date(first)), min(_date(sheet.get("to_date")), _date(last))
    people = int(_num(sheet.get("people")))
    return issue_row({"employee": None, "employee_name": "%d casual%s" % (people, "" if people == 1 else "s")},
                     start, end, HOURS_SHEET_DRAFT if state == "Draft" else HOURS_SHEET_WAITING, HOURS_SHEET, name)


def issue_row(person, first, last, issue, reference_doctype=None, reference_name=None):
    first, last = _date(first), _date(last or first)
    return {"employee": person.get("employee") or person.get("name"),
            "employee_name": person.get("employee_name"),
            "from_date": first, "to_date": last, "days": (last - first).days + 1 if first and last else 0,
            "issue": issue, "reference_doctype": reference_doctype, "reference_name": reference_name}


def request_issue(person, request, issue, reference_doctype):
    """A request still on its way, as a line of what to put right: its own days, within the sheet's."""
    return issue_row(person, request.get("from_date"), request.get("to_date") or request.get("from_date"), issue,
                     reference_doctype, request.get("name"))


def issue_text(row):
    """One line of what to put right, as a sentence."""
    first, last = _date(row.get("from_date")), _date(row.get("to_date"))
    when = show(first) if first == last or not last else "%s to %s" % (show(first), show(last))
    who = row.get("employee_name") or row.get("employee") or ""
    text = "%s, %s: %s" % (who, when, row.get("issue") or "")
    if row.get("reference_name"):
        text += " (%s)" % row["reference_name"]
    return text


def changed_people(stored, fresh):
    """Who is on one list of lines and not the other, or on both with other figures: the names."""
    def keyed(rows):
        return {row.get("employee"): tuple(round(_num(row.get(field)), 2) for field in FIGURES) for row in rows or ()}

    before, now = keyed(stored), keyed(fresh)
    names = {row.get("employee"): row.get("employee_name") or row.get("employee")
             for row in list(stored or ()) + list(fresh or ())}
    return [names.get(employee) or employee for employee in sorted(set(before) | set(now), key=lambda e: e or "")
            if before.get(employee) != now.get(employee)]


def totals(rows):
    return {field: round(sum(_num(row.get(field)) for row in rows or ()), 2) for field in FIGURES}


# ── What a verified sheet holds ───────────────────────────────────────
def spans_by_employee(sheets):
    """{employee: [(first day, last day, sheet, branch)]} of the sheets given (verified ones).
    sheets: [{"name", "branch", "from_date", "to_date", "employees": [employee]}]"""
    spans = {}
    for sheet in sheets or ():
        first, last = _date(sheet.get("from_date")), _date(sheet.get("to_date"))
        if not first or not last:
            continue
        for employee in sheet.get("employees") or ():
            spans.setdefault(employee, []).append((first, last, sheet.get("name"), sheet.get("branch")))
    return spans


def held(spans, days):
    """[(day, sheet, branch)] of the days a verified sheet of the person holds, earliest first."""
    out = []
    for day in sorted({_date(day) for day in days or () if _date(day)}):
        for first, last, sheet, branch in spans or ():
            if first <= day <= last:
                out.append((day, sheet, branch))
                break
    return out


def unverified(spans, days):
    """The days no verified sheet of the person covers."""
    return [day for day in sorted({_date(day) for day in days or () if _date(day)})
            if not any(first <= day <= last for first, last, _sheet, _branch in spans or ())]


def lock_message(who, holding):
    """Why a verified day cannot change. holding: held(...), not empty."""
    days = [day for day, _sheet, _branch in holding]
    sheets = sorted({(branch or "", sheet) for _day, sheet, branch in holding})
    whose = ", ".join("%s (%s)" % (sheet, branch) if branch else sheet for branch, sheet in sheets)
    return ("The attendance of %s on %s is verified on %s and cannot change. The General Manager reopens it first."
            % (who, days_text(days), whose))


# ── The payroll ───────────────────────────────────────────────────────
def gate_on(values):
    """Payroll Settings: on unless it is unticked (a site that never saved the setting has it on)."""
    value = (values or {}).get(SETTING)
    return True if value is None or value == "" else bool(int(_num(value)))


def payroll_people(people):
    """Those of a payroll its branches verify: the active (on_sheet). people: [{"employee", "employee_name",
    "branch", "status"}]."""
    return [person for person in people or () if (person.get("status") or "") == ACTIVE]


def payroll_gaps(people, sheets, start, end, days_by_employee=None):
    """Who a payroll would pay for days no verified sheet covers, by branch ("" for those with none).

    people: [{"employee", "employee_name", "branch"}]; sheets: the verified sheets (spans_by_employee);
    days_by_employee: the days a weekly payroll pays each person, else every day from start to end.
    Returns {branch: [{"employee", "employee_name", "days"}]}"""
    spans = spans_by_employee(sheets)
    period = days_between(start, end)
    gaps = {}
    for person in people or ():
        employee = person.get("employee")
        wanted = (days_by_employee or {}).get(employee, []) if days_by_employee is not None else period
        missing = unverified(spans.get(employee), wanted)
        if missing:
            gaps.setdefault(person.get("branch") or "", []).append(
                {"employee": employee, "employee_name": person.get("employee_name") or employee, "days": missing})
    return gaps


def gaps_message(gaps, waiting, verified_branches, fed=None):
    """What stops a payroll, a branch to a line. waiting: {branch: the state of its sheet not yet verified};
    verified_branches: the branches with a verified sheet for these days; fed: those of them whose Casual Hours
    Sheets feed their casuals by the hour, so that one missing is missing from the sheet."""
    lines = []
    for branch in sorted(gaps, key=lambda name: (name == "", name)):
        people = gaps[branch]
        if not branch:
            lines.append("No branch: %s. Set their branch, then verify their attendance there." % names_text(people))
        elif branch in (fed or ()):
            lines.append("%s: %s worked on days the Casual Hours Sheet gives, but are not on it. Put them on the "
                         "sheet, or take them off this payroll." % (branch, names_text(people)))
        elif branch in (verified_branches or ()):
            lines.append("%s: %s not on its verified sheet. The General Manager reopens it, and it is verified "
                         "again." % (branch, names_text(people)))
        else:
            lines.append("%s: attendance not verified yet (%s)." % (branch, WAITING_TEXT.get(
                (waiting or {}).get(branch), (waiting or {}).get(branch))))
    return lines


def branch_lines(people, sheets, waiting, start, end, days_by_employee=None):
    """The payroll's branches as its form shows them: [{"branch", "people", "missing", "state", "sheets"}].
    state: "Verified" when nobody is missing, else what the branch's sheet waits for."""
    gaps = payroll_gaps(people, sheets, start, end, days_by_employee)
    counted = {}
    for person in people or ():
        branch = person.get("branch") or ""
        counted[branch] = counted.get(branch, 0) + 1
    out = []
    for branch in sorted(counted, key=lambda name: (name == "", name)):
        missing = len(gaps.get(branch) or [])
        mine = [{"name": sheet.get("name"), "verified_by": sheet.get("verified_by"), "verified_on": sheet.get("verified_on")}
                for sheet in sheets or () if (sheet.get("branch") or "") == branch]
        if not missing:
            state = VERIFIED_STATE
        elif not branch:
            state = "No branch"
        elif mine:
            state = "Not all on the verified sheet"
        else:
            state = WAITING_TEXT.get((waiting or {}).get(branch), (waiting or {}).get(branch))
        out.append({"branch": branch, "people": counted[branch], "missing": missing, "state": state, "sheets": mine})
    return out


# ── Marking the days nobody marked ────────────────────────────────────
# Luuka, 8 Nov 2026: "add button to mark attendance and it only filter by those number of employee and those dates".
# A sheet with HR marks the days on it nobody marked, of its own people, and nothing else.
MARK_STATUSES = ("Present", "Absent", "Half Day", "On Leave", "Work From Home")
MARK_NEEDS_LEAVE_TYPE = ("On Leave",)
MARK_TAKES_LEAVE_TYPE = ("On Leave", "Half Day")
# the lines of what to put right that marking puts right
MARKABLE = (NOT_MARKED, CLOCKED)
MARK_PROBLEMS_SHOWN = 20


def days_to_mark(issues):
    """{employee: {"employee", "employee_name", "days", "clocked"}} from the sheet's lines of what to put right: the
    days nobody marked, and of those, the days the clock saw. Each list of days sorted."""
    out = {}
    for row in issues or ():
        if row.get("issue") not in MARKABLE or not row.get("employee"):
            continue
        person = out.setdefault(row["employee"], {"employee": row["employee"], "days": [], "clocked": [],
                                                  "employee_name": row.get("employee_name") or row["employee"]})
        for day in days_between(row.get("from_date"), row.get("to_date") or row.get("from_date")):
            if day not in person["days"]:
                person["days"].append(day)
            if row.get("issue") == CLOCKED and day not in person["clocked"]:
                person["clocked"].append(day)
    for person in out.values():
        person["days"].sort()
        person["clocked"].sort()
    return out


def mark_errors(status, leave_type, leave_type_found=True):
    """What stops the days being marked: a status Attendance does not take, or leave with no leave type."""
    if status not in MARK_STATUSES:
        return ["Pick what to mark the days: %s." % ", ".join(MARK_STATUSES)]
    if status in MARK_NEEDS_LEAVE_TYPE and not leave_type:
        return ["Pick the leave type."]
    if leave_type and status in MARK_TAKES_LEAVE_TYPE and not leave_type_found:
        return ["There is no leave type %s." % leave_type]
    return []


def chosen_days(to_mark, employees, days):
    """[(employee, day)] to mark: the people and days picked, where the sheet still has nothing marked. A person or
    a day that is not on the sheet's list is never marked, whatever is sent."""
    people = {str(employee) for employee in employees or () if employee}
    picked = {_date(day) for day in days or ()} - {None}
    out = []
    for employee in sorted(to_mark or {}):
        if employee not in people:
            continue
        out += [(employee, day) for day in to_mark[employee]["days"] if day in picked]
    return out


def mark_problem(who, day, reason):
    return "%s, %s: %s" % (who, show(day), reason)


def mark_summary(marked, problems, shown=MARK_PROBLEMS_SHOWN):
    """What marking did, in a line or a few: how many days were marked, and those that were not, with why."""
    lines = ["%d %s marked." % (marked, "day" if marked == 1 else "days")]
    problems = list(problems or ())
    if problems:
        lines.append("%d not marked:" % len(problems))
        lines += problems[:shown]
        if len(problems) > shown:
            lines.append("and %d more." % (len(problems) - shown))
    return lines


# ── A new sheet's days ────────────────────────────────────────────────
def weekly_dates(last_sheet_to, last_paid_to, today):
    """A new weekly sheet's days: from the day after the branch's last weekly sheet (else after the last weekly
    payroll, else a week back) to yesterday."""
    today = _date(today)
    yesterday = today - datetime.timedelta(days=1)
    after = _date(last_sheet_to) or _date(last_paid_to)
    first = after + datetime.timedelta(days=1) if after else yesterday - datetime.timedelta(days=6)
    return min(first, yesterday), yesterday


# ── Small helpers ─────────────────────────────────────────────────────
def days_between(first, last):
    first, last = _date(first), _date(last)
    if not first or not last or last < first:
        return []
    return [first + datetime.timedelta(days=n) for n in range((last - first).days + 1)]


def runs(dates):
    """Dates gathered into runs of consecutive days: [(first, last)]."""
    out = []
    for day in sorted({_date(day) for day in dates or () if _date(day)}):
        if out and day == out[-1][1] + datetime.timedelta(days=1):
            out[-1] = (out[-1][0], day)
        else:
            out.append((day, day))
    return out


def days_text(days):
    """"3 Oct 2026", "3 Oct 2026 to 5 Oct 2026", or several runs joined."""
    parts = []
    for first, last in runs(days):
        parts.append(show(first) if first == last else "%s to %s" % (show(first), show(last)))
    return ", ".join(parts)


def names_text(people, shown=NAMES_SHOWN):
    names = [person.get("employee_name") or person.get("employee") for person in people or ()]
    if len(names) <= shown:
        return ", ".join(names)
    return "%s and %d more" % (", ".join(names[:shown]), len(names) - shown)


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def show(day):
    day = _date(day)
    return "%d %s %d" % (day.day, MONTHS[day.month - 1], day.year) if day else ""


def _date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
