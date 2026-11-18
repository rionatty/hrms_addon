# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence rebuild (18 Nov 2026): the Shift Reports saved
before it.

  shift_key   each report not cancelled gets its section, date and shift as
              its key, which the database holds unique
  outputs     a report's Order or Job No. becomes a Plant Order (made once,
              finished in the report's section) and an output line carrying
              the report's output and waste, so Order Feasibility reads it
"""

import frappe
from frappe.utils import getdate, now


def execute():
    if not frappe.db.table_exists("Shift Report"):
        return
    for row in frappe.get_all("Shift Report", filters={"docstatus": ["<", 2]},
                              fields=["name", "work_section", "report_date", "shift", "shift_key"],
                              limit_page_length=0):
        key = "%s|%s|%s" % (row.work_section, getdate(row.report_date), row.shift)
        if row.shift_key == key:
            continue
        try:
            frappe.db.set_value("Shift Report", row.name, "shift_key", key, update_modified=False)
        except Exception:
            frappe.log_error(title="Manufacturing Excellence: key of %s" % row.name)
    frappe.db.commit()
    if not frappe.db.table_exists("Plant Order") or not frappe.db.has_column("Shift Report", "order_no"):
        return
    with_lines = set(frappe.get_all("Shift Output", filters={"parenttype": "Shift Report"}, pluck="parent",
                                    limit_page_length=0))
    for report in frappe.get_all("Shift Report", filters={"order_no": ["is", "set"], "docstatus": ["<", 2]},
                                 fields=["name", "order_no", "work_section", "branch", "report_date", "docstatus",
                                         "actual_output", "waste_qty", "waste_value", "labour_cost", "ot_hours",
                                         "ot_cost", "complaint_value"], limit_page_length=0):
        if report.name in with_lines:
            continue
        order = (report.order_no or "").strip()
        if not order:
            continue
        try:
            if not frappe.db.exists("Plant Order", order):
                frappe.get_doc({"doctype": "Plant Order", "order_no": order, "finishing_section": report.work_section,
                                "order_qty": 0, "order_value": 0, "status": "Running",
                                "released_on": report.report_date}).insert(ignore_permissions=True)
            line = frappe.get_doc({
                "doctype": "Shift Output", "parent": report.name, "parenttype": "Shift Report",
                "parentfield": "outputs", "idx": 1, "docstatus": report.docstatus, "plant_order": order,
                "good_qty": report.actual_output, "waste_qty": report.waste_qty, "waste_value": report.waste_value,
                "labour_share": report.labour_cost, "ot_hours_share": report.ot_hours,
                "ot_cost_share": report.ot_cost, "complaint_share": report.complaint_value,
                "report_date": report.report_date, "work_section": report.work_section, "branch": report.branch,
                "name": frappe.generate_hash(length=10), "creation": now(), "modified": now(),
                "owner": "Administrator", "modified_by": "Administrator"})
            line.db_insert()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Manufacturing Excellence: order of %s" % report.name)
            continue
        frappe.db.commit()
