# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The seeded Interview Invitation asked the candidate to reply to the email;
it now links to the page where they confirm or ask for another time
({{ confirm_link }}) and mentions the calendar invitation attached.

The Email Template is HR's once seeded, so its text is replaced only where
it is still exactly what was seeded. An invitation whose template does not
place the link gets it added at the end (interviews._invite). Safe to run
twice.
"""

import frappe

from hrms_addon.hrms_addon import interview_rules as rules


def execute():
    name = rules.INVITATION_TEMPLATE
    if not frappe.db.exists("Email Template", name):
        return
    body = frappe.db.get_value("Email Template", name, "response_html")
    if (body or "").strip() == rules.PREVIOUS_INVITATION_BODY:
        frappe.db.set_value("Email Template", name, "response_html", rules.INVITATION_BODY)
