# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One people activity on the floor (Manufacturing Excellence, 17 Nov 2026)."""

from frappe.model.document import Document


class PeopleLog(Document):
    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.log_validate(self)
