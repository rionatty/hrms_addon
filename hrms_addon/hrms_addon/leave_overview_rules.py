# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Leave Overview: who is away, what is stuck, what the year end will
cost, and whether there is a pattern.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_leave_overview.py exercises them without a bench. The
queries are in leave_overview.py.

FOUR QUESTIONS, ONE ROW EACH

  1  Who is away, and are we covered? On leave today and starting this
     week, and each department's count against its limit. Opened daily by
     supervisors and heads of department.
  2  What is stuck? Leave waiting on a desk and for how long, plan changes
     waiting, and anybody not back from a leave that has run out.
  3  What will the year end cost? Days earned and not taken, what they
     are worth, the days the year end would lose, and how far the annual
     plan was kept to. For the HR Manager and management.
  4  Is there a pattern? Leave by month, and for HR alone the sick leave
     worth a conversation.

WHO SEES WHAT

HR and management see everybody. A head of department or a supervisor
sees their own people and nobody else's. What leave is worth in
shillings is management's; why somebody was away (the leave type, the
sick-leave list) is HR's. There is no ranking of employees by leave
taken: it invites the wrong conversation and answers none of the four.
"""

import datetime

# ── Who sees what ─────────────────────────────────────────────────────
PAGE_ROLES = ("HR User", "HR Manager", "General Manager", "Executive Director", "Head of Department", "Supervisor")
SEES_ALL = ("HR User", "HR Manager", "General Manager", "Executive Director")
SEES_MONEY = ("HR Manager", "General Manager", "Executive Director")
SEES_WHY = ("HR User", "HR Manager")
HEADS = ("Head of Department",)


def reach(roles):
    """What somebody may see, by their roles; None when the page is not
    theirs. "all": everybody, else their own people. "money": what leave
    is worth. "why": the leave types and the sick-leave list."""
    roles = set(roles or ())
    if not roles & set(PAGE_ROLES):
        return None
    return {"all": bool(roles & set(SEES_ALL)), "money": bool(roles & set(SEES_MONEY)),
            "why": bool(roles & set(SEES_WHY)), "head": bool(roles & set(HEADS))}


def own_people(employees, me=None, departments=(), branches=(), head=False):
    """Whose leave a head of department or a supervisor sees.

    employees: [{"name", "reports_to", "department", "branch"}]. me: the
    viewer's own Employee. departments, branches: what their User
    Permissions hold them to. Their own are those who report to them, and
    those of the departments they are held to (in the branches they are
    held to, where any). A head held to no department heads their own.
    Never themselves: nobody reads their own leave as its approver.
    """
    departments, branches = set(departments or ()), set(branches or ())
    mine = next((row for row in employees or () if row.get("name") == me), None) if me else None
    if head and not departments and mine and mine.get("department"):
        departments = {mine["department"]}
    out = set()
    for row in employees or ():
        if row.get("name") == me:
            continue
        if me and row.get("reports_to") == me:
            out.add(row["name"])
        elif row.get("department") in departments and (not branches or row.get("branch") in branches):
            out.add(row["name"])
    return out


# ── 1. Who is away, and are we covered ────────────────────────────────
SOON_DAYS = 7
COVER_DAYS = 14


def away(leaves, today, soon_days=SOON_DAYS):
    """{"today": [...], "soon": [...]}: approved leave running today, and
    starting within the week, each with the day back. leaves: employee,
    employee_name, department, from_date, to_date (and whatever else the
    row carries, which is passed through)."""
    today = _date(today)
    out = {"today": [], "soon": []}
    for row in leaves or ():
        first, last = _date(row.get("from_date")), _date(row.get("to_date"))
        if not first or not last:
            continue
        line = dict(row, from_date=str(first), to_date=str(last), back_on=str(last + datetime.timedelta(days=1)))
        if first <= today <= last:
            out["today"].append(line)
        elif today < first <= today + datetime.timedelta(days=int(soon_days)):
            out["soon"].append(line)
    out["today"].sort(key=lambda line: (line["to_date"], line.get("employee_name") or ""))
    out["soon"].sort(key=lambda line: (line["from_date"], line.get("employee_name") or ""))
    return out


def cover(headcount, leaves, today, most_off=0, days=COVER_DAYS):
    """Each department against its limit: [{"department", "people",
    "off_today", "peak", "peak_on", "limit", "over"}], the one most over
    first. headcount: {department: people in it}. The peak is the most off
    on any one day from today for `days` days."""
    today = _date(today)
    window = [today + datetime.timedelta(days=offset) for offset in range(int(days))]
    off = {}
    for row in leaves or ():
        first, last = _date(row.get("from_date")), _date(row.get("to_date"))
        if not first or not last or not row.get("employee"):
            continue
        for day in window:
            if first <= day <= last:
                off.setdefault(row.get("department") or "", {}).setdefault(day, set()).add(row["employee"])
    limit = int(most_off or 0)
    out = []
    for department in sorted(set(headcount or {}) | set(off)):
        days_off = off.get(department, {})
        peak_on = max(days_off, key=lambda day: (len(days_off[day]), -day.toordinal())) if days_off else None
        peak = len(days_off[peak_on]) if peak_on else 0
        out.append({"department": department, "people": int((headcount or {}).get(department) or 0),
                    "off_today": len(days_off.get(today, ())), "peak": peak,
                    "peak_on": str(peak_on) if peak_on else None, "limit": limit,
                    "over": bool(limit) and peak > limit})
    return sorted(out, key=lambda row: (not row["over"], -row["peak"], row["department"]))


# ── 2. What is stuck ──────────────────────────────────────────────────
def waiting(rows, today):
    """Leave on a desk, the longest wait first. rows: name, employee_name,
    state, since (the day it reached the desk), and what else they carry."""
    today = _date(today)
    out = []
    for row in rows or ():
        since = _date(row.get("since"))
        out.append(dict(row, since=str(since) if since else None,
                        days=max((today - since).days, 0) if since else 0))
    return sorted(out, key=lambda row: (-row["days"], row.get("employee_name") or ""))


def longest(rows):
    return max([row["days"] for row in rows or ()] or [0])


# ── 3. What the year end will cost ────────────────────────────────────
WORKING_DAYS_A_MONTH = 26  # a day's pay is the gross over these, as encashment and the exit settlement pay it


def worth(days, gross, working_days=WORKING_DAYS_A_MONTH):
    """What days of leave are worth: a day's pay each."""
    return round(max(float(days or 0), 0.0) * float(gross or 0) / float(working_days or WORKING_DAYS_A_MONTH), 2)


