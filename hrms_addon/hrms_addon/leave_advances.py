# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Advance, on the site (minutes of 16 and 20 July 2026, §4.4).

The rules are in leave_advance_rules.py and the workflow in
leave_advance_approval.py, both without a Frappe import
(scripts/verify_leave_advance.py). This reads and writes the site.

The Leave Advance is its own document, kept apart from the loans and the
other advances:

  raise_*            raised from the approved Leave Application: by itself
                     when the leave is approved and the employee asked
                     (Leave Management Settings), or by HR's button
  advance_*          what it may be (60% of gross; for the Per Meter
                     category, of the average gross of the previous two
                     months), whether the employee qualifies, the months it
                     is taken back in, the Accounts Manager's approval, and
                     the amount recorded on the leave form
  run_*              the Leave Advance Processing: the Payroll Officer gets
                     the approved advances, downloads the Excel file for
                     Finance and submits, which makes one bank entry
  payment_*          Finance submitting that bank entry: each advance is
                     paid and its deductions go onto the payroll
  refresh_recovered  a month the payroll took (recoveries.py)

WHERE THE MONEY SITS

Frappe HR's payroll books a deduction against an employee only when it
refers to an Employee Advance. A leave advance is not one, so it is paid
into, and taken back out of, an asset account of its own, "Leave Advances"
(Leave Management Settings), which is not a receivable: each Leave Advance
keeps what that employee still owes.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import leave_accrual, leave_accrual_rules, leave_advance_rules as rules, pay, people

ADVANCE = "Leave Advance"
RUN = "Leave Advance Processing"
LINE = "Leave Advance Processing Employee"
APPLICATION = "Leave Application"


# ── 1. Raised from the approved leave ─────────────────────────────────
def on_leave_approved(leave):
    """Step 2: the employee asked for an advance on a leave now approved.
    Raised at once and sent to the Accounts Manager when they qualify; left
    with HR, saying why, when they do not. Never stops the leave itself."""
    if not leave.get("custom_salary_requested_in_advance"):
        return None
    if not leave_accrual.settings().raise_on_approval:
        _tell_hr(leave, _("{0} asked for a leave advance. Raise it from the leave application.").format(
            leave.get("employee_name") or leave.employee))
        return None
    frappe.db.savepoint("hrms_addon_leave_advance")
    try:
        return _raise(leave, send=True)
    except Exception:
        frappe.db.rollback(save_point="hrms_addon_leave_advance")
        frappe.log_error(title="HRMS Addon: leave advance for %s" % leave.name)
        _tell_hr(leave, _("{0} asked for a leave advance and it could not be raised by itself. Raise it from the "
                          "leave application.").format(leave.get("employee_name") or leave.employee))
        return None


@frappe.whitelist(methods=["POST"])
def raise_advance(leave_application):
    """The leave form's Raise Leave Advance."""
    frappe.has_permission(ADVANCE, "create", throw=True)
    leave = frappe.get_doc(APPLICATION, leave_application)
    leave.check_permission("read")
    return _raise(leave, send=False)


def _raise(leave, send=False):
    if leave.docstatus != 1 or leave.status != "Approved":
        frappe.throw(_("A leave advance follows an approved leave."), title=_(ADVANCE))
    existing = _live_advance(leave.name)
    if existing:
        return existing
    s = leave_accrual.settings()
    advance = frappe.get_doc({
        "doctype": ADVANCE, "employee": leave.employee, "company": leave.company, "posting_date": today(),
        "leave_application": leave.name, "instalments": s.instalments,
        "first_deduction": rules.first_deduction(leave.to_date),
    })
    advance.flags.ignore_permissions = True
    advance.insert()
    if send and advance.qualifies:
        # sent on as the desk would, from the draft as stored
        advance = frappe.get_doc(ADVANCE, advance.name)
        advance.workflow_state = rules.PENDING
        advance.flags.ignore_permissions = True
        advance.save()
    elif not advance.qualifies:
        _tell_hr(leave, _("{0} asked for a leave advance and does not qualify: {1}").format(
            leave.get("employee_name") or leave.employee, advance.eligibility_remarks))
    frappe.db.set_value(APPLICATION, leave.name, "custom_leave_advance", advance.name, update_modified=False)
    return advance.name


