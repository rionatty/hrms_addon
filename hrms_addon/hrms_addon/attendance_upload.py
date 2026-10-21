# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Upload Attendance: a month of attendance from one sheet.

The reading and the checks are in attendance_upload_rules.py (tested by
scripts/verify_upload_attendance.py); this is the part that asks the site
and marks the days.

  this_cycle         the cycle today is in, the period a new upload starts with
  download_template  everybody of a company, plant or department, every day
                     of the period not marked yet
  start_import       Import: the file read while the person waits, so a
                     wrong file is said at once; the marking queued
  mark_all           the background job: every row checked first, then each
                     day marked and submitted on its own, so a day that
                     fails costs only its own row
  keep_doctype       after_migrate: Frappe HR's patch that deleted their
                     Upload Attendance takes ours too if it ever runs

Each day is a Frappe HR Attendance, inserted and submitted as the person
who pressed Import. Their permissions apply, and so does every check made
on a day marked by hand, this app's (attendance.attendance_validate)
included.
"""

import base64

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime, strip_html_tags, today

from hrms_addon.hrms_addon import attendance
from hrms_addon.hrms_addon import attendance_rules as register
from hrms_addon.hrms_addon import attendance_upload_rules as rules

DOCTYPE = "Upload Attendance"
ATTENDANCE = "Attendance"
DRAFT, QUEUED, IMPORTING = "Draft", "Queued", "Importing"
DONE, DONE_WITH_PROBLEMS, FAILED = "Done", "Done with Problems", "Failed"
STATUSES = (DRAFT, QUEUED, IMPORTING, DONE, DONE_WITH_PROBLEMS, FAILED)
RUNNING = (QUEUED, IMPORTING)
# who is in the template: anybody on the staff during the period, a leaver
# up to the day they left. Frappe HR marks no attendance for Inactive.
ON_STAFF = ("Active", "Suspended", "Left")
# days written between commits, which is also how often the bar moves
BATCH = 50
# the most problems listed on the upload itself; the file has every one
LISTED = 50
# the job's own limit, and when an upload still "running" past it is taken
# to have died with its worker
TIMEOUT_HOURS = 4
SAVEPOINT = "ha_upload_attendance"
COUNTS = ("days_in_file", "marked", "already_marked", "not_marked")


# ── The form ──────────────────────────────────────────────────────────
def upload_validate(doc, method=None):
    if doc.from_date and doc.to_date and getdate(doc.to_date) < getdate(doc.from_date):
        frappe.throw(_("The To Date is before the From Date."), title=_(DOCTYPE))
    if not doc.status:
        doc.status = DRAFT
    if not doc.is_new() and running(doc) and doc.has_value_changed("attendance_file"):
        frappe.throw(_("This upload is being marked now. Change the file when it is done."), title=_(DOCTYPE))


def upload_on_trash(doc, method=None):
    if running(doc):
        frappe.throw(_("This upload is being marked now. Delete it when it is done."), title=_(DOCTYPE))


def running(doc):
    """Whether the upload is being marked: queued or under way, and not so
    long ago that its job must have died with the worker."""
    if doc.get("status") not in RUNNING:
        return False
    started = doc.get("imported_on")
    return not started or get_datetime(started) > add_to_date(now_datetime(), hours=-(TIMEOUT_HOURS + 1))


@frappe.whitelist()
def this_cycle():
    """The cycle today is in, 26th to 25th: the period a new upload starts with."""
    start, end = register.cycle_window(*register.cycle_of(getdate(today())))
    return {"from_date": str(start), "to_date": str(end)}


# ── The template ──────────────────────────────────────────────────────
@frappe.whitelist()
def download_template(company, from_date, to_date, branch=None, department=None):
    """The template for a company, plant or department: one row per person
    per day of the period not marked yet. Returned as {"filename",
    "content"} (base64), so a problem comes back as a message, not as a
    page of error in a new tab."""
    attendance.only_hr()
    frappe.has_permission(DOCTYPE, "create", throw=True)
    if not (company and from_date and to_date):
        frappe.throw(_("Pick the company and the period first."), title=_(DOCTYPE))
    start, end = getdate(from_date), getdate(to_date)
    if end < start:
        frappe.throw(_("The To Date is before the From Date."), title=_(DOCTYPE))
    people = _people(company, start, end, branch, department)
    where = ", ".join(part for part in (department, branch, company) if part)
    if not people:
        frappe.throw(_("Nobody at {0} was on the staff from {1} to {2}.").format(where, _day(start), _day(end)),
                     title=_(DOCTYPE))
    default_list = frappe.db.get_value("Company", company, "default_holiday_list")
    lists = {row.holiday_list or default_list for row in people} - {None, ""}
    rows = rules.template_rows(
        [{"employee": row.name, "employee_name": row.employee_name, "department": row.department,
          "date_of_joining": row.date_of_joining, "relieving_date": row.relieving_date,
          "holiday_list": row.holiday_list or default_list} for row in people],
        start, end, getdate(today()), set(_marked([row.name for row in people], start, end)),
        _holidays(lists, start, end))
    if not rows:
        frappe.throw(_("Every day from {0} to {1} is marked already at {2}.").format(_day(start), _day(end), where),
                     title=_(DOCTYPE))
    if len(rows) > rules.MAX_ROWS:
        frappe.throw(_("That is {0} rows. Pick a plant or a department, or fewer days.").format(len(rows)),
                     title=_(DOCTYPE))
    content = rules.build_template(rows, _names("Leave Type"), _names("Shift Type"))
    name = "Attendance %s to %s %s.xlsx" % (start, end, branch or department or company)
    return {"filename": name.replace("/", "-"), "content": base64.b64encode(content).decode(), "rows": len(rows)}


def _people(company, start, end, branch=None, department=None):
    """Everybody of the company on the staff at some point in the period:
    a leaver up to the day they left, a new hire from the day they joined."""
    filters = {"company": company, "date_of_joining": ["<=", end], "status": ["in", ON_STAFF]}
    if branch:
        filters["branch"] = branch
    if department:
        filters["department"] = ["descendants of (inclusive)", department]
    found = frappe.get_all(
        "Employee", filters=filters, limit_page_length=0,
        fields=["name", "employee_name", "department", "date_of_joining", "relieving_date", "holiday_list"],
        order_by="department asc, employee_name asc")
    return [row for row in found if not row.relieving_date or getdate(row.relieving_date) >= start]


def _marked(employees, start, end):
    """{(employee, date): (status, the Attendance)} for every day marked in
    the period, in draft or submitted: Frappe HR refuses a second one."""
    if not employees:
        return {}
    return {(row.employee, getdate(row.attendance_date)): (row.status, row.name)
            for row in frappe.get_all(
                ATTENDANCE, limit_page_length=0,
                filters={"employee": ["in", employees], "docstatus": ["<", 2],
                         "attendance_date": ["between", [start, end]]},
                fields=["name", "employee", "attendance_date", "status"])}


def _holidays(lists, start, end):
    """{holiday list: {dates}} for the period, read once per list."""
    return {name: {getdate(row.holiday_date) for row in frappe.get_all(
        "Holiday", filters={"parent": name, "parenttype": "Holiday List",
                            "holiday_date": ["between", [start, end]]},
        fields=["holiday_date"], limit_page_length=0)} for name in lists}


def _names(doctype):
    return frappe.get_all(doctype, pluck="name", order_by="name asc", limit_page_length=0)


def _day(value):
    return frappe.format(value, {"fieldtype": "Date"})


# ── Import ────────────────────────────────────────────────────────────
def start_import(doc):
    """Import: the file read now, while the person is there to be told what
    is wrong with it; the days checked and marked in the background."""
    attendance.only_hr()
    doc.check_permission("write")
    if running(doc):
        frappe.throw(_("This upload is being marked now."), title=_(DOCTYPE))
    if not doc.attendance_file:
        frappe.throw(_("Attach the filled template first."), title=_(DOCTYPE))
    try:
        found = rules.read_file(_file_bytes(doc.attendance_file), doc.attendance_file)
    except ValueError as error:
        frappe.throw(_(str(error)), title=_(DOCTYPE))
    days = len([row for row in found["rows"] if rules.text(row.get("status"))])
    if not days:
        frappe.throw(_("No row has a Status. Put a Status on each day to mark and attach the file again."),
                     title=_(DOCTYPE))
    doc.db_set(dict({field: 0 for field in COUNTS}, status=QUEUED, imported_by=frappe.session.user,
                    imported_on=now_datetime(), problems=None, problems_file=None), notify=True)
    frappe.enqueue("hrms_addon.hrms_addon.attendance_upload.mark_all", queue="long",
                   timeout=TIMEOUT_HOURS * 3600, job_id="upload_attendance::%s" % doc.name, deduplicate=True,
                   enqueue_after_commit=True, upload=doc.name)
    return {"status": QUEUED, "days": days}


def mark_all(upload):
    """The background job. A problem in the file, or one day that will not
    go in, is said on the upload; anything else stops it, as Failed."""
    doc = frappe.get_doc(DOCTYPE, upload)
    doc.db_set("status", IMPORTING, commit=True, notify=True)
    try:
        _mark_file(doc)
    except Exception as error:
        frappe.db.rollback()
        frappe.log_error(title="Upload Attendance %s stopped" % upload)
        doc.db_set({"status": FAILED, "problems": _("It stopped: {0}").format(_reason(error))},
                   commit=True, notify=True)


def _mark_file(doc):
    try:
        found = rules.read_file(_file_bytes(doc.attendance_file), doc.attendance_file)
    except ValueError as error:
        doc.db_set({"status": FAILED, "problems": _(str(error))}, commit=True, notify=True)
        return
    filled = [row for row in found["rows"] if rules.text(row.get("status"))]
    if not filled:
        doc.db_set({"status": FAILED, "problems": _("No row has a Status.")}, commit=True, notify=True)
        return
    employees = _employees({rules.text(row.get("employee")) for row in filled} - {""})
    days = [day for day in (rules.parse_date(row.get("attendance_date")) for row in filled) if day]
    marked = _marked(list(employees), min(days), max(days)) if employees and days else {}
    checked = rules.check_rows(filled, employees, _names("Leave Type"), _names("Shift Type"), marked,
                               getdate(today()))
    problems = list(checked["problems"])
    counts = {"days_in_file": len(filled), "marked": 0, "already_marked": checked["already"]}
    total = len(checked["to_mark"])
    for number, row in enumerate(checked["to_mark"], 1):
        why = _mark_day(row, employees)
        if why:
            problems.append((row["source"], why))
        else:
            counts["marked"] += 1
        if number % BATCH == 0 or number == total:
            counts["not_marked"] = len(problems)
            doc.db_set(counts, commit=True)
            frappe.publish_progress(number * 100.0 / total, title=_("Marking attendance"), doctype=DOCTYPE,
                                    docname=doc.name, description=_("{0} of {1}").format(number, total))
    counts["not_marked"] = len(problems)
    doc.db_set(dict(counts, status=DONE_WITH_PROBLEMS if problems else DONE,
                    problems=rules.listed(problems, LISTED) if problems else None,
                    problems_file=_problems_file(doc, found["header"], problems) if problems else None),
               commit=True, notify=True)


def _employees(named):
    """{name: what the checks need} for the employees the file names. The
    database matches a name without case, as the checks do."""
    if not named:
        return {}
    return {row.name: row for row in frappe.get_all(
        "Employee", filters={"name": ["in", list(named)]}, limit_page_length=0,
        fields=["name", "company", "date_of_joining", "relieving_date", "status"])}


def _mark_day(row, employees):
    """One day marked and submitted, or why not. A day that fails is rolled
    back to before it, so it takes nothing else with it."""
    frappe.db.savepoint(SAVEPOINT)
    try:
        day = frappe.get_doc({
            "doctype": ATTENDANCE, "employee": row["employee"], "attendance_date": row["attendance_date"],
            "status": row["status"], "leave_type": row["leave_type"], "shift": row["shift"],
            "company": employees[row["employee"]].company,
        })
        day.insert()
        day.submit()
        return None
    except Exception as error:
        frappe.db.rollback(save_point=SAVEPOINT)
        return _reason(error)
    finally:
        # Frappe HR's notes on a day ("No leave record found ...") are for
        # somebody at the form; a month of them is only memory here
        frappe.local.message_log = []


def _reason(error):
    return strip_html_tags(str(error)).strip() or type(error).__name__


def _problems_file(doc, header, problems):
    """The rows not marked, with why, attached to the upload."""
    saved = frappe.get_doc({
        "doctype": "File", "file_name": "%s rows not marked.xlsx" % doc.name,
        "attached_to_doctype": DOCTYPE, "attached_to_name": doc.name, "attached_to_field": "problems_file",
        "is_private": 1, "content": rules.problems_file(header, problems),
    })
    saved.insert(ignore_permissions=True)
    return saved.file_url


def _file_bytes(file_url):
    """A file's content as it is kept on the site, as bytes: File.get_content
    hands back text for a .csv."""
    if frappe.db.exists("File", {"file_url": file_url}):
        path = frappe.get_doc("File", {"file_url": file_url}).get_full_path()
    else:
        path = frappe.get_site_path("public", str(file_url).lstrip("/"))
    with open(path, "rb") as handle:
        return handle.read()


# ── After migrate ─────────────────────────────────────────────────────
def keep_doctype():
    """Ours put back if Frappe HR's patch took it.

    Frappe HR v16 deletes its Upload Attendance by name, in a patch that
    runs after the doctypes are synced. On a site already on v16 it has
    run and is done with; on a site coming from v15 it runs on the same
    migrate that brings this app's, and deletes ours. This runs after it,
    and before the navigation is written: Frappe will not save a page that
    links to a doctype that is not there."""
    if not frappe.db.exists("DocType", DOCTYPE):
        frappe.reload_doc("hrms_addon", "doctype", "upload_attendance", force=True)
        frappe.db.commit()
