# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Learning content given to one employee, and how far they are with it (learning_library.py)."""

from frappe.model.document import Document


class LearningContentAssignment(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_library

        learning_library.assignment_validate(self)


def on_doctype_update():
    """One per employee and content."""
    from hrms_addon.hrms_addon import learning

    learning.add_indexes("Learning Content Assignment")