def _live_advance(leave_application, exclude=None):
    found = frappe.get_all(ADVANCE, filters={"leave_application": leave_application, "docstatus": ["!=", 2],
                                             "name": ["!=", exclude or ""]}, pluck="name", limit=1)
    return found[0] if found else None


def _tell_hr(leave, message):
    users = people.hr_officers(leave.get("custom_branch"), leave.get("department"))
    if users:
        people.notify(users, APPLICATION, leave.name, message)


# ── 2. The advance ────────────────────────────────────────────────────
def advance_validate(doc, method=None):
    s = leave_accrual.settings()
    leave = _leave(doc.get("leave_application"))
    if not leave:
        frappe.throw(_("Choose the leave application the advance is for."), title=_(ADVANCE))
    if leave.employee != doc.get("employee"):
        frappe.throw(_("Leave application {0} is {1}'s.").format(leave.name, leave.employee_name or leave.employee),
                     title=_(ADVANCE))
    other = _live_advance(leave.name, exclude=doc.name)
    if other:
        frappe.throw(_("Leave application {0} already has leave advance {1}.").format(leave.name, other),
                     title=_(ADVANCE))
    if not cint(doc.get("instalments")):
        doc.instalments = s.instalments
    if not doc.get("first_deduction"):
        doc.first_deduction = rules.first_deduction(leave.to_date)
    _fill_amount(doc, leave, s)
    _check_eligibility(doc, leave, s)
    _build_recovery(doc)
    _check_step(doc)
    doc.status = _status(doc)


def _leave(name):
    if not name:
        return None
    return frappe.db.get_value(APPLICATION, name, ["name", "employee", "employee_name", "docstatus", "status",
                                                   "leave_type", "total_leave_days", "from_date", "to_date",
                                                   "company"], as_dict=True)


def _fill_amount(doc, leave, s):
    """What the employee earns, and the most that may be advanced: the
    Accounts Manager's figure on the form (§4.4)."""
    category = _pay_category(doc.employee)
    monthly = pay.monthly_gross(doc.employee, leave.from_date)
    recent = []
    if category == rules.PER_METER:
        recent = frappe.get_all("Salary Slip", filters={"employee": doc.employee, "docstatus": 1,
                                                        "end_date": ["<", leave.from_date]},
                                pluck="gross_pay", order_by="end_date desc", limit=max(int(s.per_meter_months), 1))
    gross, basis = rules.gross_basis(category, monthly, recent, s.per_meter_months)
    doc.pay_category = category
    doc.gross_pay = gross or 0
    doc.gross_basis = _("{0}% of {1}").format("%g" % s.advance_percent, basis) if basis else None
    ceiling = rules.allowed(gross, s)
    doc.allowed_amount = ceiling or 0
    if doc.docstatus == 0 and not flt(doc.get("amount")) and ceiling:
        doc.amount = ceiling


def _pay_category(employee):
    if not frappe.get_meta("Employee").has_field("custom_pay_category"):
        return rules.MONTHLY
    return frappe.db.get_value("Employee", employee, "custom_pay_category") or rules.MONTHLY


def _check_eligibility(doc, leave, s):
    """Regular, no bank or company loan, more than 19 days of accrued leave:
    written on the form rather than thrown, so HR can see why, and the
    workflow will not send on an advance that does not qualify."""
    person = frappe.db.get_value("Employee", doc.employee, ["status", "employment_type"], as_dict=True) or {}
    errors = rules.eligibility_errors({
        "status": person.get("status"), "employment_type": person.get("employment_type"),
        "bank_loan": _bank_loan(doc.employee), "company_loan": _company_loan(doc.employee),
        "leave_type": leave.leave_type,
        "earned_leave": leave_accrual_rules.earns(leave_accrual.leave_type_rule(leave.leave_type)),
        "leave_days": leave.total_leave_days, "outstanding": _outstanding_elsewhere(doc.employee, doc.name),
        "allowed": doc.allowed_amount or None, "amount": doc.get("amount"), "instalments": doc.get("instalments"),
    }, s)
    if leave.docstatus != 1 or leave.status != "Approved":
        errors.insert(0, _("The leave is not approved yet."))
    doc.qualifies = 0 if errors else 1
    doc.eligibility_remarks = "; ".join(errors) or None


