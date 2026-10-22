# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Upload Attendance: a month of attendance from one sheet, for any number
of people.

The reading and the checks are in attendance_upload_rules.py (tested by
scripts/verify_upload_attendance.py); this is the part that asks the site
and marks the days.

  this_cycle         the cycle today is in, the period a new upload starts with
  download_template  the template of a company, plant or department for
                     the period: a row per employee per day still to mark
  start_import       Import: the file's heading checked while the person
                     waits; the days read, checked and marked in the
                     background
  mark_all           the background job: the file read as it goes, a part at
                     a time, each part checked and then marked, a day at a
                     time, so a day that fails costs only its own row and a
                     file of any size is never held whole
  keep_doctype       after_migrate: Frappe HR's patch that deleted their
                     Upload Attendance takes ours too if it ever runs

A JOB OF ANY LENGTH

Each part saves the counts, which keeps the upload's modified time moving.
An upload that says Queued or Importing and has not moved for STOPPED_AFTER
minutes has lost its job (a worker restarted under it), and is free to be
imported again: what it marked counts as marked already, so it goes on from
where it stopped.

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
# the days read and checked together, and marked between two saves of the counts
PART = 2000
BATCH = 200
# the most problems listed on the upload itself; the file has every one
LISTED = 50
# a job is given a day; one that has not moved for this long has died
JOB_HOURS = 24
STOPPED_AFTER = 30
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


def upload_onload(doc, method=None):
    """Whether an upload that says it is being marked has stopped, so the
    form can say Import goes on from where it stopped."""
    doc.set_onload("stopped", doc.get("status") in RUNNING and not running(doc))


def upload_on_trash(doc, method=None):
    if running(doc):
        frappe.throw(_("This upload is being marked now. Delete it when it is done."), title=_(DOCTYPE))


def running(doc):
    """Whether the upload is being marked: queued or under way, and moved in
    the last STOPPED_AFTER minutes, as a live job keeps it moving."""
    if doc.get("status") not in RUNNING:
        return False
    moved = doc.get("modified")
    return not moved or get_datetime(moved) > add_to_date(now_datetime(), minutes=-STOPPED_AFTER)


@frappe.whitelist()
def this_cycle():
    """The cycle today is in, 26th to 25th: the period a new upload starts with."""
    start, end = register.cycle_window(*register.cycle_of(getdate(today())))
    return {"from_date": str(start), "to_date": str(end)}


