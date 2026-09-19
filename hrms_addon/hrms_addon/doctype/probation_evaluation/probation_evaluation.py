# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The End of probation evaluation / confirmation form (LPL/HR/32).

The logic lives in hrms_addon/hrms_addon/probation.py (rules in the tested *_rules.py
and *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import probation


class ProbationEvaluation(Document):
    def validate(self):
        probation.validate(self)

    def on_submit(self):
        probation.on_submit(self)

    def on_cancel(self):
        probation.on_cancel(self)
