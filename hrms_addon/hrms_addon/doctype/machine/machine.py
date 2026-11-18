# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A machine or line of a section: downtime and output are recorded against it."""

from frappe.model.document import Document


class Machine(Document):
    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.machine_validate(self)
