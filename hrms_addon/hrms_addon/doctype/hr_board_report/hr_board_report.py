# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The quarterly HR Board Report (LPL HR Board Report Q3 2026): its figures from the facts of its months
(board_pack.quarter_figures), the KPIs and ratings worked out, HR's words, and the deck and workbook made from both
(board_deck.py). Approved, it locks its months."""

from frappe.model.document import Document


class HRBoardReport(Document):
    def validate(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.report_validate(self)

    def before_submit(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.report_before_submit(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.report_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.report_on_cancel(self)
