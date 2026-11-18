# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A plant's production section (Manufacturing Excellence): named Section - Plant, with its dated standards and roster."""

from frappe.model.document import Document


class WorkSection(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import excellence

        excellence.section_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.section_validate(self)
