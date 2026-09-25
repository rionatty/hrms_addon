# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Cessation Benefits on the site (4.9), on Frappe HR's Full and Final
Statement.

The rules are in settlement_rules.py, without a Frappe import
(scripts/verify_exits.py). This reads and writes the site.

LPL/HR/20 is the paper: "my final salary, leave encashment, notice pay,
severance pay and any net claims ... less any statutory deductions", the
total in words, and the bank account it is remitted to. Frappe HR's Full
and Final Statement already carries payables, receivables and the assets
allocated, so the agreement is built on it.

  settlement_*  the computation Accounts draw up, the employee's own
                signature, the Executive Director's approval and the
                payroll run it is scheduled in.
  draw_up       step 3: what is due and what comes off, worked out from
                the employee's own pay, leave, advances, loans and the
                clearance form.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import pay, penalties, settlement_rules as rules, people

DOCTYPE = "Full and Final Statement"
DEFAULT_COMPONENT = "Terminal Benefits"


# ── 1. The statement ──────────────────────────────────────────────────
def settlement_validate(doc, method=None):
    from hrms_addon.hrms_addon import settlement_approval as approval

    _fill_totals(doc)
    _check_step(doc)
    doc.custom_settlement_status = (doc.get("workflow_state") or doc.get("custom_settlement_status")
                                    or approval.DRAFT)
    if doc.get("custom_employee_signed") and not doc.get("custom_employee_signed_on"):
        doc.custom_employee_signed_on = today()


def _fill_totals(doc):
    figures = rules.totals([row.as_dict() for row in doc.get("payables") or []],
                           [row.as_dict() for row in doc.get("receivables") or []])
    doc.total_payable_amount = figures["payable"]
    doc.total_receivable_amount = figures["receivable"]
    doc.custom_net_payable = figures["net"]
    doc.custom_net_in_words = _in_words(figures["net"], doc.get("company"))
    if doc.get("employee"):
        doc.custom_gross_pay = pay.monthly_gross(doc.employee)
        doc.custom_months_served = _months_served(doc)
    if doc.get("custom_separation"):
        exit_doc = frappe.db.get_value("Employee Separation", doc.custom_separation,
                                       ["custom_exit_type", "custom_notice_short_days"], as_dict=True)
        if exit_doc:
            doc.custom_exit_type = exit_doc.custom_exit_type
            doc.custom_notice_short_days = cint(exit_doc.custom_notice_short_days)


def _in_words(amount, company):
    currency = frappe.db.get_value("Company", company, "default_currency") if company else None
    try:
        return frappe.utils.money_in_words(flt(amount), currency or "UGX")
    except Exception:
        return None


def _months_served(doc):
    joined = doc.get("date_of_joining") or frappe.db.get_value("Employee", doc.employee, "date_of_joining")
    leaving = doc.get("relieving_date") or today()
    if not joined:
        return 0
    joined, leaving = getdate(joined), getdate(leaving)
    months = (leaving.year - joined.year) * 12 + (leaving.month - joined.month)
    return months - 1 if leaving.day < joined.day else months


