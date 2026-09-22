# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Reading Luuka's clockings out of BioTime instead of off each machine.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_biotime.py exercises them without a bench.

WHAT CHANGES, AND WHAT DOES NOT

Only the transport. BioTime is ZKTeco's own server: the machines push
their punches to it, and it holds the lot. So instead of this app dialling
each machine over the ZK protocol (devices.py), it asks BioTime once for
every punch since the last pull.

Everything after that is unchanged. A punch still becomes an Attendance
Device Log row first and an Employee Checkin second, the same double-read
collapsing applies, an unknown badge is still listed rather than dropped,
and a row that failed to push is still retried without going back to the
source. The machine on the wall is still an Attendance Device record,
because that is where its branch and its direction live — BioTime knows
which terminal a punch came from, not which door it guards.

The punch codes are the same 0 to 5 ZKTeco uses, so zkteco_rules decides
the direction. Nothing about that is repeated here.

THE API

BioTime 8.5:

    POST {base}/api-token-auth/            {"username", "password"}
                                           -> {"token": "..."}
    GET  {base}/iclock/api/transactions/   ?start_time=&end_time=&page=&page_size=
                                           Authorization: JWT {token}
                                           -> {"count", "next", "data": [...]}

Both paths are settings on the server record rather than constants here,
because a different BioTime version is a configuration problem and should
not need a developer.

TIME

BioTime answers in its own server's local time and so does this app.
Nothing converts a timezone: if the two machines disagree the punches land
in the wrong hour, which is a deployment check, not something code can
guess at. `window()` overlaps the previous pull by a minute so a punch
written to BioTime a moment after a pull is not lost between two runs.
"""

import datetime

AUTH_PATH = "/api-token-auth/"
TRANSACTIONS_PATH = "/iclock/api/transactions/"
TERMINALS_PATH = "/iclock/api/terminals/"

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PAGE_SIZE = 200
# a runaway page count is a bug, not a big site: BioTime pages at whatever
# page_size asks for, so this is hit only when `next` never goes away
MAX_PAGES = 500
# how far back a pull reaches when BioTime has never been read
FIRST_PULL_DAYS = 7
# the previous pull is re-read by this much, so a punch recorded a moment
# after one run is picked up by the next rather than falling between them
OVERLAP_SECONDS = 60

# what a transaction calls things (BioTime 8.5)
FIELDS = {
    "badge": "emp_code",
    "punch_time": "punch_time",
    "punch": "punch_state",
    "punch_meaning": "punch_state_display",
    "terminal_serial": "terminal_sn",
    "terminal_name": "terminal_alias",
    "area": "area_alias",
}


def base_url(url):
    """The server's address, without a trailing slash and with a scheme we
    are willing to send a password over."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return None
    return url


def endpoint(url, path):
    root = base_url(url)
    if not root:
        return None
    return root + ("/" + path.strip("/") + "/" if path else "/")


def window(last_sync, now, first_pull_days=FIRST_PULL_DAYS, overlap=OVERLAP_SECONDS):
    """The span to ask BioTime for: from just before the last pull to now.

    Never read as having been pulled: a site with no last sync reaches
    back `first_pull_days`, so a first run does not try to read years.
    """
    now = _moment(now)
    if last_sync:
        start = _moment(last_sync) - datetime.timedelta(seconds=int(overlap or 0))
    else:
        start = now - datetime.timedelta(days=int(first_pull_days or FIRST_PULL_DAYS))
    if start > now:
        start = now
    return {"start": start.strftime(TIME_FORMAT), "end": now.strftime(TIME_FORMAT)}


def query(start, end, page=1, page_size=PAGE_SIZE):
    return {"start_time": start, "end_time": end, "page": int(page),
            "page_size": int(page_size or PAGE_SIZE)}


