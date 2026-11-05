"""Overtime is counted and paid in whole hours, rounded down (Luuka, 5 Nov
2026: "over time is only rounded to full hour like if employee works for 1:30
then its should be 1hr"). An Overtime Type that counts the clock in steps, or
from a least, under an hour says so at an hour, which is what the rules now do
with it (overtime_rules.clock_hours). A step or least of an hour or more stays
as HR set it. Safe to run twice."""

import frappe
from frappe.utils import cint

TYPE = "Overtime Type"
FIELDS = ("custom_clock_step", "custom_clock_minimum")
HOUR = 60


def execute():
    if not all(frappe.db.has_column(TYPE, field) for field in FIELDS):
        return
    for row in frappe.get_all(TYPE, fields=["name", *FIELDS], limit_page_length=0):
        values = {field: HOUR for field in FIELDS if cint(row.get(field)) < HOUR}
        if values:
            frappe.db.set_value(TYPE, row.name, values, update_modified=False)
