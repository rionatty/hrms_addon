# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""My Alerts rail: which of a user's alerts is urgent, and in what order.

No Frappe import, like the other *_rules.py modules, so scripts/verify_alerts.py
exercises them without a bench.

The rail shows one person their own work: the assignments on their ToDo
list (an onboarding task, a review due, a probation evaluation, a contract
coming to its end) and the notifications they have not read. What has been
attended to leaves it: a notification once read (opening its document
reads it), an assignment once its work is done (attended). Each row is
coloured by how soon it matters, not by what kind of thing it is:

    overdue   its date has passed
    today     due today or tomorrow, or a High priority assignment
    soon      due within the week
    later     due after that
    none      nothing is due (most notifications)

A High priority assignment is never quieter than `today`: HR sets that by
hand, and it would be strange for it to sit below a task due in a week.
"""

import datetime

OVERDUE, TODAY, SOON, LATER, NONE = "overdue", "today", "soon", "later", "none"
# most urgent first: the order rows are sorted in and the rail is counted by
BANDS = (OVERDUE, TODAY, SOON, LATER, NONE)
# the toast Frappe shows when one arrives (frappe.show_alert indicators)
INDICATORS = {OVERDUE: "red", TODAY: "orange", SOON: "blue", LATER: "blue", NONE: "gray"}
SOON_DAYS = 7
HIGH = "High"
ASSIGNMENT, NOTIFICATION = "assignment", "notification"
KINDS = (ASSIGNMENT, NOTIFICATION)
# The app's own Notification Type. Frappe v16 emails a notification of any
# type but its own "Alert" (notification_skip_email_types), as each user has
# chosen in Notification Settings; the app's alerts go as this type so they
# reach the person by email too (people.notify).
EMAILED_TYPE = "HR Alert"


def attended(facts):
    """Whether an assignment's work is done, so it leaves the rail and its
    ToDo is closed: the document is gone or cancelled, or it runs on a
    workflow that no longer waits on this user. An assignment on a document
    without a workflow stays until the user marks it done.

    facts: "exists", "docstatus", "workflow" (the document has an active
    workflow and a state in it), "can_act" (the user has a step to take)."""
    if not facts.get("exists"):
        return True
    if facts.get("docstatus") == 2:
        return True
    return bool(facts.get("workflow")) and not facts.get("can_act")


def urgency(due, today, priority=None):
    """Which band an alert falls in (BANDS)."""
    band = NONE
    if due:
        left = days_left(due, today)
        if left < 0:
            band = OVERDUE
        elif left <= 1:
            band = TODAY
        elif left <= SOON_DAYS:
            band = SOON
        else:
            band = LATER
    return at_least(band, TODAY) if priority == HIGH else band


def at_least(band, floor):
    """The more urgent of the two bands."""
    return band if BANDS.index(band) <= BANDS.index(floor) else floor


def days_left(due, today):
    return (_date(due) - _date(today)).days


def when(due, today):
    """How soon it is due, as the row says it ("" when nothing is due)."""
    if not due:
        return ""
    left = days_left(due, today)
    if left < -1:
        return "overdue by %d days" % -left
    return {-1: "overdue by a day", 0: "due today", 1: "due tomorrow"}.get(left, "in %d days" % left)


def order(alerts, today):
    """The alerts most urgent first: by band, then by the soonest due date,
    and the newest first among equals — which is the order the notifications
    themselves read in, since none of them is due on a date.
    `alerts`: [{"urgency", "due", "created"}]."""
    def key(alert):
        due = alert.get("due")
        return (
            BANDS.index(alert.get("urgency") or NONE),
            days_left(due, today) if due else 10 ** 6,
        )

    newest_first = sorted(alerts, key=lambda alert: _text(alert.get("created")), reverse=True)
    return sorted(newest_first, key=key)  # a stable sort keeps the newest first within a band


def counts(alerts):
    """{band: how many}, every band present, plus "total"."""
    tally = {band: 0 for band in BANDS}
    for alert in alerts:
        tally[alert.get("urgency") or NONE] = tally.get(alert.get("urgency") or NONE, 0) + 1
    tally["total"] = len(alerts)
    return tally


def badge(alerts):
    """(how many, the band colouring the rail's count): the most urgent band
    anything is in, so the badge says at a glance whether something is late."""
    worst = NONE
    for alert in alerts:
        worst = at_least(alert.get("urgency") or NONE, worst)
    return len(alerts), worst


def title(text, limit=120):
    """One line for the row: no markup, no runs of blank space, cut short
    on a word where it is too long for the rail."""
    text = " ".join(_text(text).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def _text(value):
    return "" if value is None else str(value)


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
