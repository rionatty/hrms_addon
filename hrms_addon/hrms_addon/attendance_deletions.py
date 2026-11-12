# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance Deletion: a month of attendance deleted while everybody else keeps
working. What it does and keeps, and why not Frappe's own delete, is in
attendance_deletion_rules.py (scripts/verify_attendance_deletion.py); this is
the part that asks the site.

  count               how many records a deletion would delete, and keep and why
  check               the same, saved, for the Delete button
  start               delete them, once the person has typed the count; or go on
                      with one that stopped
  delete_all          the background job
  stop                stop at the end of the slice
  release             auto attendance may fill these days again
  progress            how far it has got, for the form
  add_indexes         on_doctype_update: what the deletion looks records up by
  ShiftTypeKeepDeleted  mixed in ahead of Frappe HR's Shift Type
                      (hooks.extend_doctype_class): auto attendance leaves the
                      days a deletion said to keep deleted

KEEP DELETED

Frappe HR's auto attendance marks a day from any punch with no attendance, and
marks Absent on any working day with none at all, from the shift's Process
Attendance After. So deleted days come back at its next run, and only a shift's
settings could stop that, for everybody on it. A deletion with Keep Deleted holds
its own dates for its own people instead, until released. The punches themselves
are left as they are.

Attendance is a submitted record and Frappe cancels before it deletes: all
cancelling does for it is let go of its punches, which is done here too.
"""

import os
import time

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, get_files_path, getdate, now_datetime

from hrms_addon.hrms_addon import attendance_deletion_rules as rules

DOCTYPE = "Attendance Deletion"
ATTENDANCE = "Attendance"
CHECKIN = "Employee Checkin"
SLIP = "Salary Slip"
WEEKLY_DAY = "Weekly Pay Day"
VERIFICATION = "Attendance Verification"
UPLOAD = "Upload Attendance"
# what an uploaded day names its upload by (attendance_upload.py)
UPLOAD_FIELD = "custom_attendance_upload"
# what a record's own links do not hold it back for: these are let go of with it
LET_GO = {(ATTENDANCE, "amended_from"), (CHECKIN, "attendance")}
BACKUP, KEPT = "deleted attendance", "attendance kept"


# ── On the form ──────────────────────────────────────────
def deletion_onload(doc, method=None):
    """Whether a deletion that says it is running has lost its job, so the form can offer to go on."""
    doc.set_onload("stopped", doc.get("status") in rules.RUNNING and not running(doc))


def deletion_validate(doc, method=None):
    """What only the job writes is put back whatever was sent, and what was chosen is fixed once it has started. A
    deletion not yet started is counted each time it is saved."""
    before = doc.get_doc_before_save()
    for field in rules.SERVER_FIELDS:
        doc.set(field, before.get(field) if before else None)
    doc.status = doc.status or rules.DRAFT
    problem = rules.period_problem(doc.get("from_date"), doc.get("to_date"))
    if problem:
        frappe.throw(_(problem), title=_(DOCTYPE))
    if doc.get("upload"):
        company = frappe.db.get_value(UPLOAD, doc.upload, "company")
        if company and company != doc.get("company"):
            frappe.throw(_("{0} is an upload of {1}. Pick that company.").format(doc.upload, company), title=_(DOCTYPE))
        # nothing held from auto attendance: a hold is a company's, a department's or one person's days, never only
        # the people an upload marked
        doc.set("keep_deleted", 0)
    if doc.status != rules.DRAFT:
        if any(doc.has_value_changed(field) for field in rules.CHOICES):
            frappe.throw(_("This deletion has started. Make a new one to delete anything else."), title=_(DOCTYPE))
        return
    doc.update(count(doc))


def deletion_on_trash(doc, method=None):
    if doc.get("status") != rules.DRAFT:
        frappe.throw(_("This deletion has started, and its record stays."), title=_(DOCTYPE))


def running(doc):
    """Whether it is queued or under way, and moved lately, as a live job keeps it moving with each slice."""
    if doc.get("status") not in rules.RUNNING:
        return False
    moved = doc.get("modified")
    return not moved or get_datetime(moved) > add_to_date(now_datetime(), minutes=-rules.STOPPED_AFTER)


def _may_delete(deletion):
    doc = frappe.get_doc(DOCTYPE, deletion)
    doc.check_permission("write")
    frappe.has_permission(ATTENDANCE, "delete", throw=True)
    return doc


@frappe.whitelist(methods=["POST"])
def check(deletion):
    """The count as it now stands, saved on the deletion."""
    doc = _may_delete(deletion)
    if doc.get("status") != rules.DRAFT:
        frappe.throw(_("This deletion has started."), title=_(DOCTYPE))
    counts = count(doc)
    doc.db_set(counts, notify=True)
    return counts


@frappe.whitelist(methods=["POST"])
def start(deletion, confirmed=None):
    """Queue the job. A new deletion needs the count typed, as it stands now: whatever was on the screen when the person
    decided, it is this many that go. One that stopped goes on from where it was."""
    doc = _may_delete(deletion)
    if running(doc):
        frappe.throw(_("This deletion is running now."), title=_(DOCTYPE))
    other = next((row.name for row in frappe.get_all(DOCTYPE, filters={"status": ["in", list(rules.RUNNING)], "name": ["!=", doc.name]},
                                                     fields=["name", "status", "modified"], limit_page_length=0) if running(row)), None)
    if other:
        frappe.throw(_("Deletion {0} is running. One runs at a time, so the site stays quick.").format(other), title=_(DOCTYPE))
    status = doc.get("status")
    if status == rules.DRAFT:
        counts = count(doc)
        doc.db_set(counts)
        if not counts[rules.TO_DELETE]:
            frappe.throw(_("There is nothing to delete."), title=_(DOCTYPE))
        if cint(confirmed) != counts[rules.TO_DELETE]:
            frappe.throw(_("The count is {0}. Type that number to delete them.").format(counts[rules.TO_DELETE]), title=_(DOCTYPE))
        doc.db_set({"started_by": frappe.session.user, "started_on": now_datetime(), "deleted": 0, "kept": 0})
    elif status not in rules.ON_HOLD and status not in rules.RUNNING:
        frappe.throw(_("This deletion has finished."), title=_(DOCTYPE))
    doc.db_set({"status": rules.QUEUED, "stop_requested": 0, "message": None}, notify=True)
    frappe.enqueue("hrms_addon.hrms_addon.attendance_deletions.delete_all", queue="long", timeout=rules.JOB_HOURS * 3600,
                   job_id="attendance_deletion", deduplicate=True, enqueue_after_commit=True, deletion=doc.name)
    return {"status": rules.QUEUED}


@frappe.whitelist(methods=["POST"])
def stop(deletion):
    """Stop at the end of the slice. One that has lost its job has nothing to wait for."""
    doc = _may_delete(deletion)
    if doc.get("status") not in rules.RUNNING:
        return {"status": doc.get("status")}
    if running(doc):
        doc.db_set("stop_requested", 1, notify=True)
    else:
        doc.db_set({"status": rules.STOPPED, "stop_requested": 0}, notify=True)
    return {"status": doc.get("status")}


@frappe.whitelist(methods=["POST"])
def release(deletion):
    """Auto attendance may fill these days again."""
    doc = _may_delete(deletion)
    doc.db_set("keep_deleted", 0, notify=True)
    return {"keep_deleted": 0}


@frappe.whitelist()
def progress(deletion):
    """How far it has got, for the form to show without being reloaded."""
    doc = frappe.get_doc(DOCTYPE, deletion)
    doc.check_permission("read")
    return {"status": doc.get("status"), "deleted": cint(doc.get("deleted")), "kept": cint(doc.get("kept"))}


@frappe.whitelist()
def upload_days(upload):
    """An upload's company and the first and last day it marked, for the form to fill in: else the upload's own dates."""
    frappe.has_permission(DOCTYPE, "write", throw=True)
    doc = frappe.get_doc(UPLOAD, upload)
    doc.check_permission("read")
    first = last = None
    if frappe.get_meta(ATTENDANCE).has_field(UPLOAD_FIELD):
        first, last = (next(iter(frappe.get_all(ATTENDANCE, filters={UPLOAD_FIELD: upload}, pluck="attendance_date",
                                                order_by="attendance_date %s" % way, limit=1)), None)
                       for way in ("asc", "desc"))
    return {"company": doc.company, "from_date": str(first or doc.get("from_date") or ""),
            "to_date": str(last or doc.get("to_date") or "")}


# ── What there is to delete ──────────────────────────────
def count(doc):
    """{count field: how many}, and the draft slips the deletion would leave out of date."""
    links = _links()
    counts = dict.fromkeys(rules.COUNTS, 0)
    for day, records, on_slips in _slices(doc, rules.COUNT_FIELDS):
        reasons = _reasons(records, on_slips, links, day)
        for record in records:
            counts[rules.counted_as(reasons.get(record.name))] += 1
    counts["draft_slips"] = _draft_slips(doc)
    return counts


def _slices(doc, fields, first=None, after=None):
    """(day, its next SLICE records, whose submitted slip covers the day), a day at a time from `first`, past the name
    `after` on that day. A day's records come from the day's own index, in name order, with no sorting to do."""
    first = getdate(first) if first else None
    choices = {"company": doc.get("company")}
    # one upload's days only, where one is chosen (Luuka, 12 Nov 2026): the days it marked name it
    for column, choice in (("department", "department"), ("employee", "employee"), ("status", "attendance_status"),
                           (UPLOAD_FIELD, "upload")):
        if doc.get(choice):
            choices[column] = doc.get(choice)
    # a weekly slip can pay a day marked after its week, which its own dates do not reach: the period's, read once
    paid_later = {}
    for row in frappe.get_all(WEEKLY_DAY, filters={"docstatus": 1, "attendance_date": [
            "between", [first or doc.get("from_date"), doc.get("to_date")]]},
            fields=["employee", "attendance_date"], limit_page_length=0):
        paid_later.setdefault(getdate(row.attendance_date), set()).add(row.employee)
    for day in rules.days_between(doc.get("from_date"), doc.get("to_date"), first):
        on_slips = set(frappe.get_all(SLIP, filters={"docstatus": 1, "start_date": ["<=", day], "end_date": [">=", day]},
                                      pluck="employee", limit_page_length=0)) | paid_later.get(getdate(day), set())
        past = after if day == first else None
        while True:
            filters = dict(choices, attendance_date=day)
            if past:
                filters["name"] = [">", past]
            records = frappe.get_all(ATTENDANCE, filters=filters, fields=list(fields), order_by="name asc",
                                     limit_page_length=rules.SLICE)
            if not records:
                break
            yield day, records, on_slips
            past = records[-1].name


def _verified_on(day):
    """The people a verified attendance sheet holds on the day."""
    if not day or not frappe.db.table_exists(VERIFICATION):
        return set()
    from hrms_addon.hrms_addon import attendance_verification

    return {employee for sheet in attendance_verification.verified_sheets(day, day) for employee in sheet["employees"]}


def _link_fields():
    """(doctype, field) of what links to Attendance, as Frappe's own check finds them; those it ignores left out."""
    from frappe.model.rename_doc import get_link_fields

    ignored = set(frappe.get_hooks("ignore_links_on_delete"))
    return [link for link in get_link_fields(ATTENDANCE) if link["parent"] not in ignored]


