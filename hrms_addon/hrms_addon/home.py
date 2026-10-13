# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The desk home, above the module tiles: a greeting, the figures that
matter today, what waits for the user, and the pages they open most.

The rules are in home_rules.py, without a Frappe import
(scripts/verify_home.py). This reads the site, in one call, and
public/js/hrms_addon_home.js draws it on Frappe's own desk page.

  summary   everything the home shows, for the logged-in user

WHOSE FIGURES

The people figures are read with frappe.get_list, so somebody limited to a
branch by a User Permission sees that branch's people, and only HR are
given them at all (home_rules.sees_people). What waits for the user is
their own, as My Alerts lists it (alerts.py): nothing here takes a user to
look at.

NEVER AN ERROR

This is the page everybody lands on. A part that cannot be read is left out
and written to the Error Log (_or), and the rest of the home still comes.
"""

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from hrms_addon.hrms_addon import alerts, hr_overview, hr_overview_rules, home_rules as rules


@frappe.whitelist()
def summary():
    """Everything the desk home shows, for the logged-in user."""
    user = frappe.session.user
    today = getdate(nowdate())
    waits = rules.waiting(_or([], _alerts))
    people = None
    if rules.sees_people(frappe.get_roles(user)) and frappe.has_permission("Employee", "read"):
        people = _or(None, _people, today)
    links = rules.shortcuts([page for page, _label in rules.SHORTCUTS if _may_open(page)])
    return {
        "greeting": hr_overview_rules.greeting(now_datetime().hour),
        "first_name": frappe.db.get_value("User", user, "first_name") or user,
        "today": str(today),
        "company": _or(None, frappe.defaults.get_user_default, "Company"),
        "waiting": waits,
        "cards": rules.cards(waits, people),
        "shortcuts": links,
        "action": rules.call_to_action(links),
    }


def _or(fallback, read, *args):
    """What `read` gives, or `fallback` where it cannot be read. Logged with
    defer_insert: a GET is rolled back, and the log has to outlive it."""
    try:
        return read(*args)
    except Exception:
        frappe.log_error(title="Desk home: %s" % getattr(read, "__name__", "read"), defer_insert=True)
        return fallback


def _alerts():
    """The user's own assignments and notifications, as My Alerts lists them."""
    return alerts.my_alerts(limit=40)["alerts"]


def _people(today):
    """The company's people today, as far as the user may see them."""
    rows = frappe.get_list("Employee", filters={"status": "Active"}, fields=["name", "date_of_joining"],
                           limit_page_length=0)
    names = [row.name for row in rows] or [""]
    first = today.replace(day=1)
    until = add_days(today, rules.ENDING_DAYS)
    return {
        "active": len(rows),
        "joined": sum(1 for row in rows if row.date_of_joining and getdate(row.date_of_joining) >= first),
        "on_site": hr_overview._on_site(names, today),
        "on_leave": hr_overview._on_leave(names, today),
        "ending": _contracts_ending(today, until),
        "ending_from": str(today),
        "ending_to": str(until),
    }


def _contracts_ending(today, until):
    """The contracts still running that end by `until`, as far as the user
    may see them. None on a site without the contracts."""
    try:
        return len(frappe.get_list("Employee Contract", filters={
            "docstatus": 1, "status": ["in", list(rules.RUNNING)], "end_date": ["between", [today, until]]},
            pluck="name", limit_page_length=0))
    except Exception:
        return 0


def _may_open(page):
    """A page the site has and the user's roles may open."""
    try:
        return bool(frappe.db.exists("Page", page) and frappe.get_cached_doc("Page", page).is_permitted())
    except Exception:
        return False
