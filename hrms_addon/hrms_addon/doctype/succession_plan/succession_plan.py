# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A year's succession plan (talent blueprint, section 6): its critical roles, reviewed and finalised by the
Talent Council as one. The workflow is succession_plan_approval.py; the glue succession_plans.py."""

from frappe.model.document import Document


class SuccessionPlan(Document):
    def validate(self):
        from hrms_addon.hrms_addon import succession_plans

        succession_plans.plan_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import succession_plans

        succession_plans.plan_on_update(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import succession_plans

        succession_plans.plan_on_submit(self)
