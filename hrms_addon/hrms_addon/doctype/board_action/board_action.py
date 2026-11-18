# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A board action: the business imperative, the HR lever, its owner and the quarter it is due, carried from quarter
to quarter with its progress (board_pack.py)."""

from frappe.model.document import Document


class BoardAction(Document):
    def validate(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.action_validate(self)
