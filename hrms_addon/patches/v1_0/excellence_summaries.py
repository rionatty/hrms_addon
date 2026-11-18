# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence rebuild (18 Nov 2026): the stored summaries the
scorecards now read, written from every Shift Report submitted before it;
and each HR Intervention's baseline and latest kept as its first KPI
readings.
"""

import frappe
from frappe.utils import getdate, today


def execute():
    from hrms_addon.hrms_addon import excellence_summary

    if frappe.db.table_exists("Section Day Summary") and frappe.db.table_exists("Shift Report"):
        first = frappe.get_all("Shift Report", filters={"docstatus": 1}, fields=["report_date"],
                               order_by="report_date asc", limit=1)
        if first:
            excellence_summary.rebuild(first[0].report_date, today())
    if not frappe.db.table_exists("Intervention KPI Reading"):
        return
    with_readings = set(frappe.get_all("Intervention KPI Reading", filters={"parenttype": "HR Intervention"},
                                       pluck="parent", limit_page_length=0))
    for row in frappe.get_all("HR Intervention", filters={"kpi": ["is", "set"]},
                              fields=["name", "raised_on", "modified", "baseline", "latest"], limit_page_length=0):
        if row.name in with_readings or (row.baseline in (None, "") and row.latest in (None, "")):
            continue
        doc = frappe.get_doc("HR Intervention", row.name)
        if row.baseline not in (None, ""):
            doc.append("kpi_readings", {"reading_date": row.raised_on, "value": row.baseline, "source": "Manual",
                                        "note": "Baseline"})
        if row.latest not in (None, "") and getdate(row.modified) >= getdate(row.raised_on):
            doc.append("kpi_readings", {"reading_date": getdate(row.modified), "value": row.latest,
                                        "source": "Manual"})
        try:
            doc.flags.ignore_links = True
            doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Manufacturing Excellence: readings of %s" % row.name)
