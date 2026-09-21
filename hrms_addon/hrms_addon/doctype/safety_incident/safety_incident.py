# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A safety incident: the accident, the sick leave and what follows."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import discipline


class SafetyIncident(Document):
    def validate(self):
        discipline.incident_validate(self)

    def on_submit(self):
        discipline.incident_on_submit(self)

    def on_cancel(self):
        discipline.incident_on_cancel(self)
