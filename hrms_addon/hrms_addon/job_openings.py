# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Opening: what it takes from its Job Requisition and its JD, and a page
of its own. The rules are in opening_rules.py.

  before_validate         the blanks from its Job Requisition (the description
                          among them), the JD's screening questions when it has
                          none, and a route no other opening has
  make_job_opening        HRMS's Create Job Opening (hooks.py
                          override_whitelisted_methods), with the requisition
                          and the number of positions it leaves out
  get_requisition_values  the blanks, for the form to fill as it opens
  get_jd_questions        the JD's screening questions, for the form
"""

import frappe

from hrms_addon.hrms_addon import opening_rules as rules
from hrms_addon.hrms_addon.job_requisition import _has_content

QUESTIONS = "custom_screening_questions"


def before_validate(doc, method=None):
    for field, value in requisition_values(doc).items():
        doc.set(field, value)
    _add_jd_questions(doc)
    _unique_route(doc)


@frappe.whitelist()
def make_job_opening(source_name: str, target_doc=None):
    """HRMS's Create Job Opening. Its field map is not where get_mapped_doc
    reads it, so the opening came without its requisition and the number of
    positions; both are set here, with the JD's screening questions."""
    from hrms.hr.doctype.job_requisition.job_requisition import make_job_opening as hrms_make_job_opening

    opening = hrms_make_job_opening(source_name, target_doc)
    opening.job_requisition = source_name
    for field, value in requisition_values(opening).items():
        opening.set(field, value)
    _add_jd_questions(opening)
    return opening


@frappe.whitelist()
def get_requisition_values(doc: str) -> dict:
    """What a new opening leaves blank, from its Job Requisition."""
    frappe.has_permission("Job Opening", "write", throw=True)
    return requisition_values(frappe.get_doc(frappe.parse_json(doc)))


@frappe.whitelist()
def get_jd_questions(designation: str) -> list:
    """The JD's screening questions, for a new opening's form."""
    frappe.has_permission("Job Opening", "write", throw=True)
    return jd_questions(designation)


def requisition_values(doc):
    name = doc.get("job_requisition")
    if not name or not frappe.db.exists("Job Requisition", name):
        return {}
    return rules.blanks_from(doc.as_dict(), frappe.get_doc("Job Requisition", name).as_dict(), _has_content)


def jd_questions(designation):
    if not designation or not frappe.db.exists("Designation", designation):
        return []
    return rules.question_rows(frappe.get_doc("Designation", designation).get("custom_jd_screening_questions"))


def _add_jd_questions(doc):
    """An opening with no screening questions starts with its JD's."""
    if doc.get("designation") and not doc.get(QUESTIONS):
        for row in jd_questions(doc.designation):
            doc.append(QUESTIONS, row)


def _unique_route(doc):
    """HRMS's route, or the one the opening has, unless another opening has
    it: then the first free one after it."""
    route = doc.get("route") or rules.route_for(doc.get("company"), doc.get("job_title"))
    taken = [other for other in frappe.get_all("Job Opening", filters={"name": ["!=", doc.name or ""]}, pluck="route")
             if other and other.startswith(route)]
    doc.route = rules.unique_route(route, taken)
