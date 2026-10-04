# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The careers portal's top bar without Login (Luuka, 4 Oct 2026).

Website Settings' Hide Login is ticked, once: an administrator who unticks
it later keeps it that way. Staff sign in at /login, or open /app. Home
stays, and opens the job list for a visitor who is not signed in
(careers.home_page); migrate clears the home page cached before.
"""

import frappe


def execute():
    frappe.db.set_single_value("Website Settings", "hide_login", 1)
