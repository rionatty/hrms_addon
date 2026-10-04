# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The app's alerts by email too.

Frappe never emails a notification of its own Alert type, and every alert
of the app's was one, so they were only ever seen in the desk. They now go
as HR Alert (people.notify), which Frappe emails to each user who has it
ticked in their Notification Settings. A user whose settings are made from
now on has it ticked already; this ticks it, once, for the users there
before. Anyone can untick it afterwards. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import alerts
from hrms_addon.hrms_addon.alerts_rules import EMAILED_TYPE


def execute():
    if not frappe.db.exists("DocType", "Notification Type") or \
            not frappe.get_meta("Notification Settings").has_field("email_notification_types"):
        return
    alerts.install_alert_type()
    for name in frappe.get_all("Notification Settings", pluck="name"):
        settings = frappe.get_doc("Notification Settings", name)
        if any(row.notification_type == EMAILED_TYPE for row in settings.email_notification_types):
            continue
        settings.append("email_notification_types", {"notification_type": EMAILED_TYPE})
        settings.flags.ignore_permissions = True
        settings.save()