def at_risk(balance, carries_forward=False, most_carried=0):
    """The days the year end would lose: what is left and not applied for,
    beyond what the Leave Type carries into the next year. A type that
    carries forward without limit loses nothing."""
    balance = max(float(balance or 0), 0.0)
    if not carries_forward:
        return round(balance, 2)
    most = float(most_carried or 0)
    return round(max(balance - most, 0.0), 2) if most > 0 else 0.0


def year_end(rows):
    """The row's four figures. rows: one per employee, with "earned" (days
    earned and not taken), "balance" (days left and not applied for),
    "gross", "carries_forward", "most_carried"."""
    earned = sum(max(float(row.get("earned") or 0), 0.0) for row in rows or ())
    value = sum(worth(row.get("earned"), row.get("gross")) for row in rows or ())
    lost = sum(at_risk(row.get("balance"), row.get("carries_forward"), row.get("most_carried")) for row in rows or ())
    return {"people": len(rows or ()), "earned": round(earned, 2), "value": round(value, 2), "at_risk": round(lost, 2),
            "unpriced": len([row for row in rows or () if float(row.get("earned") or 0) > 0 and not row.get("gross")])}


def plan_kept(counts):
    """How far the annual plan was kept to, 0 to 1: of the planned leaves
    whose first day has come, those taken or applied for. counts: {status:
    how many} (leave_rules.ROW_STATUSES). None with nothing yet due."""
    done = int(counts.get("Taken") or 0) + int(counts.get("Applied") or 0)
    due = done + int(counts.get("Not Applied") or 0)
    return round(float(done) / due, 4) if due else None


# ── 4. Is there a pattern ─────────────────────────────────────────────
ALL_LEAVE = "Leave"
# a spell of sick leave beside the rest day: it starts on a Monday, or ends
# on a Friday or a Saturday
MONDAY, FRIDAY, SATURDAY = 0, 4, 5
WORTH_A_WORD = {"spells": 3, "beside_rest": 2}
SICK_SHOWN = 10


def by_month(leaves, year, by_type=True):
    """Leave days taken in each month of `year`: [{"month": 1..12, "days":
    {leave type: days}, "total"}]. A leave across two months is shared
    between them by its calendar days. Without `by_type` every leave is
    counted as one kind, for somebody who is not told why people were away.
    """
    year = int(year)
    months = [{"month": month, "days": {}, "total": 0.0} for month in range(1, 13)]
    for row in leaves or ():
        first, last = _date(row.get("from_date")), _date(row.get("to_date"))
        if not first or not last or last < first:
            continue
        span = (last - first).days + 1
        total = float(row.get("days") or span)
        kind = (row.get("leave_type") or ALL_LEAVE) if by_type else ALL_LEAVE
        day = first
        shares = {}
        while day <= last:
            if day.year == year:
                shares[day.month] = shares.get(day.month, 0) + 1
            day += datetime.timedelta(days=1)
        for month, count in shares.items():
            share = total * count / span
            months[month - 1]["days"][kind] = round(months[month - 1]["days"].get(kind, 0.0) + share, 2)
            months[month - 1]["total"] = round(months[month - 1]["total"] + share, 2)
    return months


def sick_patterns(spells, worth_a_word=None, shown=SICK_SHOWN):
    """The sick leave worth a conversation: somebody with several spells in
    the year, or more than one beside the rest day. [{"employee",
    "employee_name", "department", "spells", "days", "beside_rest"}], the
    most beside the rest day first. A conversation, not a finding: the
    list says how often, never why.

    spells: employee, employee_name, department, from_date, to_date, days.
    """
    limits = dict(WORTH_A_WORD, **(worth_a_word or {}))
    found = {}
    for row in spells or ():
        first, last = _date(row.get("from_date")), _date(row.get("to_date"))
        if not row.get("employee") or not first or not last:
            continue
        seat = found.setdefault(row["employee"], {
            "employee": row["employee"], "employee_name": row.get("employee_name") or row["employee"],
            "department": row.get("department"), "spells": 0, "days": 0.0, "beside_rest": 0})
        seat["spells"] += 1
        seat["days"] = round(seat["days"] + float(row.get("days") or ((last - first).days + 1)), 2)
        if first.weekday() == MONDAY or last.weekday() in (FRIDAY, SATURDAY):
            seat["beside_rest"] += 1
    out = [seat for seat in found.values()
           if seat["spells"] >= limits["spells"] or seat["beside_rest"] >= limits["beside_rest"]]
    return sorted(out, key=lambda seat: (-seat["beside_rest"], -seat["spells"], seat["employee_name"]))[:int(shown)]


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
