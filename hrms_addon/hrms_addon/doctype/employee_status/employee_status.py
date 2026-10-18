# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's status as Luuka names it, and which of Frappe's own four it
counts as (employee_status_rules.py). Frappe's four are statuses here too,
made after every migrate and kept as they are; Luuka's were seeded once
(patch employee_statuses), and the list is HR's to add to.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from hrms_addon.hrms_addon import employee_status, employee_status_rules as rules


class EmployeeStatus(Document):
    def validate(self):
        self.status_name = (self.status_name or "").strip()
        before = self.get_doc_before_save()
        in_use = 0
        if before and frappe.get_meta("Employee").has_field(employee_status.FIELD):
            in_use = frappe.db.count("Employee", {employee_status.FIELD: self.name})
        errors = rules.status_errors(self.status_name, self.counts_as, self.is_standard, in_use,
                                     (before.counts_as, before.is_standard) if before else None)
        if self.is_standard and self.disabled:
            errors.append(_("{0} is a system status and stays in use.").format(self.status_name))
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Status"))

    def on_update(self):
        employee_status.forget()
        # the Employee form and list read the statuses from the boot
        frappe.cache.delete_key("bootinfo")

    def on_trash(self):
        if self.is_standard:
            frappe.throw(_("{0} is a system status and cannot be removed.").format(self.name),
                         title=_("Employee Status"))
        if frappe.get_meta("Employee").has_field(employee_status.FIELD):
            in_use = frappe.db.count("Employee", {employee_status.FIELD: self.name})
            if in_use:
                frappe.throw(_("{0} employee(s) have the status {1}: give them another first, or disable it.")
                             .format(in_use, self.name), title=_("Employee Status"))
        employee_status.forget()
        frappe.cache.delete_key("bootinfo")
