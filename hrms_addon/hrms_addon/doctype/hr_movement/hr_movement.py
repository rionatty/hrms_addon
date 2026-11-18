# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A hire, exit, transfer or conversion, on the day it took effect (board_facts.py)."""

from frappe.model.document import Document


class HRMovement(Document):
    def validate(self):
        from hrms_addon.hrms_addon import board_facts

        board_facts.fact_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import board_facts

        board_facts.fact_on_update(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import board_facts

        board_facts.fact_on_trash(self)


def on_doctype_update():
    from hrms_addon.hrms_addon import board_facts

    board_facts.add_indexes("HR Movement")
