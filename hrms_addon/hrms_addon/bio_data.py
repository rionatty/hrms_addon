# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Pre-Interview Bio-Data Form (LPL/HR/19) on Job Applicant.

The fields are fixtures (the Bio-Data tab) and the rules live in
bio_data_rules.py. This checks the tab on save and carries it onto the
Employee when the candidate is hired, with the placement (branch, employment
type, offer date: onboarding.add_placement).

Carrying over happens while the new Employee form is being built, not on
its save: Employee requires Date of Birth and Gender, so the browser would
refuse to save the form before any server hook could fill them. HRMS builds
that form in two places — Create > Employee on a Job Offer and on an
Employee Onboarding — and hooks.py override_whitelisted_methods routes both
through the functions below, which call the HRMS original and then add the
bio-data. Frappe resolves the override in frappe.model.mapper.make_mapped_doc.
"""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import bio_data_rules, onboarding


def validate(doc, method=None):
    errors = bio_data_rules.bio_data_errors(doc.as_dict(), today())
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Bio-Data"))


@frappe.whitelist()
def make_employee_from_job_offer(source_name, target_doc=None):
    from hrms.hr.doctype.job_offer.job_offer import make_employee

    employee = add_bio_data(make_employee(source_name, target_doc), "Job Offer", source_name)
    return onboarding.add_placement(employee, "Job Offer", source_name)


@frappe.whitelist()
def make_employee_from_onboarding(source_name, target_doc=None):
    from hrms.hr.doctype.employee_onboarding.employee_onboarding import make_employee

    employee = add_bio_data(make_employee(source_name, target_doc), "Employee Onboarding", source_name)
    return onboarding.add_placement(employee, "Employee Onboarding", source_name)


def add_bio_data(employee, source_doctype, source_name):
    """Fill the new Employee's blanks from the candidate's bio-data."""
    job_applicant = employee.get("job_applicant") or frappe.db.get_value(source_doctype, source_name, "job_applicant")
    if not job_applicant or not frappe.db.exists("Job Applicant", job_applicant):
        return employee

    applicant = frappe.get_doc("Job Applicant", job_applicant)
    meta = frappe.get_meta("Employee")
    # the site's certification and licence types (ticked on the list)
    certification_types = frappe.get_all("Qualification Type", filters={"is_certification": 1}, pluck="name")
    values = {
        field: value
        for field, value in bio_data_rules.employee_values(applicant.as_dict(), certification_types).items()
        if meta.has_field(field)  # the custom fields exist only once the fixtures are in
    }
    for field, value in bio_data_rules.missing_values(employee.as_dict(), values).items():
        if isinstance(value, list):
            for row in value:
                employee.append(field, row)
        else:
            employee.set(field, value)
    if meta.has_field("job_applicant") and not employee.get("job_applicant"):
        employee.set("job_applicant", job_applicant)
    return employee


def allow_hr_user_to_add_skills():
    """Let HR User (the HR Officer) create and edit Skills.

    The Officer types in the skills a candidate lists, and a skill that is
    not on the Skill list yet must be added on the spot; HRMS gives HR User
    read-only access to Skill. Granted once (patch and after_install), not
    on every migrate, so a site that later takes it away keeps it away.

    frappe.permissions.setup_custom_perms copies Skill's standard rules into
    Custom DocPerm first, as Role Permission Manager would.
    """
    from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
    from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

    setup_custom_perms("Skill")
    rule = frappe.db.get_value(
        "Custom DocPerm",
        {"parent": "Skill", "role": "HR User", "permlevel": 0, "if_owner": 0},
        ["name", "read", "write", "create"],
        as_dict=True,
    )
    if not rule:
        add_permission("Skill", "HR User", 0, "read")
        rule = frappe._dict(read=1)
    for ptype in ("read", "write", "create"):
        if not rule.get(ptype):
            update_permission_property("Skill", "HR User", 0, ptype, 1, validate=False)
    validate_permissions_for_doctype("Skill")
    frappe.clear_cache(doctype="Skill")


def after_install():
    allow_hr_user_to_add_skills()
