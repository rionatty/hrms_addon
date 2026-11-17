# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One employee's need for one training or certificate (LMS blueprint flow 4.2): made and kept up to date by
learning.py from the Training Rules, or recommended by HR, a head of department or a supervisor."""

from frappe.model.document import Document


class EmployeeTrainingRequirement(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning

        learning.requirement_validate(self)
