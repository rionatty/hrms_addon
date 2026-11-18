# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence rebuild (18 Nov 2026): the Downtime Reasons the
Shift Report's list had, each section's standards and roster as dated rows.

  Downtime Reason   the nine names the old list held, so what was saved
                    before is still a reason
  Section Standard  each section's own figures become its first standard,
                    from the day of its first shift report (else the day the
                    section was made)
  Section Assignment
                    the undated roster becomes dated: from the same day, still
                    open for the active, closed for the others
"""

import frappe
from frappe.utils import add_days, getdate

from hrms_addon.hrms_addon import excellence_rules as rules


def execute():
    if frappe.db.table_exists("Downtime Reason"):
        for name, category, planned in rules.DOWNTIME_SEED:
            if not frappe.db.exists("Downtime Reason", name):
                frappe.get_doc({"doctype": "Downtime Reason", "reason_name": name, "category": category,
                                "planned": planned, "is_active": 1}).insert(ignore_permissions=True)
    if not frappe.db.table_exists("Work Section"):
        return
    first_reports = {}
    if frappe.db.table_exists("Shift Report"):
        for row in frappe.get_all("Shift Report", fields=["work_section", "report_date"], order_by="report_date asc",
                                  limit_page_length=0):
            first_reports.setdefault(row.work_section, row.report_date)
    for name in frappe.get_all("Work Section", pluck="name", limit_page_length=0):
        section = frappe.get_doc("Work Section", name)
        start = min(getdate(section.creation), getdate(first_reports.get(name) or section.creation))
        changed = False
        if not section.get("standards"):
            values = {field: section.get(field) for field in rules.STANDARD_FIELDS}
            if any(values.values()):
                section.append("standards", dict(values, effective_from=start))
                changed = True
        if not section.get("assignments") and section.get("supervisors"):
            for old in section.supervisors:
                section.append("assignments", {
                    "employee": old.employee, "role": rules.SUPERVISOR, "shift": old.shift or rules.BOTH,
                    "from_date": start,
                    "to_date": None if old.active else max(start, add_days(getdate(section.modified), -1))})
            changed = True
        if not changed:
            continue
        try:
            section.flags.ignore_links = True
            section.save(ignore_permissions=True)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Manufacturing Excellence: standards and roster of %s" % name)
            continue
        frappe.db.commit()
