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
from frappe.utils import cint, get_datetime, now_datetime

from hrms_addon.hrms_addon import zkteco_rules as rules

CHECKIN = "Employee Checkin"
LOG = "Attendance Device Log"
DEVICE = "Attendance Device"
BADGE_FIELD = "attendance_device_id"


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
        doc.db_set({"last_status": _("Could not read"), "last_error": str(error)[:500]}, update_modified=False)
        raise
    from_moment = rules.since(doc.get("last_sync"), started, cint(doc.get("first_pull_days")) or rules.FIRST_PULL_DAYS)
    fresh = [row for row in punches if row.get("time") and get_datetime(row["time"]) > from_moment]
    clean = rules.dedupe(fresh, within=cint(doc.get("double_read_seconds")) or rules.DOUBLE_READ_SECONDS)
    collapsed = len(fresh) - len(clean)
    resolved = rules.resolve(clean, {doc.name: doc.get("direction") or rules.DIRECTION_BOTH},
                             _standing([row["device_user_id"] for row in clean]))
    found = {"read": len(punches), "new": len(fresh), "collapsed": collapsed, "pushed": 0, "unknown": 0,
             "duplicate": 0, "failed": 0}
    newest = doc.get("last_sync")
    for row in resolved:
        log = _write_log(doc, row)
        outcome = _push(doc, log)
        found[outcome] = found.get(outcome, 0) + 1
        moment = get_datetime(row["time"])
        if not newest or moment > get_datetime(newest):
            newest = moment
    doc.db_set({"last_sync": newest or doc.get("last_sync"), "last_status":
                _("Read {0}, pushed {1}").format(found["read"], found["pushed"]), "last_error": None},
               update_modified=False)
    if clear_after and found["failed"] == 0:
        _clear(doc)
    frappe.db.commit()
    return found


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


def _write_log(device, row):
    """Every punch written down before anything is made of it."""
    moment = get_datetime(row["time"])
    existing = frappe.db.get_value(LOG, {"device": device.name, "device_user_id": row["device_user_id"],
                                         "punch_time": moment}, "name")
    if existing:
        log = frappe.get_doc(LOG, existing)
        if log.status == "Pending":
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
    for name in frappe.get_all(DEVICE, filters={"enabled": 1,
                                                "source": ["!=", "BioTime"]}, pluck="name"):
        try:
            _pull(frappe.get_doc(DEVICE, name), read=_read)
        except Exception:  # noqa: BLE001
            frappe.db.rollback()
            frappe.log_error(title="HRMS Addon: attendance pull failed for %s" % name)
        else:
            frappe.db.commit()


def daily():
    """Once a day, the punches that never landed are tried again."""
    try:
        retry_failed()
    except Exception:  # noqa: BLE001
        frappe.db.rollback()
        frappe.log_error(title="HRMS Addon: retrying attendance logs failed")


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
