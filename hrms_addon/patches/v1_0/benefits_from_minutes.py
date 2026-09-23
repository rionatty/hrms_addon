# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The two benefits the minutes price (Reward and Compensation, 16 and 20
July 2026, §4.8), on the live site.

Maternity Benefit is made if it is missing. Bereavement Support was
seeded at nil for HR to fill in; the minutes fill it in — 70% of gross,
for a mother, father or child — but only where nobody has set an amount
or a percentage on it already. Safe to run twice.

It runs after the fields are synced (post_model_sync, then fixtures), so
the claim type's new fields may not exist yet on the first migrate: it
makes them from this app's own fixture file first.
"""

import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from hrms_addon.hrms_addon import benefits, benefits_rules as rules

TYPE = "Expense Claim Type"


def execute():
    if not frappe.db.exists("DocType", TYPE):
        return
    _make_fields()
    benefits.seed_standard_claims()
    name = rules.BEREAVEMENT_SUPPORT
    if not frappe.db.exists(TYPE, name):
        return
    amount, percent = frappe.db.get_value(TYPE, name, ["custom_standard_amount", "custom_percent_of_gross"])
    if (amount or 0) or (percent or 0):
        return
    for field, value in benefits.minutes_values(name).items():
        frappe.db.set_value(TYPE, name, field, value, update_modified=False)


def _make_fields():
    path = frappe.get_app_path("hrms_addon", "fixtures", "custom_field.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    fields = {}
    for row in rows:
        if row.get("dt") not in (TYPE, "Expense Claim"):
            continue
        spec = {key: value for key, value in row.items()
                if key not in ("doctype", "dt", "name", "owner", "modified_by", "creation", "modified")}
        fields.setdefault(row["dt"], []).append(spec)
    if fields:
        create_custom_fields(fields, ignore_validate=True)
