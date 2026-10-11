# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talking to Luuka's ZKTeco clocking machines.

The rules are in zkteco_rules.py, without a Frappe import
(scripts/verify_attendance.py). This is the part that reaches the machine
and writes to the site.

WHAT IT DOES

  pull(device)      reads the machine's attendance log from just after the
                    last sync, collapses a face read twice, works out which
                    way each punch went, writes every one down as an
                    Attendance Device Log, and pushes the ones it can into
                    Frappe HR's Employee Checkin
  pull_all()        every enabled machine, hourly
  retry_failed()    the punches that were written down but never landed —
                    Luuka's "attendance jumps out" — pushed again without
                    going back to the machine
  test_connection() the machine answered, and what it says it is

WHY EVERY PUNCH IS WRITTEN DOWN FIRST

Luuka's minutes say the data sometimes fails to reach the system and the
supplier has to push it. Writing the punch down before turning it into a
check-in means the record exists either way: a log row that says Failed or
Unknown Employee can be seen, corrected and re-pushed, and nothing depends
on the machine still holding it.

THE DRIVER IS OPTIONAL

pyzk (`pip install pyzk`) is imported inside the function that needs it, so
a site without the library still installs, migrates and runs; only a pull
from a real machine asks for it.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime

from hrms_addon.hrms_addon import attendance_rules, zkteco_rules as rules

CHECKIN = "Employee Checkin"
LOG = "Attendance Device Log"
DEVICE = "Attendance Device"
SHIFT = "Shift Type"
BADGE_FIELD = "attendance_device_id"
# a machine that will not answer holds the attendance back this long, and
# no longer: after it the days are marked from what the others sent
HOLD_HOURS = 6


# ── the machine and its log, as documents ─────────────────────────────
def device_validate(doc, method=None):
    errors = rules.device_errors({
        "device_name": doc.get("device_name"), "source": doc.get("source"),
        "host": doc.get("host"), "port": doc.get("port"),
        "serial_number": doc.get("serial_number"),
        "direction": doc.get("direction"), "enabled": doc.get("enabled"),
    })
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Attendance Device"))


def log_validate(doc, method=None):
    doc.punch_meaning = rules.PUNCH_MEANING.get(cint(doc.get("punch")))
    if doc.get("device_user_id") and not doc.get("employee"):
        doc.employee = _employee_for(doc.device_user_id)
    if doc.get("employee") and not doc.get("employee_name"):
        doc.employee_name = frappe.db.get_value("Employee", doc.employee, "employee_name")


def _employee_for(badge):
    return frappe.db.get_value("Employee", {BADGE_FIELD: str(badge).strip()}, "name")


# ── reading the machine ───────────────────────────────────────────────
def _driver():
    """pyzk, asked for only when a machine is really being read."""
    try:
        from zk import ZK
    except ImportError:
        frappe.throw(_("The ZKTeco driver is not installed on this server. Install it with "
                       "<code>./env/bin/pip install pyzk</code> and try again."),
                     title=_("Driver missing"))
    return ZK


def _connect(device):
    ZK = _driver()
    machine = ZK(
        device.host,
        port=cint(device.port) or 4370,
        timeout=cint(device.timeout) or 30,
        password=cint(device.get_password("comm_key", raise_exception=False) or 0),
        force_udp=bool(device.get("force_udp")),
        ommit_ping=bool(device.get("omit_ping")),
    )
    return machine.connect()


@frappe.whitelist(methods=["POST"])
def test_connection(device):
    """Does the machine answer, and what does it say it is?"""
    doc = frappe.get_doc(DEVICE, device)
    doc.check_permission("write")
    connection = None
    try:
        connection = _connect(doc)
        found = {
            "serial_number": _ask(connection, "get_serialnumber"),
            "firmware": _ask(connection, "get_firmware_version"),
            "device_time": str(_ask(connection, "get_time") or ""),
            "users": len(_ask(connection, "get_users") or []),
        }
        doc.db_set({"serial_number": found["serial_number"], "firmware": found["firmware"],
                    "last_status": _("Answered"), "last_error": None}, update_modified=False)
        return found
    except Exception as error:  # noqa: BLE001 - whatever the driver raises is what HR must see
        doc.db_set({"last_status": _("Could not connect"), "last_error": str(error)[:500]}, update_modified=False)
        frappe.throw(_("{0} did not answer: {1}").format(doc.name, error), title=_("Attendance Device"))
    finally:
        _disconnect(connection)


