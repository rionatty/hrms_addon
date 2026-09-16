# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the KRA pick lists (KRA Perspective, Level, Unit, Data Source,
Review Frequency).

What to create is decided by jd_rules.seed_plan, which has no Frappe
import and is tested without a bench. This only reads what is there and
inserts what is missing.

Seeded ONCE, never re-asserted. After seeding, each list belongs to HR: a
value they delete must stay deleted and a rename must stay renamed, which
rules out fixtures (re-imported with force on every migrate) and
after_migrate (runs every migrate). Instead:

  * existing sites — patch hrms_addon.patches.v1_0.seed_kra_masters, which
    migrate runs once;
  * fresh installs — after_install below, because Frappe marks every patch
    as already run when an app is installed
    (frappe/installer.py set_all_patches_as_completed) and never executes
    them there.
"""

import frappe

from hrms_addon.hrms_addon import jd_rules


def seed_kra_masters():
    existing = {doctype: frappe.get_all(doctype, pluck="name") for doctype in jd_rules.KRA_MASTERS}
    plan = jd_rules.seed_plan(existing, _values_in_use())
    for records in plan.values():
        for record in records:
            frappe.get_doc(record).insert(ignore_permissions=True)


def _values_in_use():
    """Values already stored on KRAs, per master.

    Those fields were Select dropdowns until now. A stored value missing
    from its new master would be a broken link and block the next save of
    that KRA, so each one is seeded too.
    """
    try:
        columns = set(frappe.db.get_table_columns("KRA"))
    except Exception:
        return {}
    in_use = {}
    for fieldname, doctype in jd_rules.KRA_FIELD_MASTERS.items():
        if fieldname in columns:
            in_use[doctype] = [
                value
                for value in frappe.get_all("KRA", distinct=True, pluck=fieldname, order_by=f"{fieldname} asc")
                if value
            ]
    return in_use


def after_install():
    seed_kra_masters()
