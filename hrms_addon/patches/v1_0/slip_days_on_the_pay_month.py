"""The days a monthly slip shows go back to the month of 26 its pay is
divided by (Luuka, 8 Nov 2026: "revert Working days to be considered need be
as 26"): every slip already made shows its own Working Days and Payment Days
again, where slip_days_on_the_calendar had given it the calendar's. Pay is
left alone. A site whose Payroll Settings show the calendar's keeps them.
Safe to run twice."""

import frappe
from frappe.utils import flt

from hrms_addon.hrms_addon import pay_days, pay_days_rules as rules

SLIP = "Salary Slip"
FIELDS = ["name", "total_working_days", "payment_days", "custom_days_in_period", "custom_days_paid"]


def execute():
    meta = frappe.get_meta(SLIP)
    if not (meta.has_field("custom_days_in_period") and meta.has_field("custom_days_paid")):
        return
    if pay_days.days_shown() == rules.CALENDAR:
        return
    for slip in frappe.get_all(SLIP, filters={"payroll_frequency": "Monthly", "salary_slip_based_on_timesheet": 0},
                               fields=FIELDS, limit_page_length=0):
        working, paid = flt(slip.total_working_days), flt(slip.payment_days)
        if (flt(slip.custom_days_in_period), flt(slip.custom_days_paid)) != (working, paid):
            frappe.db.set_value(SLIP, slip.name, {"custom_days_in_period": working, "custom_days_paid": paid},
                                update_modified=False)
