# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Penalty deductions on the site (Reward and Compensation, §4.11).

The rules are in penalty_rules.py and penalty_approval.py, without a Frappe
import (scripts/verify_penalties.py). This reads and writes the site.

A penalty is recovered the way a staff loan is (loans.py): LPL/HR/39 is
the consent for both, the instalments are a loan's schedule with no
interest, each one becomes an Additional Salary deduction, and the Salary
Slip that takes it marks it recovered (recoveries.py). Whatever is still
owed when the employee leaves is on their final settlement
(settlements.py), which is what the form's declaration agrees to.

  penalty_*  the report, the hearing, the consent, the HR Manager, the
             Executive Director, back to the HR Officer, and the payroll.
  refresh_recovered  what the payroll has taken, and a penalty fully
             recovered closed with the employee told.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import loan_rules, penalty_rules as rules, people

DOCTYPE = "Employee Penalty"
DEFAULT_COMPONENT = "Penalty Recovery"


# ── 1. The penalty ────────────────────────────────────────────────────
def penalty_validate(doc, method=None):
    from hrms_addon.hrms_addon import penalty_approval as approval

    _fill(doc)
    _build_schedule(doc)
    _check_step(doc)
    doc.approval_status = doc.get("workflow_state") or doc.get("approval_status") or approval.DRAFT
    doc.status = rules.penalty_status(doc.docstatus, doc.get("finding"), doc.get("amount"),
                                      doc.get("recovered_amount"),
                                      rejected=doc.get("workflow_state") == approval.REJECTED)


def _fill(doc):
    if doc.get("employee"):
        doc.age = rules.age(frappe.db.get_value("Employee", doc.employee, "date_of_birth"),
                            doc.get("posting_date") or today())
    liable = doc.get("finding") == rules.LIABLE
    amount = flt(doc.get("amount")) if liable else 0
    instalments = cint(doc.get("instalments"))
    doc.monthly_instalment = loan_rules.monthly_instalment(amount, 0, instalments) if amount else 0
    recovered = sum(flt(row.total) for row in doc.get("repayments") or [] if row.recovered)
    doc.recovered_amount = recovered
    doc.outstanding = rules.outstanding(amount, recovered)
    # LPL/HR/39's extent and declaration follow the terms, so they are
    # written again whenever the terms change
    doc.extent_of_deduction = (_("{0} a month for {1} month(s)").format(
        frappe.utils.fmt_money(doc.monthly_instalment), instalments) if doc.monthly_instalment else None)
    doc.declaration = rules.declaration({
        "employee_name": doc.get("employee_name"), "amount": amount, "instalments": instalments,
        "effective_from": doc.get("effective_from"), "liability": doc.get("liability"),
        "year": getdate(doc.get("incident_date")).year if doc.get("incident_date") else None,
    }) if amount else None


def _build_schedule(doc):
    """The months the penalty comes back in. What is already recovered is
    left exactly as it is; only the months still to come are redrawn."""
    amount = flt(doc.get("amount"))
    first = doc.get("effective_from")
    done = [row for row in doc.get("repayments") or [] if row.recovered]
    if doc.get("finding") != rules.LIABLE or not (amount and first and cint(doc.get("instalments"))):
        doc.set("repayments", done)
        return
    left = round(amount - sum(flt(row.total) for row in done), 2)
    months = max(cint(doc.get("instalments")) - len(done), 1)
    start = loan_rules.add_months(done[-1].payroll_date, 1) if done else first
    doc.set("repayments", done)
    if left <= 0:
        return
    for month, due, _interest, total in loan_rules.repayment_schedule(left, 0, months, start):
        doc.append("repayments", {"payroll_date": month, "principal": due, "interest": 0, "total": total})


def _check_step(doc):
    from hrms_addon.hrms_addon import penalty_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"), "finding": doc.get("finding"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_HEARING and old_state in (None, approval.DRAFT):
            errors = rules.report_errors({
                "employee": doc.get("employee"), "kind": doc.get("kind"),
                "incident_date": doc.get("incident_date"), "details": doc.get("details"),
                "today": today()}) + errors
        if old_state == approval.PENDING_HEARING and new_state in (approval.PENDING_CONSENT,
                                                                   approval.NOT_LIABLE):
            errors = rules.hearing_errors(_terms(doc)) + errors
        if old_state == approval.PENDING_CONSENT and new_state == approval.PENDING_HRM:
            errors += rules.consent_errors(dict(
                _terms(doc), liability=doc.get("liability"), reason=doc.get("reason"),
                consent=doc.get("consent"), signed_form=doc.get("signed_form"),
                by_employee=_is_the_employee(doc)))
        if new_state == approval.RECOVERING:
            errors += rules.agreement_errors(_terms(doc))
            if not doc.get("repayments"):
                errors.append(_("There are no instalments to send to the payroll."))
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Penalty"))
        if approval.is_backwards(old_state, new_state):
            # what the employee signed was the terms now being reopened
            doc.consent = 0
        else:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)


def _terms(doc):
    return {"hearing_on": doc.get("hearing_on"), "hearing_record": doc.get("hearing_record"),
            "employee_heard": doc.get("employee_heard"), "supervisor_heard": doc.get("supervisor_heard"),
            "finding": doc.get("finding"), "amount": doc.get("amount"),
            "instalments": doc.get("instalments"), "effective_from": doc.get("effective_from")}


