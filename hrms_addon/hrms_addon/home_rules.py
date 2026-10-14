# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What the desk home shows above the module tiles.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_home.py checks it without a bench. home.py reads the site and
public/js/hrms_addon_home.js draws the page. Luuka, 13 Oct 2026: "the
current desk is not that appealing and executive".

  home_of         Dashboard, or Tiles Only where Theme Settings say so
  sees_people     whose home carries the company's figures
  waiting         the user's own work: what is assigned to them and what
                  they have not read
  cards           the figures across the top
  shortcuts       the pages offered, to those who may open them
  call_to_action  the one button beside the greeting
  MODULES         the modules down the left, recruitment to exit

WHOSE FIGURES

Each user has the desk of what they may know (view_of; Luuka, 14 Oct 2026:
"HR should see a different desk than other users"):

  hr        the company's people: who is in today, the departments, what is
            coming up (last days, probations ending, birthdays)
  manager   the people who report to them, and where each is today
  staff     their own: the leave they have left, their days at work this
            month, their requests and the next holidays
  own       a user with no employee record: what waits for them only

What waits for the user, and the pages they may open, are on every desk.
"""

import datetime

DASHBOARD, TILES = "Dashboard", "Tiles Only"
HOMES = (DASHBOARD, TILES)
PEOPLE_ROLES = ("HR Manager", "HR User", "System Manager")
ASSIGNMENT, NOTIFICATION = "assignment", "notification"
OVERDUE, TODAY = "overdue", "today"
# how many rows a panel lists; the rest are in My Alerts and the ToDo list
SHOWN = 6
# a contract still running that ends within this many days is about to end
ENDING_DAYS = 30
RUNNING = ("Active", "Expiring Soon")
# the pages offered as shortcuts, in this order, to those who may open them
SHORTCUTS = (
    ("hr-overview", "HR Overview"),
    ("attendance-board", "Attendance Board"),
    ("leave-overview", "Leave Overview"),
    ("hr-calendar", "HR Calendar"),
    ("talent-board", "Talent Board"),
)
TODO = {"label": "My To Do", "route": ["List", "ToDo"], "mine": 1}
# The modules down the left of the home, by their tile's label, in the order
# of an employee's time with the company (Luuka, 13 Oct 2026: "in
# chronological order starting with recruitment all the way to exit"):
# recruited, their record set up, at work, on leave, paid, their benefits,
# loans and expenses, appraised, and Tenure last, which holds the exit.
# A tile not named here keeps Frappe's place, after these.
MODULES = (
    "Recruitment",
    "HR Setup",
    "Shift & Attendance",
    "Leaves",
    "Payroll",
    "Tax & Benefits",
    "Loans",
    "Expenses",
    "Performance",
    "Tenure",
)


def home_of(value):
    """Dashboard unless Theme Settings say Tiles Only: a setting nobody has
    touched is the dashboard."""
    return TILES if str(value or "").strip() == TILES else DASHBOARD


def sees_people(roles):
    """The company's figures are HR's."""
    return bool(set(roles or ()) & set(PEOPLE_ROLES))


def _row(alert):
    return {"title": alert.get("title") or "", "doctype": alert.get("doctype"), "docname": alert.get("docname"),
            "when": alert.get("when") or "", "band": alert.get("urgency") or "none", "key": alert.get("key")}


def waiting(alerts, shown=SHOWN):
    """The user's own work, from My Alerts' rows (most urgent first): how
    much is assigned to them, how much of it is late or due today, how many
    notifications they have not read, and the first rows of each."""
    tasks = [alert for alert in alerts or [] if alert.get("kind") == ASSIGNMENT]
    notes = [alert for alert in alerts or [] if alert.get("kind") == NOTIFICATION and alert.get("unread")]
    return {
        "tasks": len(tasks),
        "overdue": sum(1 for alert in tasks if alert.get("urgency") == OVERDUE),
        "today": sum(1 for alert in tasks if alert.get("urgency") == TODAY),
        "unread": len(notes),
        "items": [_row(alert) for alert in tasks[:shown]],
        "notes": [_row(alert) for alert in notes[:shown]],
    }


def waiting_note(waits):
    """What is said under the count of what waits for somebody."""
    if not waits.get("tasks"):
        return "Nothing waiting"
    if waits.get("overdue"):
        return "%d overdue" % waits["overdue"]
    if waits.get("today"):
        return "%d due today" % waits["today"]
    return "None overdue"


def cards(waits, people=None):
    """The figures across the top. For HR, the company's people (people:
    {"active", "joined", "on_site", "on_leave", "ending", "ending_from",
    "ending_to"}): what waits for them is beside the greeting and in the
    panel below. For everybody else, their own work.
    Each is {"key", "label", "value", "note", "tone", "route"}."""
    out = []
    if people is not None:
        active = int(people.get("active") or 0)
        joined = int(people.get("joined") or 0)
        on_site = int(people.get("on_site") or 0)
        share = round(100.0 * on_site / active, 1) if active else 0.0
        out += [
            {"key": "employees", "label": "Employees", "value": active,
             "note": "%d joined this month" % joined if joined else "Active today", "tone": "navy",
             "route": ["List", "Employee"], "filters": {"status": "Active"}},
            {"key": "on_site", "label": "On Site Today", "value": on_site,
             "note": "%s%% of employees" % ("%g" % share), "tone": "green", "route": ["attendance-board"]},
            {"key": "on_leave", "label": "On Leave Today", "value": int(people.get("on_leave") or 0),
             "note": "On approved leave", "tone": "amber", "route": ["leave-overview"]},
        ]
        ending = int(people.get("ending") or 0)
        filters = {"status": ["in", list(RUNNING)]}
        if people.get("ending_from") and people.get("ending_to"):
            filters["end_date"] = ["between", [str(people["ending_from"]), str(people["ending_to"])]]
        out.append({"key": "contracts", "label": "Contracts Ending", "value": ending,
                    "note": "In the next %d days" % ENDING_DAYS, "tone": "rose" if ending else "blue",
                    "route": ["List", "Employee Contract"], "filters": filters})
        return out
    return [
        {"key": "waiting", "label": "Waiting for You", "value": int(waits.get("tasks") or 0),
         "note": waiting_note(waits), "tone": "rose" if waits.get("overdue") else "blue",
         "route": TODO["route"], "mine": 1},
        {"key": "unread", "label": "Unread Notifications", "value": int(waits.get("unread") or 0),
         "note": "Since you last looked", "tone": "navy", "route": ["List", "Notification Log"], "mine": 1},
    ]


def shortcuts(allowed):
    """The pages offered, in their order, to somebody who may open them."""
    allowed = set(allowed or ())
    return [{"label": label, "route": [page]} for page, label in SHORTCUTS if page in allowed]


def call_to_action(links):
    """The one button beside the greeting: the first page the user may
    open, which for HR is the HR Overview; their own ToDo list otherwise."""
    return dict(links[0]) if links else dict(TODO)


# ── Each user's own desk (14 Oct 2026) ─────────────────────────────────
HR, MANAGER, STAFF, OWN = "hr", "manager", "staff", "own"
VIEWS = (HR, MANAGER, STAFF, OWN)
# a day at work, as Attendance marks one (hr_overview_rules.PRESENT)
PRESENT = ("Present", "Half Day", "Work From Home")
# what is coming up, within this many days
COMING_DAYS = 14
# the departments shown by name; the rest are added up as one
DEPARTMENTS_SHOWN = 6
# an employee's own requests, by doctype, as the desk calls each; a site without one leaves it out
REQUESTS = (
    ("Leave Application", "Leave"),
    ("Employee Advance", "Salary advance"),
    ("Allowance Request", "Allowance"),
    ("Employee Loan", "Loan"),
    ("Expense Claim", "Expense claim"),
    ("Employee Data Change Request", "Change of details"),
    ("Gate Pass", "Gate pass"),
)
# a request still in draft but not waiting for anybody
NOT_WAITING = ("Rejected", "Cancelled")
# where somebody is today, in the order a team is listed
WHERE = (
    ("not_in", "Not in yet", "none"),
    ("absent", "Absent", "overdue"),
    ("late", "Late", "today"),
    ("on_leave", "On leave", "soon"),
    ("in", "In", "good"),
)


def view_of(hr, employee, reports):
    """Which desk a user has: HR's where they may see the company's people;
    a manager's where people report to them; their own where they are an
    employee; what waits for them where they are none of these."""
    if hr:
        return HR
    if reports:
        return MANAGER
    return STAFF if employee else OWN


def days_away(today, day):
    """How far off a day is, as the desk says it."""
    gap = (day - today).days
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    return "in %d days" % gap


def _band(today, day):
    gap = (day - today).days
    return "today" if gap <= 0 else ("soon" if gap <= 3 else "later")


def _next(today, month, day):
    """The next time a day of the year comes round, today included. The
    29th of February falls on the 28th in a year without one."""
    for year in (today.year, today.year + 1):
        try:
            found = datetime.date(year, month, day)
        except ValueError:
            found = datetime.date(year, month, day - 1)
        if found >= today:
            return found
    return None


def where_today(names, clocked, marked, on_leave):
    """Where each of `names` is today, as a key of WHERE: on approved leave,
    marked absent, in (clocked in, or marked present), and of those in, late
    as Attendance marks it; not in yet otherwise. marked: {employee: (status,
    late_entry)} for today."""
    out = {}
    for name in names:
        status, late = (marked.get(name) or (None, 0))
        if name in on_leave or status == "On Leave":
            out[name] = "on_leave"
        elif status == "Absent":
            out[name] = "absent"
        elif name in clocked or status in PRESENT:
            out[name] = "late" if late else "in"
        else:
            out[name] = "not_in"
    return out


def today_board(names, clocked, marked, on_leave):
    """Where the company's people are today, a bar for each place:
    {"total", "rows": [{"key", "label", "value", "band"}]}. Late are counted
    with those in, and shown on their own as well."""
    where = where_today(names, clocked, marked, on_leave)
    counts = {key: 0 for key, _label, _band in WHERE}
    for key in where.values():
        counts[key] += 1
    rows = [
        {"key": "in", "label": "In", "value": counts["in"] + counts["late"], "band": "good"},
        {"key": "late", "label": "Late", "value": counts["late"], "band": "today"},
        {"key": "on_leave", "label": "On leave", "value": counts["on_leave"], "band": "soon"},
        {"key": "absent", "label": "Absent", "value": counts["absent"], "band": "overdue"},
        {"key": "not_in", "label": "Not in yet", "value": counts["not_in"], "band": "none"},
    ]
    return {"total": len(where), "rows": rows}


def departments(rows, shown=DEPARTMENTS_SHOWN):
    """The active employees by department, the largest first, the rest added
    up as Other. Each opens its people: {"label", "value", "filters"}. A
    department's name is shown without the company's abbreviation."""
    counts = {}
    for row in rows or []:
        key = row.get("department") or ""
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0] == "", item[0]))
    out = []
    for name, value in ordered[:shown]:
        out.append({"label": name.rsplit(" - ", 1)[0] if name else "No department", "value": value,
                    "filters": {"status": "Active", "department": name if name else ["is", "not set"]}})
    rest = sum(value for _name, value in ordered[shown:])
    if rest:
        out.append({"label": "Other", "value": rest, "filters": {"status": "Active"}})
    return out


def coming_up(employees, separations, today, days=COMING_DAYS, shown=SHOWN):
    """What is coming up in the next `days` for the company's people: last
    days of those serving notice, probations ending, birthdays and years with
    the company, the nearest first. Each is a row the home lists:
    {"title", "doctype", "docname", "when", "band", "date"}."""
    until = today + datetime.timedelta(days=days)
    found = []

    def add(day, title, doctype, docname):
        if day and today <= day <= until:
            found.append({"title": title, "doctype": doctype, "docname": docname, "when": days_away(today, day),
                          "band": _band(today, day), "date": str(day)})

    for row in separations or []:
        add(_day(row.get("custom_relieving_date")), "Last day: %s" % _who(row), "Employee Separation", row.get("name"))
    for row in employees or []:
        add(_day(row.get("custom_probation_end_date")), "Probation ends: %s" % _who(row), "Employee", row.get("name"))
        born = _day(row.get("date_of_birth"))
        if born:
            add(_next(today, born.month, born.day), "Birthday: %s" % _who(row), "Employee", row.get("name"))
        joined = _day(row.get("date_of_joining"))
        if joined:
            again = _next(today, joined.month, joined.day)
            years = again.year - joined.year if again else 0
            if years >= 1:
                add(again, "%d year%s with the company: %s" % (years, "" if years == 1 else "s", _who(row)),
                    "Employee", row.get("name"))
    found.sort(key=lambda row: (row["date"], row["title"]))
    return found[:shown]


def team_today(team, clocked, marked, on_leave, shown=12, seen=None):
    """The people who report to a manager and where each is today, those
    not in yet first: {"size", "in", "on_leave", "rows"}, each row one the
    home lists, opening the employee. seen says which of the clock,
    Attendance and approved leave the manager may read: where they may read
    neither the clock nor Attendance, nobody is said to be in or not, and
    "in" is None; where they may read neither Attendance nor leave, nobody
    is said to be on leave, and "on_leave" is None."""
    seen = seen or {"clock": True, "attendance": True, "leave": True}
    known = seen.get("clock") or seen.get("attendance")
    leave_known = seen.get("leave") or seen.get("attendance")
    where = where_today([row.get("name") for row in team or []], clocked, marked, on_leave)
    order = {key: index for index, (key, _label, _band) in enumerate(WHERE)}
    labels = {key: (label, band) for key, label, band in WHERE}
    rows = []
    for row in team or []:
        key = where.get(row.get("name"), "not_in")
        if not known and key != "on_leave":
            key = "unknown"
        label, band = labels.get(key, ("", "none"))
        rows.append({"title": _who(row), "doctype": "Employee", "docname": row.get("name"),
                     "when": label, "band": band, "where": key})
    rows.sort(key=lambda row: (order.get(row["where"], len(WHERE)), row["title"]))
    return {"size": len(rows),
            "in": sum(1 for row in rows if row["where"] in ("in", "late")) if known else None,
            "on_leave": sum(1 for row in rows if row["where"] == "on_leave") if leave_known else None,
            "rows": rows[:shown]}


def my_days(rows):
    """An employee's days at work this month, and how many of them late."""
    present = [row for row in rows or [] if row.get("status") in PRESENT]
    return {"present": len(present), "late": sum(1 for row in present if row.get("late_entry"))}


