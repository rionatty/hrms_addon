# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Say out loud what the Authorization header calls the token.

Token Prefix arrived after Luuka's BioTime Server record already existed,
so the field's default never applied to it and the box sat empty. An empty
box is read as JWT, which is the one thing it must not quietly be: their
BioTime wants Django REST Framework's plain "Token", and a blank field
gave no hint that anything was being assumed.

So a record with nothing in that box gets JWT written into it — the same
value the code was already using, now visible and changeable. Nothing else
is touched, and a record that already says something keeps saying it.
"""

import frappe

SETTINGS = "BioTime Server"
DEFAULT = "JWT"


def execute():
    if not frappe.db.exists("DocType", SETTINGS):
        return
    if not frappe.db.has_column(SETTINGS, "token_prefix"):
        return
    if frappe.db.get_single_value(SETTINGS, "token_prefix"):
        return
    frappe.db.set_single_value(SETTINGS, "token_prefix", DEFAULT)
