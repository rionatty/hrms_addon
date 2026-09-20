# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Advances on the site: leave advance (4.2), salary advance (4.10) and
the special advance the paper calls a loan (LPL/HR/21).

The rules are in advance_rules.py, without a Frappe import
(scripts/verify_leave.py). This reads and writes the site.

All three live on Frappe HR's own Employee Advance, because all three are
the same document: money paid before it is earned. The Advance Type says
which, and the workflow carries all three chains (advance_approval.py).

  advance_*   the eligibility check the charts draw as "Qualify for
              advance?", the two sanctions LPL/HR/21 carries, and the
              signatures of everyone on the chain.
  recovery    an advance is taken back through the payroll: each instalment
              becomes an Additional Salary deduction, so the payroll run
              needs no list kept by hand.
  from_leave  step 7 of the leave process: the Leave Advance raised from an
              approved LPL/HR/15 (leave.py).
  daily       the monitoring both charts ask for: an advance due to be paid,
              and one whose recovery has not started.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import advance_rules as rules, people

DOCTYPE = "Employee Advance"
DEFAULT_COMPONENT = "Advance Recovery"


# ── 1. The advance itself ─────────────────────────────────────────────
def advance_validate(doc, method=None):
    from hrms_addon.hrms_addon import advance_approval as approval

    if not doc.get("custom_advance_type"):
        doc.custom_advance_type = rules.SALARY_ADVANCE
    _fill_money(doc)
    _check_eligibility(doc)
    _build_recovery(doc)
    _check_step(doc)
    doc.custom_advance_status = doc.get("workflow_state") or doc.get("custom_advance_status") or approval.DRAFT
    if doc.get("custom_consent") and not doc.get("custom_consent_on"):
        doc.custom_consent_on = today()


def _fill_money(doc):
    """What the employee earns, what they still owe, and the ceiling that
    follows from the two."""
    if doc.get("employee"):
        doc.custom_gross_pay = _gross_pay(doc.employee)
        doc.custom_outstanding_before = _outstanding_elsewhere(doc.employee, doc.name)
    doc.custom_limit = rules.limit_for(doc.get("custom_gross_pay"))
    recovered = sum(flt(row.amount) for row in doc.get("custom_recoveries") or [] if row.recovered)
    doc.custom_recovered_amount = recovered
    doc.custom_outstanding = rules.outstanding(doc.get("custom_approved_amount") or doc.get("advance_amount"),
                                               recovered)


def _gross_pay(employee):
    rows = frappe.get_all("Salary Structure Assignment",
                          filters={"employee": employee, "docstatus": 1},
                          fields=["base"], order_by="from_date desc", limit=1)
    return flt(rows[0].base) if rows else 0


def _outstanding_elsewhere(employee, exclude):
    """What this employee still owes on advances already given. Only a
    submitted one counts: a draft is a request, not money out."""
    rows = frappe.get_all(DOCTYPE,
                          filters={"employee": employee, "docstatus": 1,
                                   "name": ["!=", exclude or ""]},
                          fields=["custom_outstanding"])
    return flt(sum(flt(row.custom_outstanding) for row in rows))


def _check_eligibility(doc):
    """The charts' "Qualify for advance?". It is written onto the form
    rather than thrown, so the HR Officer can see why and act on it; the
    workflow refuses to move an advance that does not qualify."""
    errors = rules.eligibility_errors(_facts(doc))
    doc.custom_qualifies = 0 if errors else 1
    doc.custom_eligibility_remarks = "; ".join(errors) or None


def _facts(doc):
    return {
        "advance_type": doc.get("custom_advance_type"),
        "status": frappe.db.get_value("Employee", doc.employee, "status") if doc.get("employee") else None,
        "date_of_joining": doc.get("custom_date_of_appointment"),
        "today": today(),
        "gross_pay": doc.get("custom_gross_pay"),
        "amount": doc.get("custom_approved_amount") or doc.get("advance_amount"),
        "outstanding": doc.get("custom_outstanding_before"),
        "instalments": doc.get("custom_instalments"),
    }


def _build_recovery(doc):
    """The instalments the advance comes back in. What is already recovered
    is left exactly as it is; only the months still to come are redrawn."""
    amount = flt(doc.get("custom_approved_amount")) or flt(doc.get("advance_amount"))
    instalments = cint(doc.get("custom_instalments")) or rules.DEFAULT_INSTALMENTS
    first = doc.get("custom_first_recovery_month")
    if not (amount and first):
        return
    done = [row for row in doc.get("custom_recoveries") or [] if row.recovered]
    taken = sum(flt(row.amount) for row in done)
    left = round(amount - taken, 2)
    months = max(instalments - len(done), 1)
    start = done[-1].payroll_date if done else first
    schedule = rules.recovery_schedule(left, months, rules.add_months(start, 1) if done else start)
    doc.set("custom_recoveries", done)
    for month, due in schedule:
        doc.append("custom_recoveries", {"payroll_date": month, "amount": due,
                                         "currency": doc.get("currency")})


