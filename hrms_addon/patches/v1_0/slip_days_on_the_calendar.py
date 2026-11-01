# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The days every slip already made shows (Luuka, 1 Nov 2026: "then you should
include holiday sunday"; pay_days_rules.calendar_days). A slip counted from now
on keeps them as it is counted, and one made before is given them from what it
holds. Its pay, and the Working Days and Payment Days it was worked out from,
are left as they are.

The fields are synced first: fixtures follow the patches on a migrate.
Safe to run twice."""

import frappe
from frappe.utils import date_diff, flt, getdate
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import pay_days, pay_days_rules as rules

SLIP = "Salary Slip"


def execute():
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype=SLIP)
    slips = frappe.get_all(SLIP, filters={"docstatus": ["<", 2]}, limit_page_length=0, fields=[
        "name", "employee", "start_date", "end_date", "payroll_frequency", "salary_slip_based_on_timesheet",
        "total_working_days", "payment_days", "leave_without_pay", "absent_days", "custom_days_in_period"])
    people = {row.name: row for row in frappe.get_all(
        "Employee", filters={"name": ["in", list({slip.employee for slip in slips})]}, limit_page_length=0,
        fields=["name", "date_of_joining", "relieving_date"])} if slips else {}
    on_the_month = pay_days.days_in_month()
    for slip in slips:
        if flt(slip.custom_days_in_period):
            continue
        working, paid = slip.total_working_days, slip.payment_days
        if on_the_month and pay_days.on_luuka_month(slip):
            working, paid = _calendar(slip, people.get(slip.employee) or {})
        frappe.db.set_value(SLIP, slip.name, {"custom_days_in_period": flt(working), "custom_days_paid": flt(paid)},
                            update_modified=False)


def _calendar(slip, person):
    """What a slip shows, from the days it keeps: Frappe HR's Payment Days are the days it counted from, less the
    leave without pay and the Absent Days, which hold the half days and any unmarked days it counted as absent."""
    start, end = getdate(slip.start_date), getdate(slip.end_date)
    first, last = start, end
    # as Frappe HR's Salary Slip has actual_start_date and actual_end_date
    joined, left = person.get("date_of_joining"), person.get("relieving_date")
    if joined and start < getdate(joined) <= end:
        first = getdate(joined)
    if left and start <= getdate(left) < end:
        last = getdate(left)
    on_payroll = date_diff(last, first) + 1
    return rules.calendar_days(date_diff(end, start) + 1, on_payroll, on_payroll,
                               on_payroll - flt(slip.leave_without_pay) - flt(slip.absent_days),
                               flt(slip.leave_without_pay))