def _bank_loan(employee):
    """A bank loan the employee has declared, still running."""
    meta = frappe.get_meta("Employee")
    if not meta.has_field("custom_has_bank_loan"):
        return False
    has, until = frappe.db.get_value("Employee", employee, ["custom_has_bank_loan", "custom_bank_loan_until"]) or (0, None)
    return bool(cint(has)) and (not until or getdate(until) >= getdate(today()))


def _company_loan(employee):
    """What is still owed on a company loan running now."""
    if not frappe.db.exists("DocType", "Employee Loan"):
        return 0.0
    return flt(sum(flt(value) for value in frappe.get_all(
        "Employee Loan", filters={"employee": employee, "docstatus": 1, "status": "Running"},
        pluck="outstanding", limit_page_length=0)))


def _outstanding_elsewhere(employee, exclude):
    return flt(sum(flt(value) for value in frappe.get_all(
        ADVANCE, filters={"employee": employee, "docstatus": 1, "name": ["!=", exclude or ""]},
        pluck="outstanding", limit_page_length=0)))


def _build_recovery(doc):
    """The months it is taken back in, until it is paid; after that they are
    on the payroll and stay as they are."""
    if doc.get("paid_on"):
        _totals(doc)
        return
    doc.set("recoveries", [])
    for month, amount in rules.recovery_schedule(doc.get("amount"), doc.get("instalments"), doc.get("first_deduction")):
        doc.append("recoveries", {"payroll_date": month, "amount": amount})
    _totals(doc)


def _totals(doc):
    recovered = sum(flt(row.amount) for row in doc.get("recoveries") or [] if row.recovered)
    doc.recovered_amount = round(recovered, 2)
    doc.outstanding = rules.outstanding(doc.get("amount"), recovered) if doc.get("paid_on") else 0


def _status(doc):
    on_run = bool(doc.get("processing")) and frappe.db.get_value(RUN, doc.processing, "docstatus") == 1
    return rules.advance_status(doc.docstatus, doc.get("workflow_state"), on_run, bool(doc.get("paid_on")),
                                doc.get("amount"), doc.get("recovered_amount"))


def _check_step(doc):
    from hrms_addon.hrms_addon import leave_advance_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {"remarks": doc.get("accounts_manager_remarks"),
                                                             "qualifies": doc.get("qualifies")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(ADVANCE))
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    doc.approval_status = new_state or doc.get("approval_status") or approval.DRAFT
    if old_state != new_state and new_state in approval.PENDING_STATES:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.get("branch"), doc.get("department"))
        message = _("Leave advance for {0}: {1}, for leave from {2}.").format(
            doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("amount")),
            frappe.utils.format_date(doc.get("from_date")))
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)


def advance_on_submit(doc, method=None):
    """Approved by the Accounts Manager: the amount recorded on the leave
    form (Part 4), and the Payroll Officer told."""
    doc.db_set("status", _status(doc), update_modified=False)
    frappe.db.set_value(APPLICATION, doc.leave_application, {
        "custom_leave_advance": doc.name, "custom_advance_amount": doc.amount,
        "custom_accounts_by": doc.get("accounts_manager_by") or frappe.session.user,
        "custom_accounts_on": doc.get("accounts_manager_on") or today(),
    }, update_modified=False)
    users = people.people_for("Payroll Officer", doc.get("branch"), doc.get("department"))
    if users:
        people.notify(users, doc.doctype, doc.name, _(
            "Leave advance for {0} approved: {1}. It is waiting in the Leave Advance Processing.").format(
            doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.amount)))


