# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Continuing professional development: an activity's hours and points, checked by HR (learning_loop.py)."""

from frappe.model.document import Document


class CPDLog(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_loop

        learning_loop.cpd_validate(self)

    def before_update_after_submit(self):
        from hrms_addon.hrms_addon import learning_loop

        learning_loop.cpd_validate(self)
