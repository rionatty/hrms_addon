# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A shift rotation: the cycle, the plant and who is on it."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import shifts


class ShiftRotation(Document):
    def validate(self):
        shifts.rotation_validate(self)