def _check_step(doc):
    from hrms_addon.hrms_addon import advance_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            "approved_amount": doc.get("custom_approved_amount"),
            "instalments": doc.get("custom_instalments"),
            "section_head_amount": doc.get("custom_section_head_amount"),
            "ed_amount": doc.get("custom_ed_amount"),
            "attendance_confirmed": doc.get("custom_attendance_confirmed"),
            **{field: doc.get(field) for field in approval.ALL_REMARK_FIELDS},
        })
        if new_state and new_state != approval.DRAFT and old_state in (None, approval.DRAFT):
            errors = rules.eligibility_errors(_facts(doc)) + errors
        errors += rules.sanction_errors({
            "amount": doc.get("advance_amount"),
            "section_head_amount": doc.get("custom_section_head_amount"),
            "ed_amount": doc.get("custom_ed_amount"),
            "paid_amount": doc.get("custom_approved_amount"),
        })
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Advance"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)


def _tell(doc, state):
    from hrms_addon.hrms_addon import advance_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("custom_branch"), doc.get("department"))
    message = _("{0} for {1}: {2}.").format(
        doc.get("custom_advance_type") or _("Advance"), doc.get("employee_name") or doc.employee,
        frappe.utils.fmt_money(doc.get("advance_amount"), currency=doc.get("currency")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def advance_on_submit(doc, method=None):
    """Paid. The recovery starts, and everyone the chart names is told."""
    _make_deductions(doc)
    _tell_paid(doc)
    _mark_leave(doc)


def advance_on_cancel(doc, method=None):
    for row in doc.get("custom_recoveries") or []:
        if row.additional_salary and frappe.db.exists("Additional Salary", row.additional_salary):
            deduction = frappe.get_doc("Additional Salary", row.additional_salary)
            if deduction.docstatus == 1:
                deduction.flags.ignore_permissions = True
                deduction.cancel()
    doc.custom_advance_status = "Cancelled"


def _make_deductions(doc):
    """Each instalment becomes an Additional Salary deduction, so the
    payroll run takes it without a list kept by hand (test case 5 of the
    loan script, and the same mechanism for every advance)."""
    component = doc.get("custom_recovery_component") or _component()
    if not component:
        return
    for row in doc.get("custom_recoveries") or []:
        if row.additional_salary or row.recovered:
            continue
        deduction = frappe.get_doc({
            "doctype": "Additional Salary", "employee": doc.employee, "company": doc.company,
            "salary_component": component, "amount": flt(row.amount), "payroll_date": row.payroll_date,
            "currency": doc.get("currency"), "overwrite_salary_structure_amount": 0,
            "ref_doctype": doc.doctype, "ref_docname": doc.name,
        })
        deduction.flags.ignore_permissions = True
        deduction.insert()
        deduction.submit()
        row.db_set("additional_salary", deduction.name, update_modified=False)


def _component():
    """The salary component the recovery is posted to, made once."""
    if frappe.db.exists("Salary Component", DEFAULT_COMPONENT):
        return DEFAULT_COMPONENT
    try:
        doc = frappe.get_doc({"doctype": "Salary Component", "salary_component": DEFAULT_COMPONENT,
                              "type": "Deduction", "salary_component_abbr": "AR",
                              "description": "Recovery of an employee advance (LPL/HR/21)."})
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(title="HRMS Addon: advance recovery component")
        return None


def _tell_paid(doc):
    kind = doc.get("custom_advance_type")
    users = people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    users += people.people_for("Payroll Officer", doc.get("custom_branch"), doc.get("department"))
    message = _("{0} for {1} is paid. Recovery starts {2}.").format(
        kind, doc.get("employee_name") or doc.employee,
        frappe.utils.format_date(doc.get("custom_first_recovery_month")))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name, message)


def _mark_leave(doc):
    """Part 4 of LPL/HR/15: what Accounts advanced against the leave."""
    if doc.get("custom_advance_type") != rules.LEAVE_ADVANCE or not doc.get("custom_leave_application"):
        return
    amount = flt(doc.get("custom_approved_amount")) or flt(doc.get("advance_amount"))
    frappe.db.set_value("Leave Application", doc.custom_leave_application, {
        "custom_advance": doc.name, "custom_advance_amount": amount,
        "custom_accounts_by": frappe.session.user, "custom_accounts_on": today(),
    }, update_modified=False)


# ── 2. Raised from a leave form ───────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def from_leave(leave_application):
    """Step 1 of the Leave Advance process: the HR Officer raises it from
    the employee's leave form, and the Accounts Manager is told."""
    leave = frappe.get_doc("Leave Application", leave_application)
    leave.check_permission("read")
    if leave.docstatus != 1 or leave.status != "Approved":
        frappe.throw(_("The leave advance follows an approved leave application."))
    if leave.get("custom_advance"):
        return leave.custom_advance
    advance = frappe.new_doc(DOCTYPE)
    advance.update({
        "employee": leave.employee, "company": leave.company, "posting_date": today(),
        "custom_advance_type": rules.LEAVE_ADVANCE, "custom_leave_application": leave.name,
        "custom_branch": leave.get("custom_branch"),
        "purpose": _("Salary in advance for leave from {0} to {1}").format(
            frappe.utils.format_date(leave.from_date), frappe.utils.format_date(leave.to_date)),
        "custom_reason": leave.get("description"),
        "custom_first_recovery_month": leave.to_date,
        "custom_instalments": 1,
    })
    advance.flags.ignore_permissions = True
    advance.flags.ignore_mandatory = True
    advance.insert()
    frappe.db.set_value("Leave Application", leave.name, "custom_advance", advance.name,
                        update_modified=False)
    users = people.people_for("Accounts Manager", leave.get("custom_branch"), leave.get("department"))
    if users:
        people.notify(users, DOCTYPE, advance.name,
                      _("Leave advance raised for {0}.").format(leave.employee_name or leave.employee))
    return advance.name


# ── 3. The monitoring both charts draw ────────────────────────────────
def daily():
    _tell_due_to_pay()
    _tell_recovery()


def _tell_due_to_pay():
    """Step 2 of the Salary Advance chart: the system watches the date the
    advance is to be paid and tells the HR and Payroll Officers."""
    rows = frappe.get_all(DOCTYPE,
                          filters={"docstatus": 0, "custom_advance_status": "Pending Finance",
                                   "custom_first_recovery_month": ["<=", add_days(today(), 7)]},
                          fields=["name", "employee", "employee_name", "custom_branch", "department",
                                  "custom_advance_type"], limit=200)
    for row in rows:
        users = people.people_for("Finance Officer", row.custom_branch, row.department)
        if not users:
            continue
        people.assign(DOCTYPE, row.name, users,
                      _("{0} for {1} is waiting to be paid.").format(
                          row.custom_advance_type, row.employee_name or row.employee))
    frappe.db.commit()


def _tell_recovery():
    """An advance paid and still outstanding after its last instalment
    should have been taken."""
    rows = frappe.get_all(DOCTYPE,
                          filters={"docstatus": 1, "custom_outstanding": [">", 0]},
                          fields=["name", "employee", "employee_name", "custom_outstanding",
                                  "custom_branch", "department"], limit=200)
    for row in rows:
        last = frappe.get_all("Advance Recovery",
                              filters={"parent": row.name, "parenttype": DOCTYPE},
                              fields=["payroll_date"], order_by="payroll_date desc", limit=1)
        if not last or getdate(last[0].payroll_date) >= getdate(today()):
            continue
        users = people.people_for("Payroll Officer", row.custom_branch, row.department)
        users += people.hr_officers(row.custom_branch, row.department)
        if not users:
            continue
        people.notify(list(dict.fromkeys(users)), DOCTYPE, row.name,
                      _("{0} is still owed on {1}'s advance after the last instalment.").format(
                          frappe.utils.fmt_money(row.custom_outstanding), row.employee_name or row.employee))
    frappe.db.commit()


def mark_recovered(payroll_date=None):
    """Whatever the payroll actually took, marked back onto the advances.
    A deduction that was submitted and paid is the proof."""
    filters = {"parenttype": DOCTYPE, "recovered": 0, "additional_salary": ["is", "set"]}
    if payroll_date:
        filters["payroll_date"] = payroll_date
    rows = frappe.get_all("Advance Recovery", filters=filters,
                          fields=["name", "parent", "additional_salary"], limit=500)
    touched = set()
    for row in rows:
        slips = frappe.get_all("Salary Detail",
                               filters={"additional_salary": row.additional_salary, "parenttype": "Salary Slip"},
                               pluck="parent", limit=1)
        if not slips:
            continue
        if frappe.db.get_value("Salary Slip", slips[0], "docstatus") != 1:
            continue
        frappe.db.set_value("Advance Recovery", row.name, "recovered", 1, update_modified=False)
        touched.add(row.parent)
    for name in touched:
        doc = frappe.get_doc(DOCTYPE, name)
        recovered = sum(flt(child.amount) for child in doc.custom_recoveries if child.recovered)
        doc.db_set("custom_recovered_amount", recovered)
        doc.db_set("custom_outstanding", rules.outstanding(
            doc.get("custom_approved_amount") or doc.advance_amount, recovered))
    frappe.db.commit()
    return len(touched)


# ── 4. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the three chains, on one Workflow."""
    from hrms_addon.hrms_addon import advance_approval, workflows

    workflows.setup_on_migrate(advance_approval, "Employee Advance workflow")
