# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Salary advances: the employee's request, and the Payroll Officer's monthly
run (Salary Advance Processing), processed the way a payroll is.

The rules are in advance_rules.py and advance_request_approval.py.

  request_*  the Salary Advance Request: the employee applies once and the
             supervisor approves. The request stays active month after
             month, until its last month or until it is stopped.
  run_*      the Salary Advance Processing: Get Requests brings in every
             active request for the month; each line is checked against the
             month's attendance, off-duty days, leave and the other
             conditions; each plant's HR Officer confirms their plant; the
             Payroll Officer submits. Submitting creates each employee's
             advance and one draft bank entry for Finance. When Finance
             submit the bank entry, each recovery goes onto the payroll
             (advances.payment_on_submit).
  daily      requests past their last month are ended; the Payroll Officer
             and the HR Officers are reminded when requests close and on the
             processing date.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import advance_rules as rules, people

REQUEST = "Salary Advance Request"
RUN = "Salary Advance Processing"
LINE = "Salary Advance Processing Employee"
ADVANCE = "Employee Advance"
CONFIRMERS = ("HR Manager", "System Manager")


# ── 1. The request ────────────────────────────────────────────────────
def request_validate(doc, method=None):
    from hrms_addon.hrms_addon import advance_request_approval as approval

    if not doc.get("request_date"):
        doc.request_date = today()
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {"supervisor_remarks": doc.get("supervisor_remarks")})
        if new_state == approval.PENDING_SUPERVISOR:
            errors = rules.request_errors({"employee": doc.get("employee"), "first_month": doc.get("first_month"),
                                           "until_month": doc.get("until_month"), "amount": doc.get("amount"),
                                           "today": today()}) + _other_active(doc) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(REQUEST))
        if new_state == approval.APPROVED:
            doc.approved_on = today()
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    doc.approval_status = new_state or doc.get("approval_status") or approval.DRAFT
    doc.status = request_status(doc)
    if old_state != new_state and new_state == approval.PENDING_SUPERVISOR:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.get("branch"), doc.get("department"))
        if users:
            message = _("Salary advance request from {0}, from {1}.").format(
                doc.get("employee_name") or doc.employee, _month_of(doc.get("first_month")))
            people.notify(users, doc.doctype, doc.name, message)
            people.assign(doc.doctype, doc.name, users, message)


def _other_active(doc):
    """One active request per employee."""
    others = frappe.get_all(REQUEST, filters={"employee": doc.get("employee"), "docstatus": 1,
                                              "name": ["!=", doc.name or ""],
                                              "status": rules.REQUEST_ACTIVE}, pluck="name")
    if others:
        return ["%s already has an active request (%s). Stop it before making another."
                % (doc.get("employee_name") or doc.get("employee"), others[0])]
    return []


def request_status(doc):
    from hrms_addon.hrms_addon import advance_request_approval as approval

    if doc.docstatus == 2:
        return "Cancelled"
    if doc.docstatus == 0:
        return "Rejected" if doc.get("workflow_state") == approval.REJECTED else "Draft"
    until = doc.get("until_month")
    now = getdate(today())
    if until and (getdate(until).year, getdate(until).month) < (now.year, now.month):
        return rules.REQUEST_ENDED
    return rules.REQUEST_ACTIVE


def request_on_submit(doc, method=None):
    doc.db_set("status", request_status(doc), update_modified=False)
    users = [frappe.db.get_value("Employee", doc.employee, "user_id")]
    users += people.people_for("Payroll Officer", doc.get("branch"), doc.get("department"))
    users = [user for user in dict.fromkeys(users) if user]
    if users:
        people.notify(users, doc.doctype, doc.name,
                      _("Salary advance request for {0} approved, from {1}.").format(
                          doc.get("employee_name") or doc.employee, _month_of(doc.get("first_month"))))


def request_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)


