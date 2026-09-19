# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Onboarding Review, the Frappe side of the Staff Onboarding Form (LPL/HR/04)
at 30, 60 and 90 days (the To-Be 30-60-90 Day Employee Review).

The workflow is in review_approval.py (no Frappe import, tested by
scripts/verify_probation.py):

  validate        the due date (joining plus the review's days), one review
                  of each kind per employee, the step's checks and signatures
  create_reviews  the three reviews, made when the HR Manager approves the
                  onboarding and put on the HR Officer's list for their dates
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, today

from hrms_addon.hrms_addon import people, workflows
from hrms_addon.hrms_addon import review_approval as approval


def validate(doc):
    if not doc.get("due_date") and doc.get("date_of_joining") and doc.get("review_day"):
        doc.due_date = add_days(doc.date_of_joining, cint(doc.review_day))
    other = frappe.db.get_value("Onboarding Review", {"employee": doc.employee, "review_day": doc.review_day,
                                                      "docstatus": ["!=", 2], "name": ["!=", doc.name]}, "name")
    if other:
        frappe.throw(_("{0} already has the {1}-day review: {2}.").format(doc.employee_name or doc.employee,
                                                                          doc.review_day, other))
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            field: doc.get(field) for field in ("roles_responsibilities", "feel_about_role", "supervisor_comments", "hrm_remarks")
        })
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Onboarding Review"))
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)


def create_reviews(employee, date_of_joining, onboarding=None, hr_officer=None):
    """The 30, 60 and 90-day reviews of a new employee, each on the HR
    Officer's list for its date; one already made is left alone."""
    made = []
    for day in approval.REVIEW_DAYS:
        if frappe.db.exists("Onboarding Review", {"employee": employee, "review_day": str(day), "docstatus": ["!=", 2]}):
            continue
        review = frappe.new_doc("Onboarding Review")
        review.update({"employee": employee, "review_day": str(day), "due_date": add_days(date_of_joining, day),
                       "onboarding": onboarding})
        review.insert(ignore_permissions=True)
        users = [hr_officer] if hr_officer else people.hr_officers(review.get("branch"), review.get("department"))
        people.assign("Onboarding Review", review.name, users,
                      _("{0}-day review of {1}: give the Staff Onboarding Form (LPL/HR/04) to the employee, record the "
                        "answers and send it to the supervisor.").format(day, review.employee_name),
                      date=review.due_date)
        made.append(review.name)
    return made


def setup_workflow_on_migrate():
    """after_migrate: the onboarding review workflow (workflows.py)."""
    workflows.setup_on_migrate(approval, "Onboarding Review workflow")
