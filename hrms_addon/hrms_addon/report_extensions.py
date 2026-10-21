# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Frappe HR's reports, with what Luuka read beside them.

Frappe HR's reports are theirs, and a report has no hook of its own. Frappe
v16 lets an app extend a DocType's controller (hooks.extend_doctype_class),
mixed in ahead of it and alongside any other app's: each mixin here runs the
report as Frappe HR wrote it, then adds its columns. Every other report runs
exactly as before, and should adding the columns ever fail, the report comes
back as Frappe HR made it.

  LeaveReportColumns     the leave earned beside the balances, on the
                         Employee Leave Balance, its Summary and the Leave
                         Ledger (leave_accrual.with_earned)
  SalaryRegisterColumns  the Absent Amount beside the Absent Days, on the
                         Salary Register, as Luuka's own register has it
                         (pay_days.with_absent_amount)
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


class SalaryRegisterColumns:
    def execute_module(self, filters):
        result = super().execute_module(filters)
        from hrms_addon.hrms_addon import pay_days

        if self.name != pay_days.REGISTER:
            return result
        try:
            return pay_days.with_absent_amount(result)
        except Exception:
            frappe.log_error(title="HRMS Addon: absent amount on the %s" % self.name)
            return result
