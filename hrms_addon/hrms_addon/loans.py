# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Loans Application on the site (4.4).

The rules are in loan_rules.py, without a Frappe import
(scripts/verify_loans.py). This reads and writes the site.

The Employee Loan is the one document this process needs that the site
does not already have: Frappe's lending app is not installed at Luuka, and
a staff loan recovered from the payroll is not a bank loan. Everything it
touches afterwards is Frappe HR's own — each repayment becomes an
Additional Salary deduction, so the payroll run takes it without a list
kept by hand.

  loan_*     the request, the three approvals, the terms Accounts settle,
             the employee's consent (LPL/HR/39) and the schedule.
  daily      step 6, the monitoring: a repayment due this month, a loan
             fully repaid, and one still owed after its last instalment.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import loan_rules as rules, people

DOCTYPE = "Employee Loan"
DEFAULT_COMPONENT = "Loan Repayment"


# ── 1. The loan ───────────────────────────────────────────────────────
def loan_validate(doc, method=None):
    from hrms_addon.hrms_addon import loan_approval as approval

    _fill_money(doc)
    _check_eligibility(doc)
    _build_schedule(doc)
    _check_step(doc)
    doc.approval_status = doc.get("workflow_state") or doc.get("approval_status") or approval.DRAFT
    doc.status = rules.loan_status(doc.docstatus, doc.get("approved_amount") or doc.get("loan_amount"),
                                   doc.get("recovered_amount"), doc.get("written_off"))
    if doc.get("consent") and not doc.get("consent_on"):
        doc.consent_on = today()


def _fill_money(doc):
    if doc.get("employee"):
        doc.gross_pay = _gross_pay(doc.employee)
        doc.outstanding_before = _owed_elsewhere(doc.employee, doc.name)
    doc.limit = rules.limit_for_type(doc.get("loan_type"), doc.get("gross_pay")) or 0
    doc.total_interest = rules.interest_for(doc.get("approved_amount") or doc.get("loan_amount"),
                                            doc.get("interest_rate"), doc.get("instalments"))
    doc.monthly_instalment = rules.monthly_instalment(doc.get("approved_amount") or doc.get("loan_amount"),
                                                      doc.get("interest_rate"), doc.get("instalments"))
    recovered = sum(flt(row.total) for row in doc.get("repayments") or [] if row.recovered)
    doc.recovered_amount = recovered
    total = flt(doc.get("approved_amount") or doc.get("loan_amount")) + flt(doc.total_interest)
    doc.outstanding = rules.outstanding(total, recovered)
    # LPL/HR/39's "EXTENT OF DEDUCTION" is the terms in words. It follows
    # the terms, so it is written again whenever they change rather than
    # frozen at whatever the request first said.
    if doc.get("monthly_instalment") and cint(doc.get("instalments")):
        doc.extent_of_deduction = _("{0} a month for {1} month(s)").format(
            frappe.utils.fmt_money(doc.monthly_instalment), cint(doc.get("instalments")))


def _gross_pay(employee):
    rows = frappe.get_all("Salary Structure Assignment", filters={"employee": employee, "docstatus": 1},
                          fields=["base"], order_by="from_date desc", limit=1)
    return flt(rows[0].base) if rows else 0


def _owed_elsewhere(employee, exclude):
    """What this employee still owes on loans already running. Only a
    submitted one counts: a draft is a request, not money out."""
    rows = frappe.get_all(DOCTYPE, filters={"employee": employee, "docstatus": 1,
                                            "name": ["!=", exclude or ""]},
                          fields=["outstanding"])
    return flt(sum(flt(row.outstanding) for row in rows))


def _check_eligibility(doc):
    errors = rules.eligibility_errors(_facts(doc))
    doc.qualifies = 0 if errors else 1
    doc.eligibility_remarks = "; ".join(errors) or None


