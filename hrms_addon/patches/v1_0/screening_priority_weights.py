# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What each seeded JD priority counts for in the CV screening: Essential 3
and a must-have, Preferred 2, Desirable 1, only where no weight is set. The
competencies written before they had a priority take Preferred, as a new
row does."""

import frappe

from hrms_addon.hrms_addon import cv_screening


def execute():
    cv_screening.set_priority_weights()
    if frappe.db.exists("JD Requirement Priority", "Preferred"):
        frappe.db.sql("update `tabJD Competency` set priority = 'Preferred' where ifnull(priority, '') = ''")
