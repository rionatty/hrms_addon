# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An order released to the floor: Order Feasibility sets its labour and losses against its value."""

from frappe.model.document import Document


class PlantOrder(Document):
    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.order_validate(self)
