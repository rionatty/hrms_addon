"""Employee Penalty's Frequency (Luuka, 12 Nov 2026: "on the penalty add frequency weekly deduction to cater for
casuals"): every penalty made before it is monthly, as its schedule already is, so saving one never redraws it by the
week. A new one starts weekly for a casual paid by the week (penalties._fill)."""

import frappe


def execute():
    if frappe.db.has_column("Employee Penalty", "deduction_frequency"):
        frappe.db.set_value("Employee Penalty", {"deduction_frequency": ["in", ["", None]]}, "deduction_frequency",
                            "Monthly", update_modified=False)
