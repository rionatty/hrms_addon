# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The control line on every form this app prints, as a Jinja method
(hooks.jinja): each print format starts with {{ print_control(doc) }}. What it
says is print_control_rules.py's."""

import frappe
from frappe.utils import format_datetime, get_fullname, now_datetime

from hrms_addon.hrms_addon import print_control_rules as rules


def print_control(doc):
    """The control line for the document being printed: its number, what it
    stands at, and who is printing it, now."""
    if not doc or not doc.get("name"):
        return ""
    user = frappe.session.user
    return rules.control_line(doc.get("name"), rules.status_of(doc), get_fullname(user) or user,
                              format_datetime(now_datetime(), "dd-MM-yyyy HH:mm"))
