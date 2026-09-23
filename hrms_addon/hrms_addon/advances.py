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
              needs no list kept by hand. The instalments go onto the
              payroll when the payment is recorded against the advance
              (Create > Payment), because Frappe HR refuses a deduction for
              more of an advance than has been paid out; and the payroll
              books each one back against the advance, which Frappe HR then
              shows as Returned.
  from_leave  step 7 of the leave process: the Leave Advance raised from an
              approved LPL/HR/15 (leave.py).
  daily       the monitoring both charts ask for: the salary advance run
              (chart 4.10 step 2, "System monitoring Advance payment
              date"), an advance due to be paid, and one whose recovery
              has not started.

THE RULES ARE SETTINGS

Every number the minutes give — 40% and 60% of gross, the Per Meter
standard rate, the 15th, three days of absence — lives on Advance
Settings, and advance_rules.DEFAULTS is what each one is until somebody
changes it. settings() reads them once per advance.

A SALARY ADVANCE IS PROCESSED ON A DAY

It joins the run on the 15th (or the working day before) if it was asked
for before that run closed, otherwise the next one. Its absences are
counted from the start of the payroll period — the 26th — to the
processing date; until that day they are counted to today, and on the day
the whole run is worked out again, because three days of absence can
become four in the week between asking and being paid.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import advance_rules as rules, people

DOCTYPE = "Employee Advance"
DEFAULT_COMPONENT = "Advance Recovery"
SETTINGS = "Advance Settings"
NOT_REGULAR = "Advance Employment Type"


# ── 0. The rules, as Luuka has set them ───────────────────────────────
def settings():
    """Advance Settings merged over the minutes' own numbers.

    Read from the database rather than through the document, so a stored
    nought stays a nought and anything never saved takes its default.
    """
    stored = {}
    if frappe.db.exists("DocType", SETTINGS):
        stored = dict(frappe.db.get_singles_dict(SETTINGS) or {})
        stored["not_regular_types"] = frappe.get_all(
            NOT_REGULAR, filters={"parent": SETTINGS, "parenttype": SETTINGS},
            pluck="employment_type", limit_page_length=0)
    return rules.settings_from(stored)


def settings_validate(doc, method=None):
    values = {key: doc.get(key) for key in rules.DEFAULTS}
    values["not_regular_types"] = [row.employment_type for row in doc.get("not_regular_types") or []]
    errors = rules.settings_errors(rules.settings_from(values))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SETTINGS))


def _has(doctype, fieldname):
    """A custom field that a fresh site may not have yet: fixtures are
    synced after patches, and this runs inside both."""
    return frappe.get_meta(doctype).has_field(fieldname)


# ── 1. The advance itself ─────────────────────────────────────────────
def advance_validate(doc, method=None):
    from hrms_addon.hrms_addon import advance_approval as approval

    if not doc.get("custom_advance_type"):
        doc.custom_advance_type = rules.SALARY_ADVANCE
    s = settings()
    from_run = doc.get("custom_salary_advance_run")
    if doc.custom_advance_type == rules.SALARY_ADVANCE and doc.is_new() and not from_run:
        frappe.throw(_("Salary advances are requested on a Salary Advance Request and paid through the "
                       "monthly Salary Advance Processing."), title=_("Employee Advance"))
    _stamp_requested(doc)
    if doc.custom_advance_type == rules.SALARY_ADVANCE and not from_run:
        _plan_salary(doc, s)
    _fill_money(doc, s)
    _check_eligibility(doc, s)
    _build_recovery(doc)
    _check_step(doc, s)
    doc.custom_advance_status = doc.get("workflow_state") or doc.get("custom_advance_status") or approval.DRAFT
    if doc.get("custom_consent") and not doc.get("custom_consent_on"):
        doc.custom_consent_on = today()


def _stamp_requested(doc):
    """The day the request left Draft: "submitted the required Salary
    Advance Request Form in time" is about when it was handed in, not when
    somebody started filling it in."""
    from hrms_addon.hrms_addon import advance_approval as approval

    if doc.get("custom_requested_on"):
        return
    state = doc.get("workflow_state")
    if state and state != approval.DRAFT:
        doc.custom_requested_on = today()


