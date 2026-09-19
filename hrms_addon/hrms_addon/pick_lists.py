# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the pick lists: the KRA form's (KRA Perspective, Level, Unit, Data
Source, Review Frequency), the Job Description tables' (JD Relationship
Type, Stakeholder Type, Authority Level, Horizon, ISO Standard,
Specification Type, Requirement Priority, Competency Category) and the Job
Applicant Bio-Data tab's (District, Relationship, Spoken Language,
Examination Level), and Luuka's branches (org_rules.py).

What to create is decided by jd_rules.seed_plan, which has no Frappe
import and is tested without a bench. This only reads what is there and
inserts what is missing.

Seeded ONCE, never re-asserted. After seeding, each list belongs to HR: a
value they delete must stay deleted and a rename must stay renamed, which
rules out fixtures (re-imported with force on every migrate) and
after_migrate (runs every migrate). Instead:

  * existing sites — patches hrms_addon.patches.v1_0.seed_kra_masters,
    seed_jd_masters and seed_bio_data_masters, which migrate runs once each;
  * fresh installs — after_install below, because Frappe marks every patch
    as already run when an app is installed
    (frappe/installer.py set_all_patches_as_completed) and never executes
    them there.
"""

import frappe

from hrms_addon.hrms_addon import bio_data_rules, jd_rules, onboarding_rules, org_rules, probation_rules

# Every pick list, and every (DocType, field) that picks from one
MASTERS = {**jd_rules.MASTERS, **bio_data_rules.BIO_DATA_MASTERS, **org_rules.ORG_MASTERS}
FIELD_MASTERS = {**jd_rules.FIELD_MASTERS, **bio_data_rules.BIO_DATA_FIELD_MASTERS}


def seed_kra_masters():
    seed_masters(jd_rules.KRA_MASTERS)


def seed_jd_masters():
    seed_masters(jd_rules.JD_MASTERS)


def seed_bio_data_masters():
    seed_masters(bio_data_rules.BIO_DATA_MASTERS)


def seed_branches():
    """Luuka's three branches, which every approval is routed by."""
    seed_masters(org_rules.ORG_MASTERS)


def seed_qualification_types():
    """Qualification Type, added to the Bio-Data after its other lists."""
    seed_masters({"Qualification Type": bio_data_rules.BIO_DATA_MASTERS["Qualification Type"]})
    flag_certification_types()


def flag_certification_types():
    """The seeded certification and licence types go in the interview shortlist's
    own column. Runs once with the seeding, like it, so a type HR later
    unticks stays unticked."""
    for name in bio_data_rules.CERTIFICATION_TYPES:
        if frappe.db.exists("Qualification Type", name):
            frappe.db.set_value("Qualification Type", name, "is_certification", 1)


def seed_onboarding_masters():
    """The Tool Providers, with the role preparing a department's own tools
    (its Head of Department), and the probation form's ratable factors."""
    seed_masters({**onboarding_rules.ONBOARDING_MASTERS, **probation_rules.PROBATION_MASTERS})
    for provider, role in onboarding_rules.PROVIDER_ROLES.items():
        if (frappe.db.exists("Role", role) and frappe.db.exists("Tool Provider", provider)
                and not frappe.db.get_value("Tool Provider", provider, "responsible_role")):
            frappe.db.set_value("Tool Provider", provider, "responsible_role", role)


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
    for (doctype, fieldname), master in FIELD_MASTERS.items():
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
    seed_masters(MASTERS)
    flag_certification_types()
    seed_onboarding_masters()
