# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Probation Evaluation, the Frappe side of the End of probation evaluation /
confirmation form (LPL/HR/32), and Onboarding Settings.

The rules are in probation_rules.py and the workflow in probation_approval.py
(no Frappe import, tested by scripts/verify_probation.py):

  validate     the factors (the Probation Factor list) and the objectives
               (the Job Title's Key Result Areas) on a new evaluation, the
               scores, the step's checks and signatures, and the decision's
               dates (Confirmed From, the extension's end)
  on_submit    the Executive Director decided: the Employee confirmed (its
               Confirmation Date, and Employment Type if the settings say),
               the probation extended (a new evaluation for its new end) or
               not confirmed (HR is told to follow the termination process)
  on_cancel    the decision undone on the Employee
  create_evaluation  made by the onboarding's approval (onboarding.py)
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, today

from hrms_addon.hrms_addon import people, workflows
from hrms_addon.hrms_addon import contract_rules
from hrms_addon.hrms_addon import probation_approval as approval
from hrms_addon.hrms_addon import probation_rules as rules

SETTINGS = "Onboarding Settings"
DEFAULTS = {"probation_months": 6, "extension_months": 3, "pass_mark": 60.0}


def settings():
    """Onboarding Settings, with the defaults where a value was never saved."""
    doc = frappe.get_cached_doc(SETTINGS)
    return frappe._dict(
        probation_months=cint(doc.get("probation_months")) or DEFAULTS["probation_months"],
        extension_months=cint(doc.get("extension_months")) or DEFAULTS["extension_months"],
        pass_mark=flt(doc.get("pass_mark")) or DEFAULTS["pass_mark"],
        confirmed_employment_type=doc.get("confirmed_employment_type"),
        alert_days=contract_rules.parse_alert_days(doc.get("contract_alert_days")),
        executive_director=doc.get("executive_director"),
        head_of_hr=doc.get("head_of_hr"),
    )


def validate_settings(doc):
    if doc.get("pass_mark") is not None and not 0 <= flt(doc.pass_mark) <= 100:
        frappe.throw(_("The Pass Mark is a percentage from 0 to 100."))
    doc.contract_alert_days = ", ".join(str(n) for n in contract_rules.parse_alert_days(doc.get("contract_alert_days")))


def save_default_settings():
    """Once (patch, after_install): the settings saved with their defaults,
    so the page shows what applies."""
    doc = frappe.get_single(SETTINGS)
    changed = False
    for field, value in (("probation_months", 6), ("extension_months", 3), ("pass_mark", 60),
                         ("contract_alert_days", "365, 90, 30")):
        if not doc.get(field):
            doc.set(field, value)
            changed = True
    if changed:
        doc.flags.ignore_permissions = True
        doc.save()


def validate(doc):
    """Probation Evaluation validate: every step before Decided is a draft,
    so this runs at each one."""
    s = settings()
    if not doc.get("pass_mark"):
        doc.pass_mark = s.pass_mark
    if not doc.get("factors"):
        for factor in frappe.get_all("Probation Factor", order_by="creation asc", pluck="name"):
            doc.append("factors", {"factor": factor})
    if doc.is_new() and not doc.get("objectives") and doc.get("designation"):
        for objective in rules.objectives_from_kras(_key_result_areas(doc.designation)):
            doc.append("objectives", {"objective": objective})
    if doc.get("ed_decision") == rules.EXTEND and not doc.get("new_end_of_probation") and doc.get("end_of_probation"):
        doc.new_end_of_probation = rules.add_months(doc.end_of_probation, s.extension_months)
    if doc.get("ed_decision") == rules.CONFIRM and not doc.get("confirmation_date"):
        doc.confirmation_date = doc.end_of_probation

    result = rules.scores([row.supervisor_rating for row in doc.get("factors") or []],
                          [row.supervisor_rating for row in doc.get("objectives") or []])
    doc.factors_score, doc.objectives_score, doc.total_score = result["factors"], result["objectives"], result["total"]
    doc.rating_band = rules.band(result["total"])
    doc.passed = 1 if rules.passed(result["total"], flt(doc.pass_mark)) else 0

    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, _facts(doc))
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Probation Evaluation"))
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)