def my_requests(found, shown=SHOWN):
    """An employee's own requests across the REQUESTS doctypes, the latest
    first: how many wait for a decision (a draft that is not rejected or
    cancelled), and the rows the home lists. found: [(doctype, label,
    {"name", "status", "docstatus", "modified"})]."""
    rows = []
    waiting = 0
    for doctype, label, row in found or []:
        open_ = row.get("docstatus") == 0 and row.get("status") not in NOT_WAITING
        waiting += 1 if open_ else 0
        rows.append({"title": label, "doctype": doctype, "docname": row.get("name"),
                     "when": row.get("status") or ("Draft" if row.get("docstatus") == 0 else ""),
                     "band": "today" if open_ else "none", "modified": str(row.get("modified") or "")})
    rows.sort(key=lambda row: row["modified"], reverse=True)
    return {"waiting": waiting, "rows": rows[:shown]}


def holidays(rows, today, shown=3):
    """The next holidays, as rows the home lists."""
    out = []
    for row in sorted(rows or [], key=lambda row: str(row.get("holiday_date"))):
        day = _day(row.get("holiday_date"))
        if day and day >= today:
            out.append({"title": row.get("description") or "Holiday", "when": days_away(today, day), "band": "none",
                        "date": str(day)})
    return out[:shown]


