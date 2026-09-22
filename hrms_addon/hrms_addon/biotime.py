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
def _reach(call, url, verify_tls):
    """Every request to BioTime goes through here, so a server that is off,
    unreachable or speaking a different protocol is explained in words
    rather than thrown at somebody as a Python traceback.

    The exceptions are matched on their own classes, not on the text of
    the message, because that text is written by OpenSSL and changes
    between versions.
    """
    import requests

    try:
        return call()
    except requests.exceptions.SSLError as error:
        if "WRONG_VERSION_NUMBER" in str(error):
            frappe.throw(
                _("{0} answered in plain HTTP, but the address says https://. Change the "
                  "address to http:// and untick Verify the Certificate.").format(url),
                title=_("BioTime"))
        frappe.throw(
            _("The certificate at {0} could not be verified. If BioTime uses a self-signed "
              "certificate, untick Verify the Certificate; the connection is then private "
              "but not proven.").format(url), title=_("BioTime"))
    except requests.exceptions.ConnectTimeout:
        frappe.throw(_("{0} did not answer in time. Check that BioTime is running and that "
                       "this server can reach it.").format(url), title=_("BioTime"))
    except requests.exceptions.ReadTimeout:
        frappe.throw(_("{0} accepted the connection but sent nothing back in time. It may be "
                       "working through a very large window — try a smaller page size or a "
                       "shorter first pull.").format(url), title=_("BioTime"))
    except requests.exceptions.ConnectionError:
        frappe.throw(_("Nothing answered at {0}. Check the address, the port, and that this "
                       "server is allowed to reach BioTime.").format(url), title=_("BioTime"))
    except requests.exceptions.MissingSchema:
        frappe.throw(_("BioTime's address must start http:// or https://."),
                     title=_("BioTime"))
    except requests.exceptions.RequestException as error:
        frappe.throw(_("BioTime could not be reached: {0}").format(str(error)[:200]),
                     title=_("BioTime"))


def _session(doc):
    """A signed-in session. A fresh token each run: one extra request an
    hour is cheaper than reasoning about when a JWT went stale."""
    import requests

    url = rules.endpoint(doc.base_url, doc.get("auth_path") or rules.AUTH_PATH)
    if not url:
        frappe.throw(_("BioTime's address must start http:// or https://."))
    password = doc.get_password("password", raise_exception=False)
    verify = bool(doc.get("verify_tls"))
    answer = _reach(
        lambda: requests.post(url, json={"username": doc.username, "password": password},
                              timeout=30, verify=verify),
        url, verify)
    payload = _payload(answer)
    errors = rules.token_errors(payload)
    if errors:
        frappe.throw(_("BioTime would not sign us in: {0}").format(errors[0]),
                     title=_("BioTime"))
    session = requests.Session()
    session.headers.update(rules.header(rules.token_of(payload),
                                        doc.get("token_prefix") or rules.DEFAULT_PREFIX))
    session.headers.update({"Accept": "application/json"})
    session.verify = verify
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
        answer = _reach(
            lambda: session.get(url, params=rules.query(start, end, page,
                                                        cint(doc.get("page_size"))
                                                        or rules.PAGE_SIZE),
                                timeout=120),
            url, bool(doc.get("verify_tls")))
        if answer.status_code >= 400:
            _explain_refusal(doc, answer, page)
        payload = _payload(answer)
        found = rules.rows_of(payload)
        rows.extend(found)
        seen += len(found)
        page = rules.next_page(payload, page, seen, total=seen)
    return rows


