# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's certificate, the Certification Register (LMS blueprint flow 4.6). Its expiry is chased
by learning.daily, one rung more told at each step."""

from frappe.model.document import Document


class EmployeeCertification(Document):
    @property
    def days_to_expiry(self):
        """Worked out when read, so it is never a day behind."""
        from frappe.utils import today

        from hrms_addon.hrms_addon import learning_rules

        return learning_rules.days_left(self.get("expiry_date"), today())

    def validate(self):
        from hrms_addon.hrms_addon import learning

        learning.certificate_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import learning

        learning.certificate_on_update(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import learning

        learning.certificate_on_trash(self)
