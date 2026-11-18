# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A month of learning, counted by plant and department, with its health (learning_centre.py)."""

from frappe.model.document import Document


class LearningSnapshot(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import learning_centre

        learning_centre.snapshot_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import learning_centre

        learning_centre.snapshot_validate(self)