def _check_step(doc):
    from hrms_addon.hrms_addon import settlement_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_ACCOUNTS and old_state in (None, approval.DRAFT):
            errors = rules.settlement_errors(_facts(doc)) + errors
        if old_state == approval.PENDING_EMPLOYEE and new_state != approval.DRAFT:
            errors += rules.payment_errors({
                "account_name": doc.get("custom_account_name"),
                "bank_name": doc.get("custom_bank_name"),
                "account_number": doc.get("custom_account_number"),
                "employee_signed": doc.get("custom_employee_signed")})
        if old_state == approval.PENDING_PAYROLL and new_state == approval.SCHEDULED:
            errors += rules.schedule_errors({"payroll_date": doc.get("custom_payroll_date"),
                                             "approved": doc.get("custom_ed_by")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Cessation Benefits"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)


def _facts(doc):
    return {
        "relieving_date": doc.get("relieving_date"), "date_of_joining": doc.get("date_of_joining"),
        "payables": [row.as_dict() for row in doc.get("payables") or []],
        "receivables": [row.as_dict() for row in doc.get("receivables") or []],
        "clearance": doc.get("custom_clearance"),
    }


def _tell(doc, state):
    from hrms_addon.hrms_addon import settlement_approval as approval

    if state == approval.PENDING_EMPLOYEE:
        user = frappe.db.get_value("Employee", doc.employee, "user_id") if doc.get("employee") else None
        users = [user] if user else people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    else:
        users = people.people_for(approval.ROLE_WAITING[state], doc.get("custom_branch"),
                                  doc.get("department"))
    if not users:
        return
    message = _("Full and final settlement for {0}: {1}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("custom_net_payable")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def settlement_on_submit(doc, method=None):
    """Scheduled: the settlement goes into the payroll run as an Additional
    Salary, and the payroll process follows (step 6). What it takes for
    loans is marked paid on them, and their deductions still to come are
    cancelled (loans.py)."""
    from hrms_addon.hrms_addon import loans

    _schedule_payment(doc)
    loans.settle_on_exit(doc)
    users = people.people_for("Payroll Officer", doc.get("custom_branch"), doc.get("department"))
    users += people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                      _("{0}'s settlement of {1} is scheduled for the {2} payroll.").format(
                          doc.get("employee_name") or doc.employee,
                          frappe.utils.fmt_money(doc.get("custom_net_payable")),
                          frappe.utils.format_date(doc.get("custom_payroll_date"))))


def settlement_on_cancel(doc, method=None):
    from hrms_addon.hrms_addon import loans

    loans.unsettle_on_exit(doc)
    if doc.get("custom_additional_salary") and frappe.db.exists("Additional Salary",
                                                                doc.custom_additional_salary):
        extra = frappe.get_doc("Additional Salary", doc.custom_additional_salary)
        if extra.docstatus == 1:
            extra.flags.ignore_permissions = True
            extra.cancel()
    doc.custom_settlement_status = "Cancelled"


def _schedule_payment(doc):
    """The net goes into the next payroll run as an earning, so the
    settlement is paid the way every other payment is."""
    if doc.get("custom_additional_salary") or not doc.get("custom_payroll_date"):
        return
    component = doc.get("custom_salary_component") or _component()
    if not component or flt(doc.get("custom_net_payable")) <= 0:
        return
    extra = frappe.get_doc({
        "doctype": "Additional Salary", "employee": doc.employee, "company": doc.company,
        "salary_component": component, "amount": flt(doc.custom_net_payable),
        "payroll_date": doc.custom_payroll_date, "overwrite_salary_structure_amount": 0,
        "ref_doctype": doc.doctype, "ref_docname": doc.name,
    })
    extra.flags.ignore_permissions = True
    extra.insert()
    extra.submit()
    doc.db_set("custom_additional_salary", extra.name, update_modified=False)


def _component():
    if frappe.db.exists("Salary Component", DEFAULT_COMPONENT):
        return DEFAULT_COMPONENT
    try:
        doc = frappe.get_doc({"doctype": "Salary Component", "salary_component": DEFAULT_COMPONENT,
                              "type": "Earning", "salary_component_abbr": "TB",
                              "description": "Full and final settlement (LPL/HR/20)."})
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(title="HRMS Addon: terminal benefits component")
        return None


# ── 2. Step 3: what is due and what comes off ─────────────────────────
@frappe.whitelist(methods=["POST"])
def draw_up(separation):
    """The computation, worked out from the employee's own pay, leave,
    advances, loans and clearance form. Accounts may change any of it."""
    exit_doc = frappe.get_doc("Employee Separation", separation)
    exit_doc.check_permission("read")
    if exit_doc.get("custom_settlement"):
        return exit_doc.custom_settlement
    if not exit_doc.get("custom_clearance"):
        frappe.throw(_("The Clearance Form comes first (LPL/HR/22): it says what is still outstanding."))
    # step 2 of the chart comes before step 3, and not only on paper: the
    # statement reads its relieving date off the Employee, so one drawn up
    # before they are marked Left carries no last day of service
    if not exit_doc.get("custom_status_updated"):
        frappe.throw(_("The employee is made inactive first (step 2): submit the separation, and the "
                       "last day of service reaches the statement from their record."))
    employee = exit_doc.employee
    gross = pay.monthly_gross(employee)
    clearance = frappe.db.get_value("Clearance Form", exit_doc.custom_clearance,
                                    ["outstanding_cost", "leave_balance", "days_worked"], as_dict=True) or {}
    leaving = getdate(exit_doc.get("custom_relieving_date") or today())
    found = rules.suggest({
        "gross_pay": gross,
        "days_worked_in_month": min(leaving.day, rules.WORKING_DAYS_A_MONTH),
        "leave_balance": clearance.get("leave_balance"),
        "months_served": _months_between(frappe.db.get_value("Employee", employee, "date_of_joining"),
                                         leaving),
        "notice_short_days": cint(exit_doc.get("custom_notice_short_days")),
        "advances_outstanding": _advances(employee),
        "loans_outstanding": _loans(employee),
        "penalties_outstanding": penalties.owed(employee),
        "unreturned_cost": clearance.get("outstanding_cost"),
    })
    doc = frappe.new_doc(DOCTYPE)
    doc.update({
        # relieving_date and date_of_joining are theirs, fetched from the
        # Employee and read-only; they are not set here
        "employee": employee, "company": exit_doc.company, "transaction_date": today(),
        "custom_separation": separation, "custom_clearance": exit_doc.custom_clearance,
        "custom_exit_type": exit_doc.get("custom_exit_type"),
        "custom_leave_balance": clearance.get("leave_balance"),
        "custom_account_name": frappe.db.get_value("Employee", employee, "employee_name"),
        "custom_bank_name": frappe.db.get_value("Employee", employee, "bank_name"),
        "custom_account_number": frappe.db.get_value("Employee", employee, "bank_ac_no"),
    })
    for row in found["payables"]:
        doc.append("payables", {"component": row["component"], "amount": row["amount"], "status": "Unsettled"})
    for row in found["receivables"]:
        doc.append("receivables", {"component": row["component"], "amount": row["amount"],
                                   "status": "Unsettled"})
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.insert()
    frappe.db.set_value("Employee Separation", separation, "custom_settlement", doc.name,
                        update_modified=False)
    return doc.name


def _months_between(joined, until):
    if not joined:
        return 0
    joined, until = getdate(joined), getdate(until)
    months = (until.year - joined.year) * 12 + (until.month - joined.month)
    return months - 1 if until.day < joined.day else months


def _advances(employee):
    rows = frappe.get_all("Employee Advance", filters={"employee": employee, "docstatus": 1},
                          fields=["custom_outstanding"])
    return flt(sum(flt(row.custom_outstanding) for row in rows))


def _loans(employee):
    """Still owed on loans running now: a refused request owes nothing."""
    rows = frappe.get_all("Employee Loan", filters={"employee": employee, "docstatus": 1, "status": "Running"},
                          fields=["outstanding"])
    return flt(sum(flt(row.outstanding) for row in rows))


# ── 3. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the settlement's four desks."""
    from hrms_addon.hrms_addon import settlement_approval, workflows

    workflows.setup_on_migrate(settlement_approval, "Cessation Benefits workflow")
