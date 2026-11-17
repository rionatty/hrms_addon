# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A section's shift, from the supervisor's report (Manufacturing Excellence, 17 Nov 2026). Submitted once the Production Manager or General Manager has checked it."""

from frappe.model.document import Document


class ShiftReport(Document):
    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.shift_validate(self)