def _plan_salary(doc, s):
    """The run this request joins, and what the attendance says so far."""
    from hrms_addon.hrms_addon import attendance

    asked_on = getdate(doc.get("custom_requested_on") or today())
    closed = _closed_days(doc.get("company"), asked_on, add_days(asked_on, 70))
    processed_on = rules.run_for(asked_on, s, closed)
    start, end = rules.payroll_period(processed_on)
    doc.custom_processing_date = processed_on
    doc.custom_period_start = start
    upto = min(getdate(today()), processed_on)
    absent, off_duty = set(), set()
    if doc.get("employee") and upto >= start:
        absent = _absent_days(doc.employee, start, upto)
        off_duty = {day for _who, day in attendance._off_duty_between([doc.employee], start, upto)}
    doc.custom_days_absent = rules.days_absent(absent, off_duty, s)
    doc.custom_off_duty_days = len(absent & off_duty) if cint(s["salary_off_duty_not_absent"]) else 0
    # taken back from the same month's pay, which closes on the 25th
    if not doc.get("custom_first_recovery_month"):
        doc.custom_first_recovery_month = end
    if not cint(doc.get("custom_instalments")):
        doc.custom_instalments = s["salary_instalments"]


def _closed_days(company, start, end):
    """The company's holiday list between two days: its public holidays,
    and any weekly offs it keeps."""
    company = company or frappe.defaults.get_user_default("Company")
    listed = frappe.db.get_value("Company", company, "default_holiday_list") if company else None
    if not listed:
        return set()
    return {getdate(day) for day in frappe.get_all(
        "Holiday", filters={"parent": listed, "parenttype": "Holiday List",
                            "holiday_date": ["between", [start, end]]},
        pluck="holiday_date", limit_page_length=0)}


def _absent_days(employee, start, end):
    return {getdate(day) for day in frappe.get_all(
        "Attendance", filters={"employee": employee, "docstatus": 1, "status": "Absent",
                               "attendance_date": ["between", [start, end]]},
        pluck="attendance_date", limit_page_length=0)}


def _on_leave(employee, day):
    """The approved leave that covers a day, if any."""
    rows = frappe.get_all("Leave Application",
                          filters={"employee": employee, "docstatus": 1, "status": "Approved",
                                   "from_date": ["<=", day], "to_date": [">=", day]},
                          pluck="name", limit=1)
    return rows[0] if rows else None


def _bank_loan(employee, day):
    """Has a bank loan on the day, from the employee's own record. A loan
    with an end date that has passed is no longer a loan."""
    if not employee or not _has("Employee", "custom_has_bank_loan"):
        return False
    has, until = frappe.db.get_value("Employee", employee,
                                     ["custom_has_bank_loan", "custom_bank_loan_until"]) or (0, None)
    return bool(cint(has)) and (not until or getdate(until) >= getdate(day))


def _company_loan(employee):
    """What is still owed on the company's own loans (loans.py)."""
    if not employee or not frappe.db.exists("DocType", "Employee Loan"):
        return 0
    return flt(sum(flt(value) for value in frappe.get_all(
        "Employee Loan", filters={"employee": employee, "docstatus": 1},
        pluck="outstanding", limit_page_length=0)))


def _pay_category(employee):
    if not employee or not _has("Employee", "custom_pay_category"):
        return rules.MONTHLY
    return frappe.db.get_value("Employee", employee, "custom_pay_category") or rules.MONTHLY


def _average_gross(employee, months):
    """The average gross over the last few paid months: a Per Meter
    employee's pay follows their output, so one month is not a fair base
    (minutes §4.4). None when nothing has been paid yet."""
    rows = frappe.get_all("Salary Slip", filters={"employee": employee, "docstatus": 1},
                          fields=["gross_pay"], order_by="end_date desc", limit=max(int(months or 0), 1))
    if not rows:
        return None
    return round(sum(flt(row.gross_pay) for row in rows) / len(rows), 2)


def _leave_days(doc):
    if not doc.get("custom_leave_application"):
        return None
    return frappe.db.get_value("Leave Application", doc.custom_leave_application, "total_leave_days")