def view_cards(view, waits, people=None, team=None, mine=None):
    """The figures across the top of each desk. HR's are cards(); a
    manager's are their team's; an employee's are their own."""
    if view == HR and people is not None:
        return cards(waits, people)
    waiting_card = cards(waits)[0]
    if view == MANAGER and team is not None:
        size = int(team.get("size") or 0)
        present = team.get("in")
        away = team.get("on_leave")
        share = round(100.0 * int(present) / size, 1) if size and present is not None else 0.0
        mine_filter = {"status": "Active", "reports_to": team.get("employee")}
        return [
            {"key": "team", "label": "My Team", "value": size, "note": "Report to you", "tone": "navy",
             "route": ["List", "Employee"], "filters": mine_filter},
            {"key": "team_in", "label": "In Today", "value": int(present or 0),
             "note": "%s%% of your team" % ("%g" % share) if present is not None else "Not open to you",
             "tone": "green", "route": ["List", "Employee"], "filters": mine_filter},
            {"key": "team_leave", "label": "On Leave Today", "value": int(away or 0),
             "note": "From your team" if away is not None else "Not open to you", "tone": "amber",
             "route": ["List", "Leave Application"], "filters": {"status": "Approved"}},
            waiting_card,
        ]
    if view in (STAFF, MANAGER) and mine is not None:
        employee = mine.get("employee")
        left = mine.get("leave_left")
        late = int(mine.get("late") or 0)
        waiting = int(mine.get("waiting") or 0)
        return [
            {"key": "leave_left", "label": "Leave Left", "value": left if left is not None else 0,
             "note": "Annual Leave days", "tone": "green", "route": ["List", "Leave Application"],
             "filters": {"employee": employee}},
            {"key": "present", "label": "At Work This Month", "value": int(mine.get("present") or 0),
             "note": "%d late" % late if late else "None late", "tone": "amber" if late else "blue",
             "route": ["List", "Attendance"], "filters": {"employee": employee, "docstatus": 1}},
            {"key": "requests", "label": "My Requests", "value": waiting,
             "note": "Awaiting a decision" if waiting else "None waiting", "tone": "navy"},
            waiting_card,
        ]
    return cards(waits)


def _day(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _who(row):
    return row.get("employee_name") or row.get("employee") or row.get("name") or ""