@frappe.whitelist(methods=["POST"])
def stop_request(name, reason=None):
    """The employee, or HR, stops a request: no further month picks it up."""
    doc = frappe.get_doc(REQUEST, name)
    if doc.docstatus != 1:
        frappe.throw(_("Only an approved request can be stopped."))
    user = frappe.session.user
    own = frappe.db.get_value("Employee", doc.employee, "user_id") == user
    if not own and not set(frappe.get_roles()) & {"HR User", "HR Manager", "Payroll Officer", "System Manager"}:
        frappe.throw(_("Only the employee or HR can stop this request."), frappe.PermissionError)
    if not doc.get("stopped_on"):
        doc.db_set({"stopped_on": today(), "stopped_by": user, "stop_reason": reason,
                    "status": rules.REQUEST_STOPPED})
    return rules.REQUEST_STOPPED


# ── 2. The monthly run ────────────────────────────────────────────────
def run_validate(doc, method=None):
    from hrms_addon.hrms_addon import advances

    s = advances.settings()
    _fill_period(doc, s)
    if doc.docstatus == 0:
        for row in doc.get("employees") or []:
            _work_out(row, doc, s)
        _sync_plants(doc)
        _stamp_confirmations(doc)
    paid = [row for row in doc.get("employees") or [] if row.include and row.qualifies]
    doc.total_employees = len(paid)
    doc.total_amount = round(sum(flt(row.amount) for row in paid), 2)
    doc.status = {0: "Draft", 1: "Processed", 2: "Cancelled"}[doc.docstatus]


def _fill_period(doc, s):
    from hrms_addon.hrms_addon import advances

    if not (doc.get("year") and doc.get("month") in rules.MONTHS):
        frappe.throw(_("Select the month and year."), title=_(RUN))
    month = rules.MONTHS.index(doc.month) + 1
    first = datetime.date(int(doc.year), month, 1)
    closed = advances._closed_days(doc.get("company"), first, first + datetime.timedelta(days=27))
    doc.processing_date = rules.processing_date(int(doc.year), month, s, closed)
    doc.period_start, doc.period_end = rules.payroll_period(doc.processing_date)


def _work_out(row, doc, s):
    """One employee's line: what they may have this month, and whether
    they qualify. Absences are counted to today until the processing date,
    and in full on it."""
    from hrms_addon.hrms_addon import advances, attendance

    employee = frappe.db.get_value("Employee", row.employee,
                                   ["employee_name", "status", "employment_type", "branch", "department",
                                    "date_of_joining", "salary_mode", "bank_name", "bank_ac_no"], as_dict=True)
    if not employee:
        row.qualifies, row.remarks = 0, _("The employee does not exist.")
        return
    for field in ("employee_name", "branch", "department", "salary_mode", "bank_name", "bank_ac_no"):
        row.set(field, employee.get(field))
    start, processed_on = getdate(doc.period_start), getdate(doc.processing_date)
    upto = min(getdate(today()), processed_on)
    absent, off_duty = set(), set()
    if upto >= start:
        absent = advances._absent_days(row.employee, start, upto)
        off_duty = {day for _who, day in attendance._off_duty_between([row.employee], start, upto)}
    row.days_absent = rules.days_absent(absent, off_duty, s)
    row.pay_category = advances._pay_category(row.employee)
    row.gross_pay = advances._gross_pay(row.employee)
    request = frappe.db.get_value(REQUEST, row.request, ["status", "approved_on", "first_month", "until_month",
                                                         "amount"], as_dict=True) \
        if row.get("request") else None
    entitlement = rules.entitled(rules.SALARY_ADVANCE, row.gross_pay, row.pay_category, s)
    row.amount = rules.line_amount(entitlement, request.amount if request else 0)
    errors = rules.eligibility_errors({
        "advance_type": rules.SALARY_ADVANCE, "status": employee.status,
        "employment_type": employee.employment_type, "pay_category": row.pay_category,
        "date_of_joining": employee.date_of_joining, "today": today(), "gross_pay": row.gross_pay,
        "amount": row.amount, "outstanding": advances._outstanding_elsewhere(row.employee, None),
        "instalments": s["salary_instalments"], "processing_date": processed_on, "window_start": start,
        "days_absent": row.days_absent, "on_leave": advances._on_leave(row.employee, processed_on),
        "bank_loan": advances._bank_loan(row.employee, processed_on)}, s)
    if not row.amount:
        errors = [rules.NO_GROSS] + [error for error in errors if error != rules.ASK_AMOUNT]
    if request:
        joined, why = rules.joins_run(dict(request, status=_standing(request)), processed_on, s)
        if not joined:
            errors.insert(0, why)
    else:
        errors.insert(0, rules.NO_REQUEST)
    paid_in = _paid_this_month(row.employee, doc)
    if paid_in:
        errors.insert(0, "Already paid this month in %s." % paid_in)
    row.qualifies = 0 if errors else 1
    row.remarks = "; ".join(errors) or None


