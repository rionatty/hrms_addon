"""Maternity Benefit is paid for three children at most, born since the
employee joined, twins being two (Luuka, 5 Nov 2026: "only 3 children allowed
born from when someone joins the company", "they count number of kids"). The
type already on the site is ticked to count children; its At Most stays as HR
set it. Bereavement Support's description says it is once for each parent.

The fields are synced first: fixtures follow the patches on a migrate.
Safe to run twice."""

import frappe
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import benefits, benefits_rules as rules

TYPE = "Expense Claim Type"


def execute():
    if not frappe.db.exists("DocType", TYPE):
        return
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype=TYPE)
    for name in (rules.MATERNITY_BENEFIT, rules.BEREAVEMENT_SUPPORT):
        if not frappe.db.exists(TYPE, name):
            continue
        values = benefits.minutes_values(name)
        if name == rules.MATERNITY_BENEFIT:
            frappe.db.set_value(TYPE, name, {"custom_counts_children": 1, "description": values["description"]},
                                update_modified=False)
        else:
            frappe.db.set_value(TYPE, name, "description", values["description"], update_modified=False)
