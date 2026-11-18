# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence rebuild (18 Nov 2026): the indexes the readers
filter by, made whether or not the doctypes changed on this migrate (a
DocType's search_index only reaches the table when the DocType is synced):
the Shift Report by date, section, shift, plant and supervisor; the People
Log by date and supervisor; the Employee and the grievance by section; the
case by date and section; the summaries by plant, section and supervisor
with the date; one row a section and shift on a day sheet.
"""

import frappe

INDEXES = (
    ("Shift Report", ["report_date"]), ("Shift Report", ["work_section"]), ("Shift Report", ["shift"]),
    ("Shift Report", ["branch"]), ("Shift Report", ["supervisor"]), ("Shift Report", ["plant_day_sheet"]),
    ("People Log", ["log_date"]), ("People Log", ["supervisor"]), ("People Log", ["work_section"]),
    ("Employee", ["custom_work_section"]), ("Employee Grievance", ["custom_work_section"]),
    ("Disciplinary Case", ["incident_date"]), ("Disciplinary Case", ["work_section"]),
    ("HR Intervention", ["work_section"]), ("HR Intervention", ["supervisor"]),
    ("Plant Day Sheet", ["branch", "sheet_date"]),
)


def execute():
    for doctype, fields in INDEXES:
        if not frappe.db.table_exists(doctype) or not all(frappe.db.has_column(doctype, field) for field in fields):
            continue
        try:
            frappe.db.add_index(doctype, fields)
        except Exception:
            frappe.log_error(title="Manufacturing Excellence: index on %s %s" % (doctype, fields))
    from hrms_addon.hrms_addon import excellence_sheet, excellence_summary

    excellence_summary.add_indexes()
    excellence_sheet.add_keys()
