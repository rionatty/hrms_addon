# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One role's balanced scorecard (LPL PMS FY 2026)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import bsc


class BSCAppraisalTemplate(Document):
    def validate(self):
        bsc.template_validate(self)
