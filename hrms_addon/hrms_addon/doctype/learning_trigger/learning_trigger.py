# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A process change, new equipment, an audit finding, a complaint or a defect: the refreshers it sets off
(learning_loop.py)."""

from frappe.model.document import Document


class LearningTrigger(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_loop

        if self.docstatus == 0:
            self.status = "Draft"
        learning_loop.trigger_validate(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import learning_loop

        learning_loop.trigger_on_submit(self)

    def on_cancel(self):
        self.db_set("status", "Cancelled", update_modified=False)
