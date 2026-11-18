# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A workforce issue and what HR did about it (Manufacturing Excellence): the signal that raised it and its KPI read week by week."""

from frappe.model.document import Document


class HRIntervention(Document):
    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.intervention_validate(self)
