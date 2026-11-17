# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The quarterly HR Board Report (LPL HR Board Report Q3 2026): its figures worked out from the HR Monthly
Snapshots (board_rules.quarter), HR's words, and the deck and workbook made from both (board_deck.py)."""

from frappe.model.document import Document


class HRBoardReport(Document):
    def validate(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.report_validate(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.report_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.report_on_cancel(self)
