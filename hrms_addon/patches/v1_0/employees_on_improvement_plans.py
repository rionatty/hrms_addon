"""The Employee says whether they are on an open improvement plan, in red on
the Employee list (Luuka, 5 Nov 2026: "System should have pip employees
populate in red/highlighted"). Those on a plan already, and anyone marked who
is on none, are marked as the plans stand. The fields are synced first:
fixtures follow the patches on a migrate. Safe to run twice."""

import frappe
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import pips, pip_rules as rules

PLAN = "Performance Improvement Plan"


def execute():
    if not frappe.db.exists("DocType", PLAN):
        return
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype="Employee")
    on_plans = set(frappe.get_all(PLAN, filters={"docstatus": 0, "status": ["in", list(rules.OPEN)]},
                                  pluck="employee", limit_page_length=0))
    marked = set(frappe.get_all("Employee", filters={"custom_on_pip": 1}, pluck="name", limit_page_length=0))
    for employee in sorted(filter(None, on_plans | marked)):
        pips.mark_appraisals(employee)
