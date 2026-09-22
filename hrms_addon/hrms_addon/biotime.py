# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Reading Luuka's clockings out of BioTime.

The rules are in biotime_rules.py, without a Frappe import
(scripts/verify_biotime.py). This is the part that reaches the server and
writes to the site.

  test_connection()  BioTime answered, and how many punches it is holding
                     for the last day
  pull()             every punch since the last read, written down as
                     Attendance Device Logs and pushed into Frappe HR's
                     Employee Checkin
  pull_all()         hourly, when the server record is enabled

ONLY THE TRANSPORT CHANGES

BioTime is where the machines push their punches, so this asks the server
once instead of dialling each machine (devices.py). What happens to a
punch afterwards is exactly what happened before: written down first,
pushed second, an unknown badge listed rather than dropped, a failed push
retried without going back to the source. devices.retry_failed and
devices.unknown_badges work on BioTime's rows unchanged, because they are
the same rows.

THE MACHINE ON THE WALL IS STILL A RECORD

BioTime names the terminal a punch came from; it does not know which door
that terminal guards or which plant it is in. Those live on the Attendance
Device, which is also what the direction rules read. So a terminal seen
for the first time gets an Attendance Device made for it, set to BioTime
and left for HR to give a branch and a direction — the punches are kept
meanwhile, they are simply undirected until somebody says.

THE LIBRARY

requests is imported inside the functions that need it, like pyzk in
devices.py, so a site that never talks to BioTime still installs and
migrates.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from hrms_addon.hrms_addon import biotime_rules as rules, devices, zkteco_rules as punch_rules

SETTINGS = "BioTime Server"
DEVICE = "Attendance Device"
SOURCE = "BioTime"


def settings_validate(doc, method=None):
    errors = rules.settings_errors({
        "enabled": doc.get("enabled"), "base_url": doc.get("base_url"),
        "username": doc.get("username"), "has_password": _has_password(doc),
        "verify_tls": doc.get("verify_tls"), "page_size": doc.get("page_size")})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SETTINGS))


def _has_password(doc):
    """Typed just now, or already in the vault. A Password field holds the
    new value on the doc and the old one out of sight, so both are asked."""
    if doc.get("password"):
        return True
    try:
        return bool(doc.get_password("password", raise_exception=False))
    except Exception:
        return False


def _settings():
    doc = frappe.get_single(SETTINGS)
    if not doc.get("enabled"):
        return None
    return doc


# ── 1. Talking to BioTime ─────────────────────────────────────────────
def _session(doc):
    """A signed-in session. A fresh token each run: one extra request an
    hour is cheaper than reasoning about when a JWT went stale."""
    import requests

    url = rules.endpoint(doc.base_url, doc.get("auth_path") or rules.AUTH_PATH)
    if not url:
        frappe.throw(_("BioTime's address must start http:// or https://."))
    password = doc.get_password("password", raise_exception=False)
    answer = requests.post(url, json={"username": doc.username, "password": password},
                           timeout=30, verify=bool(doc.get("verify_tls")))
    payload = _payload(answer)
    errors = rules.token_errors(payload)
    if errors:
        frappe.throw(_("BioTime would not sign us in: {0}").format(errors[0]),
                     title=_("BioTime"))
    session = requests.Session()
    session.headers.update({"Authorization": "JWT %s" % payload["token"],
                            "Accept": "application/json"})
    session.verify = bool(doc.get("verify_tls"))
    return session


def _payload(answer):
    try:
        return answer.json()
    except ValueError:
        return {"detail": (answer.text or "")[:200]}


def _transactions(doc, session, start, end):
    """Every transaction in the window, page by page."""
    url = rules.endpoint(doc.base_url, doc.get("transactions_path") or rules.TRANSACTIONS_PATH)
    page, seen, rows = 1, 0, []
    while page:
        answer = session.get(url, params=rules.query(start, end, page,
                                                     cint(doc.get("page_size"))
                                                     or rules.PAGE_SIZE),
                             timeout=120)
        if answer.status_code >= 400:
            frappe.throw(_("BioTime answered {0} for page {1}: {2}").format(
                answer.status_code, page, (answer.text or "")[:200]), title=_("BioTime"))
        payload = _payload(answer)
        found = rules.rows_of(payload)
        rows.extend(found)
        seen += len(found)
        page = rules.next_page(payload, page, seen, total=seen)
    return rows


