# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Intern Placement Letter: an internship placement at a plant, under a department and a supervisor."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import employee_data


class InternPlacement(Document):
    def validate(self):
        employee_data.placement_validate(self)

    def on_submit(self):
        employee_data.placement_on_submit(self)

    def on_cancel(self):
        employee_data.placement_on_cancel(self)
