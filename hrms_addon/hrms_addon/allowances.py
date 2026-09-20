# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Allowance Application on the site (4.3), on Frappe HR's Travel Request.

The rules are in allowance_rules.py, without a Frappe import
(scripts/verify_benefits.py). This reads and writes the site.

LPL.HR.31 is the paper: a line per kind of expense with its days and rate,
a total, less any advance already taken, and the balance due. Frappe HR's
Travel Request already carries the employee, the purpose and a costing
table, so the form is built on it: the days and the rate go onto their
costing row and the totals onto the request.

  allowance_*  the eligibility the chart draws as "Qualified?", the lines
               costed, the totals, and the four signatures.
  daily        a request approved and waiting on Accounts.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from hrms_addon.hrms_addon import allowance_rules as rules, people

DOCTYPE = "Travel Request"


def allowance_validate(doc, method=None):
    from hrms_addon.hrms_addon import allowance_approval as approval

    _cost_lines(doc)
    _check_eligibility(doc)
    _check_step(doc)
    doc.custom_allowance_status = (doc.get("workflow_state") or doc.get("custom_allowance_status")
                                   or approval.DRAFT)


def _cost_lines(doc):
    """Each line of LPL.HR.31 is its days times its rate, and the foot of
    the form follows from the lines."""
    for row in doc.get("costings") or []:
        amount = rules.line_amount(row.get("custom_days"), row.get("custom_rate"))
        if amount:
            row.total_amount = amount
        if not row.get("funded_amount"):
            row.funded_amount = row.total_amount
    if doc.get("custom_advance") and not doc.get("custom_less_advance"):
        doc.custom_less_advance = flt(frappe.db.get_value("Employee Advance", doc.custom_advance,
                                                          "custom_approved_amount")
                                      or frappe.db.get_value("Employee Advance", doc.custom_advance,
                                                             "advance_amount"))
    figures = rules.totals(_lines(doc), doc.get("custom_less_advance"))
    doc.custom_total = figures["total"]
    doc.custom_balance_due = figures["balance"]


def _lines(doc):
    return [{"expense_type": row.get("expense_type"), "days": row.get("custom_days"),
             "rate": row.get("custom_rate"), "amount": row.get("total_amount")}
            for row in doc.get("costings") or []]


def _check_eligibility(doc):
    """The chart's "Qualified?", written onto the form rather than thrown,
    so the employee can see what is missing; the workflow will not move a
    request that does not qualify."""
    errors = rules.eligibility_errors(_facts(doc))
    doc.custom_qualifies = 0 if errors else 1
    doc.custom_eligibility_remarks = "; ".join(errors) or None


def _facts(doc):
    return {
        "status": frappe.db.get_value("Employee", doc.employee, "status") if doc.get("employee") else None,
        "purpose": doc.get("purpose_of_travel") or doc.get("description"),
        "start_date": doc.get("custom_start_date"), "end_date": doc.get("custom_end_date"),
        "lines": _lines(doc), "today": today(),
    }


def _check_step(doc):
    from hrms_addon.hrms_addon import allowance_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_SUPERVISOR and old_state in (None, approval.DRAFT):
            errors = rules.eligibility_errors(_facts(doc)) + errors
        if old_state == approval.PENDING_ACCOUNTS and new_state == approval.PAID:
            errors += rules.payment_errors({"balance": doc.get("custom_balance_due"),
                                            "paid_amount": doc.get("custom_paid_amount"),
                                            "paid_on": doc.get("custom_paid_on")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Allowance Application"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)


def _tell(doc, state):
    from hrms_addon.hrms_addon import allowance_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("custom_branch"),
                              doc.get("custom_department"))
    message = _("Allowance request from {0}: {1}.").format(
        doc.get("employee_name") or doc.employee,
        frappe.utils.fmt_money(doc.get("custom_total")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message, date=doc.get("custom_start_date"))


def allowance_on_submit(doc, method=None):
    """Step 4: Accounts have set it to Paid, and the HR Officer is told."""
    users = people.hr_officers(doc.get("custom_branch"), doc.get("custom_department"))
    if not users:
        return
    people.notify(users, doc.doctype, doc.name,
                  _("{0}'s allowance of {1} has been paid.").format(
                      doc.get("employee_name") or doc.employee,
                      frappe.utils.fmt_money(doc.get("custom_paid_amount") or doc.get("custom_balance_due"))))


def allowance_on_cancel(doc, method=None):
    doc.custom_allowance_status = "Cancelled"


def daily():
    """A request approved and waiting on Accounts."""
    from hrms_addon.hrms_addon import allowance_approval as approval

    rows = frappe.get_all(DOCTYPE,
                          filters={"docstatus": 0, "custom_allowance_status": approval.PENDING_ACCOUNTS},
                          fields=["name", "employee", "employee_name", "custom_branch", "custom_department",
                                  "custom_balance_due"], limit=200)
    for row in rows:
        users = people.people_for(approval.ACCOUNTS, row.custom_branch, row.custom_department)
        if not users:
            continue
        people.assign(DOCTYPE, row.name, users,
                      _("{0}'s allowance of {1} is waiting to be paid.").format(
                          row.employee_name or row.employee, frappe.utils.fmt_money(row.custom_balance_due)))
    frappe.db.commit()


def setup_workflows_on_migrate():
    """after_migrate: the four signatures the allowance passes."""
    from hrms_addon.hrms_addon import allowance_approval, workflows

    workflows.setup_on_migrate(allowance_approval, "Allowance Application workflow")


def seed_allowance_lines():
    """The five lines LPL.HR.31 prints, as Expense Claim Types, so the
    allowance form and the claim form share one list."""
    made = []
    for name in rules.ALLOWANCE_LINES:
        if frappe.db.exists("Expense Claim Type", name):
            frappe.db.set_value("Expense Claim Type", name, "custom_is_allowance_line", 1,
                                update_modified=False)
            continue
        doc = frappe.new_doc("Expense Claim Type")
        doc.expense_type = name
        doc.custom_is_allowance_line = 1
        doc.description = _("A line of the Employee Travel Allowance form (LPL.HR.31).")
        doc.insert(ignore_permissions=True)
        made.append(name)
    return made
