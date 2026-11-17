# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Board Report Settings: the attrition target and the wage bill's component groups."""

from frappe.model.document import Document


class BoardReportSettings(Document):
    def validate(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.settings_validate(self)