def _ask(connection, name):
    getter = getattr(connection, name, None)
    return getter() if callable(getter) else None


def _disconnect(connection):
    if connection is None:
        return
    try:
        connection.enable_device()
    except Exception:  # noqa: BLE001 - a machine that will not re-enable must not hide the real error
        pass
    try:
        connection.disconnect()
    except Exception:  # noqa: BLE001
        pass


def _read(device):
    """The machine's attendance log, as plain rows."""
    connection = None
    try:
        connection = _connect(device)
        connection.disable_device()  # nobody punches while it is being read
        records = connection.get_attendance() or []
        return [{
            "device_user_id": str(getattr(record, "user_id", "")).strip(),
            "time": getattr(record, "timestamp", None),
            "punch": getattr(record, "punch", None),
            "status": getattr(record, "status", None),
            "device": device.name,
        } for record in records]
    finally:
        _disconnect(connection)


# ── the pull ──────────────────────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def pull(device, clear_after=0):
    """Read a machine and push what it has. Returns what happened."""
    doc = frappe.get_doc(DEVICE, device)
    doc.check_permission("write")
    return _pull(doc, read=_read, clear_after=cint(clear_after))


def _pull(doc, read, clear_after=0):
    """The pull itself, with the reading handed in so it can be walked
    without a machine."""
    started = now_datetime()
    try:
        punches = read(doc)
    except Exception as error:  # noqa: BLE001
        _write_failure(doc, error)
        raise
    from_moment = rules.since(doc.get("last_sync"), started, cint(doc.get("first_pull_days")) or rules.FIRST_PULL_DAYS)
    fresh = [row for row in punches if row.get("time") and get_datetime(row["time"]) > from_moment]
    clean = rules.dedupe(fresh, within=cint(doc.get("double_read_seconds")) or rules.DOUBLE_READ_SECONDS)
    collapsed = len(fresh) - len(clean)
    resolved = rules.resolve(clean, {doc.name: doc.get("direction") or rules.DIRECTION_BOTH},
                             _standing([row["device_user_id"] for row in clean]))
    found = {"read": len(punches), "new": len(fresh), "collapsed": collapsed, "pushed": 0, "unknown": 0,
             "duplicate": 0, "failed": 0}
    newest, landed = doc.get("last_sync"), []
    for row in resolved:
        log = _write_log(doc, row)
        outcome = _push(doc, log)
        found[outcome] = found.get(outcome, 0) + 1
        if outcome == "pushed":
            landed.append({"employee": log.employee, "time": row["time"]})
        moment = get_datetime(row["time"])
        if not newest or moment > get_datetime(newest):
            newest = moment
    doc.db_set({"last_sync": newest or doc.get("last_sync"), "last_status":
                _("Read {0}, pushed {1}").format(found["read"], found["pushed"]), "last_error": None},
               update_modified=False)
    found["redone"] = len(redo_absences(landed, started))
    if clear_after and found["failed"] == 0:
        _clear(doc)
    frappe.db.commit()
    return found


# ── what a read means for the attendance ──────────────────────────────
def advance_shift_sync(read_at):
    """Frappe HR marks a shift's attendance, the absences included, only up
    to its Last Sync of Checkin, and nothing moves that mark but whoever
    reads the machines. So it follows the reads: every shift marked from
    the clock may be read up to just before the read that has just come in
    (attendance_rules.sync_mark). While the machines cannot be read, the
    mark stands still and nobody is marked absent for punches that have
    not arrived. Returns the shifts it moved."""
    moved = []
    for row in frappe.get_all(SHIFT, filters={"enable_auto_attendance": 1},
                              fields=["name", "last_sync_of_checkin", "process_attendance_after"],
                              limit_page_length=0):
        mark = attendance_rules.sync_mark(row.last_sync_of_checkin, read_at)
        values = {}
        if not row.last_sync_of_checkin or get_datetime(row.last_sync_of_checkin) < mark:
            values["last_sync_of_checkin"] = mark
        if not row.process_attendance_after:
            # with no day to start from Frappe HR marks nothing at all
            values["process_attendance_after"] = getdate(mark)
        if values:
            frappe.db.set_value(SHIFT, row.name, values, update_modified=False)
            moved.append(row.name)
    return moved