def advance_before_update(doc, method=None):
    """After approval only the months it is taken back in change, and only
    until it is paid."""
    before = doc.get_doc_before_save()
    changed = before and (cint(before.get("instalments")) != cint(doc.get("instalments"))
                          or str(before.get("first_deduction") or "") != str(doc.get("first_deduction") or ""))
    if changed and doc.get("paid_on"):
        frappe.throw(_("The deductions are on the payroll already. Change them on the Additional Salary."),
                     title=_(ADVANCE))
    s = leave_accrual.settings()
    if not 1 <= cint(doc.get("instalments")) <= int(s.max_instalments):
        frappe.throw(_("A leave advance is recovered in 1 to {0} month(s).").format(int(s.max_instalments)),
                     title=_(ADVANCE))
    _build_recovery(doc)
    doc.status = _status(doc)


def advance_on_cancel(doc, method=None):
    if doc.get("paid_on"):
        frappe.throw(_("{0} is paid. Cancel the bank entry {1} first.").format(doc.name, doc.get("journal_entry")),
                     title=_(ADVANCE))
    if doc.get("processing") and frappe.db.get_value(RUN, doc.processing, "docstatus") == 1:
        frappe.throw(_("{0} is on Leave Advance Processing {1}. Cancel that first.").format(doc.name, doc.processing),
                     title=_(ADVANCE))
    doc.db_set("status", rules.CANCELLED, update_modified=False)
    if frappe.db.get_value(APPLICATION, doc.leave_application, "custom_leave_advance") == doc.name:
        frappe.db.set_value(APPLICATION, doc.leave_application,
                            {"custom_leave_advance": None, "custom_advance_amount": 0}, update_modified=False)


def refresh_recovered(name):
    """What the payroll has taken back, and what is still owed (recoveries.py)."""
    doc = frappe.get_doc(ADVANCE, name)
    if doc.docstatus != 1:
        return
    _totals(doc)
    doc.db_set({"recovered_amount": doc.recovered_amount, "outstanding": doc.outstanding, "status": _status(doc)},
               update_modified=False)


# ── 3. The Payroll Officer's run ──────────────────────────────────────
def run_validate(doc, method=None):
    seen = set()
    for row in doc.get("employees") or []:
        if row.leave_advance in seen:
            frappe.throw(_("{0} is listed more than once.").format(row.leave_advance), title=_(RUN))
        seen.add(row.leave_advance)
        if doc.docstatus == 0:
            _fill_line(row, doc)
    paid = [row for row in doc.get("employees") or [] if row.include]
    doc.total_employees = len(paid)
    doc.total_amount = round(sum(flt(row.amount) for row in paid), 2)
    if doc.docstatus == 0:
        doc.status = rules.RUN_DRAFT


def _fill_line(row, doc):
    """One advance's line: whose it is, how much, and where it is paid."""
    advance = frappe.db.get_value(ADVANCE, row.leave_advance, [
        "employee", "employee_name", "branch", "department", "leave_application", "amount", "docstatus", "status",
        "company", "processing"], as_dict=True)
    if not advance:
        row.include, row.remarks = 0, _("Leave advance {0} does not exist.").format(row.leave_advance)
        return
    person = frappe.db.get_value("Employee", advance.employee, ["salary_mode", "bank_name", "bank_ac_no"],
                                 as_dict=True) or frappe._dict()
    row.update({"employee": advance.employee, "employee_name": advance.employee_name, "branch": advance.branch,
                "department": advance.department, "leave_application": advance.leave_application,
                "amount": advance.amount, "salary_mode": person.salary_mode, "bank_name": person.bank_name,
                "bank_ac_no": person.bank_ac_no, "bank_code": _bank_code(advance.employee, person.bank_name)})
    notes = []
    if advance.company != doc.company:
        notes.append(_("Of another company."))
    if not _waiting(advance, doc.name):
        notes.append(_("{0}, not waiting to be paid.").format(_(advance.status or "")))
    if person.salary_mode == rules.BANK and not person.bank_ac_no:
        notes.append(_("No bank account number on the employee."))
    elif person.salary_mode == rules.BANK and not row.bank_code:
        notes.append(_("No bank code on the employee."))
    row.remarks = " ".join(notes) or None