def _is_the_employee(doc):
    user = frappe.db.get_value("Employee", doc.employee, "user_id") if doc.get("employee") else None
    return bool(user) and user == frappe.session.user


def _tell(doc, state):
    from hrms_addon.hrms_addon import penalty_approval as approval

    users = []
    if state == approval.PENDING_CONSENT:
        user = frappe.db.get_value("Employee", doc.employee, "user_id") if doc.get("employee") else None
        # somebody with no login signs on paper, which the HR Officer records
        users = [user] if user else list(people.hr_officers(doc.get("branch"), doc.get("department")))
    else:
        users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"), doc.get("department"))
    if not users:
        return
    if state == approval.PENDING_CONSENT:
        message = _("{0}: you were found liable for {1}, to be recovered as {2}. Read and sign the "
                    "Employee Deduction Consent.").format(
            doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("amount")),
            doc.get("extent_of_deduction") or "")
    else:
        message = _("Penalty case for {0}: {1}, {2}.").format(
            doc.get("employee_name") or doc.employee, doc.get("kind"),
            frappe.utils.format_date(doc.get("incident_date")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def penalty_on_submit(doc, method=None):
    """Recovering: the instalments become deductions on the payroll, and
    the employee and the Payroll Officers are told. A case cleared at the
    hearing, or refused, is submitted with nothing to recover."""
    from hrms_addon.hrms_addon import penalty_approval as approval

    if doc.get("workflow_state") != approval.RECOVERING or doc.get("finding") != rules.LIABLE:
        return
    _make_deductions(doc)
    users = people.people_for(approval.PAYROLL, doc.get("branch"), doc.get("department"))
    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    if user:
        users = list(users) + [user]
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                      _("{0}'s penalty of {1} comes off the payroll from {2}: {3}.").format(
                          doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("amount")),
                          frappe.utils.format_date(doc.get("effective_from")),
                          doc.get("extent_of_deduction") or ""))


def penalty_on_cancel(doc, method=None):
    taken = [row for row in doc.get("repayments") or [] if row.recovered]
    if taken:
        frappe.throw(_("{0} instalment(s) have already been taken by the payroll, so this penalty "
                       "cannot be cancelled.").format(len(taken)), title=_("Employee Penalty"))
    for row in doc.get("repayments") or []:
        if row.additional_salary and frappe.db.exists("Additional Salary", row.additional_salary):
            deduction = frappe.get_doc("Additional Salary", row.additional_salary)
            if deduction.docstatus == 1:
                deduction.flags.ignore_permissions = True
                deduction.cancel()
    doc.approval_status = rules.CANCELLED
    doc.status = rules.CANCELLED


def _make_deductions(doc):
    component = doc.get("recovery_component") or _component()
    if not component:
        return
    for row in doc.get("repayments") or []:
        if row.additional_salary or row.recovered:
            continue
        deduction = frappe.get_doc({
            "doctype": "Additional Salary", "employee": doc.employee, "company": doc.company,
            "salary_component": component, "amount": flt(row.total), "payroll_date": row.payroll_date,
            "overwrite_salary_structure_amount": 0, "ref_doctype": doc.doctype, "ref_docname": doc.name,
        })
        deduction.flags.ignore_permissions = True
        deduction.insert()
        deduction.submit()
        row.db_set("additional_salary", deduction.name, update_modified=False)


def _component():
    if frappe.db.exists("Salary Component", DEFAULT_COMPONENT):
        return DEFAULT_COMPONENT
    try:
        doc = frappe.get_doc({"doctype": "Salary Component", "salary_component": DEFAULT_COMPONENT,
                              "type": "Deduction", "salary_component_abbr": "PEN",
                              "description": "Recovery of a penalty for property lost or damaged "
                                             "(LPL/HR/39, minutes §4.11)."})
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(title="HRMS Addon: penalty recovery component")
        return None


# ── 2. What the payroll has taken ─────────────────────────────────────
def refresh_recovered(name):
    """The recovered and outstanding amounts, from the instalments marked
    recovered (recoveries.py). A penalty whose last instalment is taken is
    Recovered, and the employee and the HR Officer are told."""
    doc = frappe.get_doc(DOCTYPE, name)
    if doc.docstatus != 1:
        return
    recovered = sum(flt(row.total) for row in doc.get("repayments") or [] if row.recovered)
    was = doc.status
    status = rules.penalty_status(1, doc.finding, doc.amount, recovered)
    doc.db_set({"recovered_amount": recovered, "outstanding": rules.outstanding(doc.amount, recovered),
                "status": status}, update_modified=False)
    if was != rules.RECOVERED and status == rules.RECOVERED:
        users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
        user = frappe.db.get_value("Employee", doc.employee, "user_id")
        if user:
            users.append(user)
        if users:
            people.notify(list(dict.fromkeys(users)), DOCTYPE, name,
                          _("{0}'s penalty is fully recovered.").format(doc.employee_name or doc.employee))


def owed(employee):
    """What an employee still owes on penalties, for their final settlement."""
    rows = frappe.get_all(DOCTYPE, filters={"employee": employee, "docstatus": 1, "finding": rules.LIABLE},
                          fields=["outstanding"])
    return flt(sum(flt(row.outstanding) for row in rows))


# ── 3. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the penalty's six desks."""
    from hrms_addon.hrms_addon import penalty_approval, workflows

    workflows.setup_on_migrate(penalty_approval, "Employee Penalty workflow")