def _standing(request):
    """The request's status for a run: an ended request still covers the
    months it ran for."""
    status = request.get("status")
    return rules.REQUEST_ACTIVE if status == rules.REQUEST_ENDED else status


def _paid_this_month(employee, doc):
    """Another submitted run of the same month that paid this employee."""
    runs = frappe.get_all(RUN, filters={"docstatus": 1, "company": doc.get("company"), "year": doc.get("year"),
                                        "month": doc.get("month"), "name": ["!=", doc.name or ""]},
                          pluck="name")
    if not runs:
        return None
    lines = frappe.get_all(LINE, filters={"parent": ["in", runs], "parenttype": RUN, "employee": employee,
                                          "employee_advance": ["is", "set"]}, pluck="parent", limit=1)
    return lines[0] if lines else None


def _sync_plants(doc):
    """One confirmation row per plant with employees in the run."""
    wanted = sorted({row.branch for row in doc.get("employees") or [] if row.get("branch")})
    kept = [row for row in doc.get("plants") or [] if row.branch in wanted]
    have = {row.branch for row in kept}
    doc.set("plants", kept)
    for branch in wanted:
        if branch not in have:
            doc.append("plants", {"branch": branch, "confirmed": 0})


def _stamp_confirmations(doc):
    """A plant's HR Officer, or the HR Manager, confirms attendance and leave
    for that plant."""
    before = doc.get_doc_before_save()
    was = {row.branch: row.confirmed for row in (before.get("plants") or [])} if before else {}
    roles = set(frappe.get_roles())
    for row in doc.get("plants") or []:
        if row.confirmed and not was.get(row.branch):
            if not roles & set(CONFIRMERS) and frappe.session.user not in people.hr_officers(row.branch):
                frappe.throw(_("Only the HR Officer of {0} or the HR Manager can confirm it.").format(row.branch),
                             title=_(RUN))
            row.confirmed_by, row.confirmed_on = frappe.session.user, today()
        elif not row.confirmed:
            row.confirmed_by = row.confirmed_on = None


@frappe.whitelist(methods=["POST"])
def get_requests(name):
    """Every active request for the run's month (and plant, if one is set)."""
    from hrms_addon.hrms_addon import advances

    doc = frappe.get_doc(RUN, name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("The run is already submitted."))
    s = advances.settings()
    _fill_period(doc, s)
    have = {row.employee for row in doc.get("employees") or []}
    added = 0
    for request in frappe.get_all(REQUEST, filters={"docstatus": 1, "company": doc.company},
                                  fields=["name", "employee", "employee_name", "branch", "department", "status",
                                          "approved_on", "first_month", "until_month"],
                                  order_by="employee_name asc", limit_page_length=0):
        joined, _why = rules.joins_run(dict(request, status=_standing(request)), doc.processing_date, s)
        if not joined or request.employee in have:
            continue
        if doc.get("branch") and frappe.db.get_value("Employee", request.employee, "branch") != doc.branch:
            continue
        doc.append("employees", {"employee": request.employee, "employee_name": request.employee_name,
                                 "branch": request.branch, "department": request.department,
                                 "request": request.name, "include": 1})
        have.add(request.employee)
        added += 1
    doc.save()
    return added


