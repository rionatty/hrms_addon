# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The week for the Monday production meeting, for a plant or the company."""

from frappe.model.document import Document


class HRPartnerBrief(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import excellence_brief

        excellence_brief.brief_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import excellence_brief

        excellence_brief.brief_validate(self)
