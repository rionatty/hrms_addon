# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Loans Application on the site (4.4).

The rules are in loan_rules.py, without a Frappe import
(scripts/verify_loans.py). This reads and writes the site.

The Employee Loan is the one document this process needs that the site
does not already have: Frappe's lending app is not installed at Luuka, and
a staff loan recovered from the payroll is not a bank loan. Everything it
touches afterwards is Frappe HR's and ERPNext's own: each repayment becomes
an Additional Salary deduction, so the payroll run takes it without a list
kept by hand, and the money lent, repaid directly or written off is a
Journal Entry the loan drafts for Accounts.

  loan_*      the request, the approvals (set up in the desk,
              loan_approval.py), the terms Accounts settle, the employee's
              consent (LPL/HR/39) and the schedule
  journal_*   the money: paid out, repaid directly, written off
  settle_*    what a leaver's final settlement takes
  daily       step 6: a repayment due, one the payroll missed, a loan
              fully repaid
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import loan_rules as rules, pay, people

DOCTYPE = "Employee Loan"
ROW = "Loan Repayment"
SETTINGS = "Loan Settings"
DEFAULT_COMPONENT = "Loan Repayment"
JOURNAL = "Journal Entry"
SETTLEMENT = "Full and Final Statement"
PAYMENT, REPAYMENT, WRITE_OFF = "Payment", "Repayment", "Write Off"
PURPOSES = (PAYMENT, REPAYMENT, WRITE_OFF)
HR_ROLES = {"HR User", "HR Manager", "System Manager"}
# who books the money, and who may write a loan off
BOOKERS = {PAYMENT: {"Accounts User", "Accounts Manager", "System Manager"},
           REPAYMENT: {"Accounts User", "Accounts Manager", "System Manager"},
           WRITE_OFF: {"Accounts Manager", "HR Manager", "System Manager"}}
# Accounts' part of the loan: set only while it is with them
TERMS = ("approved_amount", "interest_rate", "first_repayment", "recovery_component")
# the request as asked: the employee's while it is a draft; Accounts settle
# the months
ASKED = ("loan_type", "loan_amount", "instalments")


# ── 0. Luuka's rules, as set ──────────────────────────────────────────
def settings():
    """Loan Settings merged over the rules' own numbers; read from the
    database so a stored nought stays a nought."""
    stored = dict(frappe.db.get_singles_dict(SETTINGS) or {}) if frappe.db.exists("DocType", SETTINGS) else {}
    return rules.settings_from(stored)


def settings_validate(doc, method=None):
    errors = rules.settings_errors({key: doc.get(key) for key in rules.DEFAULTS})
    if doc.get("loan_account"):
        found = frappe.db.get_value("Account", doc.loan_account, ["root_type", "is_group"], as_dict=True)
        if not found or found.root_type != "Asset" or cint(found.is_group):
            errors.append("The staff loans account is an asset account, not a group.")
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SETTINGS))


def loan_account(company):
    """Where the money lent sits: Loan Settings' account, else the
    company's employee advance account."""
    stored = dict(frappe.db.get_singles_dict(SETTINGS) or {}) if frappe.db.exists("DocType", SETTINGS) else {}
    account = stored.get("loan_account")
    if account and frappe.db.get_value("Account", account, "company") == company:
        return account
    return frappe.db.get_value("Company", company, "default_employee_advance_account") if company else None


# ── 1. The loan ───────────────────────────────────────────────────────
def loan_validate(doc, method=None):
    from hrms_addon.hrms_addon import loan_approval as approval

    s = settings()
    if doc.is_new():
        _request_defaults(doc, s)
    _fill_money(doc, s)
    _check_eligibility(doc, s)
    if doc.docstatus == 0:
        _build_schedule(doc, s)
    _check_step(doc, s)
    doc.approval_status = doc.get("workflow_state") or doc.get("approval_status") or approval.DRAFT
    doc.status = _status(doc)
    doc.outstanding = _outstanding(doc)


def _amount(doc):
    return flt(doc.get("approved_amount") or doc.get("loan_amount"))


def _status(doc):
    return rules.loan_status(doc.docstatus, _amount(doc) + flt(doc.get("total_interest")),
                             doc.get("recovered_amount"), cint(doc.get("written_off")), doc.get("workflow_state"))


def _outstanding(doc):
    """Owed only on a loan that ran: nothing on a request, a refusal, a
    cancelled loan or one written off."""
    if doc.docstatus != 1 or doc.status in (rules.REJECTED, rules.CANCELLED, rules.WRITTEN_OFF):
        return 0
    return rules.outstanding(_amount(doc) + flt(doc.get("total_interest")), doc.get("recovered_amount"))