def _fill_money(doc, s):
    """What the employee earns, what they still owe, and the most this kind
    of advance may be (Advance Settings)."""
    kind = doc.get("custom_advance_type")
    if doc.get("employee"):
        doc.custom_gross_pay = _gross_pay(doc.employee)
        doc.custom_outstanding_before = _outstanding_elsewhere(doc.employee, doc.name)
        doc.custom_pay_category = _pay_category(doc.employee)
    average = None
    if kind == rules.LEAVE_ADVANCE and doc.get("custom_pay_category") == rules.PER_METER and doc.get("employee"):
        average = _average_gross(doc.employee, s["leave_per_meter_months"])
    doc.custom_limit = rules.entitled(kind, doc.get("custom_gross_pay"), doc.get("custom_pay_category"),
                                      s, average) or 0
    # the minutes give the salary advance as a figure, not a ceiling: left
    # blank, it is that figure
    if not flt(doc.get("advance_amount")) and doc.custom_limit and kind == rules.SALARY_ADVANCE:
        doc.advance_amount = doc.custom_limit
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


def _check_eligibility(doc, s=None):
    """The charts' "Qualify for advance?". It is written onto the form
    rather than thrown, so the HR Officer can see why and act on it; the
    workflow refuses to move an advance that does not qualify."""
    s = s or settings()
    errors = rules.eligibility_errors(_facts(doc, s), s)
    doc.custom_qualifies = 0 if errors else 1
    doc.custom_eligibility_remarks = "; ".join(errors) or None


def _facts(doc, s=None):
    s = s or settings()
    employee = doc.get("employee")
    status, employment_type = (frappe.db.get_value("Employee", employee, ["status", "employment_type"])
                               if employee else (None, None)) or (None, None)
    kind = doc.get("custom_advance_type")
    on = doc.get("custom_processing_date") or today()
    facts = {
        "advance_type": kind,
        "status": status,
        "employment_type": employment_type,
        "pay_category": doc.get("custom_pay_category"),
        "date_of_joining": doc.get("custom_date_of_appointment"),
        "today": today(),
        "gross_pay": doc.get("custom_gross_pay"),
        "amount": doc.get("custom_approved_amount") or doc.get("advance_amount"),
        "outstanding": doc.get("custom_outstanding_before"),
        "instalments": doc.get("custom_instalments"),
    }
    if kind == rules.SALARY_ADVANCE:
        facts.update({
            "processing_date": on, "window_start": doc.get("custom_period_start"),
            "days_absent": doc.get("custom_days_absent"),
            "on_leave": _on_leave(employee, on) if employee else None,
            "bank_loan": _bank_loan(employee, on),
        })
    elif kind == rules.LEAVE_ADVANCE:
        facts.update({
            "bank_loan": _bank_loan(employee, today()),
            "company_loan": _company_loan(employee),
            "leave_days": _leave_days(doc),
            "average_gross": (_average_gross(employee, s["leave_per_meter_months"])
                              if doc.get("custom_pay_category") == rules.PER_METER and employee else None),
        })
    return facts


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


def _check_step(doc, s=None):
    from hrms_addon.hrms_addon import advance_approval as approval

    s = s or settings()
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
            errors = rules.eligibility_errors(_facts(doc, s), s) + errors
        # the Payroll Officer "ticks the qualifying employees" (§4.9): on
        # the day, with the whole period's attendance counted, somebody
        # who has stopped qualifying is rejected rather than paid
        if (doc.get("custom_advance_type") == rules.SALARY_ADVANCE
                and old_state == approval.PENDING_PAYROLL and new_state == approval.PENDING_FINANCE):
            errors = rules.eligibility_errors(_facts(doc, s), s) + errors
            held = rules.held_until(doc.get("custom_processing_date"), today(), s)
            if held:
                errors.append(held)
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
    """Passed by Finance. The recovery goes onto the payroll as far as the
    payment recorded against the advance covers it, which at this point is
    usually nothing yet; everyone the chart names is told."""
    scheduled = schedule_recovery(doc)
    if not doc.get("custom_salary_advance_run"):
        # the run tells everyone once, for all its advances
        _tell_paid(doc, scheduled)
    _mark_leave(doc)


