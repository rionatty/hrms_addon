# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interviews: Luuka's Candidate Interview Evaluation / Score Form (LPL/HR/17)
on HRMS's Interview Feedback.

The rules live in interview_rules.py (no Frappe import; tested by
scripts/verify_interviews.py). This wires them into HRMS:

  feedback_validate    Interview Feedback validate: a sheet starts with every
                       criterion, its totals are worked out, the result follows
                       the recommendation, and HRMS's average rating becomes the
                       sheet's percentage, so the Interview's panel average and
                       star summary use the scores
  get_score_criteria   the rows a new sheet starts with, for the form script
  get_skill_wise_average_rating
                       the Interview's Feedback tab shows the panel's average per
                       criterion instead of per HRMS skill (hooks.py
                       override_whitelisted_methods)
  seed_interview_criteria / after_install
                       LPL/HR/17's groups and criteria, once: a patch on existing
                       sites, after_install on new ones (Frappe marks patches as
                       run on install without running them)
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import interview_rules as rules


def feedback_validate(doc, method=None):
    """Runs after HRMS's own validate, so the average rating set here stands."""
    if not doc.get("custom_scores"):
        for row in _sheet_rows():
            doc.append("custom_scores", row)
    groups = _groups_of({row.criterion for row in doc.custom_scores if row.criterion})
    for row in doc.custom_scores:
        if row.criterion in groups:
            row.criteria_group = groups[row.criterion]

    errors = rules.score_sheet_errors(doc.custom_scores, doc.get("custom_recommendation"), submitting=doc.docstatus == 1)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Score Sheet"))

    summary = rules.score_summary(doc.custom_scores)
    doc.custom_total_score = summary["total"]
    doc.custom_max_score = summary["maximum"]
    doc.custom_score_percent = summary["percent"]
    doc.custom_score_band = summary["band"]
    doc.average_rating = rules.average_rating(summary)
    if doc.get("custom_recommendation"):
        doc.result = rules.result_for(doc.custom_recommendation)
    doc.custom_interviewer_designation = _designation_of(doc.interviewer)


@frappe.whitelist()
def get_score_criteria():
    """The rows a new score sheet starts with: every criterion not disabled, in order."""
    return _sheet_rows()


@frappe.whitelist()
def get_skill_wise_average_rating(interview: str) -> list[dict]:
    """The panel's average per criterion, for the Interview's Feedback tab.

    Same shape as HRMS's version (skill, and a 0-1 rating the tab multiplies
    by 5). An interview scored the HRMS way, on skills, keeps its skills.
    """
    frappe.has_permission("Interview", "read", interview, throw=True)
    sheets = [
        frappe.get_all(
            "Interview Feedback Score",
            filters={"parent": name, "parenttype": "Interview Feedback", "parentfield": "custom_scores"},
            fields=["criterion", "score"],
            order_by="idx asc",
        )
        for name in frappe.get_all(
            "Interview Feedback", filters={"interview": interview, "docstatus": 1}, pluck="name", order_by="creation asc"
        )
    ]
    averages = rules.criterion_averages(sheets)
    if not averages:
        from hrms.hr.doctype.interview.interview import get_skill_wise_average_rating as hrms_averages

        return hrms_averages(interview)
    return [{"skill": criterion, "rating": average / rules.TOP_SCORE} for criterion, average in averages]


def seed_interview_criteria():
    groups, criteria = rules.criteria_seed_plan(
        frappe.get_all("Interview Criteria Group", pluck="name"), frappe.get_all("Interview Criterion", pluck="name")
    )
    for record in groups + criteria:
        frappe.get_doc(record).insert(ignore_permissions=True)


def after_install():
    seed_interview_criteria()


def _sheet_rows():
    group_order = dict(frappe.get_all("Interview Criteria Group", fields=["name", "sort_order"], as_list=True))
    criteria = frappe.get_all("Interview Criterion", fields=["name", "criteria_group", "sort_order", "disabled"])
    for criterion in criteria:
        criterion["group_order"] = group_order.get(criterion.criteria_group)
    return rules.sheet_rows(criteria)


def _groups_of(criteria):
    if not criteria:
        return {}
    return dict(
        frappe.get_all(
            "Interview Criterion", filters={"name": ["in", sorted(criteria)]}, fields=["name", "criteria_group"], as_list=True
        )
    )


def _designation_of(user):
    if not user:
        return ""
    return frappe.db.get_value("Employee", {"user_id": user}, "designation", order_by="status asc") or ""