def _facts(doc):
    return {
        "status": frappe.db.get_value("Employee", doc.employee, "status") if doc.get("employee") else None,
        "date_of_joining": doc.get("date_of_appointment"), "today": today(),
        "gross_pay": doc.get("gross_pay"),
        "amount": doc.get("approved_amount") or doc.get("loan_amount"),
        "outstanding": doc.get("outstanding_before"), "instalments": doc.get("instalments"),
        "purpose": doc.get("purpose"),
        "loan_type": doc.get("loan_type"),
        "category": (frappe.db.get_value("Department", doc.department, "custom_position_category")
                     if doc.get("department") else None),
        "fee_structure": doc.get("fee_structure"),
    }


def _build_schedule(doc):
    """The months the loan comes back in. What is already recovered is left
    exactly as it is; only the months still to come are redrawn."""
    principal = flt(doc.get("approved_amount"))
    first = doc.get("first_repayment")
    if not (principal and first):
        return
    done = [row for row in doc.get("repayments") or [] if row.recovered]
    taken = sum(flt(row.principal) for row in done)
    left = round(principal - taken, 2)
    months = max(cint(doc.get("instalments")) - len(done), 1)
    start = rules.add_months(done[-1].payroll_date, 1) if done else first
    doc.set("repayments", done)
    for month, due_p, due_i, total in rules.repayment_schedule(left, doc.get("interest_rate"), months, start):
        doc.append("repayments", {"payroll_date": month, "principal": due_p, "interest": due_i,
                                  "total": total})


def _check_step(doc):
    from hrms_addon.hrms_addon import loan_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_HOD and old_state in (None, approval.DRAFT):
            errors = rules.eligibility_errors(_facts(doc)) + errors
        if old_state == approval.PENDING_ACCOUNTS and new_state == approval.PENDING_CONSENT:
            errors += rules.terms_errors({
                "amount": doc.get("loan_amount"), "approved_amount": doc.get("approved_amount"),
                "instalments": doc.get("instalments"), "first_repayment": doc.get("first_repayment"),
                "rate": doc.get("interest_rate")})
        if old_state == approval.PENDING_CONSENT and new_state == approval.RUNNING:
            errors += rules.consent_errors({
                "liability": doc.get("liability"), "amount": doc.get("approved_amount"),
                "instalments": doc.get("instalments"), "effective_from": doc.get("effective_from"),
                "consent": doc.get("consent")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Loan"))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state == approval.PENDING_CONSENT:
        _tell_terms(doc)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)


def _tell(doc, state):
    from hrms_addon.hrms_addon import loan_approval as approval

    if state == approval.PENDING_CONSENT:
        users = [frappe.db.get_value("Employee", doc.employee, "user_id")] if doc.get("employee") else []
        users = [user for user in users if user]
    else:
        users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"), doc.get("department"))
    if not users:
        return
    message = _("Loan request from {0}: {1}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("loan_amount")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def _tell_terms(doc):
    """Test case 3: the accountant has settled the terms, so the HR Officer
    is told what they are."""
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if not users:
        return
    people.notify(users, doc.doctype, doc.name,
                  _("{0}'s loan is settled at {1} over {2} month(s), {3} a month.").format(
                      doc.get("employee_name") or doc.employee,
                      frappe.utils.fmt_money(doc.get("approved_amount")), cint(doc.get("instalments")),
                      frappe.utils.fmt_money(doc.get("monthly_instalment"))))


def loan_on_submit(doc, method=None):
    """Running. The schedule becomes a monthly deduction on the payroll,
    and the HR Officer and the accountant are told the employee consented."""
    _make_deductions(doc)
    _tell_consent(doc)


def loan_on_cancel(doc, method=None):
    for row in doc.get("repayments") or []:
        if row.additional_salary and frappe.db.exists("Additional Salary", row.additional_salary):
            deduction = frappe.get_doc("Additional Salary", row.additional_salary)
            if deduction.docstatus == 1:
                deduction.flags.ignore_permissions = True
                deduction.cancel()
    doc.approval_status = "Cancelled"
    doc.status = "Cancelled"


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
                              "type": "Deduction", "salary_component_abbr": "LR",
                              "description": "Recovery of a staff loan (LPL/HR/39)."})
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(title="HRMS Addon: loan repayment component")
        return None


