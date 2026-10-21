# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Upload Attendance: the register out, the filled file back in.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_upload_attendance.py runs it without a bench.
attendance_upload.py is the part that asks the site and marks the days.

WHY THIS APP HAS ONE

Frappe HR v16 deleted its own Upload Attendance (patch
v16_0/delete_upload_attendance_doctype, "deprecated in favor of the
Employee Attendance Tool"). That tool marks one day at a time; a month kept
on paper goes in faster as one sheet. So the doctype is back, under the
name people look for, as one record per upload.

THE TEMPLATE IS THE REGISTER

The template is LPL/HR/07 as HR keep it: one row per employee, one column
per day of the period, each day a letter of the register (CODES). A row per
employee per day made a whole company over a cycle 103,182 rows (Luuka, 21
Oct 2026: "the system should be able to accomodate any number of uploads of
data"); the register makes it one row per employee, whatever their number.
Only the period is held to a year.

  a day already marked      its letter, in grey; left as it is, it is
                            counted as marked already
  a holiday                 WO, weekly off: the day's letter goes over it
                            if the employee worked it
  a day nobody can mark     "-": before joining, after leaving, after today
  any other day             blank, to fill

THE FILE BACK

Either layout: the register, or a row per day (Employee, Attendance Date,
Status, and Leave Type and Shift where wanted), which is what a Data Import
file and the file of days not marked are. A blank day, "-" and WO are not
marked. Each day says its status as a letter of the register, one of Frappe
HR's statuses, or a leave type's name. Every day is checked before anything
is written, and each problem names its row.
"""

import csv
import datetime
import io
import re

import openpyxl
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, NamedStyle, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# Frappe HR's own Attendance statuses, in their order
STATUSES = ("Present", "Absent", "On Leave", "Half Day", "Work From Home")
# the statuses a Leave Type is kept on; Frappe HR clears it on the others
TAKES_LEAVE_TYPE = ("On Leave", "Half Day")
# what a letter's leave or shift is, resolved on the site (check_days)
ANNUAL, SICK, OFF_DUTY = "annual leave", "sick leave", "off duty"
DAY, NIGHT = "day shift", "night shift"
# LPL/HR/07's letters (attendance_rules.CODE_MEANING; the checker holds the
# two to the same letters), and three of Frappe HR's statuses written short
CODES = {
    "M": ("Present", None, DAY),
    "N": ("Present", None, NIGHT),
    "A": ("Absent", None, None),
    "L": ("On Leave", ANNUAL, None),
    "S": ("On Leave", SICK, None),
    "O": ("On Leave", OFF_DUTY, None),
    "P": ("Present", None, None),
    "HD": ("Half Day", None, None),
    "WFH": ("Work From Home", None, None),
}
WEEKLY_OFF, CLOSED = "WO", "-"
# a day that says nothing to mark
NOT_MARKED = ("", CLOSED, WEEKLY_OFF)
CODE_MEANING = (
    ("M", "Present, day shift"),
    ("N", "Present, night shift"),
    ("A", "Absent"),
    ("L", "On leave, annual leave"),
    ("S", "On leave, sick leave"),
    ("O", "Off duty, a paid day off"),
    ("P", "Present"),
    ("HD", "Half day"),
    ("WFH", "Work from home"),
    ("WO", "Weekly off: not marked"),
    ("-", "Not on the payroll that day, or after today: not marked"),
)
SHEET, HOW = "Attendance", "How to fill"
WHY = "Why Not Marked"
REGISTER, ROWS = "register", "rows"
# a template covers a year at most: a period longer than that is a mistake
MAX_DAYS = 366
# how a column of a row-per-day file may be headed, compared without case;
# "Label (fieldname)" and a bare fieldname come to the same (heading())
COLUMNS = {
    "employee": ("employee", "employee id"),
    "attendance_date": ("attendance date", "date"),
    "status": ("status",),
    "leave_type": ("leave type",),
    "shift": ("shift",),
}
NEEDED = ("employee", "attendance_date", "status")
# the header is looked for in this many rows from the top
HEADER_ROWS = 10
# day first, as dates are written in Uganda
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d")
EXCEL_EPOCH = datetime.date(1899, 12, 30)

NOT_A_SHEET = "This is not an Excel (.xlsx) or .csv file. Save it as an Excel Workbook and attach it again."
NO_HEADER = ("The file has no Employee column and no days: download the template and fill that in, or give a "
             "row per day with Employee, Attendance Date and Status.")
NOTHING_FILLED = "No day is filled in. Put the day's letter on each day to mark and attach the file again."

HOW_TO_FILL = (
    "One row per employee, one column per day. Put the day's letter on each day to mark.",
    "A day left blank is not marked. A day already marked shows its letter in grey: leave it as it is.",
    "A holiday shows WO. Put the day's letter over it if the employee worked it.",
    "Instead of a letter, a day may say a leave type's name: the employee was on that leave.",
    "Attach the file to the Upload Attendance and press Import.",
)


# ── The template ──────────────────────────────────────────────────────
def period_days(start, end):
    """Every day of the period, in order."""
    start, end = _date(start), _date(end)
    return [start + datetime.timedelta(days=step) for step in range((end - start).days + 1)]


def register_rows(people, days, today, marked, holidays=None):
    """The register's rows: [(employee, name, department, [(text, kind)])],
    a cell for each day. kind: "marked" (marked already, its letter),
    "holiday" (WO), "closed" (-) or None (blank, to fill).

    people    [{"employee", "employee_name", "department", "date_of_joining",
              "relieving_date", "holiday_list"}], in the order they are listed
    marked    {(employee, date): its letter} for the days marked already
    holidays  {holiday list: {dates}}
    """
    holidays, today = holidays or {}, _date(today)
    rows = []
    for person in people:
        first = max(day for day in (days[0], _date(person.get("date_of_joining"))) if day)
        last = min(day for day in (days[-1], _date(person.get("relieving_date")), today) if day)
        kept = holidays.get(person.get("holiday_list")) or set()
        cells = []
        for day in days:
            if not first <= day <= last:
                cells.append((CLOSED, "closed"))
            elif (person["employee"], day) in marked:
                cells.append((marked[(person["employee"], day)] or "P", "marked"))
            elif day in kept:
                cells.append((WEEKLY_OFF, "holiday"))
            else:
                cells.append((None, None))
        rows.append((person["employee"], person.get("employee_name") or "", person.get("department") or "", cells))
    return rows


def build_template(rows, days, leave_types=()):
    """The register as .xlsx bytes: a row per employee, a column per day, the
    letters to pick from, and how to fill it in."""
    book = openpyxl.Workbook(write_only=True)
    _add_styles(book)
    sheet = book.create_sheet(SHEET)
    sheet.freeze_panes = "D2"
    for column, width in (("A", 14), ("B", 28), ("C", 24)):
        sheet.column_dimensions[column].width = width
    for at in range(len(days)):
        sheet.column_dimensions[get_column_letter(4 + at)].width = 7
    if rows and days:
        pick = DataValidation(type="list", formula1='"%s"' % ",".join(list(CODES) + [WEEKLY_OFF]), allow_blank=True)
        # a list to pick from, not a fence: a leave type's name may be typed
        pick.showErrorMessage = False
        pick.add("D2:%s%d" % (get_column_letter(3 + len(days)), len(rows) + 1))
        sheet.data_validations.append(pick)
    sheet.append([_styled(sheet, "Employee", "ha_head"), _styled(sheet, "Employee Name", "ha_head"),
                  _styled(sheet, "Department", "ha_head")] + [_styled(sheet, day, "ha_day_head") for day in days])
    styles = {"marked": "ha_marked", "holiday": "ha_holiday", "closed": "ha_closed", None: "ha_cell"}
    for employee, name, department, cells in rows:
        sheet.append([_styled(sheet, employee, "ha_text"), name, department]
                     + [_styled(sheet, text, styles[kind]) for text, kind in cells])
    how = book.create_sheet(HOW)
    how.column_dimensions["A"].width = 12
    how.column_dimensions["B"].width = 90
    for line in HOW_TO_FILL:
        how.append([None, line])
    how.append([])
    how.append([_styled(how, "Letter", "ha_head"), _styled(how, "What it marks", "ha_head")])
    for code, what in CODE_MEANING:
        how.append([code, what])
    if leave_types:
        how.append([])
        how.append([None, _styled(how, "Leave types a day may name", "ha_head")])
        for name in leave_types:
            how.append([None, name])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _add_styles(book):
    # named, so each of a large register's cells points at one style rather
    # than carrying its own (output_sheet.py does the same)
    middle = Alignment(horizontal="center")
    for name, style in (
        ("ha_head", {"font": Font(bold=True), "fill": PatternFill("solid", fgColor="DDE4EE")}),
        ("ha_day_head", {"font": Font(bold=True), "fill": PatternFill("solid", fgColor="DDE4EE"),
                         "number_format": "dd-mmm", "alignment": middle}),
        ("ha_text", {"number_format": "@"}),
        ("ha_date", {"number_format": "yyyy-mm-dd"}),
        ("ha_cell", {"alignment": middle}),
        ("ha_marked", {"font": Font(color="808080"), "alignment": middle}),
        ("ha_holiday", {"fill": PatternFill("solid", fgColor="EEF2F7"), "alignment": middle}),
        ("ha_closed", {"font": Font(color="A0A0A0"), "fill": PatternFill("solid", fgColor="F2F2F2"),
                       "alignment": middle}),
    ):
        book.add_named_style(NamedStyle(name=name, **style))


def _styled(sheet, value, style):
    cell = WriteOnlyCell(sheet, value)
    cell.style = style
    return cell


# ── The file back ─────────────────────────────────────────────────────
def heading(title):
    """A column heading as it is compared: no case, no "(fieldname)", an
    underscore a space."""
    text = re.sub(r"\s*\([^)]*\)\s*$", "", str(title or "")).strip().lower().replace("_", " ")
    return " ".join(text.split())


def header_columns(header):
    """{what: column number from 0} for a row-per-day file's columns, or
    None when the row has no Employee, Attendance Date and Status."""
    found = {}
    for at, title in enumerate(header or ()):
        key = heading(title)
        for what, names in COLUMNS.items():
            if key in names and what not in found:
                found[what] = at
    return found if all(what in found for what in NEEDED) else None


def register_columns(header):
    """(the Employee column, {column: its day}) for the register's heading,
    or None when the row has no Employee column or no day."""
    employee, days = None, {}
    for at, title in enumerate(header or ()):
        if employee is None and heading(title) in COLUMNS["employee"]:
            employee = at
            continue
        day = parse_date(title)
        if day:
            days[at] = day
    return (employee, days) if employee is not None and days else None


def layout_of(content, filename=""):
    """Which layout a file is in, read from its heading alone: what Import
    checks before it queues anything. ValueError when it is neither."""
    for layout, _header, _how in _headers(content, filename):
        return layout
    raise ValueError(NO_HEADER)


def days_in(content, filename=""):
    """Every day the file says something about, one after the other, read as
    it goes so a file of any size is never held whole:
    {"row": its row in the file, "employee", "attendance_date", "status",
    "leave_type", "shift", "day": the day's heading in a register}.
    A blank day, "-" and WO are not given. ValueError when the file is not
    one this reads."""
    header = None
    for number, values in enumerate(_table(content, filename), 1):
        values = tuple(values)
        if header is None:
            found = _layout(values)
            if found:
                header = found
            elif number >= HEADER_ROWS:
                raise ValueError(NO_HEADER)
            continue
        layout, how = header
        if layout == ROWS:
            record = {"row": number}
            for what, at in how.items():
                value = values[at] if at < len(values) else None
                record[what] = value.strip() if isinstance(value, str) else value
            if _text(record.get("status")).upper() in NOT_MARKED:
                continue
            yield record
            continue
        employee_at, day_columns = how
        who = values[employee_at] if employee_at < len(values) else None
        for at, day in day_columns.items():
            said = values[at] if at < len(values) else None
            if _text(said).upper() in NOT_MARKED:
                continue
            yield {"row": number, "employee": who.strip() if isinstance(who, str) else who, "attendance_date": day,
                   "status": said.strip() if isinstance(said, str) else said, "leave_type": None, "shift": None,
                   "day": day}
    if header is None:
        raise ValueError(NO_HEADER)


def _layout(values):
    columns = header_columns(values)
    if columns is not None:
        return ROWS, columns
    register = register_columns(values)
    if register is not None:
        return REGISTER, register
    return None


def _headers(content, filename):
    for number, values in enumerate(_table(content, filename), 1):
        found = _layout(tuple(values))
        if found:
            yield found[0], values, found[1]
            return
        if number >= HEADER_ROWS:
            return


def _table(content, filename):
    if str(filename or "").lower().endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        yield from csv.reader(io.StringIO(text))
        return
    try:
        book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        # a .xls, a picture, a file cut short: openpyxl says so in its own words
        raise ValueError(NOT_A_SHEET)
    try:
        sheet = book[SHEET] if SHEET in book.sheetnames else book.worksheets[0]
        yield from sheet.iter_rows(values_only=True)
    finally:
        book.close()


def parse_date(value):
    """A date from a cell: a date, a day-first text date, or an Excel day
    number. None when it is none of those."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # a date cell read without its format is the number of days since 1899
        return EXCEL_EPOCH + datetime.timedelta(days=int(value)) if 20000 < value < 80000 else None
    text = _text(value).split(" ")[0].split("T")[0]
    for pattern in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


# ── What a day says ───────────────────────────────────────────────────
def meaning(said, leave_types=()):
    """(status, leave, shift) a day says: a letter of the register, one of
    Frappe HR's statuses, or a leave type's name (On Leave, of that type).
    leave: ANNUAL, SICK, OFF_DUTY, a leave type's name or None; shift: DAY,
    NIGHT or None. ValueError when it says none of those."""
    text = _text(said)
    code = CODES.get(text.upper())
    if code:
        return code
    status = {name.lower(): name for name in STATUSES}.get(text.lower())
    if status:
        return status, None, None
    leave = {str(name).lower(): name for name in leave_types}.get(text.lower())
    if leave:
        return "On Leave", leave, None
    raise ValueError("%s is not a day of the register. Use %s, or a leave type's name."
                     % (text, ", ".join(list(CODES)[:-1]) + " or " + list(CODES)[-1]))


def leave_for(leave, names):
    """The site's Leave Type a day's leave is, or ValueError saying why not.
    names: {"leave_types", "annual", "off_duty"} as the site has them."""
    leave_types = list(names.get("leave_types") or ())
    if leave == ANNUAL:
        found = names.get("annual")
        if found not in leave_types:
            raise ValueError("L is annual leave, and there is no leave type %s." % (found or "for it"))
        return found
    if leave == OFF_DUTY:
        found = names.get("off_duty")
        if found not in leave_types:
            raise ValueError("O is off duty, and there is no leave type %s." % (found or "for it"))
        return found
    if leave == SICK:
        sick = [name for name in leave_types if "sick" in str(name).lower()]
        exact = [name for name in sick if str(name).lower() == "sick leave"]
        if len(sick) == 1 or exact:
            return (exact or sick)[0]
        raise ValueError("S is sick leave, and the site has %s. Write the leave type's name in the day instead."
                         % ("no sick leave type" if not sick else "%d sick leave types" % len(sick)))
    return leave


def shift_for(shift, default_shift, shifts):
    """The Shift Type a day's letter says, or None where it says none, or
    ValueError. M and N are the employee's own Default Shift where it is a
    day or a night shift, else the only one of its kind on the site."""
    if shift not in (DAY, NIGHT):
        return None
    night = shift == NIGHT
    if default_shift and _is_night(default_shift) == night:
        return default_shift
    kind = [name for name in shifts if _is_night(name) == night]
    if len(kind) == 1:
        return kind[0]
    if not night and not default_shift:
        # a day shift for somebody with no shift of their own: the day as it comes
        return None
    raise ValueError("%s is a %s, and the site has %s. Give the employee one as their Default Shift."
                     % ("N" if night else "M", shift, "none" if not kind else "%d" % len(kind)))


def _is_night(shift):
    # as attendance_rules reads a shift for the register
    return "night" in str(shift or "").lower()


# ── The checks ────────────────────────────────────────────────────────
def check_days(days, employees, names, marked, today, seen=None):
    """What each day comes to, before anything is written.

    days         days_in()'s records
    employees    {name: {"date_of_joining", "relieving_date", "status",
                 "default_shift"}}, matched without case, as the database does
    names        {"leave_types", "shifts", "annual", "off_duty"}: the site's
    marked       {(employee, date): (status, the Attendance, its letter)},
                 marked already, in draft or submitted
    seen         {(employee, date): row}: the days met so far in the file,
                 kept by the caller across the parts of a large file
    Returns {"to_mark": [...], "already": n, "problems": [(day, why)]}."""
    people = {str(name).lower(): name for name in employees}
    leave_names = {str(name).lower(): name for name in names.get("leave_types") or ()}
    shift_names = {str(name).lower(): name for name in names.get("shifts") or ()}
    today = _date(today)
    seen = {} if seen is None else seen
    out = {"to_mark": [], "already": 0, "problems": []}
    for record in days:
        who, given = _text(record.get("employee")), record.get("attendance_date")
        name = people.get(who.lower())
        facts = employees.get(name) or {}
        day = parse_date(given)
        joined, left = _date(facts.get("date_of_joining")), _date(facts.get("relieving_date"))
        leave_column, shift_column = _text(record.get("leave_type")), _text(record.get("shift"))
        try:
            status, leave, shift = meaning(record.get("status"), leave_names.values())
            if not who:
                raise ValueError("No employee on this row.")
            if not name:
                raise ValueError("No employee %s." % who)
            if _text(given) == "":
                raise ValueError("No Attendance Date.")
            if day is None:
                raise ValueError("%s is not a date. Write it as 2026-10-05." % _text(given))
            if day > today:
                raise ValueError("%s is after today." % day.isoformat())
            if joined and day < joined:
                raise ValueError("%s joined on %s." % (name, joined.isoformat()))
            if left and day > left:
                raise ValueError("%s left on %s." % (name, left.isoformat()))
            if facts.get("status") == "Inactive":
                raise ValueError("%s is Inactive, and attendance is not marked for an inactive employee." % name)
            if leave_column and status in TAKES_LEAVE_TYPE:
                if leave_column.lower() not in leave_names:
                    raise ValueError("No leave type %s." % leave_column)
                leave = leave_names[leave_column.lower()]
            leave = leave_for(leave, names) if leave and status in TAKES_LEAVE_TYPE else None
            if status == "On Leave" and not leave:
                raise ValueError("On Leave needs a Leave Type.")
            if shift_column:
                if shift_column.lower() not in shift_names:
                    raise ValueError("No shift %s." % shift_column)
                shift = shift_names[shift_column.lower()]
            else:
                shift = shift_for(shift, facts.get("default_shift"), shift_names.values())
            if (name, day) in seen:
                raise ValueError("%s on %s is on row %s too." % (name, day.isoformat(), seen[(name, day)]))
        except ValueError as why:
            out["problems"].append((record, str(why)))
            continue
        seen[(name, day)] = record.get("row")
        already = marked.get((name, day))
        if already:
            # its letter left as the register showed it, or the same status
            if already[0] == status or (len(already) > 2 and already[2]
                                        and _text(record.get("status")).upper() == already[2]):
                out["already"] += 1
            else:
                out["problems"].append((record, "Already marked %s on %s. Cancel that one to mark the day again."
                                        % (already[0], already[1])))
            continue
        out["to_mark"].append({"row": record.get("row"), "employee": name, "attendance_date": day, "status": status,
                               "leave_type": leave, "shift": shift, "source": record})
    return out


# ── The days not marked ───────────────────────────────────────────────
PROBLEM_HEADERS = ("Employee", "Attendance Date", "Status", "Leave Type", "Shift", WHY)


def problems_file(problems):
    """The days not marked as .xlsx bytes, a row per day with why: put right,
    the file is imported again as it is (a row-per-day file)."""
    book = openpyxl.Workbook(write_only=True)
    _add_styles(book)
    sheet = book.create_sheet(SHEET)
    sheet.freeze_panes = "B2"
    for column, width in zip("ABCDEF", (14, 16, 12, 22, 18, 70)):
        sheet.column_dimensions[column].width = width
    sheet.append([_styled(sheet, title, "ha_head") for title in PROBLEM_HEADERS])
    for record, why in sorted(problems, key=_where):
        day = parse_date(record.get("attendance_date"))
        sheet.append([_styled(sheet, _text(record.get("employee")), "ha_text"),
                      _styled(sheet, day, "ha_date") if day else record.get("attendance_date"),
                      record.get("status"), record.get("leave_type"), record.get("shift"), why])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def listed(problems, most):
    """The first problems as lines to show on the upload; the file has them all."""
    ordered = sorted(problems, key=_where)
    lines = ["Row %s%s: %s" % (record.get("row"), ", %s" % _date(record["day"]).isoformat() if record.get("day")
                               else "", why) for record, why in ordered[:most]]
    if len(ordered) > most:
        lines.append("And %d more, in the file." % (len(ordered) - most))
    return "\n".join(lines)


def _where(problem):
    record = problem[0]
    return record.get("row") or 0, _date(record.get("day")) or datetime.date.min


def text(value):
    """A cell as text, trimmed; nothing for an empty cell."""
    return _text(value)


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