def _fill_money(doc, s):
    if doc.get("employee"):
        doc.gross_pay = pay.monthly_gross(doc.employee)
        doc.outstanding_before = _owed_elsewhere(doc.employee, doc.name)
    doc.limit = rules.limit_for_type(doc.get("loan_type"), doc.get("gross_pay"), settings=s) or 0
    doc.total_interest = rules.interest_for(_amount(doc), doc.get("interest_rate"), doc.get("instalments"))
    doc.monthly_instalment = rules.monthly_instalment(_amount(doc), doc.get("interest_rate"), doc.get("instalments"))
    doc.recovered_amount = sum(flt(row.total) for row in doc.get("repayments") or [] if row.recovered)
    # LPL/HR/39's "EXTENT OF DEDUCTION" is the terms in words. It follows
    # the terms, so it is written again whenever they change rather than
    # frozen at whatever the request first said.
    if doc.get("monthly_instalment") and cint(doc.get("instalments")):
        doc.extent_of_deduction = _("{0} a month for {1} month(s)").format(
            frappe.utils.fmt_money(doc.monthly_instalment), cint(doc.get("instalments")))


def _owed_elsewhere(employee, exclude):
    """What this employee still owes on loans running now. A request, a
    refusal, a cancelled loan or one written off owes nothing."""
    rows = frappe.get_all(DOCTYPE, filters={"employee": employee, "docstatus": 1, "status": rules.RUNNING,
                                            "name": ["!=", exclude or ""]},
                          fields=["outstanding"])
    return flt(sum(flt(row.outstanding) for row in rows))


def _waiting_elsewhere(employee, exclude):
    """Another request of theirs already on its way through the approvals."""
    from hrms_addon.hrms_addon import loan_approval as approval

    for row in frappe.get_all(DOCTYPE, filters={"employee": employee, "docstatus": 0,
                                                "name": ["!=", exclude or ""]},
                              fields=["name", "approval_status"]):
        if approval.is_pending(row.approval_status):
            return row.name
    return None


def _check_eligibility(doc, s):
    errors = rules.eligibility_errors(_facts(doc), s)
    doc.qualifies = 0 if errors else 1
    doc.eligibility_remarks = "; ".join(errors) or None


def _facts(doc):
    return {
        "status": frappe.db.get_value("Employee", doc.employee, "status") if doc.get("employee") else None,
        "date_of_joining": doc.get("date_of_appointment"), "today": today(),
        "gross_pay": doc.get("gross_pay"), "amount": _amount(doc), "rate": doc.get("interest_rate"),
        "outstanding": doc.get("outstanding_before"),
        "waiting": _waiting_elsewhere(doc.employee, doc.name) if doc.get("employee") else None,
        "instalments": doc.get("instalments"), "purpose": doc.get("purpose"), "loan_type": doc.get("loan_type"),
        "category": (frappe.db.get_value("Department", doc.department, "custom_position_category")
                     if doc.get("department") else None),
        "fee_structure": doc.get("fee_structure"),
    }


def _terms_facts(doc, s):
    return {"amount": doc.get("loan_amount"), "approved_amount": doc.get("approved_amount"),
            "instalments": doc.get("instalments"), "first_repayment": doc.get("first_repayment"),
            "rate": doc.get("interest_rate"), "max_instalments": rules.max_instalments(doc.get("loan_type"), s),
            "paid_through": _paid_through(doc.get("employee")), "gross_pay": doc.get("gross_pay"),
            "max_share": s["max_share_of_gross"]}


def _paid_through(employee):
    """The last day the payroll has already paid this employee to."""
    if not employee:
        return None
    ends = frappe.get_all("Salary Slip", filters={"employee": employee, "docstatus": 1}, pluck="end_date",
                          order_by="end_date desc", limit=1)
    return ends[0] if ends else None


def _request_defaults(doc, s):
    """A new request: the terms are Accounts' to set, later; the rate starts
    at Luuka's."""
    doc.approved_amount, doc.first_repayment = None, None
    doc.interest_rate = s["default_rate"]


def _build_schedule(doc, s):
    """The months the loan comes back in, while it is not yet running, each
    on the payroll day: on the terms once Accounts set them, until then on
    what was asked."""
    principal = _amount(doc)
    first = _start(doc, s)
    if not (principal and first):
        doc.set("repayments", [row for row in doc.get("repayments") or [] if row.recovered])
        return
    doc.set("repayments", [])
    for month, due_p, due_i, total in rules.repayment_schedule(principal, doc.get("interest_rate"),
                                                                doc.get("instalments"), first):
        doc.append("repayments", {"payroll_date": month, "principal": due_p, "interest": due_i, "total": total})


def _start(doc, s):
    """The first repayment: the month Accounts set, on the payroll day; until
    they set it, the payroll day of the month after the request."""
    first = doc.get("first_repayment")
    return rules.on_day(first, s["payroll_day"]) if first else _first_month(doc, s)


def _first_month(doc, s):
    return rules.first_month(doc.get("posting_date") or today(), _paid_through(doc.get("employee")),
                             s["payroll_day"])


