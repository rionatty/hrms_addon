# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Deleting attendance by the month without slowing the site
(attendance_deletions.py; Luuka, 2 Nov 2026: "deleting attendace has been a
problem how can we delete large volumne of data without compormissing the
system perfomance").

No Frappe import, like the other *_rules.py modules, so
scripts/verify_attendance_deletion.py runs it without a bench.

WHY NOT FRAPPE'S OWN DELETE

2,000 people for 31 days is 62,000 records. Frappe deletes them from a list one
at a time, each cancelled first, each checked against everything that can link
to it, each with a Deleted Document copy, and each queues a background job of
its own to clear its comments and versions. The queue holds 500 jobs: that is
"Too many queued background jobs".

WHAT THIS DOES

One job, on the long queue. It takes a day at a time, SLICE records at a time,
deletes them together, saves, and rests before the next (pause_after), longer if
the database was slow. What says how far it got is saved in the same transaction
as what it deleted, so a job killed half way goes on from exactly where it was.

WHAT IT KEEPS

What Frappe would have refused, and what the payroll stands on:

  ON_SLIP       the person's submitted salary slip covers the day: a paid month
                goes on matching its attendance
  FROM_REQUEST  a leave application or attendance request made it: cancel that
  used_by       another document links to it, as Frappe's own check finds them
  ATTACHED      a file is attached to it

A CSV of what was deleted stands in for the Deleted Document copies, and a second
lists what was kept and why. The first opens with Upload Attendance's own columns
and goes back in through it: only the submitted days have a Status, so drafts and
cancelled records stay gone.
"""

import csv
import datetime
import io

DRAFT, QUEUED, DELETING, STOPPED, FINISHED, FAILED = "Draft", "Queued", "Deleting", "Stopped", "Finished", "Failed"
RUNNING = (QUEUED, DELETING)
ON_HOLD = (STOPPED, FAILED)

# records deleted and saved together, and the rest between two slices, in seconds
SLICE = 1000
SHORTEST_PAUSE, LONGEST_PAUSE = 0.2, 2.0
# a deletion that says it is running and has not moved for this long has lost its job
STOPPED_AFTER = 30
JOB_HOURS = 24

ON_SLIP = "On a submitted salary slip"
FROM_REQUEST = "From a leave application or attendance request"
ATTACHED = "Has an attachment"
USED_BY = "Used by %s"
TO_DELETE, KEPT_ON_SLIPS, KEPT_FROM_REQUESTS, KEPT_IN_USE = "to_delete", "kept_on_slips", "kept_from_requests", "kept_in_use"
COUNTS = (TO_DELETE, KEPT_ON_SLIPS, KEPT_FROM_REQUESTS, KEPT_IN_USE)

# what a deletion chooses, fixed once it has started, and what only the job writes
CHOICES = ("company", "from_date", "to_date", "department", "employee", "attendance_status", "upload", "keep_deleted")
SERVER_FIELDS = (*COUNTS, "draft_slips", "status", "started_by", "started_on", "finished_on", "deleted", "kept",
                 "message", "backup_file", "kept_file", "cursor_date", "cursor_name", "backup_size", "kept_size",
                 "stop_requested")

# the fields read to count, and to back up
COUNT_FIELDS = ("name", "employee", "leave_application", "attendance_request")
RECORD_FIELDS = ("name", "docstatus", "employee", "employee_name", "department", "attendance_date", "status", "leave_type",
                 "leave_application", "attendance_request", "shift", "in_time", "out_time", "working_hours", "late_entry",
                 "early_exit", "half_day_status", "overtime_type")
DOCUMENT_STATUS = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
SUBMITTED = 1
# Upload Attendance's own eight columns first, so the file goes back in through it
BACKUP_HEADERS = ("Employee", "Employee Name", "Department", "Attendance Date", "Status", "Leave Type", "Shift", "Note",
                  "Status When Deleted", "Document Status", "In Time", "Out Time", "Working Hours", "Late Entry", "Early Exit",
                  "Half Day Status", "Overtime Type", "Attendance ID")
KEPT_HEADERS = ("Employee", "Employee Name", "Department", "Attendance Date", "Status", "Why Kept", "Attendance ID")

# what frappe.model.delete_doc clears after a record: (doctype, its doctype field, its name field)
REFERENCES_DELETED = (
    ("ToDo", "reference_type", "reference_name"),
    ("Email Unsubscribe", "reference_doctype", "reference_name"),
    ("DocShare", "share_doctype", "share_name"),
    ("Version", "ref_doctype", "docname"),
    ("Comment", "reference_doctype", "reference_name"),
    ("View Log", "reference_doctype", "reference_name"),
    ("Document Follow", "ref_doctype", "ref_docname"),
    ("Notification Log", "document_type", "document_name"),
    ("Communication Link", "link_doctype", "link_name"),
    ("Tag Link", "document_type", "document_name"),
    ("__global_search", "doctype", "name"),
)
REFERENCES_CLEARED = (
    ("Communication", "reference_doctype", "reference_name"),
    ("Activity Log", "reference_doctype", "reference_name"),
    ("Activity Log", "timeline_doctype", "timeline_name"),
)


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10]) if value else None


def period_problem(from_date, to_date):
    """Why these dates cannot be deleted, or None."""
    start, end = _date(from_date), _date(to_date)
    if start and end and end < start:
        return "The To Date is before the From Date."
    return None


def days_between(from_date, to_date, first=None):
    """Each day of the period, in order, from `first` where a job goes on from there."""
    day, end = _date(first) or _date(from_date), _date(to_date)
    while day <= end:
        yield day
        day += datetime.timedelta(days=1)


def why_kept(record, on_slips, used, attached):
    """Why a record stays, or None. on_slips: the people whose submitted slip covers its day; used: {name: what uses it};
    attached: the names with a file on them."""
    if record.get("employee") in on_slips:
        return ON_SLIP
    if record.get("leave_application") or record.get("attendance_request"):
        return FROM_REQUEST
    name = record.get("name")
    if name in used:
        return USED_BY % used[name]
    if name in attached:
        return ATTACHED
    return None


def counted_as(reason):
    """The count a record goes in, by why it stays."""
    if not reason:
        return TO_DELETE
    if reason == ON_SLIP:
        return KEPT_ON_SLIPS
    if reason == FROM_REQUEST:
        return KEPT_FROM_REQUESTS
    return KEPT_IN_USE


def pause_after(took):
    """How long to rest after a slice that took this long: half as long again, so that a busy database is given room."""
    return max(SHORTEST_PAUSE, min(LONGEST_PAUSE, float(took or 0) / 2))


def _cell(value):
    return "" if value is None else value


def backup_row(record):
    """A deleted record, under BACKUP_HEADERS. Only a submitted day has a Status, so only those go back in."""
    submitted = record.get("docstatus") == SUBMITTED
    day = _date(record.get("attendance_date"))
    return [_cell(record.get("employee")), _cell(record.get("employee_name")), _cell(record.get("department")),
            day.isoformat() if day else "", _cell(record.get("status")) if submitted else "",
            _cell(record.get("leave_type")) if submitted else "", _cell(record.get("shift")) if submitted else "", "",
            _cell(record.get("status")), DOCUMENT_STATUS.get(record.get("docstatus"), ""), _cell(record.get("in_time")),
            _cell(record.get("out_time")), _cell(record.get("working_hours")), _cell(record.get("late_entry")),
            _cell(record.get("early_exit")), _cell(record.get("half_day_status")), _cell(record.get("overtime_type")),
            _cell(record.get("name"))]


def kept_row(record, reason):
    """A record kept, under KEPT_HEADERS."""
    day = _date(record.get("attendance_date"))
    return [_cell(record.get("employee")), _cell(record.get("employee_name")), _cell(record.get("department")),
            day.isoformat() if day else "", _cell(record.get("status")), reason, _cell(record.get("name"))]


def csv_bytes(rows, first=False):
    """Rows as CSV, as bytes; the first rows of a file open with the mark that tells Excel it is UTF-8."""
    text = io.StringIO(newline="")
    csv.writer(text).writerows(rows)
    return text.getvalue().encode("utf-8-sig" if first else "utf-8")


def is_held(holds, employee, company, department, day):
    """Whether a deletion that said to keep it deleted covers this person on this day, so auto attendance leaves it alone.
    holds: those deletions, with what they chose."""
    day = _date(day)
    for hold in holds or ():
        if not _date(hold.get("from_date")) <= day <= _date(hold.get("to_date")):
            continue
        if hold.get("company") != company:
            continue
        if hold.get("department") and hold.get("department") != department:
            continue
        if hold.get("employee") and hold.get("employee") != employee:
            continue
        return True
    return False
