# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The documents an employee must hold, and when they run out.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_documents.py exercises them without a bench.

Alerts, Documents & Notifications, case 1: rule-based alerts for document
expiry — the national ID, a driving permit, a work permit. Contract and
probation expiry are already watched (contracts.py, probation.py); this is
the rest of what an employee has to hold to keep working.

ONE ROW PER DOCUMENT, NOT ONE FIELD PER KIND

A field per document kind means a schema change every time Luuka add one,
and a driver with two permits has nowhere to put the second. So the
documents are rows on the employee, each naming its type, and the type
carries the policy: how long before it runs out somebody should be told,
whether it can be renewed, and who has to hold one at all.

THE THRESHOLDS

A document is chased on the same ladder a contract is (contract_rules):
three months, one month, a week, and the day it goes. Each threshold is
crossed once — a document first seen inside several of them raises one
alert, for the nearest, not four.
"""

import datetime

# days before expiry at which somebody is told, widest first
THRESHOLDS = (90, 30, 7, 0)
DEFAULT_NOTICE_DAYS = 90

VALID, EXPIRING, EXPIRED, MISSING, NOT_REQUIRED = (
    "Valid", "Expiring Soon", "Expired", "Missing", "Not Required")

# who a type applies to
EVERYBODY, FOREIGN, DRIVERS, MACHINE = (
    "All Employees", "Foreign Nationals", "Drivers", "Machine Operators")
APPLIES_TO = (EVERYBODY, FOREIGN, DRIVERS, MACHINE)

# the types seeded, with their notice in days and whether one runs out at
# all. A national ID does not expire for a Ugandan; a work permit does,
# and losing track of it stops somebody working.
SEEDED_TYPES = (
    ("National ID (NIN)", EVERYBODY, 90, 0, 1),
    ("Passport", EVERYBODY, 180, 1, 0),
    ("Work Permit", FOREIGN, 90, 1, 1),
    # a special pass stands in place of a work permit, not beside one,
    # so it is watched where it is held and demanded of nobody
    ("Special Pass", FOREIGN, 30, 1, 0),
    ("Driving Permit", DRIVERS, 60, 1, 1),
    ("Certificate of Good Conduct", EVERYBODY, 90, 1, 0),
    ("Medical Certificate", MACHINE, 60, 1, 1),
    ("Academic Certificate", EVERYBODY, 0, 0, 0),
)


def status_of(expires_on, today, notice_days=DEFAULT_NOTICE_DAYS, number=None):
    """Where a document stands on a day."""
    if not number and not expires_on:
        return MISSING
    if not expires_on:
        return VALID
    left = days_left(expires_on, today)
    if left < 0:
        return EXPIRED
    if left <= int(notice_days or DEFAULT_NOTICE_DAYS):
        return EXPIRING
    return VALID


def days_left(expires_on, today):
    return (_date(expires_on) - _date(today)).days


def threshold_crossed(expires_on, today, already=None, thresholds=THRESHOLDS):
    """The nearest threshold a document has reached and nobody has been
    told about. None where it is not due, or where the alert has gone.

    `already` is the widest threshold an alert has gone out for, so a
    document first seen inside several raises one, not four.
    """
    if not expires_on:
        return None
    left = days_left(expires_on, today)
    if left < 0:
        return None
    reached = [days for days in thresholds if left <= days]
    if not reached:
        return None
    nearest = min(reached)
    if already is not None and int(already) <= nearest:
        return None
    return nearest


def expired_today(expires_on, today):
    return bool(expires_on) and days_left(expires_on, today) == -1


def required_for(applies_to, facts):
    """Whether a type's document is one this employee has to hold."""
    if applies_to in (None, "", EVERYBODY):
        return True
    if applies_to == FOREIGN:
        return bool(facts.get("is_foreign"))
    if applies_to == DRIVERS:
        return bool(facts.get("drives"))
    if applies_to == MACHINE:
        return bool(facts.get("operates_machinery"))
    return True


def document_errors(facts):
    errors = []
    if not facts.get("document_type"):
        errors.append("Say which document this is.")
    if not facts.get("number"):
        errors.append("A document with no number on it is not on record.")
    if facts.get("issued_on") and facts.get("expires_on") \
            and str(facts["expires_on"]) < str(facts["issued_on"]):
        errors.append("A document cannot run out before it was issued.")
    if facts.get("expires_required") and not facts.get("expires_on"):
        errors.append("%s runs out. Say when." % (facts.get("document_type") or "This document"))
    return errors


def missing(required, held):
    """The documents an employee must hold and does not. required: [(type,
    applies_to)]; held: {type: number}."""
    return [name for name, applies_to in required or ()
            if not (held or {}).get(name)]


def type_errors(facts):
    errors = []
    if not facts.get("document_name"):
        errors.append("Give the document type a name.")
    if facts.get("applies_to") and facts["applies_to"] not in APPLIES_TO:
        errors.append("A type applies to %s." % ", ".join(APPLIES_TO))
    if facts.get("expires") and not int(facts.get("notice_days") or 0):
        errors.append("A document that runs out needs a notice period, or nobody is told.")
    return errors


def chase(rows, today):
    """Which rows are due to be chased, and on which threshold. Oldest
    expiry first, because that is the one somebody should do first."""
    due = []
    for row in rows or []:
        threshold = threshold_crossed(row.get("expires_on"), today, row.get("alerted_at"),
                                      thresholds=_thresholds(row.get("notice_days")))
        if threshold is None:
            continue
        due.append(dict(row, threshold=threshold, days_left=days_left(row["expires_on"], today)))
    return sorted(due, key=lambda row: str(row.get("expires_on")))


def _thresholds(notice_days):
    """A type with its own notice period is chased from there down."""
    notice = int(notice_days or 0)
    if not notice:
        return THRESHOLDS
    return tuple(sorted({notice, *[days for days in THRESHOLDS if days < notice]},
                        reverse=True))


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