@frappe.whitelist()
def preview_schedule(doc):
    """The schedule the form shows while the request is filled in, drawn as
    saving it would draw it. Nothing is written."""
    loan = frappe.get_doc(frappe.parse_json(doc))
    if loan.doctype != DOCTYPE or loan.docstatus != 0:
        return None
    if not (frappe.has_permission(DOCTYPE, "create") or frappe.has_permission(DOCTYPE, "write")):
        frappe.throw(_("You may not draw a loan's schedule."), frappe.PermissionError)
    if any(cint(row.get("recovered")) for row in loan.get("repayments") or []):
        return None
    s = settings()
    if loan.is_new():
        _request_defaults(loan, s)
    _build_schedule(loan, s)
    amount = _amount(loan)
    return {
        "repayments": [{"payroll_date": str(getdate(row.payroll_date)), "principal": row.principal,
                        "interest": row.interest, "total": row.total} for row in loan.get("repayments") or []],
        "interest_rate": loan.get("interest_rate"),
        "total_interest": rules.interest_for(amount, loan.get("interest_rate"), loan.get("instalments")),
        "monthly_instalment": rules.monthly_instalment(amount, loan.get("interest_rate"), loan.get("instalments")),
    }


def _check_step(doc, s):
    from hrms_addon.hrms_addon import loan_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if before and doc.docstatus == 0 and old_state != approval.PENDING_ACCOUNTS and _terms_changed(doc, before):
        frappe.throw(_("The terms (the amount lent, the rate, the first repayment and the deduction) are "
                       "set by Accounts, while the loan is with them."), title=_(DOCTYPE))
    if before and doc.docstatus == 0 and _asked_changed(doc, before, old_state):
        frappe.throw(_("The request (the amount, the kind of loan, the months) is changed only while it is a "
                       "draft. Accounts settle the months."), title=_(DOCTYPE))
    if doc.docstatus == 0 and doc.get("first_repayment"):
        # every repayment falls on the payroll day
        doc.first_repayment = rules.on_day(doc.first_repayment, s["payroll_day"])
    _fill_consent(doc)
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if old_state in (None, approval.DRAFT) and approval.is_pending(new_state):
            errors = rules.eligibility_errors(_facts(doc), s) + errors
        if new_state == approval.PENDING_CONSENT or (new_state == approval.RUNNING
                                                     and old_state != approval.PENDING_CONSENT):
            errors += rules.terms_errors(_terms_facts(doc, s))
        if new_state == approval.RUNNING:
            errors += rules.run_errors({
                "liability": doc.get("liability"), "amount": doc.get("approved_amount"),
                "instalments": doc.get("instalments"), "effective_from": doc.get("effective_from"),
                "consent": doc.get("consent"), "paid": doc.get("disbursed_on")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(DOCTYPE))
        if new_state not in (approval.DRAFT, approval.REJECTED):
            # a refusal keeps its reason: a desk set up in the Workflow gives
            # it here
            doc.return_remarks = None
        if new_state == approval.DRAFT:
            # the terms may change on the way back: the consent is given again
            doc.consent, doc.consent_by, doc.consent_on = 0, None, None
        if new_state == approval.PENDING_ACCOUNTS and not flt(doc.get("approved_amount")):
            doc.approved_amount = doc.get("loan_amount")  # where Accounts start from
        if new_state == approval.PENDING_ACCOUNTS and not doc.get("first_repayment"):
            doc.first_repayment = _first_month(doc, s)
        if new_state == approval.RUNNING:
            doc.witnessed_by = frappe.session.user
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    ticked = cint(doc.get("consent")) and not (before and cint(before.get("consent")))
    if ticked:
        doc.consent_by, doc.consent_on = frappe.session.user, today()
        _tell_consent(doc)
    elif not cint(doc.get("consent")):
        doc.consent_by, doc.consent_on = None, None
    if old_state != new_state:
        if new_state == approval.PENDING_CONSENT:
            _tell_terms(doc)
        if approval.is_pending(new_state):
            _tell_waiting(doc, new_state)
        if new_state in (approval.DRAFT, approval.REJECTED) and old_state not in (None, approval.DRAFT):
            _tell_back(doc, new_state, old_state)


def _fill_consent(doc):
    """The consent follows the terms: what the deduction is for, and the day
    it starts, the first repayment. A liability written by hand is kept."""
    if flt(doc.get("approved_amount")):
        written = (doc.get("liability") or "").strip()
        if not written or written.startswith(_("Staff loan of ")):
            doc.liability = _("Staff loan of {0}").format(frappe.utils.fmt_money(doc.approved_amount))
    if doc.get("first_repayment"):
        doc.effective_from = doc.first_repayment


def _terms_changed(doc, before):
    for field in TERMS:
        now, then = doc.get(field), before.get(field)
        if field in ("approved_amount", "interest_rate"):
            if flt(now) != flt(then):
                return True
        elif field == "first_repayment":
            if (str(getdate(now)) if now else "") != (str(getdate(then)) if then else ""):
                return True
        elif (now or "") != (then or ""):
            return True
    return False


def _asked_changed(doc, before, old_state):
    """The request as asked changed after it left Draft; the months only
    Accounts change, at their desk."""
    from hrms_addon.hrms_addon import loan_approval as approval

    if old_state in (None, approval.DRAFT):
        return False
    for field in ASKED:
        if field == "instalments":
            if old_state != approval.PENDING_ACCOUNTS and cint(doc.get(field)) != cint(before.get(field)):
                return True
        elif field == "loan_amount":
            if flt(doc.get(field)) != flt(before.get(field)):
                return True
        elif (doc.get(field) or "") != (before.get(field) or ""):
            return True
    return False


def _roles_acting(state):
    """Who acts on a desk, as the Workflow set up in the desk says."""
    from hrms_addon.hrms_addon import loan_approval as approval

    roles = frappe.get_all("Workflow Transition", filters={"parent": approval.WORKFLOW_NAME,
                                                           "parenttype": "Workflow", "state": state},
                           pluck="allowed")
    roles = [role for role in dict.fromkeys(roles) if role]
    return roles or [role for role in (approval.ROLE_WAITING.get(state),) if role]


def _employee_user(doc):
    return frappe.db.get_value("Employee", doc.employee, "user_id") if doc.get("employee") else None


def _tell_waiting(doc, state):
    from hrms_addon.hrms_addon import loan_approval as approval

    if state == approval.PENDING_CONSENT:
        users = [user for user in (_employee_user(doc),) if user]
    else:
        users = []
        for role in _roles_acting(state):
            users += people.people_for(role, doc.get("branch"), doc.get("department"))
    users = list(dict.fromkeys(users))
    if not users:
        return
    message = _("Loan request from {0}: {1}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("loan_amount")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def _tell_back(doc, state, old_state):
    """The chart's "Approved? No": the employee is told, and why."""
    from hrms_addon.hrms_addon import loan_approval as approval

    user = _employee_user(doc)
    if not user:
        return
    field = approval.REMARK_FIELDS.get(old_state, ("return_remarks", None))[0]
    reason = (doc.get("return_remarks") if state == approval.DRAFT else doc.get(field) or doc.get("return_remarks"))
    message = (_("Your loan request is returned: {0}") if state == approval.DRAFT
               else _("Your loan request is refused: {0}")).format(reason or "")
    people.notify([user], doc.doctype, doc.name, message.strip())


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


def _tell_consent(doc):
    """Test case 4: the HR Officer and the accountant are told the employee
    consented to the terms."""
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    users += people.people_for("Accounts User", doc.get("branch"), doc.get("department"))
    if not users:
        return
    people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                  _("{0} consented to the loan terms. Record the payment to pay it out.").format(
                      doc.get("employee_name") or doc.employee))


def loan_on_submit(doc, method=None):
    """Running: the schedule becomes a monthly deduction on the payroll. A
    refusal is submitted too, and takes nothing."""
    if doc.get("status") != rules.RUNNING:
        return
    _make_deductions(doc)
    users = [user for user in (_employee_user(doc),) if user]
    users += people.hr_officers(doc.get("branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                      _("{0}'s loan is running: {1} a month from {2}.").format(
                          doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.monthly_instalment),
                          frappe.utils.format_date(doc.get("first_repayment"))))