def redo_absences(landed, read_at):
    """A terminal that was off the network sends its punches late, after
    the day was marked absent without them. The absences the clock marked
    that those punches contradict are cancelled, which frees the day's
    punches, and Frappe HR marks the day again from all of them on its
    next run. An absence a person marked is left for them
    (attendance_rules.absences_to_redo). Returns the attendances cancelled.

    landed: [{"employee", "time"}] punches just pushed."""
    late = [row for row in landed or [] if row.get("employee")
            and attendance_rules.came_late(row.get("time"), read_at)]
    if not late:
        return []
    days = sorted({getdate(row["time"]) for row in late})
    absences = frappe.get_all(
        "Attendance", limit_page_length=0,
        filters={"employee": ["in", sorted({row["employee"] for row in late})], "docstatus": 1, "status": "Absent",
                 "attendance_date": ["between", [add_days(days[0], -1), days[-1]]]},
        fields=["name", "employee", "attendance_date", "owner", "leave_application", "attendance_request", "shift"])
    spans = {}
    for row in absences:
        if row.shift not in spans:
            times = frappe.db.get_value(SHIFT, row.shift, ["start_time", "end_time"], as_dict=True) if row.shift else None
            spans[row.shift] = bool(times) and attendance_rules.overnight(times.start_time, times.end_time)
        row["overnight"] = spans[row.shift]
    redone = []
    for name in attendance_rules.absences_to_redo(late, absences, read_at):
        try:
            attendance = frappe.get_doc("Attendance", name)
            attendance.flags.ignore_permissions = True
            # a notice or a request may point at the day: they stay, and
            # point at the day marked again in its place
            attendance.flags.ignore_links = True
            attendance.cancel()
            attendance.add_comment("Info", _("Cancelled to be marked again: punches for this day came in late."))
        except Exception:  # noqa: BLE001 - one day that will not cancel must not stop the read
            frappe.log_error(title="HRMS Addon: an absence could not be redone (%s)" % name)
            continue
        redone.append(name)
    return redone


def _standing(badges):
    """The last direction already recorded for each badge, so an unmarked
    punch carries on from where the employee really is."""
    if not badges:
        return {}
    employees = frappe.get_all("Employee", filters={BADGE_FIELD: ["in", list({str(b) for b in badges})]},
                               fields=["name", BADGE_FIELD])
    standing = {}
    for employee in employees:
        last = frappe.get_all(CHECKIN, filters={"employee": employee.name}, fields=["log_type"],
                              order_by="time desc", limit=1)
        if last and last[0].log_type:
            standing[str(employee.get(BADGE_FIELD))] = last[0].log_type
    return standing


def _write_failure(doc, error, started=None):
    """What went wrong, kept.

    A db_set inside a request that then raises is rolled back with the
    rest of it, so the record would go on showing the last good run in
    green immediately after somebody watched a pull fail. The rollback is
    done first, on purpose — nothing half-written from this run is worth
    keeping — and the failure is committed on its own.
    """
    frappe.db.rollback()
    written = {"last_status": _("Could not read"), "last_error": str(error)[:500]}
    if started is not None:
        written["last_run"] = started
    doc.db_set(written, update_modified=False)
    frappe.db.commit()


