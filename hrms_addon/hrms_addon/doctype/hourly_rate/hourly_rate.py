# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A casual's hourly rate, from a day (Luuka, 10 Nov 2026: "the hourly rate
should be independent doctype it shouldnt be on employee ... accessed by only
HR manager and officer"). The weekly slip pays each day at the rate in force
that day (weekly_pay.py); the checks are weekly_pay.rate_validate."""

from frappe.model.document import Document


class HourlyRate(Document):
    def validate(self):
        from hrms_addon.hrms_addon import weekly_pay

        weekly_pay.rate_validate(self)