def loan_on_cancel(doc, method=None):
    """Only a loan nothing has been taken back on is cancelled; one part
    repaid is repaid or written off instead."""
    taken = [row for row in doc.get("repayments") or [] if row.recovered]
    if taken:
        frappe.throw(_("{0} month(s) of this loan are already recovered. Record the rest as repaid, or "
                       "write it off, instead of cancelling.").format(len(taken)), title=_(DOCTYPE))
    entry = doc.get("disbursement_entry")
    if entry and frappe.db.get_value(JOURNAL, entry, "docstatus") == 1:
        frappe.throw(_("The payment {0} is booked. Cancel it first.").format(entry), title=_(DOCTYPE))
    _cancel_untaken(doc)
    doc.approval_status = "Cancelled"
    doc.status = rules.CANCELLED


def _make_deductions(doc, rows=None):
    component = doc.get("recovery_component") or _component(doc.get("company"))
    if not component:
        return
    for row in rows if rows is not None else doc.get("repayments") or []:
        if row.get("additional_salary") or row.get("recovered"):
            continue
        deduction = frappe.get_doc({
            "doctype": "Additional Salary", "employee": doc.employee, "company": doc.company,
            "salary_component": component, "amount": flt(row.get("total")), "payroll_date": row.get("payroll_date"),
            "overwrite_salary_structure_amount": 0, "ref_doctype": doc.doctype, "ref_docname": doc.name,
        })
        deduction.flags.ignore_permissions = True
        deduction.insert()
        deduction.submit()
        frappe.db.set_value(ROW, row.get("name"), "additional_salary", deduction.name, update_modified=False)


def _taken(additional_salary):
    """Whether a submitted Salary Slip has taken this deduction."""
    return bool(frappe.get_all("Salary Detail", filters={"parenttype": "Salary Slip", "docstatus": 1,
                                                         "additional_salary": additional_salary}, limit=1))


