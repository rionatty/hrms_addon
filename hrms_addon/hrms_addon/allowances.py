# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Allowance Request on the site (4.3).

The rules are in allowance_rules.py and allowance_approval.py, without a
Frappe import (scripts/verify_allowances.py). This reads and writes the
site.

  request_validate   on every save: the lines costed (the per-diem scale's
                     rates for the grade and the destination, grades.py,
                     else the type's standard rate), the totals and the
                     advance, the chart's "Qualified?", the four signatures
                     and who is told
  request_on_submit  Paid (steps 3 and 4): one journal entry for what
                     Accounts pay, an Additional Salary for each line the
                     payroll pays, and the HR Officer told
  request_on_cancel  both undone
  type_validate      an Allowance Type's own checks
  daily              an approved request waiting on Accounts
  seed_allowance_types  the allowances the minutes name, made once

The allowance was once kept on Frappe HR's Travel Request, which is a
travel request again: patches/v1_0/allowance_request.py moved the
allowances made there onto Allowance Requests.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import allowance_approval as approval, allowance_rules as rules, people

DOCTYPE = "Allowance Request"
TYPE = "Allowance Type"
TYPE_ACCOUNT = "Allowance Type Account"
ADVANCE = "Employee Advance"
TYPE_FIELDS = ["name", "needs_trip", "per_diem_column", "needs_acting_for", "paid_through", "salary_component",
               "standard_rate", "disabled"]
# set on a request copied from a Travel Request: it was signed and paid there
MOVED = "moved_from_travel_request"


# ── 1. The request, on every save ─────────────────────────────────────
def request_validate(doc, method=None):
    from hrms_addon.hrms_addon import grades

    types = _types(doc)
    _fill_lines(doc, types)
    scale_currency = grades.apply_scale(doc, types)
    doc.currency = scale_currency or doc.get("company_currency") or _company_currency(doc.get("company"))
    _fill_exchange_rate(doc)
    _cost_lines(doc, types)
    advance = _fill_advance(doc)
    figures = _fill_totals(doc)
    _fill_cost_center(doc)
    _check_eligibility(doc, types, advance)
    if not doc.flags.get(MOVED):
        _check_step(doc, figures)
    doc.status = rules.status_for(doc.docstatus, doc.get("workflow_state"))


def _types(doc):
    """{Allowance Type: what it says} for the types on the request."""
    names = sorted({row.allowance_type for row in doc.get("lines") or [] if row.get("allowance_type")})
    if not names:
        return {}
    return {row.name: row for row in frappe.get_all(TYPE, filters={"name": ["in", names]}, fields=TYPE_FIELDS)}


def _fill_lines(doc, types):
    """What each line's type says about it, and so what the request asks
    for: the trip, and whom the employee stands in for."""
    lines = doc.get("lines") or []
    for row in lines:
        kind = types.get(row.get("allowance_type")) or {}
        row.paid_through = kind.get("paid_through") or rules.ACCOUNTS
        row.needs_trip = cint(kind.get("needs_trip"))
        row.needs_acting_for = cint(kind.get("needs_acting_for"))
    doc.needs_trip = 1 if any(row.needs_trip for row in lines) else 0
    doc.needs_acting_for = 1 if any(row.needs_acting_for for row in lines) else 0
    doc.trip_days = rules.trip_days(doc.get("start_date"), doc.get("end_date")) if doc.needs_trip else 0


def _cost_lines(doc, types):
    """Each line is its days times its rate. A line paid by the day off the
    scale takes the trip's days when none are given; a line with no rate
    takes its type's standard rate."""
    for row in doc.get("lines") or []:
        kind = types.get(row.get("allowance_type")) or {}
        if kind.get("per_diem_column") and not flt(row.get("days")) and doc.get("trip_days"):
            row.days = doc.trip_days
        if not flt(row.get("rate")) and flt(kind.get("standard_rate")):
            row.rate = flt(kind.get("standard_rate"))
        row.amount = rules.line_amount(row.get("days"), row.get("rate"))


def _fill_advance(doc):
    """The advance taken, and what it still has to settle: taken off in
    full by default, as LPL.HR.31's "Less advance"."""
    if not doc.get("advance"):
        return None
    found = frappe.db.get_value(ADVANCE, doc.advance, ["employee", "docstatus", "paid_amount", "claimed_amount",
                                                       "return_amount", "advance_account"], as_dict=True)
    if not found:
        return None
    found.left = rules.advance_left(found.paid_amount, found.claimed_amount, found.return_amount)
    if doc.docstatus == 0 and not flt(doc.get("less_advance")) and found.left > 0:
        doc.less_advance = found.left
    return found


def _fill_totals(doc):
    figures = rules.totals([{"amount": row.get("amount"), "paid_through": row.get("paid_through")}
                            for row in doc.get("lines") or []], doc.get("less_advance"))
    doc.total = figures["total"]
    doc.through_payroll = figures["through_payroll"]
    doc.balance_due = figures["balance"]
    return figures


def _fill_cost_center(doc):
    """Charged where the employee's pay is, unless Accounts say otherwise."""
    if doc.get("cost_center") or not doc.get("employee"):
        return
    if frappe.get_meta("Employee").has_field("payroll_cost_center"):
        doc.cost_center = frappe.db.get_value("Employee", doc.employee, "payroll_cost_center")


def _fill_exchange_rate(doc):
    """A request in another currency is paid at the day's rate unless
    Accounts give one."""
    if not _foreign(doc):
        doc.exchange_rate = 1
        return
    if flt(doc.get("exchange_rate")) > 0 and flt(doc.get("exchange_rate")) != 1:
        return
    try:
        from erpnext.setup.utils import get_exchange_rate

        doc.exchange_rate = flt(get_exchange_rate(doc.currency, _home(doc), doc.get("paid_on") or today())) or 0
    except Exception:
        doc.exchange_rate = 0


def _check_eligibility(doc, types, advance):
    """The chart's "Qualified?", written on the form rather than thrown, so
    the employee sees what is missing; the workflow moves nothing that does
    not qualify."""
    errors = rules.eligibility_errors(_facts(doc, types, advance))
    doc.qualifies = 0 if errors else 1
    doc.eligibility_remarks = "; ".join(errors) or None


def _facts(doc, types, advance=None):
    return {
        "status": frappe.db.get_value("Employee", doc.employee, "status") if doc.get("employee") else None,
        "employee": doc.get("employee"), "purpose": doc.get("purpose"),
        "lines": [{"allowance_type": row.get("allowance_type"), "days": row.get("days"), "amount": row.get("amount"),
                   "needs_trip": row.get("needs_trip"), "needs_acting_for": row.get("needs_acting_for"),
                   "paid_through": row.get("paid_through"),
                   "salary_component": (types.get(row.get("allowance_type")) or {}).get("salary_component"),
                   "disabled": (types.get(row.get("allowance_type")) or {}).get("disabled")}
                  for row in doc.get("lines") or []],
        "start_date": doc.get("start_date"), "end_date": doc.get("end_date"),
        "acting_for": doc.get("acting_for"), "acting_from": doc.get("acting_from"), "acting_to": doc.get("acting_to"),
        "less_advance": doc.get("less_advance"), "advance": doc.get("advance"),
        "advance_employee": advance.employee if advance else None,
        "advance_left": advance.left if advance else None,
    }


def _check_step(doc, figures):
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"), "qualifies": doc.get("qualifies"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if old_state == approval.PENDING_ACCOUNTS and new_state == approval.PAID:
            errors += rules.payment_errors(_payment_facts(doc, figures))
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(DOCTYPE))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)
    if old_state in (None, approval.DRAFT) and new_state == approval.PENDING_SUPERVISOR:
        _tell_hr_it_was_raised(doc)