def _tell_consent(doc):
    """Test case 4: the HR Officer and the accountant are told the employee
    consented to the terms."""
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    users += people.people_for("Accounts User", doc.get("branch"), doc.get("department"))
    if not users:
        return
    people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                  _("{0} consented to the loan terms; the recovery starts {1}.").format(
                      doc.get("employee_name") or doc.employee,
                      frappe.utils.format_date(doc.get("first_repayment"))))


# ── 2. Step 6: the monitoring ─────────────────────────────────────────
def daily():
    _tell_due()
    _close_repaid()


def _tell_due():
    """A repayment falling due in the next week, told to the HR Officer and
    the employee."""
    rows = frappe.get_all("Loan Repayment",
                          filters={"parenttype": DOCTYPE, "recovered": ["!=", 1],
                                   "payroll_date": ["between", [today(), add_days(today(), 7)]]},
                          fields=["name", "parent", "payroll_date", "total"], limit=500)
    for row in rows:
        loan = frappe.db.get_value(DOCTYPE, row.parent,
                                   ["employee", "employee_name", "branch", "department", "docstatus",
                                    "outstanding"], as_dict=True)
        if not loan or loan.docstatus != 1:
            continue
        users = list(people.hr_officers(loan.branch, loan.department))
        user = frappe.db.get_value("Employee", loan.employee, "user_id")
        if user:
            users.append(user)
        if not users:
            continue
        people.notify(list(dict.fromkeys(users)), DOCTYPE, row.parent,
                      _("{0}'s loan repayment of {1} falls due on {2}. {3} still owed.").format(
                          loan.employee_name or loan.employee, frappe.utils.fmt_money(row.total),
                          frappe.utils.format_date(row.payroll_date),
                          frappe.utils.fmt_money(loan.outstanding)))
    frappe.db.commit()


def _close_repaid():
    """A loan whose last instalment has been taken is Repaid, and the
    employee and the HR Officer are told."""
    rows = frappe.get_all(DOCTYPE, filters={"docstatus": 1, "status": "Running", "outstanding": ["<=", 0]},
                          fields=["name", "employee", "employee_name", "branch", "department"], limit=200)
    for row in rows:
        frappe.db.set_value(DOCTYPE, row.name, "status", "Repaid", update_modified=False)
        users = list(people.hr_officers(row.branch, row.department))
        user = frappe.db.get_value("Employee", row.employee, "user_id")
        if user:
            users.append(user)
        if users:
            people.notify(list(dict.fromkeys(users)), DOCTYPE, row.name,
                          _("{0}'s loan is fully repaid.").format(row.employee_name or row.employee))
    frappe.db.commit()


def mark_recovered(payroll_date=None):
    """Whatever the payroll actually took, marked back onto the loans."""
    filters = {"parenttype": DOCTYPE, "recovered": ["!=", 1], "additional_salary": ["is", "set"]}
    if payroll_date:
        filters["payroll_date"] = payroll_date
    rows = frappe.get_all("Loan Repayment", filters=filters,
                          fields=["name", "parent", "additional_salary"], limit=500)
    touched = set()
    for row in rows:
        slips = frappe.get_all("Salary Detail",
                               filters={"additional_salary": row.additional_salary,
                                        "parenttype": "Salary Slip"}, pluck="parent", limit=1)
        if not slips or frappe.db.get_value("Salary Slip", slips[0], "docstatus") != 1:
            continue
        frappe.db.set_value("Loan Repayment", row.name, "recovered", 1, update_modified=False)
        touched.add(row.parent)
    for name in touched:
        doc = frappe.get_doc(DOCTYPE, name)
        recovered = sum(flt(child.total) for child in doc.repayments if child.recovered)
        total = flt(doc.approved_amount or doc.loan_amount) + flt(doc.total_interest)
        doc.db_set("recovered_amount", recovered)
        doc.db_set("outstanding", rules.outstanding(total, recovered))
        doc.db_set("status", rules.loan_status(1, total, recovered, doc.written_off))
    frappe.db.commit()
    return len(touched)


# ── 3. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the loan's five desks."""
    from hrms_addon.hrms_addon import loan_approval, workflows

    workflows.setup_on_migrate(loan_approval, "Employee Loan workflow")
