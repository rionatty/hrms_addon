# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The movers each Talent Review kept in its own table, rewritten on every
move, into the Talent Calibration Log, insert only (calibration.py): each
move an entry, as it was made. The old rows stay where they were; the
review no longer shows them. Safe to run twice.
"""

import frappe
from frappe.utils import get_datetime


def execute():
    if not (frappe.db.table_exists("Talent Calibration Entry") and frappe.db.table_exists("Talent Calibration Log")):
        return
    done = {(row.placement, row.from_box, row.to_box) for row in frappe.get_all(
        "Talent Calibration Log", filters={"source": "Migrated"}, fields=["placement", "from_box", "to_box"],
        limit_page_length=0)}
    rows = frappe.db.sql("""
        select entry.parent as talent_review, entry.placement, entry.employee, entry.employee_name, entry.from_box,
               entry.to_box, entry.moved_by, entry.moved_on, entry.reason, placement.branch, placement.department
        from `tabTalent Calibration Entry` entry
        left join `tabTalent Placement` placement on placement.name = entry.placement
        where entry.parenttype = 'Talent Review'
        order by entry.moved_on asc, entry.idx asc""", as_dict=True)
    for row in rows:
        key = (row.placement, row.from_box, row.to_box)
        if key in done or not row.placement:
            continue
        done.add(key)
        entry = frappe.get_doc({
            "doctype": "Talent Calibration Log", "talent_review": row.talent_review, "placement": row.placement,
            "employee": row.employee, "employee_name": row.employee_name, "branch": row.branch,
            "department": row.department, "event": "Moved", "source": "Migrated", "from_box": row.from_box,
            "to_box": row.to_box, "reason": row.reason, "moved_by": row.moved_by,
            "moved_on": get_datetime(row.moved_on) if row.moved_on else None})
        entry.flags.ignore_permissions = True
        entry.flags.ignore_links = True
        entry.insert()