def _payment_facts(doc, figures):
    home = _home(doc)
    account = frappe.db.get_value("Account", doc.payment_account, ["company", "account_type", "is_group",
                                                                    "account_currency"],
                                  as_dict=True) if doc.get("payment_account") else None
    return {
        "balance": figures["balance"], "through_accounts": figures["through_accounts"],
        "payment_account": doc.get("payment_account"), "payment_method": doc.get("payment_method"),
        "reference_no": doc.get("reference_no"), "reference_date": doc.get("reference_date"),
        "paid_on": doc.get("paid_on"),
        "no_account": list(dict.fromkeys(row.allowance_type for row in doc.get("lines") or []
                                         if row.get("paid_through") != rules.PAYROLL
                                         and not expense_account(row.allowance_type, doc.company))),
        "foreign": _foreign(doc), "exchange_rate": doc.get("exchange_rate"),
        "account_ok": None if not account else (account.company == doc.company and not account.is_group
                                                and account.account_type in ("Bank", "Cash")),
        "account_currency_ok": None if not account else (account.account_currency or home) == home,
    }


def expense_account(allowance_type, company):
    """The account an allowance is charged to, for the company."""
    return frappe.db.get_value(TYPE_ACCOUNT, {"parent": allowance_type, "parenttype": TYPE, "company": company},
                               "account")


