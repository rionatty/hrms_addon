# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One employee's nine-box placement."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import talent


class TalentPlacement(Document):
    def validate(self):
        talent.placement_validate(self)

    def on_update(self):
        talent.placement_on_update(self)

    def before_update_after_submit(self):
        talent.placement_before_update_after_submit(self)

    def on_submit(self):
        talent.placement_on_submit(self)

    def on_cancel(self):
        talent.placement_on_cancel(self)


def on_doctype_update():
    """The board and the reports read placements by review and step, and an
    employee's by their status: an index each (talent.add_indexes)."""
    talent.add_indexes()