def _links():
    """What can hold a record back: {"table": [{"doctype", "field", "of", "parent"}], "single": {name: doctype}}."""
    from frappe.model.dynamic_links import get_dynamic_link_map

    tables, single = [], {}
    for link in _link_fields():
        doctype, field = link["parent"], link["fieldname"]
        if (doctype, field) in LET_GO:
            continue
        if link["issingle"]:
            value = frappe.db.get_single_value(doctype, field)
            if value:
                single[value] = doctype
            continue
        if not frappe.db.table_exists(doctype):
            continue
        tables.append({"doctype": doctype, "field": field, "of": None, "parent": frappe.get_meta(doctype).istable})
    ignored = set(frappe.get_hooks("ignore_links_on_delete"))
    for df in get_dynamic_link_map().get(ATTENDANCE, []):
        meta = frappe.get_meta(df.parent)
        if df.parent in ignored:
            continue
        if meta.issingle:
            values = frappe.db.get_singles_dict(df.parent)
            if values.get(df.options) == ATTENDANCE and values.get(df.fieldname) and values.get("docstatus") != 2:
                single[values.get(df.fieldname)] = df.parent
            continue
        tables.append({"doctype": df.parent, "field": df.fieldname, "of": df.options, "parent": meta.istable})
    return {"table": tables, "single": single}


