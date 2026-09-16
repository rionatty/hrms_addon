# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Remove the old Mode of Recruitment section and column break from
Job Requisition.

Mode of Recruitment moved from the Job Description tab to the Details
tab, into the left column under Reason Why New Employee Is Required. It
now uses a Heading instead of its own Section Break and Column Break.

Removing those two records from the fixture file does not delete them
from a site that already imported them. Left behind, they are worse than
clutter: they are not named in the field_order property setter, so
Frappe places them by insert_after with its sorter walk, and the Column
Break (insert_after custom_internal_advert) would land inside the new
left column and split the checkboxes across two columns.

Job Opening keeps its own copies of both: its layout did not change.
Runs in post_model_sync, before fixtures are synced.
"""

import frappe


def execute():
    for name in ("Job Requisition-custom_recruitment_section", "Job Requisition-custom_recruitment_cb"):
        frappe.delete_doc_if_exists("Custom Field", name)
