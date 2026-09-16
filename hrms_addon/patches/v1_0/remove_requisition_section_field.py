# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Drop the Section field from Job Requisition and Job Opening.

Section turned out to be the same thing as Department for Luuka, so it
was removed from the fixtures. Removing a record from a fixture file does
NOT delete it from sites that already imported it — migrate only ever
inserts and overwrites — hence this patch.

Runs in post_model_sync, which migrate executes before syncing fixtures,
so the field cannot be re-created in the same run. Safe on sites that
never had it.
"""

import frappe


def execute():
    for name in ("Job Requisition-custom_section", "Job Opening-custom_section"):
        frappe.delete_doc_if_exists("Custom Field", name)