def _reasons(records, on_slips, links, day=None):
    """{name: why it stays}, for those of these records that stay."""
    names = [record.name for record in records]
    used = dict(links["single"])
    for link in links["table"]:
        filters = {link["field"]: ["in", names]}
        if link["of"]:
            filters.update({link["of"]: ATTENDANCE, "docstatus": ["<", 2]})
        fields = [link["field"], "parenttype"] if link["parent"] else [link["field"]]
        for row in frappe.get_all(link["doctype"], filters=filters, fields=fields, distinct=True, limit_page_length=0):
            used.setdefault(row[link["field"]], row.parenttype if link["parent"] else link["doctype"])
    attached = set(frappe.get_all("File", filters={"attached_to_doctype": ATTENDANCE, "attached_to_name": ["in", names]},
                                  pluck="attached_to_name", limit_page_length=0))
    # a day its branch has verified stays as it is, until the sheet is reopened (attendance_verification.py)
    verified = _verified_on(day)
    for record in records:
        if record.get("employee") in verified:
            used.setdefault(record.name, VERIFICATION)
    reasons = {}
    for record in records:
        reason = rules.why_kept(record, on_slips, used, attached)
        if reason:
            reasons[record.name] = reason
    return reasons


def _draft_slips(doc):
    filters = {"docstatus": 0, "company": doc.get("company"), "start_date": ["<=", doc.get("to_date")],
               "end_date": [">=", doc.get("from_date")]}
    for field in ("department", "employee"):
        if doc.get(field):
            filters[field] = doc.get(field)
    return frappe.db.count(SLIP, filters)


