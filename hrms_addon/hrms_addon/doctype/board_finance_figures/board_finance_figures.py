# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A quarter's revenue, output and staff cost by plant, typed by Finance (decided 17 Nov 2026)."""

from frappe.model.document import Document


class BoardFinanceFigures(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.finance_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import board_pack

        board_pack.finance_validate(self)
