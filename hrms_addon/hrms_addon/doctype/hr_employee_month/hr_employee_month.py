# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One employee's month for the HR board pack, frozen as at the month's end; or, imported for the
months before the system, a group of people at once (board_facts.py)."""

from frappe.model.document import Document


class HREmployeeMonth(Document):
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

    board_facts.add_indexes("HR Employee Month")