# ── The job ──────────────────────────────────────────────
def delete_all(deletion):
    """The background job. Whatever stops it, what it has done is saved, and it goes on from there when started again."""
    doc = frappe.get_doc(DOCTYPE, deletion)
    if doc.get("status") not in rules.RUNNING:
        return
    try:
        doc.db_set("status", rules.DELETING, commit=True, notify=True)
        _delete_slices(doc)
    except Exception as error:
        frappe.db.rollback()
        frappe.log_error(title="Attendance Deletion %s stopped" % deletion)
        doc.db_set({"status": rules.FAILED, "message": _("It stopped: {0}").format(str(error)[:300])}, commit=True, notify=True)


def _delete_slices(doc):
    backup = _open_file(doc, "backup_file", "backup_size", BACKUP, rules.BACKUP_HEADERS)
    kept = _open_file(doc, "kept_file", "kept_size", KEPT, rules.KEPT_HEADERS)
    links = _links()
    for day, records, on_slips in _slices(doc, rules.RECORD_FIELDS, doc.get("cursor_date"), doc.get("cursor_name")):
        began = time.monotonic()
        reasons = _reasons(records, on_slips, links, day)
        going = [record for record in records if record.name not in reasons]
        staying = [record for record in records if record.name in reasons]
        state = {
            "deleted": cint(doc.get("deleted")) + len(going),
            "kept": cint(doc.get("kept")) + len(staying),
            "cursor_date": day,
            "cursor_name": records[-1].name,
            "backup_size": _append(backup, [rules.backup_row(record) for record in going]),
            "kept_size": _append(kept, [rules.kept_row(record, reasons[record.name]) for record in staying]),
        }
        _delete(day, [record.name for record in going])
        # with what was deleted, or not at all: a job killed here goes on from the last slice saved
        doc.db_set(state, commit=True)
        if frappe.db.get_value(DOCTYPE, doc.name, "stop_requested"):
            _settle(doc, rules.STOPPED)
            return
        time.sleep(rules.pause_after(time.monotonic() - began))
    _settle(doc, rules.FINISHED)


def _delete(day, names):
    """The records, and all Frappe would have cleared after them, together."""
    if not names:
        return
    within = ["in", names]
    frappe.db.set_value(CHECKIN, {"attendance": within}, "attendance", "", update_modified=False)
    # a record staying that was amended from one of these; an amended record keeps its day
    frappe.db.set_value(ATTENDANCE, {"attendance_date": day, "amended_from": within}, "amended_from", None, update_modified=False)
    for doctype, of, name in rules.REFERENCES_DELETED:
        frappe.db.delete(doctype, {of: ATTENDANCE, name: within})
    for doctype, of, name in rules.REFERENCES_CLEARED:
        frappe.db.set_value(doctype, {of: ATTENDANCE, name: within}, {of: None, name: None}, update_modified=False)
    frappe.db.delete(ATTENDANCE, {"name": within})


