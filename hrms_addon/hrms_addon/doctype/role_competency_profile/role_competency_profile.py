# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The skills a job title needs, in a section or everywhere: the level of each, whether it is critical and its
weight (competency.py)."""

from frappe.model.document import Document


class RoleCompetencyProfile(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import competency

        competency.profile_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import competency

        competency.profile_validate(self)