def _cancel_untaken(doc):
    """The deductions still to come, cancelled; a month a slip has taken is
    left as it is."""
    cancelled = 0
    for row in doc.get("repayments") or []:
        name = row.get("additional_salary")
        if row.get("recovered") or not name or _taken(name):
            continue
        if frappe.db.get_value("Additional Salary", name, "docstatus") == 1:
            deduction = frappe.get_doc("Additional Salary", name)
            deduction.flags.ignore_permissions = True
            deduction.cancel()
            cancelled += 1
        frappe.db.set_value(ROW, row.name, "additional_salary", None, update_modified=False)
    return cancelled


def _component(company=None):
    if not frappe.db.exists("Salary Component", DEFAULT_COMPONENT):
        try:
            doc = frappe.get_doc({"doctype": "Salary Component", "salary_component": DEFAULT_COMPONENT,
                                  "type": "Deduction", "salary_component_abbr": "LR",
                                  "description": "Recovery of a staff loan (LPL/HR/39)."})
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="HRMS Addon: loan repayment component")
            return None
    ensure_loan_account(company)
    return DEFAULT_COMPONENT


def ensure_loan_account(company=None):
    """The Loan Repayment component's account for each company, so the
    payroll can book what it takes back: Frappe HR's Payroll Entry stops
    on a component with none. One already set is left as it is."""
    if not frappe.db.exists("Salary Component", DEFAULT_COMPONENT):
        return []
    component = frappe.get_doc("Salary Component", DEFAULT_COMPONENT)
    have = {row.company for row in component.get("accounts") or []}
    added = []
    for name in [company] if company else frappe.get_all("Company", pluck="name"):
        account = loan_account(name) if name else None
        if account and name not in have:
            component.append("accounts", {"company": name, "account": account})
            added.append(name)
    if added:
        component.flags.ignore_permissions = True
        component.save()
    return added


# ── 2. The money: paid out, repaid directly, written off ──────────────
@frappe.whitelist(methods=["POST"])
def make_journal(loan, purpose):
    """A Journal Entry drafted for Accounts: the loan paid out, a repayment
    made other than through the payroll, or the rest written off. The loan
    follows when it is submitted (journal_on_submit)."""
    from hrms_addon.hrms_addon import loan_approval as approval

    if purpose not in PURPOSES:
        frappe.throw(_("Choose what the entry is for."))
    if not BOOKERS[purpose] & set(frappe.get_roles()):
        frappe.throw(_("You may not book this."), frappe.PermissionError)
    doc = frappe.get_doc(DOCTYPE, loan)
    doc.check_permission("read")
    account = loan_account(doc.company)
    if not account:
        frappe.throw(_("Set the staff loans account in Loan Settings, or the company's employee advance account."))
    if purpose == PAYMENT:
        if doc.docstatus != 0 or doc.get("workflow_state") != approval.PENDING_CONSENT or not cint(doc.consent):
            frappe.throw(_("A loan is paid out once the employee has consented to its terms."))
        if doc.get("disbursement_entry"):
            frappe.throw(_("The payment is already recorded: {0}.").format(doc.disbursement_entry))
        amount = flt(doc.approved_amount)
        other = frappe.get_cached_value("Company", doc.company, "default_bank_account")
    else:
        if doc.docstatus != 1 or doc.status != rules.RUNNING:
            frappe.throw(_("Only a running loan is repaid or written off."))
        amount = flt(doc.outstanding)
        other = frappe.get_cached_value("Company", doc.company,
                                        "default_bank_account" if purpose == REPAYMENT else "write_off_account")
    je = frappe.new_doc(JOURNAL)
    je.update({
        "voucher_type": "Journal Entry" if purpose == WRITE_OFF else "Bank Entry", "company": doc.company,
        "posting_date": today(), "custom_employee_loan": doc.name, "custom_loan_purpose": purpose,
        "user_remark": _("{0}: {1}, {2}").format(_(purpose), doc.name, doc.get("employee_name") or doc.employee),
    })
    loan_row = {"account": account, "debit_in_account_currency": amount if purpose == PAYMENT else 0,
                "credit_in_account_currency": 0 if purpose == PAYMENT else amount}
    if frappe.get_cached_value("Account", account, "account_type") in ("Receivable", "Payable"):
        loan_row.update(party_type="Employee", party=doc.employee)
    other_row = {"account": other, "debit_in_account_currency": 0 if purpose == PAYMENT else amount,
                 "credit_in_account_currency": amount if purpose == PAYMENT else 0}
    for row in (loan_row, other_row) if purpose == PAYMENT else (other_row, loan_row):
        je.append("accounts", row)
    return je.as_dict()


def _on_loan_account(je, loan):
    """What the entry moves on the loan's own account: debited when paid
    out, credited when repaid or written off."""
    account = loan_account(je.company)
    debit = sum(flt(row.get("debit_in_account_currency")) for row in je.get("accounts") or [] if row.account == account)
    credit = sum(flt(row.get("credit_in_account_currency")) for row in je.get("accounts") or []
                 if row.account == account)
    return round(debit - credit, 2) if je.get("custom_loan_purpose") == PAYMENT else round(credit - debit, 2)