def rows_of(payload):
    """The transactions in a page. BioTime puts them under `data`; a
    version that answers a bare list is read too."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "results"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def next_page(payload, page, seen, total=None):
    """The next page to ask for, or None.

    `next` is trusted where BioTime gives one; otherwise the count decides.
    A page that returned nothing ends the walk whatever either says, which
    is what stops a server with a broken `next` being read forever.
    """
    page = int(page or 1)
    if not rows_of(payload):
        return None
    if page >= MAX_PAGES:
        return None
    if isinstance(payload, dict):
        if payload.get("next"):
            return page + 1
        if payload.get("next") is None and "next" in payload:
            return None
        count = payload.get("count")
        if count is not None and total is not None and int(seen) >= int(count):
            return None
    return page + 1


def row_errors(row):
    """What makes a transaction unusable. A punch with no badge or no time
    is not a punch, and nothing downstream could place it."""
    errors = []
    if not str(row.get(FIELDS["badge"]) or "").strip():
        errors.append("a transaction with no employee code on it")
    if not row.get(FIELDS["punch_time"]):
        errors.append("a transaction with no punch time on it")
    return errors


def row_to_log(row):
    """A BioTime transaction, as the fields of an Attendance Device Log."""
    return {
        "device_user_id": str(row.get(FIELDS["badge"]) or "").strip(),
        "punch_time": _punch_time(row.get(FIELDS["punch_time"])),
        "punch": _int(row.get(FIELDS["punch"])),
        "punch_meaning": row.get(FIELDS["punch_meaning"]) or None,
        "terminal_serial": row.get(FIELDS["terminal_serial"]) or None,
        "terminal_name": row.get(FIELDS["terminal_name"]) or None,
    }


def readings(rows):
    """Every usable transaction as a reading, and what was skipped.

    The order is the order they happened, because everything downstream —
    the double-read collapse, the in-and-out pairing — reads them that way.
    """
    good, skipped = [], []
    for row in rows or []:
        errors = row_errors(row)
        if errors:
            skipped.append({"row": row, "why": "; ".join(errors)})
            continue
        good.append(row_to_log(row))
    good.sort(key=lambda row: (str(row["punch_time"]), row["device_user_id"]))
    return {"readings": good, "skipped": skipped}


def terminals_of(readings_):
    """The terminals a batch of punches came from, so each can be matched
    to the machine on the wall."""
    out = {}
    for row in readings_ or []:
        serial = row.get("terminal_serial")
        if serial and serial not in out:
            out[serial] = row.get("terminal_name")
    return out


def settings_errors(facts):
    errors = []
    if not facts.get("enabled"):
        return errors
    if not base_url(facts.get("base_url")):
        errors.append("Give BioTime's address, starting http:// or https://.")
    if not facts.get("username"):
        errors.append("Say which BioTime user this app signs in as.")
    if not facts.get("has_password"):
        errors.append("That user needs a password.")
    if base_url(facts.get("base_url")) and facts["base_url"].strip().startswith("http://") \
            and facts.get("verify_tls"):
        errors.append("There is no certificate to verify on a plain http:// address. Either "
                      "use https:// or untick the check.")
    if int(facts.get("page_size") or 0) < 1:
        errors.append("A page of no transactions is not a page.")
    return errors


def token_errors(payload):
    """What BioTime said when it would not hand over a token."""
    if not isinstance(payload, dict):
        return ["BioTime did not answer with anything we could read."]
    if payload.get("token"):
        return []
    for key in ("non_field_errors", "detail", "error", "message"):
        said = payload.get(key)
        if said:
            return [str(said[0]) if isinstance(said, list) and said else str(said)]
    return ["BioTime answered without a token and without saying why."]


def _punch_time(value):
    """BioTime writes "2026-09-22 07:14:03". A value already a datetime is
    left as it is."""
    if isinstance(value, datetime.datetime):
        return value
    text = str(value or "").strip().replace("T", " ")
    if not text:
        return None
    return text[:19]


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _moment(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    return datetime.datetime.fromisoformat(str(value)[:19].replace("T", " "))