def _already_logged(punches):
    """The punches in this batch that already have a log row.

    One query for the batch rather than one per punch: the window is a
    span, so the rows that could match are a span too.
    """
    if not punches:
        return set()
    moments = [get_datetime(row["time"]) for row in punches if row.get("time")]
    if not moments:
        return set()
    rows = frappe.get_all(LOG, filters={
        "device": ["in", sorted({row["device"] for row in punches})],
        "punch_time": ["between", [min(moments), max(moments)]],
    }, fields=["device", "device_user_id", "punch_time"], limit_page_length=0)
    return {(row.device, str(row.device_user_id), str(row.punch_time)[:19]) for row in rows}


def _write_log(device, row):
    """Every punch written down before anything is made of it."""
    moment = get_datetime(row["time"])
    existing = frappe.db.get_value(LOG, {"device": device.name, "device_user_id": row["device_user_id"],
                                         "punch_time": moment}, "name")
    if existing:
        log = frappe.get_doc(LOG, existing)
        # only a punch that LANDED is a duplicate. One that failed, or that
        # nobody carries the badge for, keeps its status: retry_failed
        # looks for exactly those, and marking them Duplicate would take
        # them out of the queue and leave them claiming they were already
        # there — which is the one failure this whole module exists for.
        if log.status != "Pushed":
            return log
        log.db_set("status", "Duplicate", update_modified=False)
        return log
    log = frappe.get_doc({
        "doctype": LOG, "device": device.name, "device_user_id": row["device_user_id"], "punch_time": moment,
        "punch": row.get("punch") if isinstance(row.get("punch"), int) else None,
        "device_status": row.get("status") if isinstance(row.get("status"), int) else None,
        "log_type": row.get("log_type"), "status": "Pending", "pulled_on": now_datetime(),
    })
    log.flags.ignore_permissions = True
    log.insert()
    return log


def _push(device, log):
    """One log row into Frappe HR's Employee Checkin. Returns what happened."""
    if log.status in ("Pushed", "Duplicate"):
        return "duplicate" if log.status == "Duplicate" else "pushed"
    if not log.employee:
        log.db_set({"status": "Unknown Employee",
                    "error": _("No employee carries the Attendance Device ID {0}.").format(log.device_user_id)},
                   update_modified=False)
        return "unknown"
    try:
        from hrms.hr.doctype.employee_checkin.employee_checkin import add_log_based_on_employee_field

        checkin = add_log_based_on_employee_field(
            employee_field_value=log.device_user_id,
            timestamp=str(log.punch_time),
            device_id=device.name,
            log_type=log.log_type,
            skip_auto_attendance=1 if device.get("skip_auto_attendance") else 0,
            employee_fieldname=BADGE_FIELD,
        )
        log.db_set({"status": "Pushed", "employee_checkin": checkin.name, "error": None}, update_modified=False)
        return "pushed"
    except frappe.DuplicateEntryError:
        log.db_set({"status": "Duplicate", "error": None}, update_modified=False)
        return "duplicate"
    except Exception as error:  # noqa: BLE001 - one bad punch must not stop the pull
        log.db_set({"status": "Failed", "error": str(error)[:500]}, update_modified=False)
        return "failed"


def _clear(device):
    """Empty the machine's log once everything it held has landed."""
    connection = None
    try:
        connection = _connect(device)
        connection.clear_attendance()
    finally:
        _disconnect(connection)


@frappe.whitelist(methods=["POST"])
def retry_failed(device=None, limit=500):
    """The punches that were written down but never landed. Luuka's
    "attendance jumps out": this pushes them again without the machine."""
    if not frappe.has_permission(LOG, "write"):
        frappe.throw(_("You may not push attendance logs."), frappe.PermissionError)
    filters = {"status": ["in", ("Failed", "Unknown Employee", "Pending")]}
    if device:
        filters["device"] = device
    found = {"pushed": 0, "unknown": 0, "duplicate": 0, "failed": 0}
    for name in frappe.get_all(LOG, filters=filters, pluck="name", order_by="punch_time asc",
                               limit=cint(limit) or 500):
        log = frappe.get_doc(LOG, name)
        if not log.employee:
            log.employee = _employee_for(log.device_user_id)
            if log.employee:
                log.db_set("employee", log.employee, update_modified=False)
        outcome = _push(frappe.get_doc(DEVICE, log.device), log)
        found[outcome] = found.get(outcome, 0) + 1
    frappe.db.commit()
    return found


