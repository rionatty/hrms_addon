# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent read from the appraisal year (Luuka, 5 Oct 2026: "build a
coherent module properly linked with appraisal").

- The employment type a graduate trainee is on, made once.
- A Talent Review set up on one appraisal cycle reads the appraisal plan
  that cycle is a quarter of, so its placements carry the year to date.
- The placements not yet finalised read their year again: the quarters,
  the improvement plan, management's decision, and the competency evidence
  from whichever form the employee is on.

Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import talent


def execute():
    talent.seed_masters()
    for review in frappe.get_all(talent.REVIEW, filters={"appraisal_plan": ["in", ("", None)],
                                                         "appraisal_cycle": ["is", "set"]},
                                 fields=["name", "appraisal_cycle"]):
        plan = frappe.db.get_value("Appraisal Plan Quarter", {"appraisal_cycle": review.appraisal_cycle,
                                                              "parenttype": "Appraisal Plan"}, "parent")
        if plan:
            frappe.db.set_value(talent.REVIEW, review.name, "appraisal_plan", plan, update_modified=False)
    for employee in set(frappe.get_all(talent.PLACEMENT, filters={"docstatus": 0}, pluck="employee")):
        talent._refresh_open_placements(employee)