def journal_on_submit(doc, method=None):
    loan, purpose = doc.get("custom_employee_loan"), doc.get("custom_loan_purpose")
    if not (loan and purpose in PURPOSES):
        return
    amount = _on_loan_account(doc, loan)
    if amount <= 0:
        frappe.throw(_("The entry does not move the staff loans account {0}.").format(loan_account(doc.company)),
                     title=_(DOCTYPE))
    target = frappe.get_doc(DOCTYPE, loan)
    if purpose == PAYMENT:
        if round(amount, 2) != round(flt(target.approved_amount), 2):
            frappe.throw(_("The payment is {0}; the loan is {1}.").format(
                frappe.utils.fmt_money(amount), frappe.utils.fmt_money(target.approved_amount)), title=_(DOCTYPE))
        frappe.db.set_value(DOCTYPE, loan, {"disbursed_on": doc.posting_date, "disbursement_entry": doc.name,
                                            "disbursement_reference": doc.get("cheque_no") or doc.name},
                            update_modified=False)
        users = people.people_for("Payroll Officer", target.get("branch"), target.get("department"))
        users += people.hr_officers(target.get("branch"), target.get("department"))
        if users:
            people.notify(list(dict.fromkeys(users)), DOCTYPE, loan,
                          _("{0}'s loan is paid out. Run it to start the deductions.").format(
                              target.get("employee_name") or target.employee))
        return
    if target.docstatus != 1 or target.status != rules.RUNNING:
        frappe.throw(_("{0} is not running.").format(loan), title=_(DOCTYPE))
    if amount > flt(target.outstanding):
        frappe.throw(_("{0} is more than the {1} still owed.").format(
            frappe.utils.fmt_money(amount), frappe.utils.fmt_money(target.outstanding)), title=_(DOCTYPE))
    if purpose == REPAYMENT:
        apply_payment(target, amount, doc.posting_date, JOURNAL, doc.name, rules.PAID_DIRECTLY)
    else:
        if round(amount, 2) != round(flt(target.outstanding), 2):
            frappe.throw(_("A write-off is the whole of what is still owed: {0}.").format(
                frappe.utils.fmt_money(target.outstanding)), title=_(DOCTYPE))
        _write_off(target, amount, doc)


def journal_on_cancel(doc, method=None):
    loan, purpose = doc.get("custom_employee_loan"), doc.get("custom_loan_purpose")
    if not (loan and purpose in PURPOSES) or not frappe.db.exists(DOCTYPE, loan):
        return
    target = frappe.get_doc(DOCTYPE, loan)
    if purpose == PAYMENT:
        if target.docstatus == 1:
            frappe.throw(_("{0} is running on this payment. Cancel the loan first.").format(loan), title=_(DOCTYPE))
        frappe.db.set_value(DOCTYPE, loan, {"disbursed_on": None, "disbursement_entry": None,
                                            "disbursement_reference": None}, update_modified=False)
    elif purpose == REPAYMENT:
        remove_payment(target, JOURNAL, doc.name)
    elif target.get("write_off_entry") == doc.name:
        _undo_write_off(target)


def apply_payment(doc, amount, day, reference_type, reference_name, label):
    """A payment made other than through the payroll, marked on the loan:
    the months still to come are drawn again over what is left, as many as
    there were, or the loan is repaid."""
    rows = [row.as_dict() for row in doc.repayments]
    principal_left, interest_left = rules.left(_amount(doc), flt(doc.total_interest), rows)
    part_p, part_i = rules.split(amount, principal_left, interest_left)
    to_come = [row for row in doc.repayments if not row.recovered]
    first = min((getdate(row.payroll_date) for row in to_come), default=None)
    start = rules.resume_from(rules.add_months(first, -1) if first else getdate(day), today(), _day(doc))
    _cancel_untaken(doc)
    for row in to_come:
        frappe.db.delete(ROW, {"name": row.name})
    _insert_row(doc, {"payroll_date": getdate(day), "principal": part_p, "interest": part_i,
                      "total": round(part_p + part_i, 2), "recovered": 1, "reference_type": reference_type,
                      "reference_name": reference_name, "remarks": label, "months_left": len(to_come)})
    _draw_again(doc.name, round(principal_left - part_p, 2), round(interest_left - part_i, 2), len(to_come), start)


def remove_payment(doc, reference_type, reference_name):
    """A payment taken back off (its entry, or the final settlement, was
    cancelled): what is left is drawn again over the months there were."""
    rows = [row for row in doc.repayments if row.get("reference_type") == reference_type
            and row.get("reference_name") == reference_name]
    if not rows:
        return
    months = max(cint(rows[0].get("months_left")), 1)
    to_come = [row for row in doc.repayments if not row.recovered]
    _cancel_untaken(doc)
    for row in rows + to_come:
        frappe.db.delete(ROW, {"name": row.name})
    doc = frappe.get_doc(DOCTYPE, doc.name)
    principal_left, interest_left = rules.left(_amount(doc), flt(doc.total_interest),
                                               [row.as_dict() for row in doc.repayments])
    _draw_again(doc.name, principal_left, interest_left, months, _resume(doc))


