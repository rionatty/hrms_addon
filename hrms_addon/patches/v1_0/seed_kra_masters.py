# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the KRA pick lists on sites that already have the app.

The KRA form's five dropdowns (Perspective, Applies To (Level), Unit, Data
Source, Review Frequency) change from fixed Select options to Links to
master DocTypes HR can extend.

Runs in post_model_sync: after the master DocTypes are synced, before the
fixtures turn the KRA fields into Links, so every value already stored on
a KRA gets its master record first and stays a valid link.

The field type change itself is safe on import: fixtures delete and
re-insert a Custom Field (frappe/modules/import_file.py delete_old_doc),
so the Select -> Link type check, which only runs on update, never fires,
and the column (varchar either way) keeps its data.
"""

from hrms_addon.hrms_addon.kra_masters import seed_kra_masters


def execute():
    seed_kra_masters()
