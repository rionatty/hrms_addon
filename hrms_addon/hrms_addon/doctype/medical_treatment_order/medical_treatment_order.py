# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The order an employee takes to the hospital for treatment (safety.py)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import safety


class MedicalTreatmentOrder(Document):
    def validate(self):
        safety.order_validate(self)

    def on_update(self):
        safety.order_on_update(self)

    def on_submit(self):
        safety.order_on_submit(self)

    def on_cancel(self):
        safety.order_on_cancel(self)