def _tell_hr_it_was_raised(doc):
    """Step 1 of the chart: the HR Officer is told the request exists.
    Told, not asked: their own turn comes at Pending HR Officer."""
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if users:
        people.notify(list(users), doc.doctype, doc.name, _(
            "{0} has asked for an allowance of {1}. It is with their supervisor first.").format(
            doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("total"), currency=doc.currency)))


def _tell(doc, state):
    users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"), doc.get("department"))
    message = _("Allowance request from {0}: {1}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("total"), currency=doc.currency))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message, date=doc.get("start_date"))


# ── 2. Paid, and cancelled ────────────────────────────────────────────
def request_on_submit(doc, method=None):
    """Paid (steps 3 and 4): one journal entry for what Accounts pay, an
    Additional Salary for each line the payroll pays, and the HR Officer
    told. A rejected request is submitted too, and pays nothing."""
    status = rules.status_for(doc.docstatus, doc.get("workflow_state"))
    if doc.get("workflow_state") != approval.PAID or doc.flags.get(MOVED):
        doc.db_set("status", status, update_modified=False)
        return
    entry, bank = _journal_entry(doc)
    _payroll_additions(doc)
    doc.db_set({"status": status, "journal_entry": entry.name if entry else None, "paid_amount": bank},
               update_modified=False)
    _tell_paid(doc)


def _journal_entry(doc):
    """What Accounts pay, in one entry: each allowance charged to its
    expense account, the advance taken settled, and the rest paid from the
    bank (or, when the advance was more, the refund received into it).
    Returns the entry and what the bank paid."""
    lines = []
    for row in doc.get("lines") or []:
        if row.get("paid_through") == rules.PAYROLL:
            continue
        account = expense_account(row.allowance_type, doc.company)
        row.db_set("expense_account", account, update_modified=False)
        lines.append({"expense_account": account, "amount": row.get("amount"), "paid_through": row.paid_through})
    rows = rules.journal_rows(lines, doc.get("less_advance"), doc.get("exchange_rate") if _foreign(doc) else 1)
    if not rows["expenses"] and not rows["advance"]:
        return None, 0
    cost_center = doc.get("cost_center") or frappe.get_cached_value("Company", doc.company, "cost_center")
    remark = _("Allowance {0}: {1}").format(doc.name, doc.get("employee_name") or doc.employee)
    entry = frappe.new_doc("Journal Entry")
    entry.company = doc.company
    entry.posting_date = doc.get("paid_on") or today()
    entry.user_remark = remark
    if not rows["bank"]:
        entry.voucher_type = "Journal Entry"
    else:
        entry.voucher_type = "Cash Entry" if doc.get("payment_method") == rules.CASH else "Bank Entry"
        entry.cheque_no = doc.get("reference_no")
        entry.cheque_date = doc.get("reference_date")
    for account, amount in rows["expenses"]:
        entry.append("accounts", {"account": account, "debit_in_account_currency": amount,
                                  "cost_center": cost_center, "user_remark": remark})
    if rows["advance"]:
        entry.append("accounts", {"account": frappe.db.get_value(ADVANCE, doc.advance, "advance_account"),
                                  "credit_in_account_currency": rows["advance"], "party_type": "Employee",
                                  "party": doc.employee, "reference_type": ADVANCE, "reference_name": doc.advance,
                                  "is_advance": "Yes", "cost_center": cost_center, "user_remark": remark})
    if rows["bank"] > 0:
        entry.append("accounts", {"account": doc.payment_account, "credit_in_account_currency": rows["bank"]})
    elif rows["bank"] < 0:
        entry.append("accounts", {"account": doc.payment_account, "debit_in_account_currency": -rows["bank"]})
    entry.flags.ignore_permissions = True
    entry.insert()
    entry.submit()
    return entry, rows["bank"]


def _payroll_additions(doc):
    """Each line the payroll pays, an Additional Salary in the payroll month
    the request is paid in."""
    types = _types(doc)
    rate = flt(doc.get("exchange_rate")) if _foreign(doc) else 1
    when = rules.payroll_date(doc.get("paid_on") or today())
    for row in doc.get("lines") or []:
        if row.get("paid_through") != rules.PAYROLL or row.get("additional_salary") or flt(row.get("amount")) <= 0:
            continue
        addition = frappe.get_doc({
            "doctype": "Additional Salary", "employee": doc.employee, "company": doc.company,
            "salary_component": (types.get(row.allowance_type) or {}).get("salary_component"),
            "amount": round(flt(row.amount) * rate, 2), "payroll_date": when, "currency": _home(doc),
            "overwrite_salary_structure_amount": 0, "ref_doctype": DOCTYPE, "ref_docname": doc.name,
        })
        addition.flags.ignore_permissions = True
        addition.insert()
        addition.submit()
        row.db_set("additional_salary", addition.name, update_modified=False)


def _tell_paid(doc):
    """Step 4: the HR Officer is told it is paid."""
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if users:
        people.notify(users, doc.doctype, doc.name, _("{0}'s allowance of {1} has been paid.").format(
            doc.get("employee_name") or doc.employee, frappe.utils.fmt_money(doc.get("total"), currency=doc.currency)))


def request_on_cancel(doc, method=None):
    """Cancelled after it was paid: its journal entry and its payroll
    additions go with it. An addition a salary slip has already paid stays,
    and Frappe HR says so."""
    if doc.get("journal_entry") and frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus") == 1:
        entry = frappe.get_doc("Journal Entry", doc.journal_entry)
        entry.flags.ignore_permissions = True
        entry.cancel()
    for row in doc.get("lines") or []:
        if row.get("additional_salary") and frappe.db.get_value("Additional Salary", row.additional_salary,
                                                                "docstatus") == 1:
            addition = frappe.get_doc("Additional Salary", row.additional_salary)
            addition.flags.ignore_permissions = True
            addition.cancel()
    doc.db_set("status", rules.status_for(2, doc.get("workflow_state")), update_modified=False)


# ── 3. The Allowance Type ─────────────────────────────────────────────
def type_validate(doc, method=None):
    if not cint(doc.get("needs_trip")):
        doc.per_diem_column = None
    component_type = frappe.db.get_value("Salary Component", doc.salary_component, "type") \
        if doc.get("salary_component") else None
    accounts = []
    for row in doc.get("accounts") or []:
        found = frappe.db.get_value("Account", row.account, ["company", "is_group"], as_dict=True) or {}
        accounts.append({"company": row.company, "account": row.account, "account_company": found.get("company"),
                         "is_group": found.get("is_group")})
    errors = rules.type_errors({"paid_through": doc.get("paid_through"), "salary_component": doc.get("salary_component"),
                                "component_type": component_type, "accounts": accounts})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TYPE))


