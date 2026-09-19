# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's contract: prepared, signed, watched to its end, renewed or not.

The logic lives in hrms_addon/hrms_addon/contracts.py (rules in the tested *_rules.py
and *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import contracts


class EmployeeContract(Document):
    def validate(self):
        contracts.validate(self)

    def on_submit(self):
        contracts.on_submit(self)

    def on_cancel(self):
        contracts.on_cancel(self)
