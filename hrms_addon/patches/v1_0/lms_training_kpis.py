"""The programmes' KPIs and their impact reviews read from HR's own list (Training KPI) from 18 Nov 2026, in place of
a fixed list: the eight the Shift Reports give are seeded with their unit and the Shift Report measure they are read
from, and each KPI named under Other on a programme or a review becomes one of its own. The kinds of test a result
can be (Assessment Type) are seeded too. Safe to run again."""

import frappe

KPI = "Training KPI"
ASSESSMENT_TYPES = ("Written Test", "Practical Test", "Oral Test", "Observation", "Online Quiz")


def execute():
    from hrms_addon.hrms_addon import learning_delivery_rules as rules

    for name, better, unit, measure in rules.SEEDED_KPIS:
        if not frappe.db.exists(KPI, name):
            frappe.get_doc({"doctype": KPI, "kpi_name": name, "better": better, "unit": unit,
                            "source": rules.SHIFT_REPORTS, "shift_measure": measure, "window_days": 30,
                            "is_active": 1}).insert(ignore_permissions=True)
    for doctype in ("Training Program KPI", "Training Impact Review"):
        for row in frappe.get_all(doctype, filters={"kpi": rules.OTHER}, fields=["name", "kpi_name", "better"]):
            name = (row.kpi_name or "").strip()[:140]
            if not name:
                continue
            if not frappe.db.exists(KPI, name):
                frappe.get_doc({"doctype": KPI, "kpi_name": name, "better": row.better or rules.HIGHER,
                                "source": rules.MANUAL, "window_days": 30, "is_active": 1}).insert(
                    ignore_permissions=True)
            frappe.db.set_value(doctype, row.name, {"kpi": name, "kpi_name": None}, update_modified=False)
    for name in ASSESSMENT_TYPES:
        if not frappe.db.exists("Assessment Type", name):
            frappe.get_doc({"doctype": "Assessment Type", "assessment_type": name}).insert(ignore_permissions=True)