# ── 4. Every day ──────────────────────────────────────────────────────
def daily():
    """An approved request waiting on Accounts, put on their list."""
    rows = frappe.get_all(DOCTYPE, filters={"docstatus": 0, "workflow_state": approval.PENDING_ACCOUNTS},
                          fields=["name", "employee", "employee_name", "branch", "department", "total", "currency"],
                          limit=200)
    for row in rows:
        users = people.people_for(approval.ACCOUNTS, row.branch, row.department)
        if users:
            people.assign(DOCTYPE, row.name, users, _("{0}'s allowance of {1} is waiting to be paid.").format(
                row.employee_name or row.employee, frappe.utils.fmt_money(row.total, currency=row.currency)))
    frappe.db.commit()


# ── 5. Wiring and seeds ───────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the four signatures the allowance passes."""
    from hrms_addon.hrms_addon import workflows

    workflows.setup_on_migrate(approval, "Allowance Request workflow")


def seed_allowance_types():
    """The allowances the minutes name, made once; one HR have changed is
    left as they left it. The accounts the LPL.HR.31 lines had as Expense
    Claim Types come across, and the acting allowance takes a salary
    component of that name where there is one."""
    made = []
    for spec in rules.SEED_TYPES:
        name = spec["allowance_type"]
        if frappe.db.exists(TYPE, name):
            continue
        doc = frappe.get_doc(dict(spec, doctype=TYPE))
        for row in frappe.get_all("Expense Claim Account", filters={"parent": name, "parenttype": "Expense Claim Type"},
                                  fields=["company", "default_account"]):
            if row.default_account:
                doc.append("accounts", {"company": row.company, "account": row.default_account})
        if spec["paid_through"] == rules.PAYROLL and frappe.db.exists("Salary Component", name):
            doc.salary_component = name
        # a payroll allowance with no component yet is made all the same: the
        # request says to set it, and HR set it on the type
        doc.flags.ignore_permissions = doc.flags.ignore_mandatory = doc.flags.ignore_validate = True
        doc.insert()
        made.append(name)
    return made


def _foreign(doc):
    return bool(doc.get("currency") and doc.currency != _home(doc))


def _home(doc):
    return doc.get("company_currency") or _company_currency(doc.get("company"))


def _company_currency(company):
    return frappe.get_cached_value("Company", company, "default_currency") if company else None