def _resume(doc):
    """Where a schedule drawn again picks up: after the last month the
    payroll took, on the loan's own day of the month, never a month gone."""
    last = max((getdate(row.payroll_date) for row in doc.repayments
                if row.recovered and not row.get("reference_name")), default=None)
    return rules.resume_from(last or rules.add_months(doc.get("first_repayment"), -1), today(), _day(doc))


def _day(doc):
    """The loan's own day of the month: its first repayment's."""
    return getdate(doc.first_repayment).day if doc.get("first_repayment") else None


def _draw_again(name, principal, interest, months, start):
    doc = frappe.get_doc(DOCTYPE, name)
    new_rows = []
    if round(principal + interest, 2) > 0:
        for month, due_p, due_i, total in rules.spread(principal, interest, max(months, 1), start, _day(doc)):
            new_rows.append(_insert_row(doc, {"payroll_date": month, "principal": due_p, "interest": due_i,
                                              "total": total}))
    _renumber(name)
    doc = frappe.get_doc(DOCTYPE, name)
    _make_deductions(doc, [row for row in doc.repayments if row.name in {r.name for r in new_rows}])
    refresh_recovered(name)


def _insert_row(doc, values):
    row = frappe.get_doc(dict(values, doctype=ROW, parent=doc.name, parenttype=DOCTYPE, parentfield="repayments",
                              idx=len(frappe.get_all(ROW, filters={"parent": doc.name, "parenttype": DOCTYPE})) + 1))
    row.db_insert()
    return row


def _renumber(name):
    """The schedule in date order, numbered 1, 2, 3...: a row put in the
    middle would otherwise share its number with the one it follows."""
    rows = frappe.get_all(ROW, filters={"parent": name, "parenttype": DOCTYPE},
                          fields=["name", "payroll_date", "recovered", "idx"])
    rows.sort(key=lambda row: (str(row.payroll_date), -cint(row.recovered), cint(row.idx)))
    for number, row in enumerate(rows, 1):
        if cint(row.idx) != number:
            frappe.db.set_value(ROW, row.name, "idx", number, update_modified=False)


def _write_off(doc, amount, je):
    to_come = [row for row in doc.repayments if not row.recovered]
    _cancel_untaken(doc)
    for row in to_come:
        frappe.db.delete(ROW, {"name": row.name})
    frappe.db.set_value(DOCTYPE, doc.name, {"written_off": 1, "written_off_amount": amount,
                                            "written_off_on": je.posting_date, "write_off_entry": je.name,
                                            "written_off_months": len(to_come)}, update_modified=False)
    refresh_recovered(doc.name)


def _undo_write_off(doc):
    months = max(cint(doc.get("written_off_months")), 1)
    frappe.db.set_value(DOCTYPE, doc.name, {"written_off": 0, "written_off_amount": 0, "written_off_on": None,
                                            "write_off_entry": None, "written_off_months": 0},
                        update_modified=False)
    doc = frappe.get_doc(DOCTYPE, doc.name)
    principal_left, interest_left = rules.left(_amount(doc), flt(doc.total_interest),
                                               [row.as_dict() for row in doc.repayments])
    _draw_again(doc.name, principal_left, interest_left, months, _resume(doc))


# ── 3. A leaver's final settlement ────────────────────────────────────
def settle_on_exit(settlement):
    """What the final settlement takes for loans (its Loans Outstanding
    line) is marked paid on the employee's running loans, the oldest first,
    and their deductions still to come are cancelled."""
    from hrms_addon.hrms_addon import settlement_rules

    taken = round(sum(flt(row.amount) for row in settlement.get("receivables") or []
                      if row.get("component") == settlement_rules.LOANS), 2)
    for name in frappe.get_all(DOCTYPE, filters={"employee": settlement.employee, "docstatus": 1,
                                                 "status": rules.RUNNING},
                               pluck="name", order_by="posting_date asc"):
        if taken <= 0:
            break
        doc = frappe.get_doc(DOCTYPE, name)
        part = min(taken, flt(doc.outstanding))
        if part > 0:
            apply_payment(doc, part, settlement.get("transaction_date") or today(), SETTLEMENT, settlement.name,
                          rules.FINAL_SETTLEMENT)
            taken = round(taken - part, 2)


def unsettle_on_exit(settlement):
    for name in dict.fromkeys(frappe.get_all(ROW, filters={"parenttype": DOCTYPE, "reference_type": SETTLEMENT,
                                                           "reference_name": settlement.name}, pluck="parent")):
        remove_payment(frappe.get_doc(DOCTYPE, name), SETTLEMENT, settlement.name)


