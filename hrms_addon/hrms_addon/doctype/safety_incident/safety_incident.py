# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A safety incident: the accident, its two reports and what follows (safety.py)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import safety


class SafetyIncident(Document):
    def validate(self):
        safety.incident_validate(self)

    def on_update(self):
        safety.incident_on_update(self)

    def on_submit(self):
        safety.incident_on_submit(self)

    def before_update_after_submit(self):
        safety.incident_before_update_after_submit(self)

    def on_update_after_submit(self):
        safety.incident_on_update_after_submit(self)

    def on_cancel(self):
        safety.incident_on_cancel(self)
