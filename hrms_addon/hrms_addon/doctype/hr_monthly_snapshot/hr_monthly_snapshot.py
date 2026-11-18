# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A month's build for the HR board pack: its status, its totals, its reconciliation by plant and its data quality.
The month's figures are its fact rows (board_facts.py)."""

from frappe.model.document import Document


class HRMonthlySnapshot(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import board_facts

        board_facts.snapshot_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import board_facts

        board_facts.snapshot_validate(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import board_facts

        board_facts.snapshot_on_trash(self)