def _waiting(advance, run):
    """Approved and not yet on another submitted run."""
    if advance.docstatus != 1 or advance.status not in (rules.APPROVED, rules.PROCESSING):
        return False
    return not advance.processing or advance.processing == run or frappe.db.get_value(
        RUN, advance.processing, "docstatus") != 1


def _bank_code(employee, bank_name):
    """The employee's Bank Code, else the SWIFT number of the Bank they
    name, when there is one."""
    code = frappe.db.get_value("Employee", employee, "custom_bank_code") if frappe.get_meta(
        "Employee").has_field("custom_bank_code") else None
    if not code and bank_name and frappe.db.exists("Bank", bank_name):
        code = frappe.db.get_value("Bank", bank_name, "swift_number")
    return code or None


@frappe.whitelist(methods=["POST"])
def get_advances(name):
    """Every approved leave advance of the run's company (and plant) not yet
    on a submitted run. Returns how many were added."""
    doc = frappe.get_doc(RUN, name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("The run is already submitted."))
    filters = {"docstatus": 1, "status": rules.APPROVED, "company": doc.company}
    if doc.get("branch"):
        filters["branch"] = doc.branch
    have = {row.leave_advance for row in doc.get("employees") or []}
    added = 0
    for name_ in frappe.get_all(ADVANCE, filters=filters, pluck="name", order_by="employee_name asc",
                                limit_page_length=0):
        if name_ in have:
            continue
        doc.append("employees", {"leave_advance": name_, "include": 1})
        added += 1
    doc.save()
    return added


def run_before_submit(doc, method=None):
    for row in doc.get("employees") or []:
        _fill_line(row, doc)
    included = [row for row in doc.get("employees") or [] if row.include]
    errors = rules.run_errors({
        "included": len(included), "bank_account": doc.get("bank_account"),
        "payment_method": doc.get("payment_method"), "reference_no": doc.get("reference_no"),
        "reference_date": doc.get("reference_date"),
        "no_account": [row.employee_name or row.employee for row in included
                       if row.salary_mode == rules.BANK and not row.bank_ac_no],
        "not_approved": [row.leave_advance for row in included if not _waiting(frappe.db.get_value(
            ADVANCE, row.leave_advance, ["docstatus", "status", "processing"], as_dict=True) or frappe._dict(),
            doc.name)],
    })
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(RUN))
    doc.total_employees = len(included)
    doc.total_amount = round(sum(flt(row.amount) for row in included), 2)


def run_on_submit(doc, method=None):
    """One draft bank entry for Finance paying every advance in the run."""
    included = [row for row in doc.get("employees") or [] if row.include]
    account = leave_advance_account(doc.company)
    recovery_component(doc.company)
    entry = frappe.new_doc("Journal Entry")
    entry.voucher_type = "Cash Entry" if doc.payment_method == "Cash" else "Bank Entry"
    entry.company = doc.company
    entry.posting_date = doc.posting_date
    entry.cheque_no = doc.get("reference_no")
    entry.cheque_date = doc.get("reference_date")
    entry.user_remark = _("Leave advances ({0})").format(doc.name)
    for row in included:
        entry.append("accounts", {"account": account, "debit_in_account_currency": flt(row.amount),
                                  "user_remark": _("Leave advance {0}: {1} {2}").format(
                                      row.leave_advance, row.employee, row.employee_name)})
    entry.append("accounts", {"account": doc.bank_account, "credit_in_account_currency": doc.total_amount})
    entry.flags.ignore_permissions = True
    entry.insert()
    doc.db_set({"journal_entry": entry.name, "status": rules.RUN_SENT}, update_modified=False)
    for row in included:
        frappe.db.set_value(ADVANCE, row.leave_advance, {"processing": doc.name, "status": rules.PROCESSING},
                            update_modified=False)
    plants = sorted({row.branch for row in included if row.get("branch")}) or [None]
    users = []
    for plant in plants:
        users += people.people_for("Finance Officer", plant) + people.people_for("Payroll Officer", plant)
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name, _(
            "Leave advances: {0} employee(s), {1}. Pay them and submit bank entry {2}.").format(
            len(included), frappe.utils.fmt_money(doc.total_amount), entry.name))


