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

# BioTime has shipped more than one sign-in endpoint, and they do not mint
# the same kind of token. /api-token-auth/ is the old one; the newer API is
# guarded by Django REST Framework's SimpleJWT, which refuses a token it
# did not mint with "Given token not valid for any token type". When that
# happens the sign-in worked and the token is simply the wrong sort — the
# answer is a different path, not a different password.
AUTH_PATH_CANDIDATES = (
    "/api-token-auth/",
    "/jwt-api-token-auth/",
    "/api/token/",
    "/api-token-auth/token/",
)
# where the token sits in the answer, in the order they are looked for
TOKEN_KEYS = ("token", "access", "access_token")
# what the Authorization header calls it. SimpleJWT's own default is
# Bearer; BioTime has used JWT.
PREFIXES = ("JWT", "Bearer", "Token")
DEFAULT_PREFIX = "JWT"
# SimpleJWT's own code for a token it will not accept, and the sentence it
# sends with it — a build that drops the code still says the sentence
TOKEN_REJECTED = "token_not_valid"
TOKEN_REJECTED_SAID = "not valid for any token type"

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
    is not a punch, and nothing downstream could place it.

    A time that cannot be read is checked HERE rather than left to the
    first thing that parses it. One transaction carrying an epoch integer
    or 0000-00-00 would otherwise raise out of the middle of a pull and
    take the whole batch with it — and then every hourly run after it,
    because the window would keep reaching back over the same bad row.
    """
    errors = []
    if not str(row.get(FIELDS["badge"]) or "").strip():
        errors.append("a transaction with no employee code on it")
    if not row.get(FIELDS["punch_time"]):
        errors.append("a transaction with no punch time on it")
    elif not readable(row.get(FIELDS["punch_time"])):
        errors.append("a transaction whose punch time could not be read: %s"
                      % str(row.get(FIELDS["punch_time"]))[:40])
    return errors


def readable(value):
    """Whether a punch time is a time at all."""
    try:
        _moment(_punch_time(value))
    except (ValueError, TypeError):
        return False
    return True


def key_of(punch):
    """What makes a punch the same punch: the machine, the badge, the
    second it happened."""
    return (punch.get("device"), str(punch.get("device_user_id") or ""),
            str(punch.get("time"))[:19])


def unseen(punches, seen):
    """Only the punches that have not been written down already.

    The window overlaps the last pull on purpose, so a punch BioTime had
    not yet stored when we last looked is caught. That overlap means the
    previous run's own punches come back too, and they must not be put
    through the direction rules a second time: those rules alternate IN
    and OUT from what is standing, so re-reading one punch flips every
    punch after it. Which are new is a question about what is written
    down, not about the clock.
    """
    seen = seen or set()
    return [punch for punch in punches or [] if key_of(punch) not in seen]


def high_water(newest, held=None, floor=None):
    """How far a pull may say it has read.

    Never past a punch it could not write down — the next window starts
    where this one stopped, so a punch left behind by a terminal nobody
    has a record for would fall outside every window after it and be lost
    without anybody being told. And never backwards, which would read the
    same days for ever.
    """
    if newest is None:
        return _moment(floor) if floor is not None else None
    mark = _moment(newest)
    if held is not None:
        limit = _moment(held) - datetime.timedelta(seconds=1)
        if mark > limit:
            mark = limit
    if floor is not None and mark < _moment(floor):
        mark = _moment(floor)
    return mark


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


def token_of(payload):
    """The token in a sign-in answer, wherever this BioTime puts it."""
    if not isinstance(payload, dict):
        return None
    for key in TOKEN_KEYS:
        value = payload.get(key)
        if value:
            return str(value)
    return None


def header(token, prefix=DEFAULT_PREFIX):
    return {"Authorization": "%s %s" % (prefix or DEFAULT_PREFIX, token)}


def token_rejected(payload):
    """Whether a 401 means the token was refused rather than missing.

    SimpleJWT answers {"detail": ..., "code": "token_not_valid"} when it
    parsed the header and would not accept what was in it — which, right
    after a sign-in that worked, means the sign-in minted the wrong sort of
    token.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("code") == TOKEN_REJECTED:
        return True
    said = str(payload.get("detail") or "")
    return TOKEN_REJECTED in said or TOKEN_REJECTED_SAID in said


def token_errors(payload):
    """What BioTime said when it would not hand over a token."""
    if not isinstance(payload, dict):
        return ["BioTime did not answer with anything we could read."]
    if token_of(payload):
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
