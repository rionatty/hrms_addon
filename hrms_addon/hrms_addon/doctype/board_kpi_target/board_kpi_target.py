# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A board metric's target for the company or a plant over a period, with its amber and red bands (board_pack.py)."""

from frappe.model.document import Document


class BoardKPITarget(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.target_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.target_validate(self)
