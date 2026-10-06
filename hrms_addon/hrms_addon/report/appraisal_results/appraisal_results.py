# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Appraisal Results (Performance Management, test cases 5, 6 and 10): every
appraisal of a period with its score, what is to become of the employee (a
promotion, a salary increase, an improvement plan, or nothing more) and how
far that has got, from the score's suggestion to management's approval.

The rows are appraisals.results(): the outcome is what management approved,
else the decision on the Performance Review the appraisal is on, else what
the score alone suggests (appraisal_rules.result_outcome). Prepare Report
for Management puts what is shown on a Performance Review, which the
General Manager and the Executive Director approve
(performance_review_approval.py).
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import appraisal_rules as rules
from hrms_addon.hrms_addon import appraisals

# the summary's name for each outcome, and its colour
OUTCOME_LABELS = {rules.PROMOTION: "Promotions", rules.INCREASE: "Salary Increases",
                  rules.PIP: "Improvement Plans", rules.CLOSE: "Closed"}
OUTCOME_INDICATORS = {rules.PROMOTION: "Green", rules.INCREASE: "Blue", rules.PIP: "Red", rules.CLOSE: "Grey"}


def execute(filters=None):
    rows = appraisals.results(frappe._dict(filters or {}))
    return columns(), rows, None, _chart(rows), _summary(rows)


def columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Job Title"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation",
         "width": 150},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"label": _("Plant"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 110},
        {"label": _("Quarter"), "fieldname": "quarter", "fieldtype": "Data", "width": 75},
        {"label": _("Form"), "fieldname": "form", "fieldtype": "Data", "width": 90},
        {"label": _("Score"), "fieldname": "score", "fieldtype": "Percent", "width": 80},
        {"label": _("Rating"), "fieldname": "band", "fieldtype": "Data", "width": 110},
        {"label": _("Year to Date"), "fieldname": "year_score", "fieldtype": "Percent", "width": 105},
        {"label": _("Outcome"), "fieldname": "outcome", "fieldtype": "Data", "width": 210},
        {"label": _("Increase %"), "fieldname": "increase", "fieldtype": "Percent", "width": 95},
        {"label": _("Stage"), "fieldname": "stage", "fieldtype": "Data", "width": 140},
        {"label": _("Performance Review"), "fieldname": "review", "fieldtype": "Link",
         "options": "Performance Review", "width": 150},
        {"label": _("Position Change"), "fieldname": "position_change", "fieldtype": "Link",
         "options": "Employee Position Change", "width": 140},
        {"label": _("Improvement Plan"), "fieldname": "improvement_plan", "fieldtype": "Link",
         "options": "Performance Improvement Plan", "width": 140},
        {"label": _("Appraisal"), "fieldname": "appraisal", "fieldtype": "Link", "options": "Appraisal",
         "width": 150},
        {"label": _("Appraisal Status"), "fieldname": "appraisal_status", "fieldtype": "Data", "width": 160},
        {"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 220},
    ]


def _summary(rows):
    figures = rules.results_summary(rows)
    return [
        {"label": _("Appraised"), "value": figures["appraised"], "datatype": "Int", "indicator": "Blue"},
        {"label": _("Average Score"), "value": figures["average"], "datatype": "Percent", "indicator": "Blue"},
        {"label": _("Below the Pass Mark"), "value": figures["below_pass"], "datatype": "Int",
         "indicator": "Red" if figures["below_pass"] else "Green"},
        *({"label": _(OUTCOME_LABELS[outcome]), "value": figures[outcome], "datatype": "Int",
           "indicator": OUTCOME_INDICATORS[outcome]} for outcome in rules.DECISIONS),
        {"label": _(rules.WITH_MANAGEMENT), "value": figures[rules.WITH_MANAGEMENT], "datatype": "Int",
         "indicator": "Orange"},
        {"label": _(rules.APPROVED), "value": figures[rules.APPROVED], "datatype": "Int", "indicator": "Green"},
    ]


def _chart(rows):
    if not rows:
        return None
    figures = rules.results_summary(rows)
    return {
        "data": {"labels": [_(OUTCOME_LABELS[outcome]) for outcome in rules.DECISIONS],
                 "datasets": [{"name": _("Employees"), "values": [figures[outcome] for outcome in rules.DECISIONS]}]},
        "type": "bar",
        "height": 220,
    }
