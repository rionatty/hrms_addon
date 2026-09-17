# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Put Job Requisition's Connections back in a tab of its own.

For a while the list sat in a Connections section on the Details tab: two
property setters hid the standard connections_tab and switched its
dashboard off, and the form script moved the list into an HTML field of
that section. The tab is back, straight after Job Description.

Fixtures only add and update records, so the two setters and the
section's two custom fields are deleted here; neither custom field has a
database column. The new field_order setter, which places the tab, comes
in with the fixtures after this patch.
"""

import frappe

REMOVED = (
    ("Property Setter", "Job Requisition-connections_tab-show_dashboard"),
    ("Property Setter", "Job Requisition-connections_tab-hidden"),
    ("Custom Field", "Job Requisition-custom_connections_section"),
    ("Custom Field", "Job Requisition-custom_connections_html"),
)


def execute():
    for doctype, name in REMOVED:
        frappe.delete_doc_if_exists(doctype, name)
    frappe.clear_cache(doctype="Job Requisition")
