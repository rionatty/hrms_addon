"""Checks Attendance Deletion, without a bench, on a real SQL database (SQLite):

    python scripts/verify_attendance_deletion.py

Luuka, 2 Nov 2026: "deleting attendace has been a problem how can we delete large
volumne of data without compormissing the system perfomance".

  1  the rules: what stays and why, the pause, the files' rows
  2  the count, and what a deletion chooses
  3  the job: what goes, what stays, what goes with it, and the two files
  4  the file goes back in through Upload Attendance's own reader
  5  killed at any statement, or failing at any statement, and started again, it
     ends exactly as a run that was never stopped: the same records, the same files
  6  starting, stopping and going on; only HR; one at a time
  7  Keep Deleted: auto attendance leaves the days alone, and may fill them again
  8  the slices: the same number of reads a slice, however many people
  9  wiring: the doctype, the Shift Type mixin, the menus, the list's big selections
 10  upstream: what it mirrors in Frappe and Frappe HR
"""
import datetime
import glob
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []
D = datetime.date


def check(condition, label, detail=""):
    if not condition:
        fail.append(label)
        print("FAIL", label, detail)


def load_from(name, folder=APP):
    spec = importlib.util.spec_from_file_location(name, os.path.join(folder, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load_from("attendance_deletion_rules")  # proves it has no Frappe import
U = load_from("attendance_upload_rules")
print("loaded attendance_deletion_rules.py without Frappe")

# ── 1. The rules ─────────────────────────────────────────
PLAIN = {"name": "A", "employee": "E1"}
check(R.why_kept(PLAIN, set(), {}, set()) is None, "a plain record goes")
check(R.why_kept(PLAIN, {"E1"}, {}, set()) == R.ON_SLIP, "their submitted slip covers the day")
check(R.why_kept(dict(PLAIN, leave_application="LV"), set(), {}, set()) == R.FROM_REQUEST, "a leave application made it")
check(R.why_kept(dict(PLAIN, attendance_request="AR"), set(), {}, set()) == R.FROM_REQUEST, "an attendance request made it")
check(R.why_kept(PLAIN, set(), {"A": "Overtime Slip"}, set()) == "Used by Overtime Slip", "another document uses it")
check(R.why_kept(PLAIN, set(), {}, {"A"}) == R.ATTACHED, "a file is attached")
check(R.why_kept(dict(PLAIN, leave_application="LV"), {"E1"}, {"A": "X"}, {"A"}) == R.ON_SLIP, "a paid day says so first")
for reason, field in ((None, R.TO_DELETE), (R.ON_SLIP, R.KEPT_ON_SLIPS), (R.FROM_REQUEST, R.KEPT_FROM_REQUESTS),
                      ("Used by X", R.KEPT_IN_USE), (R.ATTACHED, R.KEPT_IN_USE)):
    check(R.counted_as(reason) == field, "%s is counted in %s" % (reason, field))
check(R.pause_after(0) == R.SHORTEST_PAUSE and R.pause_after(None) == R.SHORTEST_PAUSE, "it always rests")
check(R.pause_after(1) == 0.5, "half as long again as the slice took, so a busy database is given room")
check(R.pause_after(100) == R.LONGEST_PAUSE, "up to a limit")
check(list(R.days_between("2026-08-30", "2026-09-02")) == [D(2026, 8, 30), D(2026, 8, 31), D(2026, 9, 1), D(2026, 9, 2)], "each day")
check(list(R.days_between("2026-08-30", "2026-09-02", D(2026, 9, 1))) == [D(2026, 9, 1), D(2026, 9, 2)], "from where it got to")
check(list(R.days_between("2026-09-02", "2026-08-30")) == [], "no days in a period that runs backwards")
check(R.period_problem("2026-09-02", "2026-09-01") and not R.period_problem("2026-09-01", "2026-09-01") and not R.period_problem(None, None),
      "the To Date before the From Date is said")
check(R.BACKUP_HEADERS[:8] == U.HEADERS, "the file opens with Upload Attendance's own columns")
check(len(R.BACKUP_HEADERS) == len(R.backup_row({"docstatus": 1})), "a value for every heading")
check(len(R.KEPT_HEADERS) == len(R.kept_row({}, "why")), "and for every heading of the second file")
check(R.csv_bytes([["a"]], first=True).startswith(b"\xef\xbb\xbf") and not R.csv_bytes([["a"]]).startswith(b"\xef\xbb\xbf"),
      "only the file's first bytes carry the mark for Excel")
check(R.csv_bytes([["a,b", 'c"d']]).decode().strip() == '"a,b","c""d"', "commas and quotes are safe in a cell")


# ── A site, on SQLite ────────────────────────────────────
sqlite3.register_adapter(D, lambda day: day.isoformat())
sqlite3.register_adapter(datetime.datetime, lambda when: when.isoformat(" "))
sqlite3.register_converter("DATE", lambda raw: D.fromisoformat(raw.decode()))


class Row(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


class Killed(BaseException):
    """A worker killed: nothing catches this, and nothing is rolled back but by the database."""


class Failure(Exception):
    pass


ATTENDANCE_COLUMNS = "name TEXT PRIMARY KEY, docstatus INT DEFAULT 1, employee TEXT, employee_name TEXT, company TEXT, department TEXT, " \
                     "attendance_date DATE, status TEXT, leave_type TEXT, leave_application TEXT, attendance_request TEXT, shift TEXT, " \
                     "in_time TEXT, out_time TEXT, working_hours REAL, late_entry INT, early_exit INT, half_day_status TEXT, " \
                     "overtime_type TEXT, amended_from TEXT"
TABLES = {
    "tabAttendance": ATTENDANCE_COLUMNS,
    "tabEmployee Checkin": "name TEXT PRIMARY KEY, employee TEXT, attendance TEXT, shift TEXT, shift_start TEXT, time TEXT, skip_auto_attendance INT DEFAULT 0, offshift INT DEFAULT 0",
    "tabSalary Slip": "name TEXT PRIMARY KEY, docstatus INT, employee TEXT, company TEXT, department TEXT, start_date DATE, end_date DATE",
    "tabWeekly Pay Day": "name TEXT PRIMARY KEY, docstatus INT, parent TEXT, employee TEXT, attendance_date DATE, hours REAL",
    "tabOvertime Details": "name TEXT PRIMARY KEY, parent TEXT, parenttype TEXT, reference_document TEXT, docstatus INT",
    "tabLate Arrival Notice": "name TEXT PRIMARY KEY, attendance TEXT, docstatus INT",
    "tabFile": "name TEXT PRIMARY KEY, file_url TEXT, file_size INT, attached_to_doctype TEXT, attached_to_name TEXT, attached_to_field TEXT, is_private INT, file_name TEXT",
    "tabToDo": "name TEXT PRIMARY KEY, reference_type TEXT, reference_name TEXT",
    "tabEmail Unsubscribe": "name TEXT PRIMARY KEY, reference_doctype TEXT, reference_name TEXT",
    "tabDocShare": "name TEXT PRIMARY KEY, share_doctype TEXT, share_name TEXT",
    "tabVersion": "name TEXT PRIMARY KEY, ref_doctype TEXT, docname TEXT",
    "tabComment": "name TEXT PRIMARY KEY, reference_doctype TEXT, reference_name TEXT, docstatus INT DEFAULT 0",
    "tabView Log": "name TEXT PRIMARY KEY, reference_doctype TEXT, reference_name TEXT",
    "tabDocument Follow": "name TEXT PRIMARY KEY, ref_doctype TEXT, ref_docname TEXT",
    "tabNotification Log": "name TEXT PRIMARY KEY, document_type TEXT, document_name TEXT",
    "tabCommunication Link": "name TEXT PRIMARY KEY, link_doctype TEXT, link_name TEXT",
    "tabTag Link": "name TEXT PRIMARY KEY, document_type TEXT, document_name TEXT",
    "__global_search": "doctype TEXT, name TEXT",
    "tabCommunication": "name TEXT PRIMARY KEY, reference_doctype TEXT, reference_name TEXT",
    "tabActivity Log": "name TEXT PRIMARY KEY, reference_doctype TEXT, reference_name TEXT, timeline_doctype TEXT, timeline_name TEXT",
    "tabGeneric Reference": "name TEXT PRIMARY KEY, ref_type TEXT, ref_name TEXT, docstatus INT",
    "tabAttendance Deletion": "name TEXT PRIMARY KEY, company TEXT, department TEXT, employee TEXT, attendance_status TEXT, from_date DATE, to_date DATE, "
                              "keep_deleted INT, to_delete INT, draft_slips INT, kept_on_slips INT, kept_from_requests INT, kept_in_use INT, "
                              "status TEXT, started_by TEXT, started_on TEXT, finished_on TEXT, deleted INT, kept INT, message TEXT, backup_file TEXT, "
                              "kept_file TEXT, cursor_date DATE, cursor_name TEXT, backup_size INT, kept_size INT, stop_requested INT, modified TEXT",
}


def table_of(doctype):
    return doctype if doctype.startswith("__") else "tab" + doctype


def where_of(filters):
    clauses, values = [], []
    for field, wanted in (filters or {}).items():
        column = "`%s`" % field
        if isinstance(wanted, (list, tuple)):
            operator, target = wanted
            if operator == "in":
                clauses.append("%s IN (%s)" % (column, ", ".join("?" * len(target))))
                values.extend(target)
            elif operator == "between":
                clauses.append("%s BETWEEN ? AND ?" % column)
                values.extend(target)
            elif operator == "is":
                clauses.append("(%s IS NULL OR %s = '')" % (column, column))
            else:
                clauses.append("%s %s ?" % (column, operator))
                values.append(target)
        else:
            clauses.append("%s = ?" % column)
            values.append(wanted)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", values


class Doc:
    """A saved Attendance Deletion, as far as the code reads it."""

    def __init__(self, site, name):
        self.site, self.name = site, name
        row = site.conn.execute('SELECT * FROM "tabAttendance Deletion" WHERE name = ?', (name,)).fetchone()
        if row is None:
            raise Failure("no such deletion")
        self.values = dict(row)

    def get(self, field):
        return self.values.get(field)

    def __getattr__(self, field):
        return self.values.get(field)

    def check_permission(self, ptype):
        self.site.calls.append(("check_permission", ptype))
        if not self.site.may_write:
            raise PermissionError("refused")

    def db_set(self, values, value=None, commit=False, notify=False, update_modified=True):
        if not isinstance(values, dict):
            values = {values: value}
        self.values.update(values)
        columns = ", ".join("`%s` = ?" % column for column in values)
        self.site.run('UPDATE "tabAttendance Deletion" SET %s, modified = ? WHERE name = ?' % columns,
                      [*values.values(), self.site.now.isoformat(" "), self.name])
        if commit:
            self.site.commit()

    def set_onload(self, key, value):
        self.values.setdefault("__onload", {})[key] = value


class Site:
    """Frappe, as far as attendance_deletions reads it, over a real database. The calls read and write real rows, so what
    they find and what a rollback undoes are what SQL does."""

    def __init__(self, folder=None):
        self.conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row
        for table, columns in TABLES.items():
            self.conn.execute('CREATE TABLE "%s" (%s)' % (table, columns))
        self.conn.commit()
        self.folder = folder or tempfile.mkdtemp(prefix="deletion-")
        os.makedirs(os.path.join(self.folder, "private"))
        os.makedirs(os.path.join(self.folder, "public"))
        self.calls, self.statements, self.queued, self.errors, self.pauses, self.commits = [], 0, [], [], [], 0
        self.now = datetime.datetime(2026, 11, 2, 9, 0, 0)
        self.fault_at, self.fault = None, None
        self.may_write, self.may_delete = True, True
        self.during_pause = None
        self.singles = {}
        self.dynamic = []
        self.hold_lookups = 0
        self.install()

    def run(self, sql, values=()):
        self.statements += 1
        if self.fault_at is not None and self.statements == self.fault_at:
            self.fault_at = None
            raise self.fault
        return self.conn.execute(sql, list(values))

    def commit(self):
        self.commits += 1
        self.conn.commit()

    def add(self, into, /, **values):
        columns = ", ".join("`%s`" % column for column in values)
        self.conn.execute('INSERT INTO "%s" (%s) VALUES (%s)' % (table_of(into), columns, ", ".join("?" * len(values))), list(values.values()))

    def rows(self, sql, *values):
        return [dict(row) for row in self.conn.execute(sql, values).fetchall()]

    def names(self, doctype="Attendance"):
        return [row[0] for row in self.conn.execute('SELECT name FROM "%s" ORDER BY name' % table_of(doctype))]

    def install(self):
        site = self
        module = types.ModuleType("frappe")
        module.__path__ = []
        module._ = lambda text, *args, **kwargs: text
        module.session = types.SimpleNamespace(user="hr@example.com")
        module.local = types.SimpleNamespace()
        module.PermissionError = PermissionError
        module.DoesNotExistError = LookupError

        def throw(message, exc=Failure, title=None):
            raise exc(message)

        def get_all(doctype, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, distinct=False, or_filters=None):
            where, values = where_of(filters)
            columns = [pluck] if pluck else list(fields or ["name"])
            select = ", ".join("`%s`" % column for column in columns)
            sql = 'SELECT %s%s FROM "%s"%s' % ("DISTINCT " if distinct else "", select, table_of(doctype), where)
            if order_by:
                sql += " ORDER BY " + order_by
            if limit_page_length:
                sql += " LIMIT %d" % limit_page_length
            found = site.run(sql, values).fetchall()
            return [row[0] for row in found] if pluck else [Row(dict(row)) for row in found]

        def get_doc(doctype, name=None):
            if isinstance(doctype, dict):
                return FileDoc(doctype)
            return Doc(site, name)

        class FileDoc:
            def __init__(self, values):
                self.values = values

            def insert(self, ignore_permissions=False):
                site.calls.append(("file", self.values["file_name"], ignore_permissions, self.values["is_private"]))
                values = {key: value for key, value in self.values.items() if key != "doctype"}
                values["name"] = values["file_name"]
                columns = ", ".join("`%s`" % column for column in values)
                site.run('INSERT INTO "tabFile" (%s) VALUES (%s)' % (columns, ", ".join("?" * len(values))), list(values.values()))
                return self

        def has_permission(doctype, ptype, throw=False):
            site.calls.append(("has_permission", doctype, ptype))
            if not site.may_delete and throw:
                raise PermissionError("refused")
            return site.may_delete

        def log_error(title=None, defer_insert=False):
            site.errors.append(title)

        def enqueue(method, **kwargs):
            site.queued.append((method, kwargs))

        class Meta:
            def __init__(self, doctype):
                self.istable = doctype == "Overtime Details"
                self.issingle = doctype in site.singles

        def get_cached_value(doctype, name, fields):
            return site.people.get(name, ("LPL", None))

        def set_value(doctype, filters, field, value=None, update_modified=True):
            values = field if isinstance(field, dict) else {field: value}
            where, wanted = where_of(filters)
            columns = ", ".join("`%s` = ?" % column for column in values)
            site.run('UPDATE "%s" SET %s%s' % (table_of(doctype), columns, where), [*values.values(), *wanted])

        def db_delete(doctype, filters):
            where, wanted = where_of(filters)
            site.run('DELETE FROM "%s"%s' % (table_of(doctype), where), wanted)

        def count(doctype, filters):
            where, wanted = where_of(filters)
            return site.run('SELECT COUNT(*) FROM "%s"%s' % (table_of(doctype), where), wanted).fetchone()[0]

        def get_value(doctype, name, field):
            row = site.run('SELECT `%s` FROM "%s" WHERE name = ?' % (field, table_of(doctype)), [name]).fetchone()
            return row[0] if row else None

        module.db = types.SimpleNamespace(
            commit=lambda: site.commit(), rollback=lambda: site.conn.rollback(), set_value=set_value, delete=db_delete, count=count,
            get_value=get_value, get_single_value=lambda doctype, field: site.singles.get(doctype, {}).get(field),
            get_singles_dict=lambda doctype: site.singles.get(doctype, {}), table_exists=lambda doctype: table_of(doctype) in TABLES,
            add_index=lambda doctype, fields: site.calls.append(("index", doctype, fields)))
        module.get_all, module.get_doc, module.throw, module.has_permission = get_all, get_doc, throw, has_permission
        module.log_error, module.enqueue, module.get_meta = log_error, enqueue, Meta
        module.get_cached_value = get_cached_value
        module.get_hooks = lambda name: ["Comment", "Version", "File", "ToDo"]
        module.whitelist = lambda *args, **kwargs: (lambda function: function)
        utils = types.ModuleType("frappe.utils")
        utils.cint = lambda value: int(float(value or 0))
        utils.getdate = lambda value=None: value if isinstance(value, D) else D.fromisoformat(str(value)[:10])
        utils.get_datetime = lambda value: value if isinstance(value, datetime.datetime) else datetime.datetime.fromisoformat(str(value))
        utils.now_datetime = lambda: site.now
        utils.add_to_date = lambda when, minutes=0: when + datetime.timedelta(minutes=minutes)
        utils.get_files_path = lambda *parts, is_private=0: os.path.join(site.folder, "private" if is_private else "public", *parts)
        model, rename_doc, dynamic_links = types.ModuleType("frappe.model"), types.ModuleType("frappe.model.rename_doc"), types.ModuleType("frappe.model.dynamic_links")
        model.__path__ = []
        rename_doc.get_link_fields = lambda doctype: [
            {"parent": "Attendance", "fieldname": "amended_from", "issingle": 0},
            {"parent": "Employee Checkin", "fieldname": "attendance", "issingle": 0},
            {"parent": "Overtime Details", "fieldname": "reference_document", "issingle": 0},
            {"parent": "Late Arrival Notice", "fieldname": "attendance", "issingle": 0},
            {"parent": "Gone Doctype", "fieldname": "attendance", "issingle": 0},
            {"parent": "Comment", "fieldname": "link_name", "issingle": 0},
            {"parent": "Some Settings", "fieldname": "attendance", "issingle": 1},
        ]
        dynamic_links.get_dynamic_link_map = lambda: {"Attendance": site.dynamic}
        package = types.ModuleType("hrms_addon")
        package.__path__ = []
        app = types.ModuleType("hrms_addon.hrms_addon")
        app.__path__ = []
        sys.modules.update({"frappe": module, "frappe.utils": utils, "frappe.model": model, "frappe.model.rename_doc": rename_doc,
                            "frappe.model.dynamic_links": dynamic_links, "hrms_addon": package, "hrms_addon.hrms_addon": app,
                            "hrms_addon.hrms_addon.attendance_deletion_rules": R})
        self.glue = load_from("attendance_deletions")
        self.frappe = module

        def sleep(seconds):
            site.pauses.append(seconds)
            if site.during_pause:
                site.during_pause()

        self.glue.time = types.SimpleNamespace(sleep=sleep, monotonic=lambda: 0.0)
        self.people = {}

    def deletion(self, name="HR-ATD-1", **choices):
        values = dict(name=name, company="LPL", from_date=D(2026, 8, 26), to_date=D(2026, 9, 25), keep_deleted=1, status="Draft",
                      deleted=0, kept=0, stop_requested=0, modified=self.now.isoformat(" "))
        values.update(choices)
        self.add("Attendance Deletion", **values)
        self.conn.commit()
        return Doc(self, name)


def populate(site, people=6, days=5, first=D(2026, 8, 30)):
    """people x days of attendance, each with what collects around a record."""
    for number in range(people):
        employee = "E%d" % number
        site.people[employee] = ("LPL", "PP" if number % 2 == 0 else "QA")
        for offset in range(days):
            day = first + datetime.timedelta(days=offset)
            name = "HR-ATT-%s-%02d" % (employee, offset)
            site.add("Attendance", name=name, employee=employee, employee_name="Name %d" % number, company="LPL",
                     department=site.people[employee][1], attendance_date=day, status="Present", shift="Day",
                     in_time="%s 08:00:00" % day, out_time="%s 17:00:00" % day, working_hours=9, late_entry=0, early_exit=0)
            site.add("Employee Checkin", name="CK-%s" % name, employee=employee, attendance=name, shift="Day",
                     shift_start="%s 08:00:00" % day, time="%s 08:01:00" % day)
            site.add("Version", name="V-%s" % name, ref_doctype="Attendance", docname=name)
            site.add("Comment", name="C-%s" % name, reference_doctype="Attendance", reference_name=name)
            site.add("Activity Log", name="AL-%s" % name, reference_doctype="Attendance", reference_name=name,
                     timeline_doctype="Attendance", timeline_name=name)
            site.add("__global_search", doctype="Attendance", name=name)
    site.conn.commit()


def snapshot(site):
    """All the job leaves behind: the rows that matter and the files' bytes."""
    tables = {table: [tuple(row) for row in site.conn.execute('SELECT * FROM "%s" ORDER BY 1, 2' % table)]
              for table in TABLES if table not in ("tabAttendance Deletion", "tabFile")}
    deletion = dict(site.conn.execute('SELECT status, deleted, kept, cursor_date, cursor_name, backup_size, kept_size FROM "tabAttendance Deletion"').fetchone())
    files = {}
    for path in sorted(glob.glob(os.path.join(site.folder, "*", "*.csv"))):
        with open(path, "rb") as handle:
            files[os.path.basename(path)] = handle.read()
    return tables, deletion, files


def complicated(site):
    """A site with each thing that keeps a record back."""
    populate(site)
    site.add("Salary Slip", name="SS-PAID", docstatus=1, employee="E0", company="LPL", department="PP", start_date=D(2026, 8, 26), end_date=D(2026, 9, 25))
    site.add("Salary Slip", name="SS-DRAFT", docstatus=0, employee="E1", company="LPL", department="QA", start_date=D(2026, 8, 26), end_date=D(2026, 9, 25))
    site.add("Salary Slip", name="SS-GONE", docstatus=2, employee="E2", company="LPL", department="PP", start_date=D(2026, 8, 26), end_date=D(2026, 9, 25))
    site.add("Salary Slip", name="SS-EARLIER", docstatus=1, employee="E3", company="LPL", department="QA", start_date=D(2026, 7, 26), end_date=D(2026, 8, 25))
    site.add("Salary Slip", name="SS-LATER", docstatus=1, employee="E4", company="LPL", department="PP", start_date=D(2026, 9, 26), end_date=D(2026, 10, 25))
    site.add("Salary Slip", name="SS-OTHER-CO", docstatus=0, employee="X", company="Other Co", start_date=D(2026, 8, 26), end_date=D(2026, 9, 25))
    site.add("Salary Slip", name="SS-OLD-DRAFT", docstatus=0, employee="E1", company="LPL", department="QA", start_date=D(2026, 6, 26), end_date=D(2026, 7, 25))
    site.add("Salary Slip", name="SS-NEXT-DRAFT", docstatus=0, employee="E1", company="LPL", department="QA", start_date=D(2026, 9, 26), end_date=D(2026, 10, 25))
    site.conn.execute("UPDATE tabAttendance SET leave_application = 'LV-1', status = 'On Leave' WHERE name = 'HR-ATT-E1-00'")
    site.conn.execute("UPDATE tabAttendance SET attendance_request = 'AR-1' WHERE name = 'HR-ATT-E1-01'")
    site.add("Overtime Details", name="OD-1", parent="OT-1", parenttype="Overtime Slip", reference_document="HR-ATT-E2-00", docstatus=1)
    site.add("Late Arrival Notice", name="LN-1", attendance="HR-ATT-E2-01", docstatus=2)
    site.add("File", name="F-1", file_url="/files/x.png", attached_to_doctype="Attendance", attached_to_name="HR-ATT-E2-02")
    site.add("File", name="F-2", file_url="/files/y.png", attached_to_doctype="Employee", attached_to_name="HR-ATT-E3-03")
    site.conn.execute("UPDATE tabAttendance SET docstatus = 2 WHERE name = 'HR-ATT-E3-00'")
    site.conn.execute("UPDATE tabAttendance SET docstatus = 0 WHERE name = 'HR-ATT-E3-01'")
    site.conn.execute("UPDATE tabAttendance SET amended_from = 'HR-ATT-E4-00' WHERE name = 'HR-ATT-E4-01'")
    site.conn.execute("UPDATE tabAttendance SET attendance_date = '2026-09-26' WHERE name = 'HR-ATT-E5-04'")
    site.add("Attendance", name="HR-ATT-OTHER", employee="X", company="Other Co", attendance_date=D(2026, 9, 1), status="Present")
    site.add("Attendance", name="HR-ATT-BEFORE", employee="E5", company="LPL", attendance_date=D(2026, 8, 25), status="Present")
    site.add("ToDo", name="T-1", reference_type="Attendance", reference_name="HR-ATT-E3-02")
    site.add("ToDo", name="T-2", reference_type="Employee", reference_name="HR-ATT-E3-02")
    site.add("Tag Link", name="TL-1", document_type="Attendance", document_name="HR-ATT-E3-02")
    site.add("Communication", name="CM-1", reference_doctype="Attendance", reference_name="HR-ATT-E3-02")
    site.conn.commit()


# ── 2. The count ─────────────────────────────────────────
site = Site()
complicated(site)
doc = site.deletion()
counted = site.glue.count(doc)
# 6 x 5 = 30, less E5's day moved out of the period; E0's 5 on a submitted slip, E1's 2 from requests, E2's 3 in use
check(counted == {"to_delete": 29 - 5 - 2 - 3, "kept_on_slips": 5, "kept_from_requests": 2, "kept_in_use": 3, "draft_slips": 1},
      "the count: what goes, what stays and why, and the draft slips left out of date", counted)
read_links = [call for call in site.calls if call[0] == "index"]
check(not read_links, "counting writes nothing", read_links)
check(site.names() == sorted(site.names()) and len(site.names()) == 32, "and leaves every record there", len(site.names()))
counted = site.glue.count(site.deletion("D-QA", department="QA"))
check(counted["kept_on_slips"] == 0 and counted["kept_from_requests"] == 2 and counted["to_delete"] == 3 + 5 + 4,
      "a department: E1's other 3, E3's 5 and E5's 4 in the period", counted)
counted = site.glue.count(site.deletion("D-EMP", employee="E2"))
check(counted["to_delete"] == 2 and counted["kept_in_use"] == 3 and counted["draft_slips"] == 0, "one employee", counted)
counted = site.glue.count(site.deletion("D-STATUS", attendance_status="On Leave"))
check(counted == {"to_delete": 0, "kept_on_slips": 0, "kept_from_requests": 1, "kept_in_use": 0, "draft_slips": 1}, "one status", counted)
counted = site.glue.count(site.deletion("D-DAY", from_date=D(2026, 8, 30), to_date=D(2026, 8, 30)))
check(sum(counted[field] for field in R.COUNTS) == 6, "one day", counted)
counted = site.glue.count(site.deletion("D-NONE", from_date=D(2020, 1, 1), to_date=D(2020, 1, 2)))
check(not any(counted.values()), "dates with nothing on them", counted)
counted = site.glue.count(site.deletion("D-OTHER", company="Other Co"))
check(counted["to_delete"] == 1, "another company's are its own", counted)
# a casual's day paid on a later week's slip: that slip's dates do not reach it, its list of days does
late = Site()
complicated(late)
late.add("Weekly Pay Day", name="WPD-1", docstatus=1, parent="SS-WEEK", employee="E5", attendance_date=D(2026, 8, 30), hours=10)
late.add("Weekly Pay Day", name="WPD-2", docstatus=2, parent="SS-WEEK-GONE", employee="E5", attendance_date=D(2026, 8, 31), hours=10)
late.add("Weekly Pay Day", name="WPD-3", docstatus=0, parent="SS-WEEK-DRAFT", employee="E5", attendance_date=D(2026, 9, 1), hours=10)
late.conn.commit()
counted = late.glue.count(late.deletion("D-LATE", employee="E5"))
check(counted["kept_on_slips"] == 1 and counted["to_delete"] == 3,
      "a day a weekly slip paid after its week is kept; one on a cancelled or a draft slip is not", counted)


def validated(doc, before=None, changed=()):
    doc.get_doc_before_save = lambda: before
    doc.has_value_changed = lambda field: field in changed
    doc.is_new = lambda: before is None
    doc.set = lambda field, value: doc.values.__setitem__(field, value)
    doc.update = lambda values: doc.values.update(values)
    site.glue.deletion_validate(doc)
    return doc


site = Site()
populate(site)
doc = site.deletion()
doc.values.update(deleted=999, status="Finished", to_delete=1, backup_file="/evil", stop_requested=1, cursor_name="Z")
validated(doc)
check((doc.status, doc.deleted, doc.backup_file, doc.stop_requested, doc.cursor_name) == ("Draft", None, None, None, None) and doc.to_delete == 30,
      "what only the job writes cannot be sent in, and a new deletion is counted as it is saved", doc.values)
started = site.deletion("D-2", status="Finished", deleted=5, to_delete=5)
kept_doc = Doc(site, "D-2")
kept_doc.values.update(deleted=999, status="Draft")
validated(kept_doc, before=started)
check((kept_doc.status, kept_doc.deleted) == ("Finished", 5), "nor changed afterwards", kept_doc.values)
try:
    validated(Doc(site, "D-2"), before=started, changed=("to_date",))
    check(False, "what was chosen is fixed once it has started")
except Failure:
    pass
try:
    doc = Doc(site, "HR-ATD-1")
    doc.values["to_date"] = D(2026, 8, 1)
    validated(doc)
    check(False, "the To Date before the From Date is refused")
except Failure:
    pass
try:
    site.glue.deletion_on_trash(Doc(site, "D-2"))
    check(False, "the record of one that started stays")
except Failure:
    pass
site.glue.deletion_on_trash(Doc(site, "HR-ATD-1"))


# ── 3. The job ───────────────────────────────────────────
def run_clean(setup=complicated):
    site = Site()
    setup(site)
    doc = site.deletion(status="Queued", started_by="hr@example.com")
    site.glue.delete_all(doc.name)
    return site


site = run_clean()
kept_names = {"HR-ATT-E0-%02d" % n for n in range(5)} | {"HR-ATT-E1-00", "HR-ATT-E1-01", "HR-ATT-E2-00", "HR-ATT-E2-01", "HR-ATT-E2-02",
                                                         "HR-ATT-E5-04", "HR-ATT-OTHER", "HR-ATT-BEFORE"}
check(set(site.names()) == kept_names, "what goes and what stays, by record", sorted(set(site.names()) ^ kept_names))
deletion = Doc(site, "HR-ATD-1")
check((deletion.status, deletion.deleted, deletion.kept) == ("Finished", 19, 10), "the counts it ends on", deletion.values)
check(deletion.finished_on and not deletion.message and not deletion.stop_requested, "finished, and when", deletion.values)
check(not site.errors, "with nothing logged", site.errors)
gone = "HR-ATT-E3-02"
punches = dict(site.rows('SELECT name, attendance FROM "tabEmployee Checkin"') and [(row["name"], row["attendance"]) for row in site.rows('SELECT name, attendance FROM "tabEmployee Checkin"')])
check(punches["CK-HR-ATT-E3-02"] == "" and punches["CK-HR-ATT-E0-00"] == "HR-ATT-E0-00" and punches["CK-HR-ATT-E5-04"] == "HR-ATT-E5-04",
      "a punch lets go of what was deleted, as cancelling does, and keeps what stays", punches)
check(site.rows("SELECT skip_auto_attendance FROM \"tabEmployee Checkin\" WHERE name = 'CK-HR-ATT-E3-02'")[0]["skip_auto_attendance"] == 0,
      "and is left to be marked if the days are ever let go of")
for doctype, of in (("Version", "docname"), ("Comment", "reference_name"), ("ToDo", "reference_name")):
    left = site.rows('SELECT COUNT(*) AS n FROM "tab%s" WHERE "%s" = ? AND name != ?' % (doctype, of), gone, "T-2")[0]["n"]
    check(left == 0, "%s of a deleted record goes with it" % doctype)
check(site.rows("SELECT COUNT(*) AS n FROM \"tabVersion\" WHERE docname = 'HR-ATT-E0-00'")[0]["n"] == 1, "and of a record that stays, stays")
check([row["name"] for row in site.rows('SELECT name FROM "tabToDo"')] == ["T-2"], "and of anything else of the same name, stays")
check(not site.rows("SELECT * FROM \"tabTag Link\"") and not site.rows("SELECT * FROM __global_search WHERE name = ?", gone), "tags and global search too")
check(site.rows("SELECT reference_doctype, reference_name FROM tabCommunication") == [{"reference_doctype": None, "reference_name": None}],
      "a communication is let go of, not deleted")
activity = site.rows("SELECT reference_name, timeline_name FROM \"tabActivity Log\" WHERE name = ?", "AL-" + gone)[0]
check(activity == {"reference_name": None, "timeline_name": None}, "so is the activity log", activity)
check(site.rows("SELECT amended_from FROM tabAttendance WHERE name = 'HR-ATT-E5-04'")[0]["amended_from"] is None, "nothing stays pointing at what went")
# a record that stays, amended from one that goes
site2 = Site()
populate(site2)
site2.conn.execute("UPDATE tabAttendance SET amended_from = 'HR-ATT-E4-00', leave_application = 'LV' WHERE name = 'HR-ATT-E4-01'")
site2.conn.execute("UPDATE tabAttendance SET attendance_date = (SELECT attendance_date FROM tabAttendance WHERE name = 'HR-ATT-E4-00') WHERE name = 'HR-ATT-E4-01'")
site2.conn.commit()
doc2 = site2.deletion(status="Queued")
site2.glue.delete_all(doc2.name)
check(site2.names() == ["HR-ATT-E4-01"], "the amended record stays for its leave application", site2.names())
check(site2.rows("SELECT amended_from FROM tabAttendance")[0]["amended_from"] is None, "and lets go of the record it was amended from, which went")
amended_both = Site()
populate(amended_both, people=1, days=2)
amended_both.conn.execute("UPDATE tabAttendance SET docstatus = 2 WHERE name = 'HR-ATT-E0-00'")
amended_both.conn.execute("UPDATE tabAttendance SET amended_from = 'HR-ATT-E0-00', attendance_date = '2026-08-30' WHERE name = 'HR-ATT-E0-01'")
amended_both.conn.commit()
amended_both.glue.delete_all(amended_both.deletion(status="Queued").name)
check(amended_both.names() == [], "a cancelled record and its amended copy both go: the copy holds nothing back", amended_both.names())

site = run_clean()
pattern = os.path.join(site.folder, "private", "HR-ATD-1 %s.csv")
with open(pattern % "deleted attendance", "rb") as handle:
    backup = handle.read()
with open(pattern % "attendance kept", "rb") as handle:
    kept_file = handle.read()
deletion = Doc(site, "HR-ATD-1")
check(backup.startswith(b"\xef\xbb\xbfEmployee,Employee Name,") and backup.count(b"\xef\xbb\xbf") == 1, "the file opens with its heading, once")
lines = backup.decode("utf-8-sig").splitlines()
check(len(lines) == 20, "a line for each record deleted", len(lines))
check(any(line.startswith("E3,Name 3,QA,2026-08-30,,,,,Present,Cancelled,") and line.endswith(",HR-ATT-E3-00") for line in lines),
      "a cancelled record has no Status, so it cannot go back in, and says what it was", lines[:3])
check(any(line.startswith("E3,Name 3,QA,2026-08-31,,,,,Present,Draft,") for line in lines), "nor a draft")
check(any(line.startswith("E4,Name 4,PP,2026-08-30,Present,,Day,,Present,Submitted,2026-08-30 08:00:00,2026-08-30 17:00:00,9") for line in lines),
      "a submitted one has all of it", lines[-1])
kept_lines = kept_file.decode("utf-8-sig").splitlines()
check(kept_lines[0] == ",".join(R.KEPT_HEADERS) and len(kept_lines) == 11, "the second file: a line for each record kept in the period", len(kept_lines))
for needle in ("On a submitted salary slip,HR-ATT-E0-00", "From a leave application or attendance request,HR-ATT-E1-00",
               "From a leave application or attendance request,HR-ATT-E1-01", "Used by Overtime Slip,HR-ATT-E2-00", "Used by Late Arrival Notice,HR-ATT-E2-01",
               "Has an attachment,HR-ATT-E2-02"):
    check(any(line.endswith(needle) for line in kept_lines), "the second file says why: %s" % needle, kept_lines)
check(deletion.backup_size == len(backup) and deletion.kept_size == len(kept_file), "what is saved is how far the files have got")
files = site.rows('SELECT name, file_url, file_size, attached_to_doctype, attached_to_name, attached_to_field, is_private FROM "tabFile" WHERE attached_to_doctype = ?', "Attendance Deletion")
check(len(files) == 2 and all(row["is_private"] == 1 and row["attached_to_name"] == "HR-ATD-1" for row in files), "both attached to the deletion, private", files)
check({row["attached_to_field"] for row in files} == {"backup_file", "kept_file"} and deletion.backup_file == "/private/files/HR-ATD-1 deleted attendance.csv", "in its fields", files)
check({row["file_url"]: row["file_size"] for row in files}[deletion.backup_file] == len(backup), "at their full size", files)
check(site.pauses and all(pause >= R.SHORTEST_PAUSE for pause in site.pauses), "it rests between slices", site.pauses)
check(site.commits >= len(site.pauses), "saving each one: no transaction is held across slices", (site.commits, len(site.pauses)))
check(not site.queued, "and queues nothing for each record", site.queued)
check(len(site.pauses) >= 5 and deletion.deleted == 19, "a slice is the rest of a day, with a save and a rest after it", site.pauses)
idle = Site()
populate(idle, people=1, days=1)
idle.glue.delete_all(idle.deletion(status="Finished").name)
check(len(idle.names()) == 1, "a job for a deletion not queued does nothing", idle.names())


# ── 4. Back through Upload Attendance ────────────────────
header = U.header_of(backup, "x.csv")
check(tuple(header)[:8] == U.HEADERS, "Upload Attendance reads the file's heading", header)
back = list(U.days_in(backup, "x.csv"))
check(len(back) == 17 and {row["status"] for row in back} == {"Present"}, "and only the submitted days: 19 less a draft and a cancelled", len(back))
check(back[0]["employee"].startswith("E") and U.parse_date(back[0]["attendance_date"]) == D(2026, 8, 30) and back[0]["shift"] == "Day", "with their employee, date and shift", back[0])
check(all(U.parse_date(row["attendance_date"]) for row in back), "every date reads")


# ── 5. Killed at any statement ───────────────────────────
small = lambda site: (complicated(site))
clean = run_clean(small)
clean_state = snapshot(clean)
statements = clean.statements
R.SLICE, slice_was = 2, R.SLICE
clean = run_clean(small)
clean_state = snapshot(clean)
statements = clean.statements
check(statements > 300, "a run of small slices, so there is plenty to interrupt", statements)
killed_differently, failed_differently = [], []
# all of them takes minutes: ATTENDANCE_DELETION_EVERY_STATEMENT=1 asks for it
step = 1 if os.environ.get("ATTENDANCE_DELETION_EVERY_STATEMENT") else int(os.environ.get("ATTENDANCE_DELETION_STEP") or 13)
for at in range(1, statements + 1, step):
    for fault, differently in ((Killed("worker gone"), killed_differently), (Failure("deadlock"), failed_differently)):
        site = Site()
        complicated(site)
        doc = site.deletion(status="Queued", started_by="hr@example.com")
        started_at = site.statements
        site.fault_at, site.fault = started_at + at, fault
        try:
            site.glue.delete_all(doc.name)
        except Killed:
            site.conn.rollback()  # what the database does when a connection dies
        site.fault_at = None
        status = Doc(site, doc.name).status
        if isinstance(fault, Failure) and site.fault_at is None and status not in ("Failed", "Finished", "Deleting"):
            differently.append((at, "status", status))
        # started again, as the Resume button does
        site.now += datetime.timedelta(hours=1)
        site.queued.clear()
        if Doc(site, doc.name).status != "Finished":
            site.glue.start(doc.name)
            if not site.queued:
                differently.append((at, "not queued"))
            site.glue.delete_all(doc.name)
        tables, deletion, files = snapshot(site)
        if (tables, deletion, files) != clean_state:
            differently.append((at, "differs", deletion))
        shutil.rmtree(site.folder, ignore_errors=True)
check(not killed_differently, "killed at a statement (1 in %d of %d here) and started again, it ends exactly as if never stopped: same records, same files" % (step, statements), killed_differently[:3])
check(not failed_differently, "and failing at any of them too", failed_differently[:3])
site = Site()
complicated(site)
doc = site.deletion(status="Queued")
site.fault_at, site.fault = site.statements + 120, Failure("deadlock on a row")
site.glue.delete_all(doc.name)
failed = Doc(site, doc.name)
check(failed.status == "Failed" and "deadlock on a row" in failed.message and site.errors == ["Attendance Deletion HR-ATD-1 stopped"],
      "a failure says so on the deletion, and in the Error Log", failed.values)
check(0 < failed.deleted < 19, "with what it had done still saved", failed.deleted)
R.SLICE = slice_was


# ── 6. Starting, stopping, going on ──────────────────────
site = Site()
populate(site)
site.deletion(to_delete=30)
try:
    site.glue.start("HR-ATD-1", confirmed=29)
    check(False, "the wrong count typed starts nothing")
except Failure as error:
    check("30" in str(error) and not site.queued, "the wrong count typed starts nothing, and says what it is", error)
try:
    site.glue.start("HR-ATD-1")
    check(False, "no count typed starts nothing")
except Failure:
    pass
check(Doc(site, "HR-ATD-1").status == "Draft", "and it stays as it was")
answer = site.glue.start("HR-ATD-1", confirmed="30")
doc = Doc(site, "HR-ATD-1")
check(answer == {"status": "Queued"} and doc.status == "Queued" and doc.started_by == "hr@example.com" and doc.started_on, "the right count starts it", doc.values)
method, options = site.queued[0]
check(method == "hrms_addon.hrms_addon.attendance_deletions.delete_all" and options["queue"] == "long" and options["deduplicate"] is True
      and options["job_id"] == "attendance_deletion" and options["deletion"] == "HR-ATD-1" and options["enqueue_after_commit"] is True,
      "one job, on the long queue, one at a time across the site", site.queued)
check(options["timeout"] >= 3600 * 6, "with time enough for a year of attendance", options)
try:
    site.glue.start("HR-ATD-1")
    check(False, "a deletion running is not started again")
except Failure:
    pass
site.deletion("HR-ATD-2", to_delete=30)
try:
    site.glue.start("HR-ATD-2", confirmed=30)
    check(False, "one at a time")
except Failure as error:
    check("HR-ATD-1" in str(error) and len(site.queued) == 1, "one at a time, and it says which is running", error)
site.conn.execute("UPDATE tabAttendance SET company = 'None' WHERE 1 = 1")
site.conn.commit()
site.now += datetime.timedelta(minutes=R.STOPPED_AFTER + 1)
site.glue.deletion_onload(doc := Doc(site, "HR-ATD-1"))
check(doc.values["__onload"]["stopped"] is True, "one that has not moved for %d minutes has lost its job, and the form can say so" % R.STOPPED_AFTER)
check(not site.glue.running(Doc(site, "HR-ATD-1")), "and is not counted as running")
site.deletion("HR-ATD-3", to_delete=0)
try:
    site.glue.start("HR-ATD-3", confirmed=0)
    check(False, "nothing to delete starts nothing")
except Failure as error:
    check("nothing" in str(error), "nothing to delete starts nothing", error)
site = Site()
populate(site)
doc = site.deletion(status="Finished", deleted=5)
try:
    site.glue.start(doc.name)
    check(False, "a finished one is not started again")
except Failure:
    pass

site = Site()
populate(site, people=30, days=5)
R.SLICE, slice_was = 20, R.SLICE
doc = site.deletion(status="Queued")
pauses = []


def stop_once():
    pauses.append(1)
    if len(pauses) == 2:
        site.glue.stop(doc.name)
        site.conn.commit()


site.during_pause = stop_once
site.glue.delete_all(doc.name)
stopped = Doc(site, doc.name)
check(stopped.status == "Stopped" and stopped.deleted == 50 and not stopped.stop_requested and len(site.names()) == 100, "Stop: at the end of the next slice, its work saved", stopped.values)
file_size = site.rows("SELECT file_size FROM tabFile WHERE file_url = ?", stopped.backup_file)[0]["file_size"]
check(file_size == stopped.backup_size and file_size > 100, "the file's size up to date, for it to be downloaded", file_size)
site.during_pause = None
site.glue.start(doc.name)
check(Doc(site, doc.name).status == "Queued" and len(site.queued) == 1, "Resume queues it without asking for the count again", site.queued)
site.glue.delete_all(doc.name)
done = Doc(site, doc.name)
check((done.status, done.deleted, site.names()) == ("Finished", 150, []), "and it finishes the rest", done.values)
with open(os.path.join(site.folder, "private", "HR-ATD-1 deleted attendance.csv"), encoding="utf-8-sig") as handle:
    check(len(handle.read().splitlines()) == 151, "with one line for each, across the stop")
check(not os.listdir(os.path.join(site.folder, "public")), "and nothing of it where the website serves files")
vanished = Site()
populate(vanished, people=2, days=2)
outer_slice, R.SLICE = R.SLICE, 1
doc = vanished.deletion(status="Queued")
vanished.during_pause = lambda: vanished.conn.execute("UPDATE \"tabAttendance Deletion\" SET stop_requested = 1") and vanished.conn.commit()
vanished.glue.delete_all(doc.name)
os.remove(os.path.join(vanished.folder, "private", "HR-ATD-1 deleted attendance.csv"))
vanished.during_pause = None
vanished.glue.start(doc.name)
vanished.glue.delete_all(doc.name)
gone_file = vanished.rows("SELECT COUNT(*) AS n FROM tabFile WHERE attached_to_field = 'backup_file'")[0]["n"]
check(Doc(vanished, doc.name).status == "Finished" and gone_file == 1, "the file gone from the disk: it starts a new one, under the record it had", Doc(vanished, doc.name).values)
R.SLICE = outer_slice
check(len(site.pauses) >= 150 / 20, "no slice is more than its size", len(site.pauses))
R.SLICE = slice_was
scrambled = Site()
R.SLICE, slice_was = 2, R.SLICE
for number in range(9, 0, -1):
    scrambled.add("Attendance", name="HR-ATT-%d" % number, employee="E%d" % (number % 3), company="LPL", attendance_date=D(2026, 9, 1), status="Present", docstatus=1)
scrambled.conn.execute("UPDATE tabAttendance SET leave_application = 'LV' WHERE name = 'HR-ATT-3'")
scrambled.conn.commit()
scrambled.glue.delete_all(scrambled.deletion(status="Queued").name)
check(scrambled.names() == ["HR-ATT-3"] and Doc(scrambled, "HR-ATD-1").deleted == 8, "records in no order all come up, a kept one stepped over", scrambled.names())
R.SLICE = slice_was
site = Site()
populate(site)
doc = site.deletion(status="Deleting")
site.now += datetime.timedelta(minutes=R.STOPPED_AFTER + 1)
check(site.glue.stop(doc.name) == {"status": "Stopped"} and Doc(site, doc.name).status == "Stopped", "Stop on one that lost its job: nothing to wait for")
check(site.glue.stop(site.deletion("D-OVER", status="Finished").name) == {"status": "Finished"}, "Stop on a finished one changes nothing")

site = Site()
populate(site)
site.may_write = False
site.deletion(to_delete=30)
for method, args in ((site.glue.start, {"confirmed": 30}), (site.glue.stop, {}), (site.glue.check, {}), (site.glue.release, {})):
    try:
        method("HR-ATD-1", **args)
        check(False, "%s needs write on the deletion" % method.__name__)
    except PermissionError:
        pass
site = Site()
populate(site)
site.may_delete = False
site.deletion(to_delete=30)
for method, args in ((site.glue.start, {"confirmed": 30}), (site.glue.stop, {}), (site.glue.check, {}), (site.glue.release, {})):
    try:
        method("HR-ATD-1", **args)
        check(False, "%s needs delete on Attendance" % method.__name__)
    except PermissionError:
        pass
check(not site.queued, "and nothing is queued for those refused")
refused = Site()
refused.deletion()
refused.may_write = False
try:
    refused.glue.progress("HR-ATD-1")
    check(False, "how far it has got is for whoever may read the deletion")
except PermissionError:
    pass
lost = Site()
populate(lost)
lost.deletion(status="Deleting", stop_requested=1, modified="2026-11-01 09:00:00")
lost.glue.start("HR-ATD-1")
check(Doc(lost, "HR-ATD-1").stop_requested == 0 and len(lost.queued) == 1, "a stop asked of a job that died is not left to stop the next one", Doc(lost, "HR-ATD-1").values)
site = Site()
populate(site)
site.deletion(to_delete=1)
check(site.glue.check("HR-ATD-1")["to_delete"] == 30 and Doc(site, "HR-ATD-1").to_delete == 30, "Check: the count as it now stands, saved")
check(site.glue.progress("HR-ATD-1") == {"status": "Draft", "deleted": 0, "kept": 0}, "Progress: for whoever may read it")
site.conn.execute("UPDATE \"tabAttendance Deletion\" SET status = 'Finished'")
site.conn.commit()
try:
    site.glue.check("HR-ATD-1")
    check(False, "Check on one that has started changes nothing")
except Failure:
    pass


# ── 7. Keep Deleted ──────────────────────────────────────
HOLD = {"company": "LPL", "from_date": D(2026, 9, 1), "to_date": D(2026, 9, 30), "department": None, "employee": None}
check(R.is_held([HOLD], "E1", "LPL", "PP", D(2026, 9, 1)) and R.is_held([HOLD], "E1", "LPL", "PP", "2026-09-30"), "its first and last days")
check(not R.is_held([HOLD], "E1", "LPL", "PP", D(2026, 8, 31)) and not R.is_held([HOLD], "E1", "LPL", "PP", D(2026, 10, 1)), "not the days around them")
check(not R.is_held([HOLD], "E1", "Other", "PP", D(2026, 9, 5)), "not another company")
check(R.is_held([dict(HOLD, department="PP")], "E1", "LPL", "PP", D(2026, 9, 5)) and not R.is_held([dict(HOLD, department="PP")], "E1", "LPL", "QA", D(2026, 9, 5)), "its department alone")
check(R.is_held([dict(HOLD, employee="E1")], "E1", "LPL", "PP", D(2026, 9, 5)) and not R.is_held([dict(HOLD, employee="E1")], "E2", "LPL", "PP", D(2026, 9, 5)), "its employee alone")
check(not R.is_held([], "E1", "LPL", "PP", D(2026, 9, 5)) and R.is_held([dict(HOLD, company="No"), HOLD], "E1", "LPL", "PP", D(2026, 9, 5)), "any of them")


class Base:
    name = "Day"

    def get_employee_checkins(self):
        return [Row(employee="E1", shift_start=datetime.datetime(2026, 9, 5, 8), time=datetime.datetime(2026, 9, 5, 8, 1)),
                Row(employee="E1", shift_start=None, time=datetime.datetime(2026, 8, 5, 8, 1)),
                Row(employee="E1", shift_start=datetime.datetime(2026, 8, 31, 20), time=datetime.datetime(2026, 9, 1, 6, 0)),
                Row(employee="E2", shift_start=datetime.datetime(2026, 9, 5, 8), time=datetime.datetime(2026, 9, 5, 8, 1))]

    def get_dates_for_attendance(self, employee):
        return [D(2026, 8, 31), D(2026, 9, 1), D(2026, 10, 1)]

    def unlinked_checkins_exist(self):
        return True


site = Site()
site.people = {"E1": ("LPL", "PP"), "E2": ("LPL", "QA")}
site.deletion(status="Finished", from_date=D(2026, 9, 1), to_date=D(2026, 9, 30), department="PP")
site.deletion("D-OFF", status="Finished", from_date=D(2026, 8, 1), to_date=D(2026, 8, 31), keep_deleted=0)
site.deletion("D-DRAFT", status="Draft", from_date=D(2026, 8, 1), to_date=D(2026, 8, 31), keep_deleted=1)
Mixed = type("Mixed", (site.glue.ShiftTypeKeepDeleted, Base), {})
logs = Mixed().get_employee_checkins()
check([(log.employee, str((log.shift_start or log.time).date())) for log in logs] == [("E1", "2026-08-05"), ("E1", "2026-08-31"), ("E2", "2026-09-05")],
      "a punch on a held day is not marked; one on another day, or of someone else, is. A night shift's morning punch belongs to the day it began. "
      "A draft holds nothing, nor one let go of", logs)
check(Mixed().get_dates_for_attendance("E1") == [D(2026, 8, 31), D(2026, 10, 1)], "nor is a held day marked Absent")
check(Mixed().get_dates_for_attendance("E2") == Base().get_dates_for_attendance("E2"), "someone it does not cover is marked as ever")
site.add("Employee Checkin", name="CK-1", employee="E1", attendance="", shift="Day", shift_start="2026-09-05 08:00:00", time="2026-09-05 08:01:00")
site.add("Employee Checkin", name="CK-LINKED", employee="E2", attendance="HR-ATT-X", shift="Day", shift_start="2026-09-05 08:00:00", time="2026-09-05 08:01:00")
site.add("Employee Checkin", name="CK-SKIPPED", employee="E2", attendance="", skip_auto_attendance=1, shift="Day", shift_start="2026-09-05 08:00:00", time="2026-09-05 08:01:00")
site.add("Employee Checkin", name="CK-OFFSHIFT", employee="E2", attendance="", offshift=1, shift="Day", shift_start="2026-09-05 08:00:00", time="2026-09-05 08:01:00")
site.add("Employee Checkin", name="CK-OTHER-SHIFT", employee="E2", attendance="", shift="Night", shift_start="2026-09-05 08:00:00", time="2026-09-05 08:01:00")
site.conn.commit()
site.frappe.local.__dict__.clear()
check(not Mixed().unlinked_checkins_exist(), "a shift's start time can change with only held punches waiting: others marked, skipped, off shift or on another shift do not count")
site.add("Employee Checkin", name="CK-2", employee="E2", attendance=None, shift="Day", shift_start="2026-09-05 08:00:00", time="2026-09-05 08:01:00")
site.conn.commit()
check(Mixed().unlinked_checkins_exist(), "but not with others waiting, as Frappe HR has it")
Empty = type("Empty", (site.glue.ShiftTypeKeepDeleted, type("None_", (Base,), {"unlinked_checkins_exist": lambda self: False})), {})
check(not Empty().unlinked_checkins_exist(), "and none waiting is none waiting")
before = site.statements
for _ in range(5):
    site.glue.held("E1", D(2026, 9, 5))
check(site.statements == before, "the holds are read once in a run, for all it asks", site.statements - before)
free = Site()
free.conn.execute("DELETE FROM \"tabAttendance Deletion\"")
Free = type("Free", (free.glue.ShiftTypeKeepDeleted, Base), {})
check(len(Free().get_employee_checkins()) == len(Base().get_employee_checkins()) and Free().unlinked_checkins_exist(), "with nothing held, all is as Frappe HR has it")
released = Site()
released.people = {"E1": ("LPL", "PP")}
released.deletion(status="Finished", from_date=D(2026, 9, 1), to_date=D(2026, 9, 30))
check(released.glue.held("E1", D(2026, 9, 5)), "held")
released.glue.release("HR-ATD-1")
released.frappe.local.__dict__.clear()
check(not released.glue.held("E1", D(2026, 9, 5)) and Doc(released, "HR-ATD-1").keep_deleted == 0, "Let Auto Attendance Fill These Days lets them go")
missing = Site()
missing.frappe.db.table_exists = lambda doctype: False
missing.conn.execute('DROP TABLE "tabAttendance Deletion"')
check(not missing.glue.held("E1", D(2026, 9, 5)), "before the table exists (deployed, not yet migrated) auto attendance carries on")


# ── 8. The same reads a slice, however many people ───────
def statements_for(people):
    site = Site()
    populate(site, people=people, days=1)
    doc = site.deletion(status="Queued")
    site.glue.delete_all(doc.name)
    return site.statements, site


few, _few = statements_for(10)
many, _many = statements_for(900)
check(many == few, "900 people in one slice take no more statements than 10: %d and %d" % (many, few))
check(few < 100, "and few of them: two reads for each day of the month, whatever is on it, and the slice itself", few)
check(len(_many.names()) == 0 and Doc(_many, "HR-ATD-1").deleted == 900, "and all of them go", Doc(_many, "HR-ATD-1").values)
site = Site()
populate(site)
site.glue.add_indexes()
indexed = [call[1:] for call in site.calls if call[0] == "index"]
check(("Employee Checkin", ["attendance"]) in indexed and ("Overtime Details", ["reference_document"]) in indexed and ("Late Arrival Notice", ["attendance"]) in indexed,
      "what a slice looks records up by is indexed", indexed)
check(("Attendance", ["amended_from"]) not in indexed and not [call for call in indexed if call[0] in ("Comment", "Gone Doctype", "Some Settings")],
      "and nothing else: not a self link looked up by day, an ignored doctype, a doctype gone or a Single", indexed)
broken = Site()
broken.frappe.db.add_index = lambda doctype, fields: (_ for _ in ()).throw(Failure("too big"))
broken.glue.add_indexes()
check(broken.errors, "an index that will not build holds up no migrate", broken.errors)
check(not Doc(_many, "HR-ATD-1").message, "with no message", Doc(_many, "HR-ATD-1").values)
single = Site()
populate(single, people=1, days=2)
single.singles = {"Some Settings": {"attendance": "HR-ATT-E0-00"}}
single.glue.delete_all(single.deletion(status="Queued").name)
check(single.names() == ["HR-ATT-E0-00"], "a Single that points at a record holds it back", single.names())
dynamic = Site()
populate(dynamic, people=1, days=4)
dynamic.dynamic = [Row(parent="Generic Reference", fieldname="ref_name", options="ref_type"),
                   Row(parent="Comment", fieldname="reference_name", options="reference_doctype")]
dynamic.add("Generic Reference", name="G1", ref_type="Attendance", ref_name="HR-ATT-E0-00", docstatus=1)
dynamic.add("Generic Reference", name="G2", ref_type="Attendance", ref_name="HR-ATT-E0-01", docstatus=2)
dynamic.add("Generic Reference", name="G3", ref_type="Employee", ref_name="HR-ATT-E0-02", docstatus=1)
dynamic.conn.commit()
dynamic.glue.delete_all(dynamic.deletion(status="Queued").name)
check(dynamic.names() == ["HR-ATT-E0-00"], "a dynamic link holds it back, unless cancelled or to another doctype, as Frappe's check has it", dynamic.names())


# ── 9. Wiring ────────────────────────────────────────────
folder = os.path.join(APP, "doctype", "attendance_deletion")
meta = json.load(open(os.path.join(folder, "attendance_deletion.json"), encoding="utf-8"))
fields = {field["fieldname"]: field for field in meta["fields"]}
check(meta["name"] == "Attendance Deletion" and meta["module"] == "HRMS Addon" and meta["autoname"].startswith("HR-ATD-") and meta.get("track_changes") == 1, "the doctype", meta["name"])
check(meta["field_order"] == [field["fieldname"] for field in meta["fields"]], "its fields in order")
check({row["role"] for row in meta["permissions"]} == {"System Manager", "HR Manager"}, "only the HR Manager and the System Manager", meta["permissions"])
for field in R.SERVER_FIELDS:
    check(field in fields and fields[field].get("read_only") == 1 and fields[field].get("no_copy") == 1, "%s only the job writes, and a copy does not take" % field)
for field in R.CHOICES:
    check(field in fields and not fields[field].get("read_only"), "%s is chosen" % field)
check(fields["keep_deleted"].get("default") == "1", "Keep Deleted is on until unticked")
check(fields["status"]["options"].split("\n") == [R.DRAFT, R.QUEUED, R.DELETING, R.STOPPED, R.FINISHED, R.FAILED] and fields["status"]["default"] == R.DRAFT, "its statuses")
check(fields["attendance_status"]["options"].split("\n")[1:] == list(U.STATUSES) and fields["attendance_status"]["options"].startswith("\n"), "any status until one is chosen")
for field in ("cursor_date", "cursor_name", "backup_size", "kept_size", "stop_requested"):
    check(fields[field].get("hidden") == 1, "%s is the job's own" % field)
for field in ("backup_file", "kept_file"):
    check(fields[field]["fieldtype"] == "Attach", "%s is a file" % field)
attendance_fields = {field["fieldname"] for field in json.load(open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "attendance", "attendance.json"), encoding="utf-8"))["fields"]} if os.path.isdir(APPS_ROOT) else None
if attendance_fields:
    check(set(R.RECORD_FIELDS) - {"name", "docstatus"} <= attendance_fields and set(R.COUNT_FIELDS) - {"name"} <= attendance_fields, "every field read is Attendance's own",
          set(R.RECORD_FIELDS) - {"name", "docstatus"} - attendance_fields)
controller = open(os.path.join(folder, "attendance_deletion.py"), encoding="utf-8").read()
for needle in ("attendance_deletions.deletion_onload(self)", "attendance_deletions.deletion_validate(self)", "attendance_deletions.deletion_on_trash(self)",
               "def on_doctype_update():\n    attendance_deletions.add_indexes()"):
    check(needle in controller, "the controller: %s" % needle)
hooks_src = open(os.path.join(PACKAGE, "hooks.py"), encoding="utf-8").read().replace("\r\n", "\n")
check('"Shift Type": ["hrms_addon.hrms_addon.attendance_deletions.ShiftTypeKeepDeleted"]' in hooks_src, "auto attendance goes through the mixin")
navigation = open(os.path.join(APP, "navigation_rules.py"), encoding="utf-8").read()
check(navigation.count('"Attendance Deletion"') >= 4, "it is on the menus beside Upload Attendance", navigation.count('"Attendance Deletion"'))
attendance_src = open(os.path.join(APP, "attendance.py"), encoding="utf-8").read().replace("\r\n", "\n")
check("if attendance_deletions.held(employee.name, day):\n            continue" in attendance_src, "automatic attendance leaves a held day too")
form = open(os.path.join(folder, "attendance_deletion.js"), encoding="utf-8").read()
glue_src = open(os.path.join(APP, "attendance_deletions.py"), encoding="utf-8").read().replace("\r\n", "\n")
for name in ("check", "start", "stop", "release"):
    check('@frappe.whitelist(methods=["POST"])\ndef %s(deletion' % name in glue_src, "%s changes things, so POST only" % name)
check('@frappe.whitelist()\ndef progress(deletion):' in glue_src, "progress is the form's to read")
check('const HA_ATTENDANCE_DELETION = "hrms_addon.hrms_addon.attendance_deletions.";' in form, "the form calls the module")
check('+ "progress?deletion="' in form and "fetch(" in form, "and follows it without a dialog")
check("frappe.db.sql(" not in glue_src, "no SQL of its own: Frappe's calls, as the app's others are")
bulk_src = open(os.path.join(APP, "bulk.py"), encoding="utf-8").read().replace("\r\n", "\n")
check('if action == "cancel":\n        _not_this_much_attendance(doctype, docnames)' in bulk_src and "_not_this_much_attendance(doctype, items)" in bulk_src,
      "a list's big selection of attendance goes to the deletion, cancelled or deleted")

# ── 10. Upstream ─────────────────────────────────────────
delete_path = os.path.join(APPS_ROOT, "frappe", "frappe", "model", "delete_doc.py")
if os.path.exists(delete_path):
    delete_src = open(delete_path, encoding="utf-8").read()
    links_part = delete_src.split("def delete_dynamic_links(doctype, name):", 1)[1].split("def delete_references(", 1)[0]
    theirs = re.findall(r'delete_references\("([^"]+)", doctype, name(?:, "([^"]+)")?(?:, "([^"]+)")?\)', links_part)
    ours = {row[0]: row for row in R.REFERENCES_DELETED}
    check(len(theirs) >= 8, "Frappe's delete_dynamic_links reads as this expects", theirs)
    for doctype, of, name in theirs:
        check(doctype in ours and (not of or ours[doctype][1] == of) and (not name or ours[doctype][2] == name), "what Frappe clears after a record, this clears: %s" % doctype, ours.get(doctype))
        if not of:
            check(ours[doctype][1:] == ("reference_doctype", "reference_name"), "%s by Frappe's default fields" % doctype, ours.get(doctype))
    for needle, why in (('clear_references("Communication", doctype, name)', "communications let go of"),
                        ('clear_references("Activity Log", doctype, name)', "activity log let go of"),
                        ('clear_references("Activity Log", doctype, name, "timeline_doctype", "timeline_name")', "and its timeline"),
                        ('frappe.db.delete("Communication Link", {"link_doctype": link_doctype, "link_name": link_name})', "communication links gone"),
                        ('"frappe.model.delete_doc.delete_dynamic_links"', "and Frappe queues a job for it, for every record: why this does not go through it"),
                        ("add_to_deleted_document(doc)", "a Deleted Document copy of each")):
        check(needle in delete_src, "Frappe's delete: %s (%r not found)" % (why, needle))
    for needle, why in (('frappe.db.delete("__global_search", {"doctype": doc.doctype, "name": doc.name})', "global search"),):
        check(needle in open(os.path.join(APPS_ROOT, "frappe", "frappe", "utils", "global_search.py"), encoding="utf-8").read(), "Frappe's delete: %s" % why)
    check('frappe.db.delete("Tag Link", {"document_type": doc.doctype, "document_name": doc.name' in open(os.path.join(APPS_ROOT, "frappe", "frappe", "desk", "doctype", "tag", "tag.py"), encoding="utf-8").read(), "Frappe's delete: tag links")
    queue_src = open(os.path.join(APPS_ROOT, "frappe", "frappe", "utils", "background_jobs.py"), encoding="utf-8").read()
    check("MAX_QUEUED_JOBS = 500" in queue_src, "the queue holds 500 jobs")
    check('.set("attendance", "")' in open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "attendance", "attendance.py"), encoding="utf-8").read(), "cancelling lets go of punches with a blank, as this does")
    shift_src = open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "shift_type", "shift_type.py"), encoding="utf-8").read()
    for needle, why in (("def get_employee_checkins(self) -> list[dict]:", "punches are read through this"),
                        ("def get_dates_for_attendance(self, employee: str) -> list[str]:", "Absent days through this"),
                        ("def unlinked_checkins_exist(self):", "a shift's start time waits on this"),
                        ('"attendance": ["is", "not set"], "skip_auto_attendance": 0, "offshift": 0}', "with these filters"),
                        ("attendance_date = key[1].date()", "a punch's day is its shift_start's")):
        check(needle in shift_src, "Frappe HR's Shift Type: %s (%r not found)" % (why, needle))
    database_src = open(os.path.join(APPS_ROOT, "frappe", "frappe", "database", "database.py"), encoding="utf-8").read()
    check("def add_index(" in open(os.path.join(APPS_ROOT, "frappe", "frappe", "database", "mariadb", "database.py"), encoding="utf-8").read(), "add_index is there")
    check("def delete(self" in database_src and "def set_value(" in database_src and "def count(" in database_src, "the calls used are there")
    file_src = open(os.path.join(APPS_ROOT, "frappe", "frappe", "core", "doctype", "file", "file.py"), encoding="utf-8").read()
    check("if not self._content:\n\t\t\treturn" in file_src and "def validate_file_on_disk(self):" in file_src, "a File made from a path on disk is not read in, so its size is no limit")
else:
    print("Frappe's source not found here: upstream not checked")

print()
print("FAILED: %d" % len(fail) if fail else "ALL ATTENDANCE DELETION CHECKS PASSED")
sys.exit(1 if fail else 0)