def run_on_cancel(doc, method=None):
    if doc.get("journal_entry") and frappe.db.exists("Journal Entry", doc.journal_entry):
        if frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus") == 1:
            frappe.throw(_("Cancel the bank entry {0} first.").format(doc.journal_entry), title=_(RUN))
        frappe.delete_doc("Journal Entry", doc.journal_entry, ignore_permissions=True)
    for row in doc.get("employees") or []:
        if frappe.db.get_value(ADVANCE, row.leave_advance, "processing") == doc.name:
            frappe.db.set_value(ADVANCE, row.leave_advance, {"processing": None, "status": rules.APPROVED},
                                update_modified=False)
    doc.db_set("status", rules.RUN_CANCELLED, update_modified=False)


@frappe.whitelist()
def bank_file(name):
    """The Excel file the Payroll Officer sends Finance: employee number,
    name, bank code, account number and amount (§4.4)."""
    from frappe.utils.xlsxutils import make_xlsx

    doc = frappe.get_doc(RUN, name)
    doc.check_permission("read")
    rows = rules.bank_file_rows([row.as_dict() for row in doc.get("employees") or []])
    frappe.response["filename"] = "%s.xlsx" % doc.name
    frappe.response["filecontent"] = make_xlsx(rows, "Leave Advances").getvalue()
    frappe.response["type"] = "binary"


# ── 4. Finance pays ───────────────────────────────────────────────────
def payment_on_submit(doc, method=None):
    """The run's bank entry submitted: each advance is paid, and its
    deductions go onto the payroll for their months."""
    for run in frappe.get_all(RUN, filters={"journal_entry": doc.name, "docstatus": 1}, pluck="name"):
        frappe.db.set_value(RUN, run, "status", rules.RUN_PAID, update_modified=False)
        made = []
        for row in frappe.get_all(LINE, filters={"parent": run, "parenttype": RUN, "include": 1},
                                  pluck="leave_advance"):
            advance = frappe.get_doc(ADVANCE, row)
            advance.db_set({"paid_on": doc.posting_date, "journal_entry": doc.name}, update_modified=False)
            schedule_recovery(advance)
            refresh_recovered(advance.name)
            made.append(advance)
        _tell_paid(run, made)


def payment_on_cancel(doc, method=None):
    """The bank entry cancelled before the payroll took anything: the
    deductions come off and the advances wait to be paid again."""
    for run in frappe.get_all(RUN, filters={"journal_entry": doc.name, "docstatus": 1}, pluck="name"):
        names = frappe.get_all(LINE, filters={"parent": run, "parenttype": RUN, "include": 1}, pluck="leave_advance")
        taken = frappe.get_all("Leave Advance Recovery", filters={"parent": ["in", names or [""]],
                                                                  "parenttype": ADVANCE, "recovered": 1},
                               pluck="parent", limit=1)
        if taken:
            frappe.throw(_("The payroll has already taken back part of {0}. The payment stays.").format(taken[0]),
                         title=_(RUN))
        for name in names:
            advance = frappe.get_doc(ADVANCE, name)
            for row in advance.get("recoveries") or []:
                if row.additional_salary and frappe.db.exists("Additional Salary", row.additional_salary):
                    deduction = frappe.get_doc("Additional Salary", row.additional_salary)
                    if deduction.docstatus == 1:
                        deduction.flags.ignore_permissions = True
                        deduction.cancel()
                row.db_set("additional_salary", None, update_modified=False)
            advance.db_set({"paid_on": None, "journal_entry": None, "status": rules.PROCESSING}, update_modified=False)
            refresh_recovered(name)
        frappe.db.set_value(RUN, run, "status", rules.RUN_SENT, update_modified=False)


