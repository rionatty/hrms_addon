# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Who holds a role in a branch: the people a task, an alert or a document
goes to (org_rules.py: each branch has its own HR Officer, Heads of
Department and supervisors; the HR Manager and the Executive Director serve
every branch).

A user's Branch and Department User Permissions say where they serve; one
with none serves every branch. onboarding_rules.activity_assignees picks
among them.
"""

import frappe

from hrms_addon.hrms_addon import onboarding_rules as rules

HR_OFFICER = rules.HR_OFFICER_ROLE


def holders(role):
    """[{"user", "branches", "departments"}] for the enabled users holding
    `role`, with the Branch and Department User Permissions limiting them."""
    users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", distinct=True)
    if not users:
        return []
    users = frappe.get_all(
        "User",
        filters=[["name", "in", users], ["name", "not in", ["Administrator", "Guest"]], ["enabled", "=", 1]],
        pluck="name",
    )
    limits = {user: {"Branch": set(), "Department": set()} for user in users}
    if users:
        for perm in frappe.get_all(
            "User Permission",
            filters={"user": ["in", users], "allow": ["in", ["Branch", "Department"]]},
            fields=["user", "allow", "for_value"],
        ):
            limits[perm.user][perm.allow].add(perm.for_value)
    return [{"user": user, "branches": limits[user]["Branch"], "departments": limits[user]["Department"]}
            for user in sorted(users)]


def people_for(role, branch, department=None):
    """The holders of `role` serving this branch (and department), else those
    serving every branch: [users], possibly empty."""
    return rules.activity_assignees(role, {}, holders(role), branch, department)


def hr_officers(branch, department=None):
    """The branch's HR Officers, else the HR Managers (one for every branch)."""
    return people_for(HR_OFFICER, branch, department) or people_for("HR Manager", branch, department)


def assign(doctype, name, users, description, date=None, notify=0):
    """Put the document on each user's ToDo list (skipping one already
    there), sharing it read-only with anyone who cannot open it."""
    from frappe.desk.form.assign_to import _add

    for user in [user for user in users if user]:
        if frappe.db.exists("ToDo", {"reference_type": doctype, "reference_name": name, "allocated_to": user,
                                     "status": "Open"}):
            continue
        _add({"assign_to": [user], "doctype": doctype, "name": name, "description": description,
              "date": date, "notify": notify}, ignore_permissions=True)


def notify(users, doctype, name, subject, message=None):
    """An alert in each user's notifications (and email, as they have set)."""
    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

    users = [user for user in users if user]
    if users:
        enqueue_create_notification(users, {
            "type": "Alert",
            "document_type": doctype,
            "document_name": name,
            "subject": subject,
            "email_content": message or subject,
        })
