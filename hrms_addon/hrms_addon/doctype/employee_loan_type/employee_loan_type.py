# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A kind of loan Luuka give, with its own rules (loan_rules.TYPE_DEFAULTS):
who lends, who may borrow and how much (review item 25)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import loans


class EmployeeLoanType(Document):
    def validate(self):
        loans.type_validate(self)