def _facts(doc):
    def rows(table, label_field):
        return [{"label": " ".join(str(row.get(label_field) or "").split())[:60],
                 "employee_rating": row.employee_rating, "supervisor_rating": row.supervisor_rating}
                for row in doc.get(table) or []]

    return {
        "factors": rows("factors", "factor"),
        "objectives": rows("objectives", "objective"),
        "supervisor_remarks": doc.get("supervisor_remarks"),
        "manager_remarks": doc.get("manager_remarks"),
        "hod_remarks": doc.get("hod_remarks"),
        "hrm_recommendation": doc.get("hrm_recommendation"),
        "hrm_remarks": doc.get("hrm_remarks"),
        "ed_decision": doc.get("ed_decision"),
        "end_of_probation": str(doc.end_of_probation) if doc.get("end_of_probation") else None,
        "new_end_of_probation": str(doc.new_end_of_probation) if doc.get("new_end_of_probation") else None,
        "confirmation_date": str(doc.confirmation_date) if doc.get("confirmation_date") else None,
    }


def _key_result_areas(designation):
    """The Job Title's Key Result Areas (its Job Description tab), as text."""
    rows = frappe.get_all(
        "JD Key Result Area",
        filters={"parent": designation, "parenttype": "Designation", "parentfield": "custom_jd_key_result_areas"},
        fields=["kra", "key_outputs"], order_by="idx asc",
    )
    return [row.key_outputs or row.kra for row in rows]


def on_submit(doc):
    """The Executive Director decided."""
    employee = frappe.get_doc("Employee", doc.employee)
    employee.custom_probation_status = rules.STATUS_AFTER[doc.ed_decision]
    if doc.ed_decision == rules.CONFIRM:
        employee.final_confirmation_date = doc.confirmation_date
        if settings().confirmed_employment_type:
            employee.employment_type = settings().confirmed_employment_type
    elif doc.ed_decision == rules.EXTEND:
        employee.custom_probation_end_date = doc.new_end_of_probation
    employee.flags.ignore_permissions = True
    employee.save()
    if doc.ed_decision == rules.EXTEND:
        following = create_evaluation(doc.employee, doc.new_end_of_probation, onboarding=doc.get("onboarding"),
                                      extension_of=doc.name)
        doc.db_set("next_evaluation", following.name)
    elif doc.ed_decision == rules.TERMINATE:
        users = people.hr_officers(doc.get("branch"), doc.get("department"))
        message = _("{0} was not confirmed at the end of probation: follow the termination process.").format(
            doc.employee_name)
        people.assign("Probation Evaluation", doc.name, users, message)
        people.notify(users, "Probation Evaluation", doc.name, message)


def on_cancel(doc):
    """The decision undone: the Employee back on probation (extended if this
    was an extension's evaluation), an extension's new evaluation dropped
    while still a draft."""
    following = doc.get("next_evaluation")
    if following and frappe.db.get_value("Probation Evaluation", following, "docstatus") == 0:
        frappe.delete_doc("Probation Evaluation", following, ignore_permissions=True)
    employee = frappe.get_doc("Employee", doc.employee)
    employee.custom_probation_status = rules.EXTENDED if doc.get("extension_of") else rules.ON_PROBATION
    employee.custom_probation_end_date = doc.end_of_probation
    if doc.ed_decision == rules.CONFIRM and str(employee.get("final_confirmation_date") or "") == str(doc.confirmation_date or ""):
        employee.final_confirmation_date = None
    employee.flags.ignore_permissions = True
    employee.save()


def create_evaluation(employee, end_of_probation, onboarding=None, extension_of=None, hr_officer=None):
    """A draft evaluation for the employee's probation ending on that date,
    on the HR Officer's list for then. Returns it."""
    evaluation = frappe.new_doc("Probation Evaluation")
    evaluation.update({"employee": employee, "end_of_probation": end_of_probation, "onboarding": onboarding,
                       "extension_of": extension_of})
    evaluation.insert(ignore_permissions=True)
    users = [hr_officer] if hr_officer else people.hr_officers(evaluation.get("branch"), evaluation.get("department"))
    people.assign("Probation Evaluation", evaluation.name, users,
                  _("End of probation evaluation for {0}, due {1}: record the self-assessment and send it to the "
                    "supervisor.").format(evaluation.employee_name, end_of_probation), date=end_of_probation)
    return evaluation


def setup_workflow_on_migrate():
    """after_migrate: the probation evaluation workflow (workflows.py)."""
    workflows.setup_on_migrate(approval, "Probation Evaluation workflow")


def after_install():
    save_default_settings()