def _explain_refusal(doc, answer, page):
    """Why BioTime turned a page down.

    The one worth naming is a 401 carrying SimpleJWT's token_not_valid: the
    sign-in worked and handed us a token this API will not accept, which
    means the Sign-in Path is the wrong one for this BioTime rather than
    anything being wrong with the password.
    """
    payload = _payload(answer)
    if answer.status_code == 401 and rules.token_rejected(payload):
        frappe.throw(
            _("BioTime signed us in and then refused the token on {0}. That means the Sign-in "
              "Path is the wrong one for this BioTime, not that the password is wrong — the "
              "two endpoints do not mint the same kind of token."
              "<br><br>Press <b>Find the Sign-in Path</b>: it tries the ones BioTime has "
              "shipped and says which of them gives a token this server will take.")
            .format(doc.get("transactions_path") or rules.TRANSACTIONS_PATH),
            title=_("BioTime"))
    if answer.status_code == 401:
        frappe.throw(_("BioTime would not accept the sign-in on page {0}. Check the user name "
                       "and password, and that the account may read transactions.").format(page),
                     title=_("BioTime"))
    if answer.status_code == 403:
        frappe.throw(_("BioTime signed us in but will not let that account read transactions. "
                       "Give it permission, or use one that has it."), title=_("BioTime"))
    if answer.status_code == 404:
        frappe.throw(_("There is nothing at {0} on this BioTime. Check the Transactions Path.")
                     .format(doc.get("transactions_path") or rules.TRANSACTIONS_PATH),
                     title=_("BioTime"))
    frappe.throw(_("BioTime answered {0} for page {1}: {2}").format(
        answer.status_code, page, (answer.text or "")[:200]), title=_("BioTime"))


@frappe.whitelist(methods=["POST"])
def find_sign_in():
    """Try the sign-in endpoints BioTime has shipped and say which one
    gives a token the transactions API will actually accept.

    It changes nothing. It signs in, asks for a single transaction, and
    reports — so somebody can put the answer in the form themselves rather
    than have this app quietly rewrite their settings.
    """
    import requests

    doc = frappe.get_single(SETTINGS)
    doc.check_permission("write")
    password = doc.get_password("password", raise_exception=False)
    verify = bool(doc.get("verify_tls"))
    span = rules.window(None, now_datetime(), first_pull_days=1)
    reading = rules.endpoint(doc.base_url,
                             doc.get("transactions_path") or rules.TRANSACTIONS_PATH)
    if not reading:
        frappe.throw(_("BioTime's address must start http:// or https://."))

    tried = []
    for auth_path in rules.AUTH_PATH_CANDIDATES:
        url = rules.endpoint(doc.base_url, auth_path)
        try:
            answer = _reach(
                lambda: requests.post(url, json={"username": doc.username,
                                                 "password": password},
                                      timeout=30, verify=verify), url, verify)
        except Exception:  # noqa: BLE001
            tried.append({"auth_path": auth_path, "prefix": None,
                          "result": _("could not be reached")})
            continue
        token = rules.token_of(_payload(answer))
        if not token:
            tried.append({"auth_path": auth_path, "prefix": None,
                          "result": _("no token here ({0})").format(answer.status_code)})
            continue
        for prefix in rules.PREFIXES:
            # not through _reach: one endpoint refusing must not end the
            # search, so a failure here is written down and the next one
            # is tried
            try:
                probe = requests.get(reading,
                                     params=rules.query(span["start"], span["end"], 1, 1),
                                     headers=rules.header(token, prefix), timeout=60,
                                     verify=verify)
            except requests.exceptions.RequestException as error:
                tried.append({"auth_path": auth_path, "prefix": prefix,
                              "result": str(error)[:100]})
                continue
            if probe.status_code < 400:
                doc.db_set({"last_status": _("Sign-in path {0} with {1} works").format(
                    auth_path, prefix), "last_error": None, "last_run": now_datetime()},
                    update_modified=False)
                frappe.db.commit()
                return {"found": True, "auth_path": auth_path, "prefix": prefix,
                        "tried": tried}
            tried.append({"auth_path": auth_path, "prefix": prefix,
                          "result": _("token refused ({0})").format(probe.status_code)})
    doc.db_set({"last_status": _("No sign-in path worked"), "last_run": now_datetime()},
               update_modified=False)
    frappe.db.commit()
    return {"found": False, "tried": tried}


@frappe.whitelist(methods=["POST"])
def test_connection():
    """BioTime answered, and what it is holding."""
    doc = frappe.get_single(SETTINGS)
    doc.check_permission("write")
    span = rules.window(None, now_datetime(), first_pull_days=1)
    try:
        session = _session(doc)
        rows = _transactions(doc, session, span["start"], span["end"])
    except Exception as error:  # noqa: BLE001
        # the same courtesy a pull gets: the record says what went wrong,
        # so somebody reading it later does not have to find the log
        doc.db_set({"last_status": _("Could not reach BioTime"),
                    "last_error": str(error)[:500], "last_run": now_datetime()},
                   update_modified=False)
        frappe.db.commit()
        raise
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