def pull_all():
    """Hourly: every enabled machine, each on its own so one that is off
    does not stop the rest."""
    # a machine whose punches come from BioTime is read by biotime.py, not
    # dialled here; one with no source set yet is dialled as it always was
    started, answered, silent = now_datetime(), 0, 0
    for name in frappe.get_all(DEVICE, filters={"enabled": 1,
                                                "source": ["!=", "BioTime"]}, pluck="name"):
        try:
            _pull(frappe.get_doc(DEVICE, name), read=_read)
        except Exception:  # noqa: BLE001
            frappe.db.rollback()
            frappe.log_error(title="HRMS Addon: attendance pull failed for %s" % name)
            silent += 1
        else:
            frappe.db.commit()
            answered += 1
    # the attendance follows the reads: marked up to now when every machine
    # answered, and held for one that did not, though not for ever
    if answered and (not silent or _held_long_enough(started)):
        advance_shift_sync(started)
        frappe.db.commit()


def _held_long_enough(now):
    """Whether the attendance has waited HOLD_HOURS for a machine that
    will not answer."""
    marks = [get_datetime(row.last_sync_of_checkin) for row in frappe.get_all(
        SHIFT, filters={"enable_auto_attendance": 1}, fields=["last_sync_of_checkin"], limit_page_length=0)
        if row.last_sync_of_checkin]
    if not marks:
        return True
    return (get_datetime(now) - min(marks)).total_seconds() >= HOLD_HOURS * 3600


def daily():
    """Once a day, the punches that never landed are tried again, and a
    machine that has gone silent is told to its plant's HR."""
    try:
        retry_failed()
    except Exception:  # noqa: BLE001
        frappe.db.rollback()
        frappe.log_error(title="HRMS Addon: retrying attendance logs failed")
    try:
        tell_silent_machines()
    except Exception:  # noqa: BLE001
        frappe.db.rollback()
        frappe.log_error(title="HRMS Addon: telling HR of a silent machine failed")


def tell_silent_machines():
    """A machine that has sent punches before and none for a day and a
    half (board_rules.SILENT_ALERT_HOURS): its plant's HR Officers are told
    each day it stays silent, so it is found before the payroll and not
    at it. Returns the machines told about."""
    from hrms_addon.hrms_addon import board_rules, people

    machines = frappe.get_all(DEVICE, filters={"enabled": 1}, fields=["name", "device_name", "branch"],
                              limit_page_length=0)
    if not machines:
        return []
    last = {row.device: row.last_seen for row in frappe.get_all(
        LOG, filters={"device": ["in", [row.name for row in machines]]},
        fields=["device", "MAX(punch_time) as last_seen"], group_by="device")}
    now, told = now_datetime(), []
    for machine in machines:
        seen = last.get(machine.name)
        if not board_rules.silent_since(seen, now):
            continue
        users = people.hr_officers(machine.branch)
        if not users:
            continue
        people.notify(users, DEVICE, machine.name, _("{0} has sent no punches since {1}. Check the machine and "
                                                      "its network.").format(machine.device_name or machine.name,
                                                                             frappe.utils.format_datetime(seen)))
        told.append(machine.name)
    frappe.db.commit()
    return told


@frappe.whitelist()
def unknown_badges():
    """Badges the machines report that nobody owns: usually an employee
    whose Attendance Device ID was never filled in."""
    found = {}
    for row in frappe.get_all(LOG, filters={"status": "Unknown Employee"},
                              fields=["device_user_id", "punch_time", "device"], order_by="punch_time desc"):
        seen = found.setdefault(row.device_user_id, {"device_user_id": row.device_user_id, "punches": 0,
                                                     "last_seen": row.punch_time, "device": row.device})
        seen["punches"] += 1
        if row.punch_time and str(row.punch_time) > str(seen["last_seen"]):
            seen["last_seen"], seen["device"] = row.punch_time, row.device
    return sorted(found.values(), key=lambda row: str(row["last_seen"]), reverse=True)