def schedule_recovery(advance):
    """Each month's deduction, an Additional Salary for the payroll."""
    component = recovery_component(advance.company)
    made = 0
    for row in advance.get("recoveries") or []:
        if row.additional_salary or row.recovered:
            continue
        deduction = frappe.get_doc({
            "doctype": "Additional Salary", "employee": advance.employee, "company": advance.company,
            "salary_component": component, "amount": flt(row.amount), "payroll_date": row.payroll_date,
            "currency": frappe.get_cached_value("Company", advance.company, "default_currency"),
            "overwrite_salary_structure_amount": 0, "ref_doctype": ADVANCE, "ref_docname": advance.name,
        })
        deduction.flags.ignore_permissions = True
        deduction.insert()
        deduction.submit()
        row.db_set("additional_salary", deduction.name, update_modified=False)
        made += 1
    return made


def _tell_paid(run, made):
    if not made:
        return
    users = []
    for advance in made:
        users += people.people_for("Payroll Officer", advance.get("branch"), advance.get("department"))
        users += people.hr_officers(advance.get("branch"), advance.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), RUN, run, _(
            "Leave advances paid for {0} employee(s); their deductions are on the payroll.").format(len(made)))


# ── 5. The accounts ───────────────────────────────────────────────────
def leave_advance_account(company):
    """Leave Management Settings' Leave Advance Account for the company;
    else "Leave Advances", made once beside the company's employee advance
    account (or under its current assets)."""
    chosen = leave_accrual.settings().leave_advance_account
    if chosen and frappe.db.get_value("Account", chosen, "company") == company:
        return chosen
    abbr = frappe.get_cached_value("Company", company, "abbr")
    name = "%s - %s" % (rules.ACCOUNT_NAME, abbr)
    if frappe.db.exists("Account", name):
        return name
    beside = frappe.get_cached_value("Company", company, "default_employee_advance_account")
    parent = frappe.db.get_value("Account", beside, "parent_account") if beside else None
    if not parent:
        found = frappe.get_all("Account", filters={"company": company, "is_group": 1, "root_type": "Asset",
                                                   "account_name": "Current Assets"}, pluck="name", limit=1)
        parent = found[0] if found else None
    if not parent:
        frappe.throw(_("Set the Leave Advance Account in Leave Management Settings."), title=_(RUN))
    account = frappe.get_doc({"doctype": "Account", "account_name": rules.ACCOUNT_NAME, "parent_account": parent,
                              "company": company, "is_group": 0})
    account.flags.ignore_permissions = True
    account.insert()
    return account.name


def recovery_component(company=None):
    """The Leave Advance Recovery deduction, made once, taking each month
    back into the leave advance account of every company it is used in."""
    name = rules.RECOVERY_COMPONENT
    if not frappe.db.exists("Salary Component", name):
        component = frappe.get_doc({"doctype": "Salary Component", "salary_component": name, "type": "Deduction",
                                    "salary_component_abbr": rules.RECOVERY_ABBR, "depends_on_payment_days": 0,
                                    "is_tax_applicable": 0,
                                    "description": "Recovery of a leave advance (Leave Advance)."})
        component.flags.ignore_permissions = True
        component.insert()
    if company:
        component = frappe.get_doc("Salary Component", name)
        if company not in {row.company for row in component.get("accounts") or []}:
            component.append("accounts", {"company": company, "account": leave_advance_account(company)})
            component.flags.ignore_permissions = True
            component.save()
    return name


# ── 6. Wiring ─────────────────────────────────────────────────────────
def setup_on_migrate():
    """after_migrate: the Leave Advance workflow."""
    from hrms_addon.hrms_addon import leave_advance_approval, workflows

    workflows.setup_on_migrate(leave_advance_approval, "Leave Advance workflow")
