# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The appraisal templates laid out like Luuka's workbook, every Job Title
naming its template, and the employee's own self-appraisal, on a site that
already has templates and appraisals under way.

1. The fields this writes exist first: fixtures are synced only after
   every patch has run.
2. Appraisal Settings are saved with their defaults: employees appraise
   themselves, and the cycles a plan opens score KRAs automatically.
3. Each scorecard template is laid out as the workbook is: its form type,
   each perspective's KPIs together, and the perspective's weight on its
   first KPI.
4. The supervisory form (LPL/HR/18) gets its template, and a Job Title with
   no template is given the active scorecard made for it.
5. The appraisals under way go on as they were raised: the self-appraisal
   is on for them, the supervisor's name is filled in, and a plan's
   appraisal still in Draft now waits on the employee's self-appraisal.
6. A plan's cycle that was set to Manual Rating, and holds no goals rated
   by hand, is scored automatically, as a new cycle is.

Everything here writes straight to the database, so nothing is refused by
a check that did not exist when the records were made. Safe to run twice.
"""

import frappe
from frappe.utils import flt
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import appraisal_approval as approval, appraisal_rules, bsc, bsc_rules

TEMPLATE = "Appraisal Template"
SETTINGS = "Appraisal Settings"


def execute():
    sync_fixtures("hrms_addon")
    for doctype in ("Appraisal", TEMPLATE, "Designation", "Appraisal Cycle"):
        frappe.clear_cache(doctype=doctype)
    _settings()
    for name in frappe.get_all(TEMPLATE, pluck="name"):
        _lay_out(name)
    if frappe.db.exists("DocType", "Appraisal Template Factor"):
        bsc.seed_supervisory_template()
    _designations()
    _appraisals()
    _cycles()


def _settings():
    if not frappe.db.exists("DocType", SETTINGS) or frappe.db.get_singles_dict(SETTINGS):
        return
    for key, value in appraisal_rules.SETTINGS_DEFAULTS.items():
        frappe.db.set_single_value(SETTINGS, key, value)


def _lay_out(name):
    """Section A as the workbook has it, written row by row."""
    kpis = frappe.get_all("BSC Template KPI", filters={"parent": name, "parenttype": TEMPLATE,
                                                       "parentfield": "custom_kpis"},
                          fields=["name", "perspective", "kpi", "timing", "weight", "idx"], order_by="idx asc")
    perspectives = frappe.get_all("BSC Template Perspective", filters={"parent": name, "parenttype": TEMPLATE,
                                                                       "parentfield": "custom_perspectives"},
                                  fields=["perspective", "weight"], order_by="idx asc")
    if not (kpis or perspectives):
        return
    if not frappe.db.get_value(TEMPLATE, name, "custom_form_type"):
        frappe.db.set_value(TEMPLATE, name, "custom_form_type", bsc_rules.FORM_BSC, update_modified=False)
    if any(flt(row.weight) for row in kpis):
        return  # already laid out
    weights = {row.perspective: flt(row.weight) for row in perspectives}
    rows = [dict(row, weight=None) for row in kpis]
    for perspective, weight in weights.items():
        first = next((row for row in rows if row["perspective"] == perspective), None)
        if first:
            first["weight"] = weight
        elif weight:
            # a weighted perspective with no KPI listed under it keeps its weight
            rows.append({"name": None, "perspective": perspective, "kpi": perspective, "timing": None,
                         "weight": weight})
    arranged, _perspectives = bsc_rules.arrange_kpis(rows)
    for idx, row in enumerate(arranged, 1):
        if row.get("name"):
            frappe.db.set_value("BSC Template KPI", row["name"], {"weight": row["weight"], "idx": idx},
                                update_modified=False)
        else:
            frappe.get_doc({"doctype": "BSC Template KPI", "parent": name, "parenttype": TEMPLATE,
                            "parentfield": "custom_kpis", "idx": idx, "perspective": row["perspective"],
                            "kpi": row["kpi"], "weight": row["weight"]}).db_insert()


def _designations():
    """A Job Title with no template names the active scorecard made for it."""
    for designation in frappe.get_all("Designation", filters={"appraisal_template": ["is", "not set"]},
                                      pluck="name"):
        template = bsc.template_for(designation=designation)
        if template:
            frappe.db.set_value("Designation", designation, "appraisal_template", template, update_modified=False)


def _appraisals():
    frappe.db.sql("update `tabAppraisal` set custom_self_appraisal = 1 where docstatus < 2")
    for row in frappe.get_all("Appraisal", filters={"custom_supervisor": ["is", "set"]},
                              fields=["name", "custom_supervisor"]):
        frappe.db.set_value("Appraisal", row.name, "custom_supervisor_name",
                            frappe.db.get_value("Employee", row.custom_supervisor, "employee_name"),
                            update_modified=False)
    for name in frappe.get_all("Appraisal", filters={"docstatus": 0, "workflow_state": approval.DRAFT,
                                                     "custom_plan": ["is", "set"]}, pluck="name"):
        frappe.db.set_value("Appraisal", name, {"workflow_state": approval.PENDING_SELF,
                                                "custom_appraisal_status": approval.PENDING_SELF},
                            update_modified=False)


def _cycles():
    for cycle in frappe.get_all("Appraisal Cycle", filters={"kra_evaluation_method": appraisal_rules.KRA_MANUAL,
                                                            "custom_plan": ["is", "set"],
                                                            "status": ["!=", "Completed"]}, pluck="name"):
        appraisals = frappe.get_all("Appraisal", filters={"appraisal_cycle": cycle}, pluck="name")
        if appraisals and frappe.get_all("Appraisal Goal", filters={"parent": ["in", appraisals],
                                                                    "parenttype": "Appraisal"}, limit=1):
            continue  # goals rated by hand stay rated by hand
        frappe.db.set_value("Appraisal Cycle", cycle, "kra_evaluation_method", appraisal_rules.KRA_AUTOMATED,
                            update_modified=False)
        for name in frappe.get_all("Appraisal", filters={"appraisal_cycle": cycle, "docstatus": 0}, pluck="name"):
            frappe.db.set_value("Appraisal", name, "rate_goals_manually", 0, update_modified=False)