# ── The template ──────────────────────────────────────────────────────
@frappe.whitelist()
def download_template(company, from_date, to_date, branch=None, department=None):
    """The template of a company, plant or department for the period: a row
    per employee per day still to be marked. Returned as {"filename",
    "content" (base64), "rows"}, so a problem comes back as a message, not
    as a page of error in a new tab."""
    attendance.only_hr()
    frappe.has_permission(DOCTYPE, "create", throw=True)
    if not (company and from_date and to_date):
        frappe.throw(_("Pick the company and the period first."), title=_(DOCTYPE))
    start, end = getdate(from_date), getdate(to_date)
    if end < start:
        frappe.throw(_("The To Date is before the From Date."), title=_(DOCTYPE))
    if (end - start).days + 1 > rules.MAX_DAYS:
        frappe.throw(_("That is {0} days. Pick a period of a year at most.").format((end - start).days + 1),
                     title=_(DOCTYPE))
    people = _people(company, start, end, branch, department)
    where = ", ".join(part for part in (department, branch, company) if part)
    if not people:
        frappe.throw(_("Nobody at {0} was on the staff from {1} to {2}.").format(where, _day(start), _day(end)),
                     title=_(DOCTYPE))
    default_list = frappe.db.get_value("Company", company, "default_holiday_list")
    lists = {row.holiday_list or default_list for row in people} - {None, ""}
    marked = _marked([row.name for row in people], start, end)
    staff = [{"employee": row.name, "employee_name": row.employee_name, "department": row.department,
              "date_of_joining": row.date_of_joining, "relieving_date": row.relieving_date,
              "holiday_list": row.holiday_list or default_list} for row in people]
    on = getdate(today())
    total = rules.count_rows(staff, start, end, on, marked)
    if total > rules.MAX_ROWS:
        frappe.throw(_("That is {0} rows, more than one Excel sheet holds. Pick a plant or a department, or fewer "
                       "days.").format(frappe.format(total, {"fieldtype": "Int"})), title=_(DOCTYPE))
    if not total:
        frappe.throw(_("No day is left to mark at {0} from {1} to {2}: each is marked already, or after today.")
                     .format(where, _day(start), _day(end)), title=_(DOCTYPE))
    content = rules.build_template(rules.template_rows(staff, start, end, on, marked, _holidays(lists, start, end)),
                                   total, _names("Leave Type"), _names("Shift Type"))
    name = "Attendance %s to %s %s.xlsx" % (start, end, branch or department or company)
    return {"filename": name.replace("/", "-"), "content": base64.b64encode(content).decode(), "rows": total}


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
    """Import: the file's heading checked while the person waits, so a wrong
    file is said at once; the days read, checked and marked in the
    background, however many there are."""
    attendance.only_hr()
    doc.check_permission("write")
    if running(doc):
        frappe.throw(_("This upload is being marked now."), title=_(DOCTYPE))
    if not doc.attendance_file:
        frappe.throw(_("Attach the filled template first."), title=_(DOCTYPE))
    try:
        rules.header_of(_file_bytes(doc.attendance_file), doc.attendance_file)
    except ValueError as error:
        frappe.throw(_(str(error)), title=_(DOCTYPE))
    doc.db_set(dict({field: 0 for field in COUNTS}, status=QUEUED, imported_by=frappe.session.user,
                    imported_on=now_datetime(), problems=None, problems_file=None), notify=True)
    frappe.enqueue("hrms_addon.hrms_addon.attendance_upload.mark_all", queue="long",
                   timeout=JOB_HOURS * 3600, job_id="upload_attendance::%s" % doc.name, deduplicate=True,
                   enqueue_after_commit=True, upload=doc.name)
    return {"status": QUEUED}


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
    content = _file_bytes(doc.attendance_file)
    try:
        # the days counted first, read as they come, for the bar to move by
        total = sum(1 for _record in rules.days_in(content, doc.attendance_file))
    except ValueError as error:
        doc.db_set({"status": FAILED, "problems": _(str(error))}, commit=True, notify=True)
        return
    if not total:
        doc.db_set({"status": FAILED, "problems": _(rules.NOTHING_FILLED)}, commit=True, notify=True)
        return
    counts = {"days_in_file": total, "marked": 0, "already_marked": 0, "not_marked": 0}
    doc.db_set(counts, commit=True, notify=True)
    names = _site_names()
    # people: {name: what the checks need}; index: {name in small letters: name,
    # or None for one the site does not have}, so each is looked up once
    people, index, seen, problems = {}, {}, {}, []
    done, shown = 0, -1
    for part in _parts(rules.days_in(content, doc.attendance_file), PART):
        _learn(people, index, part)
        dates = [day for day in (rules.parse_date(record.get("attendance_date")) for record in part) if day]
        here = list({index.get(rules.text(record.get("employee")).lower()) for record in part} - {None})
        marked = _marked(here, min(dates), max(dates)) if here and dates else {}
        checked = rules.check_days(part, people, names, marked, getdate(today()), seen=seen)
        problems += checked["problems"]
        counts["already_marked"] += checked["already"]
        for row in checked["to_mark"]:
            why = _mark_day(row, people)
            if why:
                problems.append((row["source"], why))
            else:
                counts["marked"] += 1
            done += 1
            if done % BATCH == 0:
                counts["not_marked"] = len(problems)
                doc.db_set(counts, commit=True)
        done += len(part) - len(checked["to_mark"])
        counts["not_marked"] = len(problems)
        # a part saved is a part the job has got through: the upload moves on
        doc.db_set(counts, commit=True)
        percent = int(done * 100 / total)
        if percent != shown:
            shown = percent
            frappe.publish_progress(percent, title=_("Marking attendance"), doctype=DOCTYPE, docname=doc.name,
                                    description=_("{0} of {1} days").format(min(done, total), total))
    doc.db_set(dict(counts, status=DONE_WITH_PROBLEMS if problems else DONE,
                    problems=rules.listed(problems, LISTED) if problems else None,
                    problems_file=_problems_file(doc, rules.header_of(content, doc.attendance_file), problems)
                    if problems else None),
               commit=True, notify=True)


def _parts(records, size):
    """The days in parts of `size`, read as they come."""
    part = []
    for record in records:
        part.append(record)
        if len(part) >= size:
            yield part
            part = []
    if part:
        yield part


def _site_names():
    """What a row's Leave Type and Shift are checked against: the site's own."""
    return {"leave_types": _names("Leave Type"), "shifts": _names("Shift Type")}


def _learn(people, index, part):
    """The employees a part names that are not looked up yet, read once each,
    and those the site does not have remembered as such. The database
    matches a name without case, as the checks do."""
    wanted = {rules.text(record.get("employee")) for record in part} - {""}
    wanted = [name for name in wanted if name.lower() not in index]
    if not wanted:
        return
    for name in wanted:
        index[name.lower()] = None
    for row in frappe.get_all("Employee", filters={"name": ["in", wanted]}, limit_page_length=0,
                              fields=["name", "company", "date_of_joining", "relieving_date", "status"]):
        people[row.name] = row
        index[row.name.lower()] = row.name


def _mark_day(row, people):
    """One day marked and submitted, or why not. A day that fails is rolled
    back to before it, so it takes nothing else with it."""
    frappe.db.savepoint(SAVEPOINT)
    try:
        day = frappe.get_doc({
            "doctype": ATTENDANCE, "employee": row["employee"], "attendance_date": row["attendance_date"],
            "status": row["status"], "leave_type": row["leave_type"], "shift": row["shift"],
            "company": people[row["employee"]].company,
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
    """The rows not marked, each as it was with why, attached to the upload."""
    saved = frappe.get_doc({
        "doctype": "File", "file_name": "%s days not marked.xlsx" % doc.name,
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
