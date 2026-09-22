"""Verify the BioTime integration, without a bench:

    python scripts/verify_biotime.py

Luuka's attendance is read from BioTime — ZKTeco's own server, which the
machines push their punches to — rather than by dialling each machine.
Integration case 2 of the testing workbook.

  1  the window, the paging, and what a transaction becomes
  2  the paper: the server record, and the machine that still owns the door
  3  the glue reads BioTime and writes the same log everything else reads
  4  wiring: hourly, and the direct poll leaves BioTime's machines alone

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import datetime
import glob
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    if len(got) != len(needles):
        fail.append("%s: expected %d error(s), got %s" % (label, len(needles), got))
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


def hooks_dict():
    tree = ast.parse(read("hrms_addon", "hooks.py"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


B = load("biotime_rules")
Z = load("zkteco_rules")
hooks = hooks_dict()
print("loaded biotime_rules.py without Frappe")

# ── 1. The address ────────────────────────────────────────────────────
if B.base_url("https://biotime.luuka.co.ug:8098/") != "https://biotime.luuka.co.ug:8098":
    fail.append("a trailing slash is not part of the address")
if B.base_url("biotime.luuka.co.ug") is not None:
    fail.append("an address with no scheme is refused: a password is being sent over it")
if B.base_url("  ") is not None:
    fail.append("and so is no address at all")
if B.endpoint("https://x", "/api-token-auth/") != "https://x/api-token-auth/":
    fail.append("the sign-in endpoint is the address plus the path: %s"
                % B.endpoint("https://x", "/api-token-auth/"))
if B.endpoint("https://x/", "iclock/api/transactions") != "https://x/iclock/api/transactions/":
    fail.append("however the two are punctuated")

# ── 2. The window ─────────────────────────────────────────────────────
now = datetime.datetime(2026, 9, 22, 9, 0, 0)
first = B.window(None, now, first_pull_days=7)
if first["start"] != "2026-09-15 09:00:00" or first["end"] != "2026-09-22 09:00:00":
    fail.append("a first read reaches back the days it is told to: %s" % first)
again = B.window("2026-09-22 08:30:00", now)
if again["start"] != "2026-09-22 08:29:00":
    fail.append("a later read overlaps the one before by a minute, so a punch written a moment "
                "after a run is not lost between two of them: %s" % again)
if again["end"] != "2026-09-22 09:00:00":
    fail.append("and reads up to now")
ahead = B.window("2026-09-23 00:00:00", now)
if ahead["start"] > ahead["end"]:
    fail.append("a last sync in the future must not ask BioTime for a window back to front")
if B.OVERLAP_SECONDS <= 0:
    fail.append("without an overlap a punch can fall between two pulls")

params = B.query("2026-09-22 08:00:00", "2026-09-22 09:00:00", page=2, page_size=50)
if params != {"start_time": "2026-09-22 08:00:00", "end_time": "2026-09-22 09:00:00",
              "page": 2, "page_size": 50}:
    fail.append("BioTime is asked by start_time, end_time, page and page_size: %s" % params)

# ── 3. The paging ─────────────────────────────────────────────────────
page = {"count": 3, "next": "http://x?page=2", "data": [{"a": 1}]}
if B.rows_of(page) != [{"a": 1}]:
    fail.append("the transactions sit under data")
if B.rows_of({"results": [{"a": 1}]}) != [{"a": 1}]:
    fail.append("a version that calls them results is read too")
if B.rows_of(None) != [] or B.rows_of({}) != []:
    fail.append("nothing readable is no rows, not a crash")
if B.next_page(page, 1, seen=1) != 2:
    fail.append("a page that says there is another is followed")
if B.next_page({"count": 1, "next": None, "data": [{"a": 1}]}, 1, seen=1) is not None:
    fail.append("and one that says there is not, is not")
if B.next_page({"data": []}, 1, seen=0) is not None:
    fail.append("an empty page ends the walk whatever it claims, or a broken `next` is read "
                "for ever")
if B.next_page(page, B.MAX_PAGES, seen=1) is not None:
    fail.append("and there is a ceiling on how many pages are asked for")

# ── 4. What a transaction becomes ─────────────────────────────────────
row = {"emp_code": "101", "punch_time": "2026-09-22 07:14:03", "punch_state": "0",
       "punch_state_display": "Check In", "terminal_sn": "CGE8231", "terminal_alias": "Gate A"}
became = B.row_to_log(row)
if became["device_user_id"] != "101":
    fail.append("the badge is BioTime's employee code: %s" % became)
if became["punch_time"] != "2026-09-22 07:14:03":
    fail.append("and the moment is the punch time")
if became["punch"] != 0:
    fail.append("the punch state is a number, so the direction rules can read it")
if became["terminal_serial"] != "CGE8231" or became["terminal_name"] != "Gate A":
    fail.append("and the terminal is named, so the machine on the wall can be found")
if B.row_to_log({"emp_code": 7, "punch_time": "2026-09-22T07:14:03"})["punch_time"] \
        != "2026-09-22 07:14:03":
    fail.append("a time written with a T in it is still a time")

expect("a usable transaction", B.row_errors(row))
expect("one with no badge", B.row_errors(dict(row, emp_code="  ")), "no employee code")
expect("one with no time", B.row_errors(dict(row, punch_time=None)), "no punch time")

found = B.readings([dict(row, punch_time="2026-09-22 09:00:00"),
                    dict(row, emp_code=None),
                    dict(row, punch_time="2026-09-22 07:00:00")])
if len(found["readings"]) != 2 or len(found["skipped"]) != 1:
    fail.append("an unusable transaction is set aside and named, not dropped: %s" % found)
if found["readings"][0]["punch_time"] > found["readings"][1]["punch_time"]:
    fail.append("the punches come back in the order they happened, which is how the pairing "
                "downstream reads them")
if not found["skipped"][0].get("why"):
    fail.append("and what was wrong with the one set aside is said")

terminals = B.terminals_of(found["readings"])
if terminals != {"CGE8231": "Gate A"}:
    fail.append("the terminals a batch came from are listed once each: %s" % terminals)

# the punch codes are ZKTeco's own, so nothing about direction is repeated
for code in (0, 1, 2, 3, 4, 5):
    if code not in Z.PUNCH_DIRECTION:
        fail.append("punch state %s is not one zkteco_rules knows: the two must agree" % code)
if "PUNCH_DIRECTION" in read("hrms_addon", "hrms_addon", "biotime_rules.py"):
    fail.append("the direction map belongs to zkteco_rules; do not keep a second copy")
print("the reading: the window, the paging, and a transaction turned into a punch")

# ── 5. The settings ───────────────────────────────────────────────────
good = {"enabled": 1, "base_url": "https://biotime.luuka.co.ug:8098", "username": "hrms",
        "has_password": True, "verify_tls": 1, "page_size": 200}
expect("a complete server record", B.settings_errors(good))
expect("switched off, nothing is asked of it", B.settings_errors(dict(good, enabled=0)))
expect("no address", B.settings_errors(dict(good, base_url="biotime.luuka.co.ug")),
       "starting http:// or https://")
expect("no user", B.settings_errors(dict(good, username=None)), "which BioTime user")
expect("no password", B.settings_errors(dict(good, has_password=False)), "needs a password")
expect("verifying a certificate that is not there",
       B.settings_errors(dict(good, base_url="http://10.0.0.5:8098")),
       "no certificate to verify")
expect("a page of nothing", B.settings_errors(dict(good, page_size=0)), "not a page")

expect("a token", B.token_errors({"token": "abc"}))
expect("no token and a reason", B.token_errors({"non_field_errors": ["Unable to log in"]}),
       "Unable to log in")
expect("no token and no reason", B.token_errors({}), "without saying why")
expect("not even json", B.token_errors("<html>"), "anything we could read")
print("the settings: an address we will send a password over, and a user that can read")

# ── 6. The paper ──────────────────────────────────────────────────────
server = fields_of(doctype("BioTime Server"))
if not doctype("BioTime Server").get("issingle"):
    fail.append("Luuka have one BioTime: the record is a Single")
for fieldname in ("enabled", "base_url", "username", "password", "verify_tls", "page_size",
                  "first_pull_days", "auth_path", "transactions_path", "last_sync",
                  "last_status", "last_error", "terminals_seen"):
    if fieldname not in server:
        fail.append("the server record has no %s" % fieldname)
if server.get("password", {}).get("fieldtype") != "Password":
    fail.append("the password is a Password field, not a Data one")
for fieldname in ("last_sync", "last_status", "last_error", "terminals_seen"):
    if not server.get(fieldname, {}).get("read_only"):
        fail.append("%s is written by the pull, not typed" % fieldname)
for fieldname, default in (("auth_path", B.AUTH_PATH),
                           ("transactions_path", B.TRANSACTIONS_PATH)):
    if server.get(fieldname, {}).get("default") != default:
        fail.append("%s must default to what BioTime 8.5 uses (%s), so a different version is "
                    "a setting and not a code change" % (fieldname, default))

device = fields_of(doctype("Attendance Device"))
if "source" not in device:
    fail.append("a machine must say whether its punches are dialled or come from BioTime")
if set((device.get("source", {}).get("options") or "").split("\n")) != {"Direct", "BioTime"}:
    fail.append("a machine is read Direct or through BioTime: %s" % device.get("source"))
if device.get("source", {}).get("default") != "Direct":
    fail.append("a machine already on the wall keeps being dialled unless somebody says "
                "otherwise")
if device.get("host", {}).get("reqd"):
    fail.append("a BioTime terminal has no address of its own to give: host must not be "
                "unconditionally mandatory")
if "BioTime" not in (device.get("host", {}).get("mandatory_depends_on") or ""):
    fail.append("but a machine this app dials still needs one")
for fieldname in ("serial_number", "direction", "branch"):
    if fieldname not in device:
        fail.append("the machine on the wall still owns its %s" % fieldname)
# a machine fed by BioTime has no address of its own, and must not be
# asked for one: that would refuse the record biotime.py makes for a
# terminal it has just seen for the first time
expect("a machine this app dials", Z.device_errors(
    {"device_name": "Gate A", "source": "Direct", "host": "10.0.0.7", "port": 4370,
     "direction": "In and Out"}))
expect("one dialled with no address", Z.device_errors(
    {"device_name": "Gate A", "source": "Direct", "port": 4370, "direction": "In and Out"}),
    "IP address or host name")
expect("one fed by BioTime", Z.device_errors(
    {"device_name": "Gate A", "source": "BioTime", "serial_number": "CGE8231",
     "direction": "In and Out"}))
expect("one fed by BioTime with no serial", Z.device_errors(
    {"device_name": "Gate A", "source": "BioTime", "direction": "In and Out"}),
    "found by its serial number")
# an unrecognised source is named as such and the machine is treated as
# dialled, which is the safe way round: it asks for an address rather than
# quietly trusting a server nobody configured
said = Z.device_errors({"device_name": "Gate A", "source": "Telepathy", "serial_number": "X",
                        "direction": "In and Out"})
if not any("A machine is read" in message for message in said):
    fail.append("a source that is neither must be named: %s" % said)
if not any("IP address" in message for message in said):
    fail.append("and the machine treated as one this app dials")
if Z.dialled(None) is not True:
    fail.append("a machine with no source set yet is dialled, as it always was")
if Z.dialled("BioTime"):
    fail.append("and one fed by BioTime is not")
print("the paper: one server record, and the machine that still owns the door")

# ── 7. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "biotime.py")
known = set(server) | set(device) | {"doctype", "name", "flags", "base_url", "username"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update", "get_password"):
        continue
    if fieldname not in known:
        fail.append("biotime.py reads or writes %s, which is on neither record" % fieldname)
for needle, why in (
    ("rules.window(", "the span comes from the rules"),
    ("rules.query(", "and so does what BioTime is asked"),
    ("rules.next_page(", "and when to stop asking"),
    ("rules.readings(", "and what a transaction becomes"),
    ("rules.token_errors(", "and what BioTime said when it would not sign us in"),
    ("punch_rules.dedupe(", "a face read twice is still one reading"),
    ("punch_rules.resolve(", "and the direction is still ZKTeco's own rule"),
    ("devices._write_log(", "a punch is still written down before anything is made of it"),
    ("devices._push(", "and pushed into Employee Checkin the same way"),
    ("devices._standing(", "an unmarked punch still carries on from where the employee is"),
    ("get_password(", "the password is read out of the vault, never off the field"),
    ("import requests", "the library is imported where it is used, so a site without a "
                        "BioTime still migrates"),
):
    if needle not in glue:
        fail.append("biotime.py: %s (%r not found)" % (why, needle))
if "per_device=True" not in glue:
    fail.append("two terminals a minute apart are two doors, not one double read: the collapse "
                "must be per machine")
for name in ("test_connection", "pull"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("biotime.%s reaches out and writes: a whitelisted POST method" % name)
if glue.count("check_permission(") < 2:
    fail.append("each whitelisted method must check the caller may act")
if "verify=" not in glue or "verify_tls" not in glue:
    fail.append("whether the certificate is verified is the site's choice and must be honoured")
controller = read("hrms_addon", "hrms_addon", "doctype", "biotime_server", "biotime_server.py")
if "    def validate(self):\n        biotime.settings_validate(self)" not in controller:
    fail.append("the server controller must hand validate to biotime.settings_validate")
# nothing about a punch's meaning is decided twice
if "PUNCH_MEANING" in glue:
    fail.append("what a punch means belongs to zkteco_rules; do not keep a second copy")
print("glue: BioTime read, the same log written, nothing about a punch decided twice")

# ── 8. Wiring ─────────────────────────────────────────────────────────
hourly = hooks.get("scheduler_events", {}).get("hourly", [])
if "hrms_addon.hrms_addon.biotime.pull_all" not in hourly:
    fail.append("the BioTime pull runs hourly, beside the direct one")
if "hrms_addon.hrms_addon.devices.pull_all" not in hourly:
    fail.append("and a machine still dialled directly is still dialled")
direct = read("hrms_addon", "hrms_addon", "devices.py")
if '"source": ["!=", "BioTime"]' not in direct:
    fail.append("the direct poll must leave BioTime's machines alone, or every punch is read "
                "twice")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if "BioTime Server" not in nav:
    fail.append("the server record has no way in")
if not os.path.exists(os.path.join(APP, "doctype", "biotime_server", "biotime_server.js")):
    fail.append("the server record has no form script, so nobody can test the connection")
# ── 7b. A server that will not answer says so in words ────────────────
# A raw SSLError or ConnectionError reaches the desk as a Python traceback,
# which is what happened the first time this was pointed at a BioTime
# speaking plain HTTP on an https:// address.
if "def _reach(" not in glue:
    fail.append("every request must go through one place that explains a failure")
reach = glue.split("def _reach(")[1].split(chr(10) + "def ")[0]
for needle, why in (
    ("SSLError", "a TLS mismatch is the one people hit first"),
    ("WRONG_VERSION_NUMBER", "and https:// onto a plain-HTTP server is named by its symptom"),
    ("ConnectTimeout", "a server that never picks up"),
    ("ReadTimeout", "and one that picks up and says nothing are different problems"),
    ("ConnectionError", "a wrong address or a closed port"),
    ("RequestException", "and anything else still gets a sentence rather than a traceback"),
):
    if needle not in reach:
        fail.append("_reach does not handle %s: %s" % (needle, why))
if "frappe.throw" not in reach:
    fail.append("_reach must throw a message, not re-raise the library's exception")
# every outbound request goes through it
for call in ("requests.post(", "session.get("):
    for line in glue.split(chr(10)):
        if call in line and "_reach" not in line and "lambda" not in line:
            fail.append("%s is called outside _reach, so its failure would reach the desk raw"
                        % call.rstrip("("))
            break
# and a failed test says so on the record, as a pull already does
tested = glue.split("def test_connection")[1].split(chr(10) + "def ")[0]
if "last_error" not in tested:
    fail.append("a failed Test the Connection must be written on the record, so somebody "
                "reading it later does not have to go to the log")
if "raise" not in tested:
    fail.append("and still reach the person who pressed the button")
print("failure: a server that will not answer is explained, and written down")

print("wiring: hourly, beside the direct poll, and never reading a punch twice")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL BIOTIME CHECKS PASSED")