def run_before_submit(doc, method=None):
    from hrms_addon.hrms_addon import advances

    s = advances.settings()
    was = [(row.employee, int(row.qualifies or 0), flt(row.amount)) for row in doc.get("employees") or []]
    for row in doc.get("employees") or []:
        _work_out(row, doc, s)
    now = [(row.employee, int(row.qualifies or 0), flt(row.amount)) for row in doc.get("employees") or []]
    changed = [a[0] for a, b in zip(was, now) if a != b]
    if changed:
        frappe.throw(_("Attendance or pay has changed since the run was saved for: {0}. Save the run again and "
                       "check the lines.").format(", ".join(changed)), title=_(RUN))
    errors = rules.run_errors({
        "processing_date": doc.processing_date, "today": today(),
        "unconfirmed": [row.branch for row in doc.get("plants") or [] if not row.confirmed],
        "included": doc.total_employees, "bank_account": doc.get("bank_account"),
        "payment_method": doc.get("payment_method"), "reference_no": doc.get("reference_no"),
        "reference_date": doc.get("reference_date")}, s)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(RUN))


def run_on_submit(doc, method=None):
    """Each qualifying employee's advance, created and passed for payment,
    and one draft bank entry for Finance."""
    from hrms_addon.hrms_addon import advance_approval as approval, advances

    s = advances.settings()
    made = []
    for row in doc.get("employees") or []:
        if not (row.include and row.qualifies):
            continue
        advance = frappe.get_doc({
            "doctype": ADVANCE, "employee": row.employee, "company": doc.company,
            "posting_date": doc.processing_date, "advance_amount": row.amount,
            "currency": frappe.get_cached_value("Company", doc.company, "default_currency"),
            "purpose": _("Salary advance for {0} {1}").format(doc.month, doc.year),
            "advance_account": _advance_account(row.employee, doc.company),
            "custom_advance_type": rules.SALARY_ADVANCE, "custom_salary_advance_run": doc.name,
            "custom_salary_advance_request": row.get("request"), "custom_branch": row.get("branch"),
            "department": row.get("department"), "custom_approved_amount": row.amount,
            "custom_instalments": s["salary_instalments"], "custom_processing_date": doc.processing_date,
            "custom_period_start": doc.period_start, "custom_first_recovery_month": doc.period_end,
            "custom_days_absent": row.days_absent, "workflow_state": approval.DRAFT,
        })
        advance.flags.ignore_permissions = True
        advance.insert()
        advance.workflow_state = approval.PAID
        advance.submit()
        row.db_set("employee_advance", advance.name, update_modified=False)
        made.append(advance)
    if not made:
        return
    entry = _bank_entry(doc, made)
    doc.db_set("journal_entry", entry.name, update_modified=False)
    plants = sorted({row.get("branch") for row in doc.get("employees") or [] if row.include and row.qualifies})
    users = _users("Payroll Officer", plants) + _users("Finance Officer", plants)
    users = list(dict.fromkeys(users))
    if users:
        people.notify(users, doc.doctype, doc.name,
                      _("Salary advances for {0} {1}: {2} employee(s), {3}. Submit bank entry {4} once paid.").format(
                          doc.month, doc.year, len(made), frappe.utils.fmt_money(doc.total_amount), entry.name))


def _advance_account(employee, company):
    return frappe.db.get_value("Employee", employee, "employee_advance_account") \
        or frappe.db.get_value("Company", company, "default_employee_advance_account")


def _bank_entry(doc, made):
    """One bank (or cash) entry paying every advance in the run. Submitting
    it marks each advance paid, and puts its recovery on the payroll."""
    entry = frappe.new_doc("Journal Entry")
    entry.voucher_type = "Cash Entry" if doc.payment_method == "Cash" else "Bank Entry"
    entry.company = doc.company
    entry.posting_date = doc.processing_date
    entry.cheque_no = doc.get("reference_no")
    entry.cheque_date = doc.get("reference_date")
    entry.user_remark = _("Salary advances for {0} {1} ({2})").format(doc.month, doc.year, doc.name)
    total = 0.0
    for advance in made:
        entry.append("accounts", {"account": advance.advance_account, "party_type": "Employee",
                                  "party": advance.employee, "debit_in_account_currency": advance.advance_amount,
                                  "reference_type": ADVANCE, "reference_name": advance.name, "is_advance": "Yes"})
        total += flt(advance.advance_amount)
    entry.append("accounts", {"account": doc.bank_account, "credit_in_account_currency": round(total, 2)})
    entry.flags.ignore_permissions = True
    entry.insert()
    return entry