@frappe.whitelist(methods=["POST"])
def test_connection():
    """BioTime answered, and what it is holding."""
    doc = frappe.get_single(SETTINGS)
    doc.check_permission("write")
    session = _session(doc)
    span = rules.window(None, now_datetime(), first_pull_days=1)
    rows = _transactions(doc, session, span["start"], span["end"])
    found = rules.readings(rows)
    terminals = rules.terminals_of(found["readings"])
    doc.db_set({"last_status": _("Answered: {0} punch(es) in the last day").format(len(rows)),
                "last_error": None, "last_run": now_datetime(),
                "terminals_seen": ", ".join(
                    "%s (%s)" % (name or _("unnamed"), serial)
                    for serial, name in sorted(terminals.items()))[:500] or None},
               update_modified=False)
    return {"punches": len(rows), "usable": len(found["readings"]),
            "skipped": len(found["skipped"]), "terminals": terminals}


# ── 2. The machines BioTime names ─────────────────────────────────────
def _device_for(serial, name, company=None):
    """The Attendance Device a terminal stands for. One seen for the first
    time is made, so its punches have somewhere to hang, and left without
    a branch or a direction for HR to give it."""
    existing = frappe.db.get_value(DEVICE, {"serial_number": serial}, "name")
    if existing:
        return frappe.get_doc(DEVICE, existing)
    try:
        device = frappe.get_doc({
            "doctype": DEVICE, "device_name": name or _("BioTime terminal {0}").format(serial),
            "serial_number": serial, "source": SOURCE, "enabled": 1,
            "company": company or frappe.defaults.get_user_default("Company"),
            "direction": punch_rules.DIRECTION_BOTH})
        device.flags.ignore_permissions = True
        device.flags.ignore_mandatory = True
        device.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: a BioTime terminal with no machine record")
        return None
    return device


# ── 3. The pull ───────────────────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def pull():
    doc = frappe.get_single(SETTINGS)
    doc.check_permission("write")
    if not doc.get("enabled"):
        frappe.throw(_("Reading from BioTime is switched off."))
    return _pull(doc, _read)


def _read(doc, span):
    session = _session(doc)
    return _transactions(doc, session, span["start"], span["end"])


def _pull(doc, read):
    """The pull itself, with the reading handed in so it can be walked
    without a server."""
    started = now_datetime()
    span = rules.window(doc.get("last_sync"), started,
                        cint(doc.get("first_pull_days")) or rules.FIRST_PULL_DAYS)
    try:
        rows = read(doc, span)
    except Exception as error:  # noqa: BLE001
        doc.db_set({"last_status": _("Could not read"), "last_error": str(error)[:500],
                    "last_run": started}, update_modified=False)
        raise
    found = rules.readings(rows)
    terminals = rules.terminals_of(found["readings"])
    machines = {}
    for serial, name in terminals.items():
        device = _device_for(serial, name)
        if device:
            machines[serial] = device

    punches, directions = [], {}
    for row in found["readings"]:
        device = machines.get(row.get("terminal_serial"))
        if not device:
            continue
        directions[device.name] = device.get("direction") or punch_rules.DIRECTION_BOTH
        punches.append({"device": device.name, "device_user_id": row["device_user_id"],
                        "time": row["punch_time"], "punch": row.get("punch")})

    # a face read twice at the SAME terminal is one reading; two terminals
    # within a minute and a half are two doors, not one double read
    clean = punch_rules.dedupe(punches, per_device=True)
    resolved = punch_rules.resolve(
        clean, directions, devices._standing([row["device_user_id"] for row in clean]))

    tally = {"read": len(rows), "usable": len(found["readings"]), "skipped": len(found["skipped"]),
             "collapsed": len(punches) - len(clean), "pushed": 0, "unknown": 0, "duplicate": 0,
             "failed": 0, "no_terminal": len(found["readings"]) - len(punches)}
    by_name = {device.name: device for device in machines.values()}
    newest = doc.get("last_sync")
    for row in resolved:
        device = by_name.get(row["device"])
        if not device:
            continue
        log = devices._write_log(device, row)
        outcome = devices._push(device, log)
        tally[outcome] = tally.get(outcome, 0) + 1
        moment = get_datetime(row["time"])
        if not newest or moment > get_datetime(newest):
            newest = moment
    doc.db_set({
        "last_sync": newest or doc.get("last_sync"), "last_run": started,
        "last_pulled": tally["pushed"],
        "last_status": _("Read {0}, pushed {1}").format(tally["read"], tally["pushed"]),
        "last_error": None,
        "terminals_seen": ", ".join("%s (%s)" % (name or _("unnamed"), serial)
                                    for serial, name in sorted(terminals.items()))[:500] or None,
    }, update_modified=False)
    frappe.db.commit()
    return tally


def pull_all():
    """Hourly. Nothing happens while the server record is switched off,
    and a machine still set to Direct is polled by devices.pull_all as it
    always was."""
    doc = _settings()
    if not doc:
        return
    try:
        _pull(doc, _read)
    except Exception:
        frappe.log_error(title="HRMS Addon: the hourly BioTime pull")
