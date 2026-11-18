# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A mentor's session with a trainee or a successor."""

from frappe.model.document import Document


class MentoringSession(Document):
    def validate(self):
        from hrms_addon.hrms_addon import graduates

        graduates.session_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import graduates

        graduates.session_on_update(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import graduates

        graduates.session_on_trash(self)
