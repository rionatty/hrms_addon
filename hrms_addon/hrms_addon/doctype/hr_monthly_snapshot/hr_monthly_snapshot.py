# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A month's figures by plant for the HR board pack, built from the site at the month's end or imported for the
months before it (board_pack.py)."""

from frappe.model.document import Document


class HRMonthlySnapshot(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.snapshot_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.snapshot_validate(self)
