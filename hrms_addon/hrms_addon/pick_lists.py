# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the pick lists: the KRA form's (KRA Perspective, Level, Unit, Data
Source, Review Frequency) and the Job Description tables' (JD Relationship
Type, Stakeholder Type, Authority Level, Horizon, ISO Standard,
Specification Type, Requirement Priority, Competency Category).

What to create is decided by jd_rules.seed_plan, which has no Frappe
import and is tested without a bench. This only reads what is there and
inserts what is missing.

Seeded ONCE, never re-asserted. After seeding, each list belongs to HR: a
value they delete must stay deleted and a rename must stay renamed, which
rules out fixtures (re-imported with force on every migrate) and
after_migrate (runs every migrate). Instead:

  * existing sites — patches hrms_addon.patches.v1_0.seed_kra_masters and
    seed_jd_masters, which migrate runs once each;
  * fresh installs — after_install below, because Frappe marks every patch
    as already run when an app is installed
    (frappe/installer.py set_all_patches_as_completed) and never executes
    them there.
"""

import frappe

from hrms_addon.hrms_addon import jd_rules


def seed_kra_masters():
    seed_masters(jd_rules.KRA_MASTERS)


def seed_jd_masters():
    seed_masters(jd_rules.JD_MASTERS)


def seed_masters(masters):
    existing = {doctype: frappe.get_all(doctype, pluck="name") for doctype in masters}
    plan = jd_rules.seed_plan(existing, _values_in_use(masters), masters)
    for records in plan.values():
        for record in records:
            frappe.get_doc(record).insert(ignore_permissions=True)


def _values_in_use(masters):
    """Values already stored in the fields that pick from these masters.

    Those fields were Select dropdowns until now. A stored value missing
    from its new master would be a broken link and block the next save of
    the document holding it, so each one is seeded too. A field whose
    column does not exist yet (the KRA custom fields on a fresh install,
    before fixtures) has nothing stored.
    """
    in_use = {}
    for (doctype, fieldname), master in jd_rules.FIELD_MASTERS.items():
        if master not in masters:
            continue
        try:
            columns = set(frappe.db.get_table_columns(doctype))
        except Exception:
            continue
        if fieldname in columns:
            in_use.setdefault(master, []).extend(
                value
                for value in frappe.get_all(doctype, distinct=True, pluck=fieldname, order_by=f"{fieldname} asc")
                if value
            )
    return in_use


def after_install():
    seed_masters(jd_rules.MASTERS)
