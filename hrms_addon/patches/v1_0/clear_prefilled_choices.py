# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Clear the choices Frappe made by itself.

Frappe gives a Select with no default its first option on every new
document and row. Until the performance module's choices began with a
blank:

1. An appraisal raised by the Appraisal Plan, or taken from its template
   again, came rated 1 on every factor and objective, by the employee and
   by the supervisor (appraisal_rules.prefilled_ratings). Each open
   appraisal is cleared of those and scored again; one that loses every
   rating of the employee's was never self-appraised.
2. Every employee fetched into a Performance Review came decided as a
   Promotion, so the check that management decided on everyone never asked
   (appraisal_rules.prefilled_decisions). An open review is cleared of its
   Promotions, with a comment saying whose.
3. An improvement plan came closed as Improved, its points Met before any
   review (pip_rules.prefilled). An open plan is cleared of both.

Nothing submitted is changed: the submitted appraisals and filed reviews
that carry such choices are listed in the migrate output for HR to check.
Safe to run twice.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms_addon.hrms_addon import appraisal_approval as approval, appraisal_rules, appraisals, pip_rules

RATING_TABLES = ("Appraisal Factor Rating", "Appraisal Objective Rating")
# written as Frappe stores them: a score not given is 0, never NULL, which
# the database refuses for a number column
SCORE_FIELDS = ("custom_factors_score", "custom_objectives_score", "custom_total_score", "final_score",
                "total_score", "self_score", "custom_annual_score")


def execute():
    for line in _appraisals() + _reviews() + _plans():
        print("HRMS Addon: %s" % line)


def _appraisals():
    cleared, filed, unrated = [], [], []
    for appraisal in frappe.get_all("Appraisal", filters={"docstatus": ["!=", 2]},
                                    fields=["name", "docstatus", approval.STATE_FIELD, approval.SELF_FIELD]):
        rows, table_of = [], {}
        for doctype in RATING_TABLES:
            for row in frappe.get_all(doctype, filters={"parent": appraisal.name, "parenttype": "Appraisal"},
                                      fields=["name", "employee_rating", "supervisor_rating"]):
                rows.append(row)
                table_of[row.name] = doctype
        state = appraisal.get(approval.STATE_FIELD) or (approval.COMPLETED if appraisal.docstatus else approval.DRAFT)
        found = appraisal_rules.prefilled_ratings(
            rows, supervisor_had_it=state not in approval.BEFORE_SUPERVISOR,
            employee_had_it=bool(appraisal.get(approval.SELF_FIELD)) and state != approval.DRAFT)
        if not found:
            continue
        if appraisal.docstatus == 1:
            filed.append(appraisal.name)
            continue
        for column, names in found.items():
            for name in names:
                frappe.db.set_value(table_of[name], name, column, "", update_modified=False)
        doc = frappe.get_doc("Appraisal", appraisal.name)
        appraisals._score(doc)
        frappe.db.set_value("Appraisal", doc.name, dict({field: flt(doc.get(field)) for field in SCORE_FIELDS},
                                                        custom_band=doc.get("custom_band")), update_modified=False)
        cleared.append(doc.name)
        if "employee_rating" in found and doc.get(approval.SELF_FIELD) and state not in approval.BEFORE_SUPERVISOR:
            unrated.append(doc.name)
    # further on, an appraisal left with no rating of the employee's was never self-appraised
    gave = appraisals.gave_self_appraisal(unrated)
    for name in unrated:
        if name not in gave:
            frappe.db.set_value("Appraisal", name, approval.SELF_FIELD, 0, update_modified=False)
    lines = []
    if cleared:
        lines.append("ratings Frappe had filled in as 1 cleared on %d open appraisal(s): %s"
                     % (len(cleared), ", ".join(cleared)))
    if filed:
        lines.append("submitted appraisals rated 1 throughout, as Frappe filled them in, to check (cancel and amend "
                     "any nobody rated): %s" % ", ".join(filed))
    return lines


def _reviews():
    cleared, filed = [], []
    for review in frappe.get_all("Performance Review", filters={"docstatus": ["!=", 2]}, fields=["name", "docstatus"]):
        rows = frappe.get_all("Performance Review Employee",
                              filters={"parent": review.name, "parenttype": "Performance Review"},
                              fields=["name", "employee", "employee_name", "decision", "position_change"])
        names = appraisal_rules.prefilled_decisions(rows)
        if not names:
            continue
        who = [row for row in rows if row.name in names]
        if review.docstatus == 1:
            filed.append("%s (%s)" % (review.name, ", ".join(
                "%s%s" % (row.employee_name or row.employee,
                          " in %s" % row.position_change if row.position_change else "") for row in who)))
            continue
        for name in names:
            frappe.db.set_value("Performance Review Employee", name, "decision", "", update_modified=False)
        frappe.get_doc("Performance Review", review.name).add_comment("Info", _(
            "Decision cleared for {0}: it had been filled in as Promotion by default. Record it again.").format(
            ", ".join(row.employee_name or row.employee for row in who)))
        cleared.append(review.name)
    lines = []
    if cleared:
        lines.append("Promotion filled in by default cleared on %d open review(s): %s"
                     % (len(cleared), ", ".join(cleared)))
    if filed:
        lines.append("filed reviews that recorded a Promotion, to check each was decided: %s" % "; ".join(filed))
    return lines


def _plans():
    cleared = []
    for plan in frappe.get_all("Performance Improvement Plan", filters={"docstatus": 0}, fields=["name", "outcome"]):
        objectives = frappe.get_all("PIP Objective",
                                    filters={"parent": plan.name, "parenttype": "Performance Improvement Plan"},
                                    fields=["name", "progress", "reviewed_on"])
        outcome, names = pip_rules.prefilled(plan.outcome, objectives)
        if not (outcome or names):
            continue
        if outcome:
            frappe.db.set_value("Performance Improvement Plan", plan.name, "outcome", "", update_modified=False)
        for name in names:
            frappe.db.set_value("PIP Objective", name, "progress", "", update_modified=False)
        cleared.append(plan.name)
    if not cleared:
        return []
    return ["outcome and unreviewed points Frappe had filled in cleared on %d open improvement plan(s): %s"
            % (len(cleared), ", ".join(cleared))]