# ── 4. Step 6: the monitoring ─────────────────────────────────────────
def daily():
    _tell_due()
    _tell_missed()
    _close_repaid()


def _running(name):
    return frappe.db.get_value(DOCTYPE, name, ["employee", "employee_name", "branch", "department", "docstatus",
                                               "status", "outstanding"], as_dict=True)


def _running_loans():
    """The loans the payroll is taking back now. Only their months are
    watched: a request has a schedule drawn too."""
    return frappe.get_all(DOCTYPE, filters={"docstatus": 1, "status": rules.RUNNING}, pluck="name")


def _tell_due():
    """A repayment falling due in the next week, told to the HR Officer and
    the employee."""
    running = _running_loans()
    if not running:
        return
    rows = frappe.get_all(ROW, filters={"parenttype": DOCTYPE, "parent": ["in", running], "recovered": ["!=", 1],
                                        "payroll_date": ["between", [today(), add_days(today(), 7)]]},
                          fields=["name", "parent", "payroll_date", "total"], limit=500)
    for row in rows:
        loan = _running(row.parent)
        if not loan or loan.docstatus != 1 or loan.status != rules.RUNNING:
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
                          frappe.utils.format_date(row.payroll_date), frappe.utils.fmt_money(loan.outstanding)))
    frappe.db.commit()


def _tell_missed():
    """A month the payroll did not take, some days after it: the HR Officer
    and the Payroll Officer are told once."""
    grace = settings()["missed_grace_days"]
    running = _running_loans()
    if not running:
        return
    rows = frappe.get_all(ROW, filters={"parenttype": DOCTYPE, "parent": ["in", running], "recovered": ["!=", 1],
                                        "missed_told": ["!=", 1], "payroll_date": ["<", add_days(today(), -grace)]},
                          fields=["name", "parent", "payroll_date", "total", "recovered", "missed_told"], limit=500)
    for row in rules.missed([dict(row) for row in rows], today(), grace):
        loan = _running(row["parent"])
        if not loan or loan.docstatus != 1 or loan.status != rules.RUNNING:
            continue
        users = list(people.hr_officers(loan.branch, loan.department))
        users += people.people_for("Payroll Officer", loan.branch, loan.department)
        if users:
            people.notify(list(dict.fromkeys(users)), DOCTYPE, row["parent"],
                          _("{0}'s loan repayment of {1} for {2} was not taken by the payroll. {3} still owed.").format(
                              loan.employee_name or loan.employee, frappe.utils.fmt_money(row["total"]),
                              frappe.utils.format_date(row["payroll_date"]), frappe.utils.fmt_money(loan.outstanding)))
        frappe.db.set_value(ROW, row["name"], "missed_told", 1, update_modified=False)
    frappe.db.commit()


def _close_repaid():
    """A loan whose last instalment has been taken is Repaid, and the
    employee and the HR Officer are told."""
    rows = frappe.get_all(DOCTYPE, filters={"docstatus": 1, "status": rules.RUNNING, "outstanding": ["<=", 0]},
                          fields=["name", "employee", "employee_name", "branch", "department"], limit=200)
    for row in rows:
        frappe.db.set_value(DOCTYPE, row.name, "status", rules.REPAID, update_modified=False)
        _tell_repaid(row)
    frappe.db.commit()


def _tell_repaid(loan):
    users = list(people.hr_officers(loan.branch, loan.department))
    user = frappe.db.get_value("Employee", loan.employee, "user_id")
    if user:
        users.append(user)
    if users:
        people.notify(list(dict.fromkeys(users)), DOCTYPE, loan.name,
                      _("{0}'s loan is fully repaid.").format(loan.employee_name or loan.employee))


def refresh_recovered(name):
    """The recovered and outstanding amounts, from the months marked
    recovered — by the Salary Slip that took them (recoveries.py), a
    payment made directly or the final settlement. A loan whose last month
    is taken is Repaid, one whose slip was cancelled is Running again, and
    one written off stays so."""
    doc = frappe.get_doc(DOCTYPE, name)
    if doc.docstatus != 1:
        return
    was = doc.status
    recovered = sum(flt(child.total) for child in doc.repayments if child.recovered)
    doc.recovered_amount = recovered
    doc.status = _status(doc)
    doc.db_set("recovered_amount", recovered)
    doc.db_set("status", doc.status)
    doc.db_set("outstanding", _outstanding(doc))
    if was != rules.REPAID and doc.status == rules.REPAID:
        _tell_repaid(doc)


def close_rejected(doc):
    """A refusal made before the fix: nothing owed, no deductions."""
    _cancel_untaken(doc)
    doc.db_set("status", rules.REJECTED)
    doc.db_set("outstanding", 0)


# ── 5. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the loan's workflow (made once, then set up in the
    desk) and the repayment component's account."""
    from hrms_addon.hrms_addon import loan_approval, workflows

    workflows.setup_on_migrate(loan_approval, "Employee Loan workflow")
    try:
        ensure_loan_account()
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="HRMS Addon: loan repayment account")
