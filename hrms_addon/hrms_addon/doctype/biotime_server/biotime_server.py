# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Where Luuka's clockings are read from."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import biotime


class BioTimeServer(Document):
    def validate(self):
        biotime.settings_validate(self)
