# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A leave followed through: its approval chased, its cover checked, and
what changes after it is approved.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_leave_follow.py exercises them without a bench. The glue is
leave_follow.py.

WHAT WAS MISSING (the leave review of 11 Oct 2026)

Luuka's own process was there end to end: the plan, the three signatures,
the advance, the report back. Three things around it were not.

  1  An approval could stall. A leave waiting on a supervisor, a head of
     department or HR was never chased, and an approver on leave took the
     desk away with them. Now the desk is reminded, then the level above
     is told; and while an approver is away, whoever relieves them is
     asked in their place, where they hold the role to sign.

  2  Cover was checked on the annual plan only. An application outside the
     plan, or beside it, could empty a section. Now every application is
     read against who else is off the same days, and names who takes over
     the work.

  3  After approval there was only cancel and apply again. Now a leave is
     ended early (the employee came back, or was recalled) and the days
     not taken go back to the balance; it is extended by a leave of its
     own, approved as any leave is; and one nobody came back from is
     counted as overdue, not left as a note for HR.
"""

import datetime

# ── Settings (Leave Management Settings), and what blank means ────────
DEFAULTS = {
    "remind_after_days": 2,     # the desk is reminded
    "escalate_after_days": 4,   # the level above is told
    "most_off": 0,              # 0: the Annual Leave Plan's own limit
    "cover_blocks": 0,          # planned leave over the limit is refused, not only said
    "reliever_from_days": 0,    # 0: a reliever is never asked for
    "overdue_after_days": 1,    # days past the last day before a leave is overdue
}
LONGEST_WAIT = 60


def settings_from(stored):
    """The settings, what was never saved taking its default. A figure
    saved as 0 is 0: that step is switched off."""
    out = {}
    for key, default in DEFAULTS.items():
        value = (stored or {}).get(key)
        try:
            out[key] = default if value in (None, "") else int(float(value))
        except (TypeError, ValueError):
            out[key] = default
    return out


def settings_errors(settings):
    errors = []
    for key, label in (("remind_after_days", "The reminder"), ("escalate_after_days", "The escalation")):
        if not 0 <= int(settings.get(key) or 0) <= LONGEST_WAIT:
            errors.append("%s comes after between 0 and %d days." % (label, LONGEST_WAIT))
    remind, escalate = int(settings.get("remind_after_days") or 0), int(settings.get("escalate_after_days") or 0)
    if remind and escalate and escalate <= remind:
        errors.append("The level above is told after the desk has been reminded, not before.")
    for key, label in (("most_off", "Most off at once"), ("reliever_from_days", "The reliever's days"),
                       ("overdue_after_days", "Days before a leave is overdue")):
        if int(settings.get(key) or 0) < 0:
            errors.append("%s cannot be less than nothing." % label)
    return errors


# ── 1. An approval that stalls ────────────────────────────────────────
REMINDED, ESCALATED = "Reminded", "Escalated"
# who hears of a leave its desk has not moved: the level above
LEVEL_ABOVE = {"Supervisor": "Head of Department", "Head of Department": "HR User", "HR User": "HR Manager"}


def days_waiting(since, today):
    """How many days a leave has been on its desk."""
    since, today = _date(since), _date(today)
    if not since or not today:
        return 0
    return max((today - since).days, 0)


def chase(since, today, told, remind_after, escalate_after):
    """What is due on a leave still on its desk: ESCALATED once it has
    waited `escalate_after` days, REMINDED once `remind_after`, each said
    once. None when nothing is due, or the step is switched off (0)."""
    waited = days_waiting(since, today)
    if int(escalate_after or 0) > 0 and waited >= int(escalate_after):
        return None if told == ESCALATED else ESCALATED
    if int(remind_after or 0) > 0 and waited >= int(remind_after):
        return None if told in (REMINDED, ESCALATED) else REMINDED
    return None


def at_the_desk(desk, away=None, able=()):
    """Who is asked to act on a leave at a desk today.

    desk: the users whose desk it is. away: {user: {"until": date,
    "stand_in": user or None}} for those of them on leave today. able: the
    users who hold a role that may sign at this desk.

    Somebody at their desk is asked. Somebody away is not: whoever relieves
    them is, where they may sign (and are not away themselves). Returns
    {"ask": [users], "standing_in": {stand-in: who for}, "empty": nobody
    is there to ask, so the level above must hear of it now}.
    """
    away, able = away or {}, set(able or ())
    ask, standing_in = [], {}
    for user in desk or []:
        if user not in away:
            if user not in ask:
                ask.append(user)
            continue
        stand_in = (away[user] or {}).get("stand_in")
        if stand_in and stand_in in able and stand_in not in away:
            standing_in.setdefault(stand_in, user)
    for stand_in in standing_in:
        if stand_in not in ask:
            ask.append(stand_in)
    # somebody at this desk in their own right is asked as that, not as a stand-in
    return {"ask": ask, "standing_in": {user: who for user, who in standing_in.items() if user not in (desk or [])},
            "empty": not ask}


# ── 2. Cover ──────────────────────────────────────────────────────────
# leave that is planned, and so can wait for a day the section can spare
# (leave_rules.ANNUAL, leave_rules.UNPAID): sickness, a birth and a death
# do not wait, and are never refused for cover
PLANNED_LEAVE = ("Annual Leave", "Leave Without Pay")


def cover_refused(leave_type, clashes, blocks):
    """Whether a leave is refused for leaving its department short: only
    where Luuka have said so, and only leave that can wait."""
    return bool(clashes) and bool(int(blocks or 0)) and leave_type in PLANNED_LEAVE


def reliever_errors(facts):
    """Problems with who takes over the work.

    facts: "employee", "reliever", "reliever_name", "reliever_status",
    "reliever_away" (they are on leave themselves in those days), "days",
    "needed_from" (a reliever is asked for from this many days; 0 never).
    """
    errors = []
    reliever = facts.get("reliever")
    needed = int(facts.get("needed_from") or 0)
    if not reliever:
        if needed and float(facts.get("days") or 0) >= needed:
            errors.append("Name who takes over the work: a leave of %d day(s) or more needs a reliever." % needed)
        return errors
    who = facts.get("reliever_name") or reliever
    if reliever == facts.get("employee"):
        errors.append("Nobody relieves themselves: name somebody else.")
    elif facts.get("reliever_status") not in (None, "", "Active"):
        errors.append("%s is not in service (%s), so cannot take over the work." % (who, facts["reliever_status"]))
    elif facts.get("reliever_away"):
        errors.append("%s is on leave in those days too, so cannot take over the work." % who)
    return errors


# ── 3. What changes after approval ────────────────────────────────────
RECALLED, RETURNED, EXTENSION = "Recalled", "Returned Early", "Extension"
ENDED_EARLY = (RECALLED, RETURNED)
CHANGE_KINDS = (RECALLED, RETURNED, EXTENSION)


def end_early_errors(facts):
    """Problems with ending an approved leave early.

    facts: "docstatus", "status", "from_date", "to_date", "last_day" (the
    last day of leave taken), "kind", "reason".
    """
    errors = []
    if facts.get("docstatus") != 1 or facts.get("status") != "Approved":
        errors.append("Only an approved leave is ended early.")
        return errors
    if facts.get("kind") not in ENDED_EARLY:
        errors.append("Say whether the employee was recalled or came back early.")
    first, last, upto = _date(facts.get("from_date")), _date(facts.get("to_date")), _date(facts.get("last_day"))
    if not upto:
        errors.append("Give the last day of leave taken.")
    elif upto >= last:
        errors.append("The leave already ends on %s. Give an earlier last day." % _day(last))
    elif upto < first:
        errors.append("A leave not started is cancelled, not ended early: the first day is %s." % _day(first))
    if not str(facts.get("reason") or "").strip():
        errors.append("Say why the leave ends early.")
    return errors


def given_back(to_date, last_day):
    """(first, last) of the days an ended leave gives back, or None."""
    last, upto = _date(to_date), _date(last_day)
    if not last or not upto or upto >= last:
        return None
    return upto + datetime.timedelta(days=1), last


def extension_errors(facts):
    """Problems with extending a leave.

    facts: "docstatus", "status", "to_date", "new_to", "reason".
    """
    errors = []
    if facts.get("docstatus") != 1 or facts.get("status") != "Approved":
        errors.append("Only an approved leave is extended.")
        return errors
    last, upto = _date(facts.get("to_date")), _date(facts.get("new_to"))
    if not upto:
        errors.append("Give the new last day.")
    elif upto <= last:
        errors.append("The leave already runs to %s. Give a later last day." % _day(last))
    if not str(facts.get("reason") or "").strip():
        errors.append("Say why the leave is extended.")
    return errors


def extension_window(to_date, new_to):
    """(first, last) of the leave an extension applies for: the day after
    the leave ends, to the new last day."""
    return _date(to_date) + datetime.timedelta(days=1), _date(new_to)


def back_on(to_date, worked_days):
    """The day somebody came back from a leave, by the clock: the first day
    after its last on which they were at work. None while there is none."""
    last = _date(to_date)
    after = sorted(day for day in (_date(value) for value in worked_days or ()) if day and last and day > last)
    return after[0] if after else None


def overdue_days(to_date, today, reported_back=False, extended_to=None, after_days=1):
    """How many days somebody is overdue from a leave: the days past its
    last day (or the last day of its extension) with nobody having said,
    and no clock having shown, that they are back. Nothing until
    `after_days` have passed; 0 switches the count off."""
    after_days = int(after_days or 0)
    last, today = _date(extended_to) or _date(to_date), _date(today)
    if reported_back or not after_days or not last or not today:
        return 0
    late = (today - last).days - 1  # the day after the last is the day due back
    return late if late >= after_days else 0


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _day(value):
    value = _date(value)
    return "%d %s %d" % (value.day, value.strftime("%b"), value.year) if value else ""
