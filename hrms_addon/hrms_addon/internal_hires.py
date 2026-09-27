# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A member of staff hired through recruitment. The rules are in
internal_hire_rules.py.

  link_employee        Job Applicant validate: a new application from
                       someone who works here is linked to their employee
                       record (Current Employee), found the way the screening
                       finds them (cv_screening.employees_like)
  refuse_new_employee  Create > Employee, from a Job Offer or an Employee
                       Onboarding (bio_data.py), for someone already on the
                       staff: refused, pointing to the move instead
  make_internal_move   the Job Offer's Create > Position Change or Transfer:
                       a new Employee Position Change when the job title
                       changes, else Frappe HR's Employee Transfer, filled
                       from the offer
  get_internal_move    the move already made for an offer, or which one to
                       make, for the Job Offer form
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import cv_screening
from hrms_addon.hrms_addon import internal_hire_rules as rules

EMPLOYEE_FIELDS = ["name", "employee_name", "designation", "branch", "department", "company", "status"]


def link_employee(doc, method=None):
    """A new application: the employee record it points to, when there is
    exactly one and it is active. HR may link or unlink one by hand after."""
    if doc.is_new() and not doc.get("custom_employee"):
        doc.custom_employee = rules.employee_match(cv_screening.employees_like(doc, limit=5))


def refuse_new_employee(job_applicant):
    """Stops a second employee record for someone already on the staff."""
    staff = frappe.db.get_value("Job Applicant", job_applicant, "custom_employee") if job_applicant else None
    if staff and frappe.db.get_value("Employee", staff, "status") == "Active":
        frappe.throw(
            _("{0} already works here ({1}). Move them into the job from the Job Offer instead: Create > Position "
              "Change, or Transfer.").format(frappe.db.get_value("Job Applicant", job_applicant, "applicant_name")
                                            or job_applicant, staff),
            title=_("Already an Employee"))


def _move_for(offer):
    """(the employee, their moves, the kind of move) for an internal offer."""
    staff = offer.get("custom_employee") or frappe.db.get_value("Job Applicant", offer.job_applicant, "custom_employee")
    if not staff:
        frappe.throw(_("{0} is not on the staff: the offer leads to Employee Onboarding.").format(
            offer.applicant_name or offer.job_applicant), title=_("Internal Move"))
    employee = frappe.db.get_value("Employee", staff, EMPLOYEE_FIELDS, as_dict=True) or frappe._dict()
    opening = frappe.db.get_value("Job Applicant", offer.job_applicant, "job_title")
    target = {"designation": offer.designation, "branch": offer.get("custom_branch"),
              "department": frappe.db.get_value("Job Opening", opening, "department") if opening else None}
    moves = rules.changes(employee, target)
    return employee, moves, rules.move_kind(moves)


@frappe.whitelist()
def make_internal_move(source_name: str):
    """The Job Offer's Create > Position Change / Transfer: the new document,
    not saved, for HR to complete (the effective date, and for a position
    change the pay and the supervisor)."""
    offer = frappe.get_doc("Job Offer", source_name)
    offer.check_permission("read")
    employee, moves, kind = _move_for(offer)
    if not kind:
        frappe.throw(_("{0} already holds this job, in this branch and department.").format(employee.employee_name),
                     title=_("Internal Move"))
    doc = frappe.new_doc(kind)
    if kind == rules.POSITION_CHANGE:
        doc.update({
            "change_type": "Promotion", "employee": employee.name, "employee_name": employee.employee_name,
            "company": employee.company, "branch": employee.branch, "department": employee.department,
            "current_designation": employee.designation, "new_designation": offer.designation,
            "job_description": offer.designation, "desired_position": offer.designation, "job_offer": offer.name,
            "new_branch": moves.get("branch", (None, None))[1], "new_department": moves.get("department", (None, None))[1],
        })
    else:
        doc.update({"employee": employee.name, "employee_name": employee.employee_name, "company": employee.company,
                    "department": employee.department, "custom_job_offer": offer.name})
        for row in rules.transfer_rows(moves):
            doc.append("transfer_details", row)
    return doc


@frappe.whitelist()
def get_internal_move(job_offer: str) -> dict:
    """For the Job Offer form: {"doctype", "name"} of the move already made
    for it, or {"doctype": the kind to make} (None when nothing changes)."""
    offer = frappe.get_doc("Job Offer", job_offer)
    offer.check_permission("read")
    for doctype, link in ((rules.POSITION_CHANGE, "job_offer"), (rules.TRANSFER, "custom_job_offer")):
        name = frappe.db.get_value(doctype, {link: job_offer, "docstatus": ["!=", 2]}, "name")
        if name:
            return {"doctype": doctype, "name": name}
    return {"doctype": _move_for(offer)[2], "name": None}
