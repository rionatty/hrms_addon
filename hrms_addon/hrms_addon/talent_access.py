# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Who sees which talent records. The rules are in talent_access_rules.py
(no Frappe import; scripts/verify_talent.py).

  *_has_permission      hooks.py has_permission: a narrowed user opens only
                        the records of their team, their departments, their
                        mentees, or their own development plan
  *_query_conditions    hooks.py permission_query_conditions: the same for
                        lists, reports and link searches

Frappe v16 treats anything but True from has_permission as a refusal, so
each returns a bool.
"""

import frappe

from hrms_addon.hrms_addon import talent_access_rules as rules

_CACHE = "ha_talent_scope"


def scope(user=None):
    """The user's employee, team and departments, read once a request."""
    user = user or frappe.session.user
    cache = getattr(frappe.local, _CACHE, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _CACHE, cache)
    if user not in cache:
        roles = frappe.get_roles(user)
        me = frappe.db.get_value("Employee", {"user_id": user}, "name") if user not in ("Guest",) else None
        team = rules.team_from(me, _reports()) if me and set(roles) & set(rules.MANAGERS) else set()
        departments = set(frappe.get_all("User Permission", filters={"user": user, "allow": "Department"},
                                         pluck="for_value")) if rules.HEAD in roles else set()
        cache[user] = {"narrowed": rules.narrowed(roles), "scope": rules.scope_of(roles, me, team, departments)}
    return cache[user]


def _reports():
    """{manager: [their direct reports]} for everyone still employed."""
    out = {}
    for row in frappe.get_all("Employee", filters={"reports_to": ["is", "set"], "status": ["!=", "Left"]},
                              fields=["name", "reports_to"], limit_page_length=0):
        out.setdefault(row.reports_to, []).append(row.name)
    return out


def _allowed(doctype, doc, user):
    found = scope(user)
    if not found["narrowed"]:
        return True
    spec = rules.DOCTYPES[doctype]
    record = {field: doc.get(field) for field in (spec["employee"], spec.get("mentor"), spec["department"]) if field}
    if spec.get("rotations"):
        record["rotation_supervisors"] = [row.get("supervisor") for row in doc.get("rotations") or []
                                          if row.get("supervisor")]
    return bool(rules.visible(doctype, record, found["scope"]))


def _conditions(doctype, user):
    found = scope(user)
    if not found["narrowed"]:
        return ""
    return rules.conditions(doctype, found["scope"], frappe.db.escape)


# ── has_permission ────────────────────────────────────────────────────
def placement_has_permission(doc, ptype=None, user=None):
    return _allowed("Talent Placement", doc, user or frappe.session.user)


def program_has_permission(doc, ptype=None, user=None):
    return _allowed("Talent Program", doc, user or frappe.session.user)


def position_has_permission(doc, ptype=None, user=None):
    return _allowed("Succession Position", doc, user or frappe.session.user)


def trainee_has_permission(doc, ptype=None, user=None):
    return _allowed("Graduate Trainee Program", doc, user or frappe.session.user)


# ── permission_query_conditions ───────────────────────────────────────
def placement_query_conditions(user=None, doctype=None):
    return _conditions("Talent Placement", user or frappe.session.user)


def program_query_conditions(user=None, doctype=None):
    return _conditions("Talent Program", user or frappe.session.user)


def position_query_conditions(user=None, doctype=None):
    return _conditions("Succession Position", user or frappe.session.user)


def trainee_query_conditions(user=None, doctype=None):
    return _conditions("Graduate Trainee Program", user or frappe.session.user)