def _settle(doc, status):
    """The end, or a stop: the files' sizes put right, as they have grown since they were attached."""
    for url_field, size_field in (("backup_file", "backup_size"), ("kept_file", "kept_size")):
        frappe.db.set_value("File", {"file_url": doc.get(url_field)}, "file_size", cint(doc.get(size_field)), update_modified=False)
    values = {"status": status, "stop_requested": 0}
    if status == rules.FINISHED:
        values["finished_on"] = now_datetime()
    doc.db_set(values, commit=True, notify=True)


def _open_file(doc, url_field, size_field, title, header):
    """The path of a private CSV of the deletion's own, ready to be added to. Going on after a job was killed, it is cut
    back to what was saved as done: what the job wrote after that is written again."""
    file_name = "%s %s.csv" % (doc.name, title)
    path = get_files_path(file_name, is_private=1)
    if doc.get(url_field) and os.path.exists(path):
        os.truncate(path, cint(doc.get(size_field)))
        return path
    with open(path, "wb") as handle:
        handle.write(rules.csv_bytes([header], first=True))
    file_url = "/private/files/%s" % file_name
    if not doc.get(url_field):
        frappe.get_doc({"doctype": "File", "file_name": file_name, "file_url": file_url, "is_private": 1,
                        "attached_to_doctype": DOCTYPE, "attached_to_name": doc.name, "attached_to_field": url_field,
                        "file_size": os.path.getsize(path)}).insert(ignore_permissions=True)
    doc.db_set({url_field: file_url, size_field: os.path.getsize(path)}, commit=True)
    return path


def _append(path, rows):
    """The rows added to the file, on the disk before the records go. Returns the file's size."""
    if rows:
        with open(path, "ab") as handle:
            handle.write(rules.csv_bytes(rows))
            handle.flush()
            os.fsync(handle.fileno())
    return os.path.getsize(path)


def add_indexes():
    """on_doctype_update: each slice looks records up by what links to them, and a punch table runs to millions. A speed-up
    only, so a table that will not take one holds nothing else up."""
    for link in _link_fields():
        doctype, field = link["parent"], link["fieldname"]
        # a Single has no table of its own
        if (doctype, field) == (ATTENDANCE, "amended_from") or not frappe.db.table_exists(doctype):
            continue
        try:
            frappe.db.add_index(doctype, [field])
        except Exception:
            frappe.log_error(title="Attendance Deletion: index on %s.%s" % (doctype, field), defer_insert=True)


# ── Keep Deleted ─────────────────────────────────────────
def _holds():
    """The deletions holding their days. Read once for a job or a request: auto attendance asks for every punch."""
    holds = getattr(frappe.local, "ha_attendance_holds", None)
    if holds is None:
        holds = []
        if frappe.db.table_exists(DOCTYPE):
            holds = frappe.get_all(DOCTYPE, filters={"keep_deleted": 1, "status": ["!=", rules.DRAFT]},
                                   fields=["company", "from_date", "to_date", "department", "employee"], limit_page_length=0)
        frappe.local.ha_attendance_holds = holds
    return holds


def held(employee, day):
    """Whether a deletion said this person's day stays deleted."""
    holds = _holds()
    if not holds:
        return False
    company, department = frappe.get_cached_value("Employee", employee, ["company", "department"])
    return rules.is_held(holds, employee, company, department, day)


class ShiftTypeKeepDeleted:
    def get_employee_checkins(self):
        return [log for log in super().get_employee_checkins()
                if not held(log.get("employee"), log.get("shift_start") or log.get("time"))]

    def get_dates_for_attendance(self, employee):
        return [day for day in super().get_dates_for_attendance(employee) if not held(employee, day)]

    def unlinked_checkins_exist(self):
        """Frappe HR refuses to change a shift's start time while punches wait to be marked: one on a day held waits for
        nothing."""
        if not super().unlinked_checkins_exist():
            return False
        if not _holds():
            return True
        logs = frappe.get_all(CHECKIN, filters={"shift": self.name, "attendance": ["is", "not set"], "skip_auto_attendance": 0,
                                                "offshift": 0}, fields=["employee", "shift_start", "time"], limit_page_length=0)
        return any(not held(log.employee, log.shift_start or log.time) for log in logs)
