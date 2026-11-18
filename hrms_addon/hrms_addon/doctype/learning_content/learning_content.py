# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A policy, SOP, manual, video, link, presentation, toolbox talk or quiz, with its versions (learning_library.py)."""

from frappe.model.document import Document


class LearningContent(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_library

        learning_library.content_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import learning_library

        learning_library.content_on_update(self)