def advance_on_cancel(doc, method=None):
    for row in doc.get("custom_recoveries") or []:
        if row.additional_salary and frappe.db.exists("Additional Salary", row.additional_salary):
            deduction = frappe.get_doc("Additional Salary", row.additional_salary)
            if deduction.docstatus == 1:
                deduction.flags.ignore_permissions = True
                deduction.cancel()
    doc.custom_advance_status = "Cancelled"


def schedule_recovery(doc):
    """Each instalment becomes an Additional Salary deduction, so the
    payroll run takes it without a list kept by hand (test case 5 of the
    loan script, and the same mechanism for every advance).

    Only as far as the payment recorded against the advance covers it:
    Frappe HR refuses a deduction from salary for more of an advance than
    has been paid out (paid, less what was claimed, less what is already
    on the payroll). What the payment does not cover waits for the rest of
    it. Returns how many instalments went onto the payroll.
    """
    if doc.docstatus != 1:
        return 0
    room = flt(doc.get("paid_amount")) - flt(doc.get("claimed_amount")) - _scheduled(doc.name)
    waiting = [row for row in doc.get("custom_recoveries") or [] if not (row.additional_salary or row.recovered)]
    if not waiting or room <= 0:
        return 0
    component = doc.get("custom_recovery_component") or _component(doc.get("company"))
    if not component:
        return 0
    made = 0
    for row in sorted(waiting, key=lambda row: str(row.payroll_date)):
        if flt(row.amount) > room + 0.005:
            break
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
        room -= flt(row.amount)
        made += 1
    return made


def _scheduled(advance):
    """What is already on the payroll for an advance, as Frappe HR counts
    it: every submitted deduction that refers to it."""
    return flt(sum(flt(amount) for amount in frappe.get_all(
        "Additional Salary", filters={"ref_doctype": DOCTYPE, "ref_docname": advance, "docstatus": 1},
        pluck="amount", limit_page_length=0)))


def unschedule_beyond_paid(doc):
    """A payment cancelled: the instalments the payroll has not taken yet
    come off it, latest first, until what stays is covered by what is still
    paid. Returns how many came off."""
    if doc.docstatus != 1:
        return 0
    covered = flt(doc.get("paid_amount")) - flt(doc.get("claimed_amount"))
    scheduled = _scheduled(doc.name)
    removed = 0
    rows = [row for row in doc.get("custom_recoveries") or [] if row.additional_salary and not row.recovered]
    for row in sorted(rows, key=lambda row: str(row.payroll_date), reverse=True):
        if scheduled <= covered + 0.005:
            break
        if frappe.db.exists("Additional Salary", row.additional_salary):
            deduction = frappe.get_doc("Additional Salary", row.additional_salary)
            if deduction.docstatus == 1:
                deduction.flags.ignore_permissions = True
                deduction.cancel()
        row.db_set("additional_salary", None, update_modified=False)
        scheduled -= flt(row.amount)
        removed += 1
    return removed


def _advances_paid_by(voucher):
    """The Employee Advances a Payment Entry or Journal Entry pays out."""
    if voucher.doctype == "Payment Entry":
        names = [row.reference_name for row in voucher.get("references") or []
                 if row.get("reference_doctype") == DOCTYPE]
    else:
        names = [row.reference_name for row in voucher.get("accounts") or []
                 if row.get("reference_type") == DOCTYPE and flt(row.get("debit_in_account_currency")) > 0]
    return list(dict.fromkeys(name for name in names if name))


def payment_on_submit(doc, method=None):
    """Payment Entry and Journal Entry: an advance paid out goes onto the
    payroll. Frappe HR has already written the paid amount onto it by now
    (the ledger entries this voucher made)."""
    for name in _advances_paid_by(doc):
        advance = frappe.get_doc(DOCTYPE, name)
        scheduled = schedule_recovery(advance)
        if scheduled:
            _tell_scheduled(advance, scheduled)


def payment_on_cancel(doc, method=None):
    for name in _advances_paid_by(doc):
        unschedule_beyond_paid(frappe.get_doc(DOCTYPE, name))


