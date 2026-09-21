# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The documents an employee holds, on the site.

The rules are in document_rules.py, without a Frappe import
(scripts/verify_documents.py). This reads and writes the site.

  type_validate      a kind of document and the policy on it
  employee_validate  each document's status and the days left on it,
                     worked out on the employee's own form
  daily              the chasing: three months, a month, a week, and the
                     day it goes, each threshold crossed once
  missing_documents  who has to hold one and does not

Alerts, Documents & Notifications, case 1. Contract and probation expiry
are already watched (contracts.py, probation.py); this is the rest of what
somebody has to hold to keep working — the national ID, a work permit, a
driving permit.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import document_rules as rules, people

TYPE = "Employee Document Type"


def type_validate(doc, method=None):
    errors = rules.type_errors({
        "document_name": doc.get("document_name"), "applies_to": doc.get("applies_to"),
        "expires": doc.get("expires"), "notice_days": doc.get("notice_days")})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TYPE))


# ── 1. On the employee's own form ─────────────────────────────────────
def employee_validate(doc, method=None):
    """Called from a doc_event on Frappe HR's Employee."""
    rows = doc.get("custom_documents") or []
    if not rows:
        doc.custom_documents_status = None
        return
    day = today()
    policy = _policy([row.document_type for row in rows if row.document_type])
    for row in rows:
        kind = policy.get(row.document_type, {})
        errors = rules.document_errors({
            "document_type": row.document_type, "number": row.number,
            "issued_on": row.issued_on, "expires_on": row.expires_on,
            "expires_required": kind.get("expires")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors),
                         title=_("Employee Document"))
        row.status = rules.status_of(row.expires_on, day,
                                     kind.get("notice_days") or rules.DEFAULT_NOTICE_DAYS,
                                     row.number)
        row.days_left = rules.days_left(row.expires_on, day) if row.expires_on else None
    doc.custom_documents_status = _summary(rows, doc)


def _policy(names):
    if not names:
        return {}
    rows = frappe.get_all(TYPE, filters={"name": ["in", list(set(names))]},
                          fields=["name", "applies_to", "expires", "notice_days", "mandatory"],
                          limit=100)
    return {row.name: dict(row) for row in rows}


def _summary(rows, doc):
    """A line on the employee saying what is wrong, if anything."""
    expired = [row.document_type for row in rows if row.status == rules.EXPIRED]
    expiring = [row.document_type for row in rows if row.status == rules.EXPIRING]
    absent = missing_documents(doc)
    parts = []
    if expired:
        parts.append(_("expired: {0}").format(", ".join(expired)))
    if expiring:
        parts.append(_("running out: {0}").format(", ".join(expiring)))
    if absent:
        parts.append(_("missing: {0}").format(", ".join(absent)))
    return "; ".join(parts) or None


def missing_documents(doc):
    """What this employee has to hold and does not."""
    required = frappe.get_all(TYPE, filters={"mandatory": 1, "enabled": 1},
                              fields=["name", "applies_to"], limit=100)
    facts = {"is_foreign": doc.get("custom_is_foreign"), "drives": doc.get("custom_drives"),
             "operates_machinery": doc.get("custom_operates_machinery")}
    wanted = [(row.name, row.applies_to) for row in required
              if rules.required_for(row.applies_to, facts)]
    held = {row.document_type: row.number for row in doc.get("custom_documents") or []
            if row.number}
    return rules.missing(wanted, held)


# ── 2. The chasing ────────────────────────────────────────────────────
def daily():
    """Every document whose expiry has reached a threshold nobody has been
    told about yet."""
    day = today()
    policy = {row.name: dict(row) for row in frappe.get_all(
        TYPE, fields=["name", "notice_days", "expires"], limit=200)}
    rows = frappe.get_all(
        "Employee Document",
        filters={"parenttype": "Employee", "expires_on": ["is", "set"]},
        fields=["name", "parent", "document_type", "number", "expires_on", "alerted_at"],
        limit=5000)
    watched = [dict(row, notice_days=policy.get(row.document_type, {}).get("notice_days"))
               for row in rows]
    for row in rules.chase(watched, day):
        employee = frappe.db.get_value(
            "Employee", row["parent"],
            ["employee_name", "status", "branch", "department", "user_id"], as_dict=True)
        if not employee or employee.status != "Active":
            continue
        _tell(row, employee, day)
    frappe.db.commit()


def _tell(row, employee, day):
    users = list(people.hr_officers(employee.branch, employee.department))
    if employee.user_id:
        users.append(employee.user_id)
    users = [user for user in dict.fromkeys(users) if user]
    if users:
        left = row["days_left"]
        when = (_("runs out today") if left == 0
                else _("runs out in {0} day(s)").format(left))
        people.notify(users, "Employee", row["parent"],
                      _("{0}'s {1} ({2}) {3}, on {4}.").format(
                          employee.employee_name, row["document_type"], row["number"], when,
                          frappe.utils.format_date(row["expires_on"])))
    frappe.db.set_value("Employee Document", row["name"], "alerted_at", cint(row["threshold"]),
                        update_modified=False)


# ── 3. The types, as masters ──────────────────────────────────────────
def seed_document_types():
    """The documents Luuka's own people hold, made once and then theirs
    to amend."""
    for name, applies_to, notice, expires, mandatory in rules.SEEDED_TYPES:
        if frappe.db.exists(TYPE, name):
            continue
        try:
            doc = frappe.get_doc({
                "doctype": TYPE, "__newname": name, "document_name": name,
                "applies_to": applies_to, "notice_days": notice, "expires": expires,
                "mandatory": mandatory, "enabled": 1})
            doc.flags.ignore_permissions = True
            doc.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: seeding the document types")


def setup_on_migrate():
    seed_document_types()
