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

The people figures (employees, on site, on leave) are HR's. Everybody else
sees their own work only: what waits for them and what they have not read.
"""

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