def _component(company=None):
    """The salary component the recovery is posted to, made once. It
    credits the company's employee advance account, so the payroll books
    each deduction back against the advance."""
    if not frappe.db.exists("Salary Component", DEFAULT_COMPONENT):
        try:
            doc = frappe.get_doc({"doctype": "Salary Component", "salary_component": DEFAULT_COMPONENT,
                                  "type": "Deduction", "salary_component_abbr": "AR",
                                  "description": "Recovery of an employee advance (LPL/HR/21)."})
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="HRMS Addon: advance recovery component")
            return None
    ensure_recovery_account(company)
    return DEFAULT_COMPONENT


def ensure_recovery_account(company=None):
    """The Advance Recovery component's account for each company that has a
    default employee advance account and no account on the component yet.
    One already set is left as it is."""
    if not frappe.db.exists("Salary Component", DEFAULT_COMPONENT):
        return []
    component = frappe.get_doc("Salary Component", DEFAULT_COMPONENT)
    have = {row.company for row in component.get("accounts") or []}
    companies = [company] if company else frappe.get_all("Company", pluck="name")
    added = []
    for name in companies:
        account = frappe.db.get_value("Company", name, "default_employee_advance_account") if name else None
        if account and name not in have:
            component.append("accounts", {"company": name, "account": account})
            added.append(name)
    if added:
        component.flags.ignore_permissions = True
        component.save()
    return added


def _tell_paid(doc, scheduled=0):
    kind = doc.get("custom_advance_type")
    users = people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    users += people.people_for("Payroll Officer", doc.get("custom_branch"), doc.get("department"))
    who = doc.get("employee_name") or doc.employee
    if scheduled:
        message = _("{0} for {1} is paid. Recovery starts {2}.").format(
            kind, who, frappe.utils.format_date(doc.get("custom_first_recovery_month")))
    else:
        message = _("{0} for {1} is passed for payment. Record the payment on it (Create > Payment): the "
                    "recovery goes onto the payroll when it is recorded.").format(kind, who)
        users += people.people_for("Finance Officer", doc.get("custom_branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name, message)


def _tell_scheduled(doc, scheduled):
    users = people.people_for("Payroll Officer", doc.get("custom_branch"), doc.get("department"))
    users += people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name, _(
            "{0} for {1}: paid, and {2} instalment(s) are on the payroll from {3}.").format(
            doc.get("custom_advance_type"), doc.get("employee_name") or doc.employee, scheduled,
            frappe.utils.format_date(doc.get("custom_first_recovery_month"))))


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
    _schedule_paid()
    _tell_recovery()


def _schedule_paid():
    """A paid advance with instalments not yet on the payroll: paid before
    this was installed, or through a voucher nothing hooks."""
    for name in frappe.get_all(DOCTYPE, filters={"docstatus": 1, "paid_amount": [">", 0]}, pluck="name",
                               limit_page_length=0):
        doc = frappe.get_doc(DOCTYPE, name)
        if any(not (row.additional_salary or row.recovered) for row in doc.get("custom_recoveries") or []):
            scheduled = schedule_recovery(doc)
            if scheduled:
                _tell_scheduled(doc, scheduled)
    frappe.db.commit()


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
    filters = {"parenttype": DOCTYPE, "recovered": ["!=", 1], "additional_salary": ["is", "set"]}
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
        refresh_recovered(name)
    frappe.db.commit()
    return len(touched)


def refresh_recovered(name):
    """The recovered and outstanding amounts, from the months marked
    recovered — by the Salary Slip that took them (recoveries.py) or by
    mark_recovered."""
    doc = frappe.get_doc(DOCTYPE, name)
    if doc.docstatus != 1:
        return
    recovered = sum(flt(child.amount) for child in doc.get("custom_recoveries") or [] if child.recovered)
    doc.db_set("custom_recovered_amount", recovered)
    doc.db_set("custom_outstanding", rules.outstanding(
        doc.get("custom_approved_amount") or doc.advance_amount, recovered))


# ── 4. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the three chains, on one Workflow."""
    from hrms_addon.hrms_addon import advance_approval, workflows

    workflows.setup_on_migrate(advance_approval, "Employee Advance workflow")
    try:
        ensure_recovery_account()
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="HRMS Addon: advance recovery account")
