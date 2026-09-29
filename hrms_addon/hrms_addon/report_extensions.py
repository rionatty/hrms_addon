# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Frappe HR's leave reports, with the leave earned beside the balances.

Frappe HR's Employee Leave Balance, Employee Leave Balance Summary and Leave
Ledger are theirs, and a report has no hook of its own. Frappe v16 lets an
app extend a DocType's controller (hooks.extend_doctype_class), mixed in
ahead of it and alongside any other app's: this mixin runs the report as
Frappe HR wrote it, then adds the Earned columns (leave_accrual.with_earned).
Every other report runs exactly as before, and should adding the columns
ever fail, the report comes back as Frappe HR made it.
"""

import frappe


class LeaveReportColumns:
    def execute_module(self, filters):
        result = super().execute_module(filters)
        from hrms_addon.hrms_addon import leave_accrual

        if self.name not in leave_accrual.REPORTS:
            return result
        try:
            return leave_accrual.with_earned(self.name, result, filters)
        except Exception:
            frappe.log_error(title="HRMS Addon: earned leave on %s" % self.name)
            return result