def run_on_cancel(doc, method=None):
    if doc.get("journal_entry") and frappe.db.exists("Journal Entry", doc.journal_entry):
        if frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus") == 1:
            frappe.throw(_("Cancel the bank entry {0} first.").format(doc.journal_entry), title=_(RUN))
        frappe.delete_doc("Journal Entry", doc.journal_entry, ignore_permissions=True)
    for row in doc.get("employees") or []:
        if row.get("employee_advance") and frappe.db.exists(ADVANCE, row.employee_advance):
            advance = frappe.get_doc(ADVANCE, row.employee_advance)
            if advance.docstatus == 1:
                advance.flags.ignore_permissions = True
                advance.cancel()
    doc.db_set("status", "Cancelled", update_modified=False)


# ── 3. What the system watches ────────────────────────────────────────
def daily():
    _end_requests()
    _remind()
    frappe.db.commit()


def _end_requests():
    first = getdate(today()).replace(day=1)
    for name in frappe.get_all(REQUEST, filters={"docstatus": 1, "status": rules.REQUEST_ACTIVE,
                                                 "until_month": ["<", str(first)]}, pluck="name"):
        frappe.db.set_value(REQUEST, name, "status", rules.REQUEST_ENDED, update_modified=False)


def _remind(day=None):
    from hrms_addon.hrms_addon import advances

    s = advances.settings()
    day = getdate(day or today())
    first = day.replace(day=1)
    for company in frappe.get_all("Company", pluck="name"):
        closed = advances._closed_days(company, first, first + datetime.timedelta(days=27))
        processed_on = rules.processing_date(day.year, day.month, s, closed)
        month = rules.MONTHS[processed_on.month - 1]
        if day == rules.request_deadline(processed_on, s):
            users = list(dict.fromkeys(_users("Payroll Officer") + _users("HR User")))
            if users:
                people.notify(users, "Advance Settings", "Advance Settings", _(
                    "Salary advance requests for {0} {1} have closed. Prepare the Salary Advance Processing, "
                    "and confirm attendance and leave for each plant.").format(month, processed_on.year))
        elif day == processed_on:
            runs = frappe.get_all(RUN, filters={"company": company, "year": processed_on.year, "month": month,
                                                "docstatus": 0}, pluck="name")
            payroll = _users("Payroll Officer")
            for name in runs:
                run = frappe.get_doc(RUN, name)
                run.flags.ignore_permissions = True
                run.save()
                if payroll:
                    people.notify(payroll, RUN, name, _(
                        "Salary advances for {0} are processed today: {1} employee(s) qualify.").format(
                        month, run.total_employees))
            if not runs and payroll:
                people.notify(payroll, "Advance Settings", "Advance Settings", _(
                    "Salary advances for {0} are processed today, and no Salary Advance Processing has been "
                    "prepared.").format(month))


def _users(role, plants=None):
    """The users holding `role`: those serving these plants, or all of them."""
    if plants is None:
        return [holder["user"] for holder in people.holders(role)]
    users = []
    for plant in plants:
        users += people.people_for(role, plant)
    return list(dict.fromkeys(users))


def _month_of(value):
    day = getdate(value) if value else None
    return "%s %d" % (rules.MONTHS[day.month - 1], day.year) if day else ""


# ── 4. Wiring ─────────────────────────────────────────────────────────
def setup_on_migrate():
    """after_migrate: the request's workflow."""
    from hrms_addon.hrms_addon import advance_request_approval, workflows

    workflows.setup_on_migrate(advance_request_approval, "Salary Advance Request workflow")
