# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Each branch verifies its attendance before payroll pays it.

The rules are in attendance_verification_rules.py and the steps in
attendance_verification_approval.py, both without a Frappe import
(scripts/verify_attendance_verification.py). This reads and writes the site.

  sheet_*             the sheet: the branch's people for its days, each with
                      the Attendance Board's letters counted, and what stops
                      it, read again on every save while it is a draft; the
                      steps, their signatures, and who is told
  weekly_dates        the days a new weekly sheet covers
  refuse_*            a verified day of somebody on the sheet does not
                      change: their Attendance, and what rewrites it without
                      saving it (an approved leave application, an attendance
                      request, off duty, a late arrival notice in advance,
                      overtime sent to payroll)
  refuse_payroll      a payroll pays nobody for a day no verified sheet of
                      theirs covers: PayrollEntryVerified on its submit
                      (which makes the slips), on Submit Salary Slips and on
                      Recreate Salary Slips; slip_before_submit on a slip
                      submitted on its own
  payroll_branches    the payroll form's line per branch
  ShiftTypeVerified   auto attendance marks no absence on a verified day

Payroll Settings' custom_branches_verify_attendance turns the payroll's wait
off; a verified day stays locked either way.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, today

from hrms_addon.hrms_addon import attendance_verification_approval as approval
from hrms_addon.hrms_addon import attendance_verification_rules as rules
from hrms_addon.hrms_addon import payslip_rules, people, weekly_pay_rules, workflows

DOCTYPE = "Attendance Verification"
ROW = "Attendance Verification Employee"
ATTENDANCE = "Attendance"
SETTINGS = "Payroll Settings"
SLIP = "Salary Slip"
WEEKLY_DAY = "Weekly Pay Day"


# ── 1. The sheet ──────────────────────────────────────────────────────
def sheet_validate(doc, method=None):
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD) or approval.DRAFT
    if old_state == approval.PENDING_GM and _header(before) != _header(doc):
        # what the General Manager verifies is what HR sent
        frappe.throw(_("Return the sheet to HR to change its branch, payroll or days."), title=_(DOCTYPE))
    if not before:
        # an amended sheet comes with everything its reopened one had (Amend copies even no_copy fields)
        for field in ("reopened_by", "reopened_on", "return_remarks"):
            doc.set(field, None)
    period = payslip_rules.period_name(doc.get("from_date"), doc.get("to_date"))
    errors = rules.sheet_errors({
        "company": doc.get("company"), "branch": doc.get("branch"), "pay_kind": doc.get("pay_kind"),
        "from_date": doc.get("from_date"), "to_date": doc.get("to_date"), "period_name": period,
        "clashes": _clashes(doc)})
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))
    doc.title = rules.title_for(doc.branch, doc.pay_kind, period, doc.from_date, doc.to_date)
    doc.pay_period = period if doc.pay_kind == rules.MONTHLY else None
    fresh = _read(doc)
    doc.flags.ha_fresh = fresh
    errors = approval.step_errors(old_state, new_state, _facts(doc, fresh, new_state))
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))
    if new_state != approval.VERIFIED:
        # the figures the General Manager verifies are those already on the sheet, unchanged (step_errors)
        _write(doc, fresh)
    if old_state != new_state and new_state != approval.DRAFT:
        doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, now_datetime(),
                                                current).items():
        doc.set(field, value)
    if doc.docstatus == 0:
        doc.status = new_state
    if old_state and old_state != new_state:
        _tell_step(doc, old_state, new_state, before)


HEADER = ("company", "branch", "pay_kind", "from_date", "to_date")


def _header(doc):
    return tuple(str(doc.get(field) or "") for field in HEADER)


def _facts(doc, fresh, new_state):
    return {
        "return_remarks": doc.get("return_remarks"),
        "sheet_errors": rules.ready_errors(doc.get("to_date"), today()),
        "people": len(fresh["rows"]),
        "issues": [rules.issue_text(row) for row in fresh["issues"]],
        "changed": rules.changed_people([_plain(row) for row in doc.get("employees") or []], fresh["rows"])
        if new_state == approval.VERIFIED else [],
    }


def sheet_before_submit(doc, method=None):
    """Verified: whatever submitted it, nothing is left to put right and the figures are those that were checked
    (a plain submit skips the steps, and refuse_plain_submit only stands while the workflow is there)."""
    fresh = doc.flags.get("ha_fresh") or _read(doc)
    errors = approval.step_errors(approval.PENDING_GM, approval.VERIFIED, _facts(doc, fresh, approval.VERIFIED))
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))
    if not doc.get("verified_by"):
        doc.verified_by, doc.verified_on = frappe.session.user, now_datetime()
    doc.status = approval.VERIFIED


def sheet_on_submit(doc, method=None):
    people.withdraw(DOCTYPE, doc.name, people.people_for(approval.GM, doc.branch))
    users = {doc.get("prepared_by")} | set(people.hr_officers(doc.branch)) \
        | set(people.people_for(approval.PAYROLL_OFFICER, doc.branch))
    users.discard(frappe.session.user)
    people.notify(sorted(user for user in users if user), DOCTYPE, doc.name,
                  _("{0} is verified. Payroll may pay these days, and they change no more.").format(doc.title))


def sheet_before_cancel(doc, method=None):
    """Reopened: not once a slip has paid these days."""
    paid = _paid_slips(doc)
    if paid:
        frappe.throw(_("Salary slips that paid these days are submitted: {0}. Cancel them before the sheet is "
                       "reopened.").format(rules.names_text([{"employee": name} for name in paid])),
                     title=_(DOCTYPE))


def sheet_on_cancel(doc, method=None):
    doc.db_set({"reopened_by": frappe.session.user, "reopened_on": now_datetime(), "status": approval.REOPENED},
               update_modified=False)
    drafts = _draft_slips(doc)
    users = {doc.get("prepared_by")} | set(people.hr_officers(doc.branch))
    users.discard(frappe.session.user)
    message = _("{0} is reopened. Put the attendance right, then Amend the sheet and send it again.").format(doc.title)
    if drafts:
        message += " " + _("{0} draft salary slips were made from it: make them again once it is verified.").format(
            len(drafts))
    people.notify(sorted(user for user in users if user), DOCTYPE, doc.name, message)


def _tell_step(doc, old_state, new_state, before):
    """The General Manager is asked to verify; a return goes back to whoever prepared it and the branch's HR."""
    gms = people.people_for(approval.GM, doc.branch)
    if new_state == approval.PENDING_GM:
        message = _("{0}: the attendance is ready for you to verify.").format(doc.title)
        people.notify(gms, DOCTYPE, doc.name, message)
        people.assign(DOCTYPE, doc.name, gms, message)
    elif new_state == approval.DRAFT and old_state == approval.PENDING_GM:
        people.withdraw(DOCTYPE, doc.name, gms)
        users = {before.get("prepared_by") if before else None} | set(people.hr_officers(doc.branch))
        people.notify(sorted(user for user in users if user), DOCTYPE, doc.name,
                      _("{0} came back: {1}").format(doc.title, doc.get("return_remarks") or ""))


def _clashes(doc):
    """The branch's other live sheets of the same payroll on any of these days."""
    if not (doc.get("company") and doc.get("branch") and doc.get("pay_kind") and doc.get("from_date")
            and doc.get("to_date")):
        return []
    return frappe.get_all(DOCTYPE, filters={
        "company": doc.company, "branch": doc.branch, "pay_kind": doc.pay_kind, "docstatus": ["!=", 2],
        "name": ["!=", doc.name or ""], "from_date": ["<=", doc.to_date], "to_date": [">=", doc.from_date]},
        pluck="name", limit_page_length=0)


def _paid_slips(doc):
    employees = [row.employee for row in doc.get("employees") or [] if row.get("employee")]
    if not employees:
        return []
    slips = set(frappe.get_all(SLIP, filters={
        "employee": ["in", employees], "docstatus": 1, "start_date": ["<=", doc.to_date],
        "end_date": [">=", doc.from_date]}, pluck="name", limit_page_length=0))
    # a weekly slip pays the days on it, which can lie before its own dates (weekly_pay.py)
    slips |= {row.parent for row in frappe.get_all(WEEKLY_DAY, filters={
        "employee": ["in", employees], "docstatus": 1,
        "attendance_date": ["between", [doc.from_date, doc.to_date]]}, fields=["parent"], limit_page_length=0)}
    return sorted(slips)


def _draft_slips(doc):
    employees = [row.employee for row in doc.get("employees") or [] if row.get("employee")]
    if not employees:
        return []
    return frappe.get_all(SLIP, filters={"employee": ["in", employees], "docstatus": 0,
                                         "start_date": ["<=", doc.to_date], "end_date": [">=", doc.from_date]},
                          pluck="name", limit_page_length=0)


# ── 2. What the sheet reads ───────────────────────────────────────────
def _read(doc):
    """The branch's people for the sheet's days, each with the Board's letters counted, and what stops the sheet:
    {"rows": [line], "issues": [what to put right]}."""
    from hrms_addon.hrms_addon import attendance, attendance_board as board

    days = rules.days_between(doc.get("from_date"), doc.get("to_date"))
    found = _people(doc) if days else {}
    if not found:
        return {"rows": [], "issues": []}
    start, end = days[0], days[-1]
    employees = list(found)
    marked = board._attendance(start, end, employees)
    clocked = board._clocked(start, end, employees)
    off_duty = attendance._off_duty_between(employees, start, end)
    lines = board._register_rows(found, marked, off_duty, _holidays(found, start, end, doc.company), days,
                                 attendance.all_shift_hours(), clocked)
    overtime = _overtime_hours(employees, start, end)
    rows, issues = [], []
    for line in lines:
        person = found[line["employee"]]
        statuses = {day: row.status for day, row in (marked.get(line["employee"]) or {}).items()}
        figures = rules.person_figures(person, line["days"], line["clock"], statuses, overtime.get(line["employee"]),
                                       days)
        rows.append(dict(figures, employee=person.name, employee_name=person.employee_name,
                         department=person.department))
        issues += rules.person_issues(dict(person, employee=person.name), line["days"], line["clock"], days)
    issues += _waiting(found, start, end)
    issues.sort(key=lambda row: (str(row["from_date"]), row.get("employee_name") or "", row["issue"]))
    return {"rows": rows, "issues": issues}


PERSON_FIELDS = ("name", "employee_name", "branch", "department", "designation", "employment_type", "relieving_date",
                 "holiday_list", "status", "attendance_device_id", "default_shift", "date_of_joining",
                 "custom_pay_category")


def _people(doc):
    """{employee: row} of the branch's active people the sheet is for, by name (rules.on_sheet): those with a salary
    structure assigned by its last day."""
    found = frappe.get_all("Employee", filters={
        "company": doc.company, "branch": doc.branch, "date_of_joining": ["<=", doc.to_date],
        "status": rules.ACTIVE}, fields=list(PERSON_FIELDS), order_by="employee_name asc",
        limit_page_length=0)
    assigned = _assigned([row.name for row in found], doc.company, doc.to_date)
    for row in found:
        row["salary_structure"] = row.name in assigned
    return {row.name: row for row in found if rules.on_sheet(row, doc.pay_kind, doc.from_date, doc.to_date)}


def _assigned(employees, company, last):
    """Those of the employees with a salary structure assigned by the day: a submitted Salary Structure Assignment of
    the company from that day or before, as Frappe HR's payroll picks whom it pays (get_filtered_employees)."""
    if not employees:
        return set()
    return set(frappe.get_all("Salary Structure Assignment", filters={
        "docstatus": 1, "company": company, "employee": ["in", employees], "from_date": ["<=", last]},
        pluck="employee", limit_page_length=0))


def _holidays(found, start, end, company):
    """The days off each person's holiday list keeps, else the company's (as the Board reads them)."""
    lists = {row.holiday_list for row in found.values() if row.holiday_list}
    default = frappe.db.get_value("Company", company, "default_holiday_list") if company else None
    if default:
        lists.add(default)
    kept = {}
    for name in lists:
        kept[name] = {getdate(row.holiday_date) for row in frappe.get_all(
            "Holiday", filters={"parent": name, "parenttype": "Holiday List", "holiday_date": ["between", [start, end]]},
            fields=["holiday_date"], limit_page_length=0)}
    return {"lists": kept, "default": default}


def _overtime_hours(employees, start, end):
    """{employee: the overtime hours their attendance carries}: what overtime sent to payroll wrote there."""
    hours = {}
    for row in frappe.get_all(ATTENDANCE, filters={
            "employee": ["in", employees], "docstatus": 1, "attendance_date": ["between", [start, end]],
            "actual_overtime_duration": [">", 0]}, fields=["employee", "actual_overtime_duration"],
            limit_page_length=0):
        hours[row.employee] = hours.get(row.employee, 0.0) + float(row.actual_overtime_duration or 0)
    return hours


def _waiting(found, start, end):
    """The requests still on their way that would change a day of the sheet: lines of what to put right."""
    from hrms_addon.hrms_addon import late_notice_approval, leave_approval, off_duty_approval, overtime_approval

    employees = list(found)
    out = []

    def add(rows, issue, doctype, first="from_date", last="to_date"):
        for row in rows:
            person = dict(found[row.employee], employee=row.employee)
            out.append(rules.request_issue(person, {
                "name": row.name, "from_date": max(getdate(row.get(first)), start),
                "to_date": min(getdate(row.get(last) or row.get(first)), end)}, issue, doctype))

    overlapping = {"from_date": ["<=", end], "to_date": [">=", start]}
    add(frappe.get_all("Leave Application", filters=dict(overlapping, employee=["in", employees], docstatus=0, **{
        leave_approval.STATUS_FIELD: ["in", list(leave_approval.PENDING_STATES)]}),
        fields=["name", "employee", "from_date", "to_date"], limit_page_length=0),
        rules.LEAVE_WAITING, "Leave Application")
    add(frappe.get_all("Attendance Request", filters=dict(overlapping, employee=["in", employees], docstatus=0),
                       fields=["name", "employee", "from_date", "to_date"], limit_page_length=0),
        rules.ATTENDANCE_REQUEST_WAITING, "Attendance Request")
    add(frappe.get_all("Off Duty Request", filters={
        "employee": ["in", employees], "docstatus": 0, "status": ["in", list(off_duty_approval.PENDING_STATES)],
        "off_date": ["between", [start, end]]}, fields=["name", "employee", "off_date"], limit_page_length=0),
        rules.OFF_DUTY_WAITING, "Off Duty Request", "off_date", "off_date")
    add(frappe.get_all("Late Arrival Notice", filters={
        "employee": ["in", employees], "docstatus": 0, "in_advance": 1,
        "status": ["in", list(late_notice_approval.PENDING_STATES)], "arrival_date": ["between", [start, end]]},
        fields=["name", "employee", "arrival_date"], limit_page_length=0),
        rules.LATE_NOTICE_WAITING, "Late Arrival Notice", "arrival_date", "arrival_date")
    lines = {}
    for row in frappe.get_all("Overtime Request Employee", filters={"parenttype": overtime_approval.DOCTYPE,
                                                                    "employee": ["in", employees]},
                              fields=["parent", "employee"], limit_page_length=0):
        lines.setdefault(row.parent, set()).add(row.employee)
    if lines:
        for request in frappe.get_all(overtime_approval.DOCTYPE, filters={
                "name": ["in", sorted(lines)], "docstatus": ["<", 2], "overtime_date": ["between", [start, end]],
                "status": ["in", [*overtime_approval.PENDING_STATES, overtime_approval.COSTED]]},
                fields=["name", "status", "overtime_date"], limit_page_length=0):
            issue = rules.OVERTIME_NOT_SENT if request.status == overtime_approval.COSTED else rules.OVERTIME_WAITING
            add([frappe._dict(name=request.name, employee=employee, overtime_date=request.overtime_date)
                 for employee in sorted(lines[request.name])], issue, overtime_approval.DOCTYPE,
                "overtime_date", "overtime_date")
    return out


def _write(doc, fresh):
    doc.set("employees", [])
    for row in fresh["rows"]:
        doc.append("employees", row)
    doc.set("issues", [])
    for row in fresh["issues"][:rules.ISSUE_ROWS]:
        doc.append("issues", row)
    doc.issues_count = len(fresh["issues"])
    doc.people = len(fresh["rows"])
    for field, value in rules.totals(fresh["rows"]).items():
        doc.set("total_" + field, value)
    doc.read_on = now_datetime()


def _plain(row):
    return {field: row.get(field) for field in ("employee", "employee_name", *rules.FIGURES)}


@frappe.whitelist()
def weekly_dates(company=None, branch=None):
    """The days a new weekly sheet covers: on from the branch's last weekly sheet, else the last weekly payroll."""
    if not frappe.has_permission(DOCTYPE, "create"):
        return {}
    last_sheet = frappe.get_all(DOCTYPE, filters={"company": company, "branch": branch, "pay_kind": rules.WEEKLY,
                                                  "docstatus": ["!=", 2]},
                                fields=["to_date"], order_by="to_date desc", limit=1) if company and branch else []
    last_paid = frappe.get_all("Payroll Entry", filters={"company": company, "payroll_frequency": rules.WEEKLY,
                                                         "docstatus": 1},
                               fields=["end_date"], order_by="end_date desc", limit=1) if company else []
    first, last = rules.weekly_dates(last_sheet[0].to_date if last_sheet else None,
                                     last_paid[0].end_date if last_paid else None, today())
    return {"from_date": str(first), "to_date": str(last)}


# ── 3. A verified day does not change ─────────────────────────────────
def verified_sheets(first, last, company=None, employees=None):
    """The verified sheets on any of these days, each with its people ("employees"), those given if any."""
    filters = {"docstatus": 1, "from_date": ["<=", last], "to_date": [">=", first]}
    if company:
        filters["company"] = company
    sheets = frappe.get_all(DOCTYPE, filters=filters, fields=["name", "branch", "from_date", "to_date", "verified_by",
                                                               "verified_on"], limit_page_length=0)
    if not sheets:
        return []
    row_filters = {"parenttype": DOCTYPE, "parent": ["in", [sheet.name for sheet in sheets]]}
    if employees is not None:
        row_filters["employee"] = ["in", list(employees)]
    on = {}
    for row in frappe.get_all(ROW, filters=row_filters, fields=["parent", "employee"], limit_page_length=0):
        on.setdefault(row.parent, []).append(row.employee)
    for sheet in sheets:
        sheet["employees"] = on.get(sheet.name, [])
    return sheets


def holding(employee, days):
    """[(day, sheet, branch)] of these days of the employee a verified sheet holds."""
    days = [getdate(day) for day in days or () if day]
    if not (employee and days):
        return []
    sheets = verified_sheets(min(days), max(days), employees=[employee])
    return rules.held(rules.spans_by_employee(sheets).get(employee), days)


def verified(employee, day):
    return bool(holding(employee, [day]))


def _refuse_days(employee, who, days):
    found = holding(employee, days)
    if found:
        frappe.throw(_(rules.lock_message(who or employee, found)), title=_(DOCTYPE))


def verified_messages(lines):
    """For code that writes attendance without saving it (overtime.send): [why] of lines (employee, who, day) on a
    verified day."""
    out = []
    for employee, who, day in lines:
        found = holding(employee, [day])
        if found:
            out.append(_(rules.lock_message(who or employee, found)))
    return out


def refuse_attendance(doc, method=None):
    """Attendance: marked, changed, cancelled or deleted. before_validate, which runs on every insert, save and
    submit even when the validation is skipped (attendance._mark_automatic)."""
    if not (doc.get("employee") and doc.get("attendance_date")):
        return
    if method == "on_trash" and cint(doc.get("docstatus")) == 2:
        return
    _refuse_days(doc.employee, doc.get("employee_name"), [doc.attendance_date])


def refuse_leave(doc, method=None):
    """Leave Application approved, or cancelled once approved: Frappe HR rewrites its days on the attendance
    straight in the database (leave_application.update_attendance, cancel_attendance)."""
    if doc.get("status") != "Approved":
        return
    _refuse_days(doc.employee, doc.get("employee_name"), rules.days_between(doc.from_date, doc.to_date))


def refuse_attendance_request(doc, method=None):
    """Attendance Request submitted or cancelled: Frappe HR changes a marked day straight in the database."""
    _refuse_days(doc.employee, doc.get("employee_name"), rules.days_between(doc.from_date, doc.to_date))


def refuse_off_duty(doc, method=None):
    """Off Duty Request approved, or cancelled once approved: the day off is written on the attendance."""
    from hrms_addon.hrms_addon import off_duty_approval

    if method == "before_cancel":
        if doc.get("status") != off_duty_approval.APPROVED:
            return
    elif (doc.get(off_duty_approval.STATE_FIELD) or doc.get("status")) != off_duty_approval.APPROVED:
        return
    _refuse_days(doc.employee, doc.get("employee_name"), [doc.off_date])


def refuse_late_notice(doc, method=None):
    """Late Arrival Notice acknowledged in advance: the day becomes a full day on the attendance."""
    from hrms_addon.hrms_addon import late_notice_approval

    state = doc.get(late_notice_approval.STATE_FIELD) or doc.get("status")
    if state != late_notice_approval.ACKNOWLEDGED or not cint(doc.get("in_advance")):
        return
    _refuse_days(doc.employee, doc.get("employee_name"), [doc.arrival_date])


class ShiftTypeVerified:
    """Auto attendance marks every working day with no attendance Absent: never a verified one. (A punch on a
    verified day is refused by refuse_attendance, and Frappe HR sets that punch aside with the reason.)"""

    def get_dates_for_attendance(self, employee):
        days = super().get_dates_for_attendance(employee)
        if not days:
            return days
        found = {day for day, _sheet, _branch in holding(employee, days)}
        return [day for day in days if getdate(day) not in found]


# ── 4. The payroll ────────────────────────────────────────────────────
def gate_on():
    return rules.gate_on(frappe.db.get_singles_dict(SETTINGS))


def payroll_problems(doc):
    """The lines saying which branches stop a payroll, or []."""
    if not gate_on() or cint(doc.get("salary_slip_based_on_timesheet")):
        return []
    found = _payroll_people(doc)
    if not found:
        return []
    days = _days_paid(doc, found)
    first, last = _range(doc, days)
    if not (first and last):
        return []
    sheets = verified_sheets(first, last, company=doc.get("company"), employees=[row["employee"] for row in found])
    gaps = rules.payroll_gaps(found, sheets, doc.start_date, doc.end_date, days)
    if not gaps:
        return []
    waiting = _waiting_states(doc, [branch for branch in gaps if branch], first, last)
    return rules.gaps_message(gaps, waiting, {sheet.branch for sheet in sheets})


def refuse_payroll(doc):
    lines = payroll_problems(doc)
    if lines:
        frappe.throw(_("Each branch verifies its attendance before payroll pays it.") + "<br>"
                     + "<br>".join(_(line) for line in lines), title=_(DOCTYPE))


class PayrollEntryVerified:
    def before_submit(self):
        # submitting the payroll is what makes its slips (Frappe HR's on_submit)
        refuse_payroll(self)
        self.flags.ha_attendance_verified = True
        return super().before_submit()

    @frappe.whitelist(methods=["POST"])
    def create_salary_slips(self):
        if not self.flags.get("ha_attendance_verified"):
            refuse_payroll(self)
        return super().create_salary_slips()

    @frappe.whitelist(methods=["POST"])
    def submit_salary_slips(self):
        refuse_payroll(self)
        return super().submit_salary_slips()


def slip_before_submit(doc, method=None):
    """A slip submitted on its own pays no day no verified sheet covers. One its payroll submits was checked with
    the payroll (PayrollEntryVerified.submit_salary_slips), and is not stopped halfway through the run."""
    if frappe.flags.get("via_payroll_entry") or not gate_on() or cint(doc.get("salary_slip_based_on_timesheet")):
        return
    days = None
    if weekly_pay_rules.on_weekly_pay(doc):
        days = {doc.employee: [getdate(row.attendance_date) for row in doc.get("custom_weekly_days") or []
                               if row.get("attendance_date")]}
        if not days[doc.employee]:
            return
    first, last = _range(doc, days)
    person = frappe.db.get_value("Employee", doc.employee, ["branch", "status"], as_dict=True) or {}
    found = rules.payroll_people([{"employee": doc.employee, "employee_name": doc.get("employee_name") or doc.employee,
                                   "branch": person.get("branch"), "status": person.get("status")}])
    if not found:
        return
    sheets = verified_sheets(first, last, employees=[doc.employee])
    gaps = rules.payroll_gaps(found, sheets, doc.start_date, doc.end_date, days)
    if gaps:
        lines = rules.gaps_message(gaps, _waiting_states(doc, [branch for branch in gaps if branch], first, last),
                                   {sheet.branch for sheet in sheets})
        frappe.throw(_("Each branch verifies its attendance before payroll pays it.") + "<br>"
                     + "<br>".join(_(line) for line in lines), title=_(DOCTYPE))


@frappe.whitelist()
def payroll_branches(payroll_entry):
    """The payroll form's line per branch: how many it pays, whether their days are verified, and who verified."""
    run = frappe.get_doc("Payroll Entry", payroll_entry)
    run.check_permission("read")
    if not gate_on() or cint(run.get("salary_slip_based_on_timesheet")):
        return {"on": 0, "lines": []}
    found = _payroll_people(run)
    if not found:
        return {"on": 1, "lines": []}
    days = _days_paid(run, found)
    first, last = _range(run, days)
    sheets = verified_sheets(first, last, company=run.company, employees=[row["employee"] for row in found])
    waiting = _waiting_states(run, sorted({row["branch"] for row in found if row["branch"]}), first, last)
    lines = rules.branch_lines(found, sheets, waiting, run.start_date, run.end_date, days)
    for line in lines:
        for sheet in line["sheets"]:
            sheet["verified_by"] = frappe.utils.get_fullname(sheet["verified_by"]) if sheet.get("verified_by") else ""
            sheet["verified_on"] = str(sheet.get("verified_on") or "")
    return {"on": 1, "lines": lines}


def _payroll_people(doc):
    """The payroll's people its branches verify: the active ones (rules.payroll_people)."""
    employees = list(dict.fromkeys(row.employee for row in doc.get("employees") or [] if row.get("employee")))
    if not employees:
        return []
    found = {row.name: row for row in frappe.get_all("Employee", filters={"name": ["in", employees]},
                                                     fields=["name", "employee_name", "branch", "status"],
                                                     limit_page_length=0)}
    return rules.payroll_people([
        {"employee": employee, "employee_name": (found.get(employee) or {}).get("employee_name") or employee,
         "branch": (found.get(employee) or {}).get("branch"), "status": (found.get(employee) or {}).get("status")}
        for employee in employees])


def _days_paid(doc, found):
    """A weekly payroll pays the days still unpaid, which can lie before its Start (weekly_pay.days_to_pay); any
    other pays every day of its dates (None)."""
    if not weekly_pay_rules.on_weekly_pay(doc):
        return None
    from hrms_addon.hrms_addon import weekly_pay

    paid = weekly_pay.days_to_pay([row["employee"] for row in found], doc.get("start_date"), doc.get("end_date"),
                                  doc.get("company"))
    return {employee: [getdate(day["attendance_date"]) for day in rows] for employee, rows in paid.items()}


def _range(doc, days):
    first, last = doc.get("start_date"), doc.get("end_date")
    first, last = (getdate(first) if first else None), (getdate(last) if last else None)
    every = [day for rows in (days or {}).values() for day in rows]
    if every:
        first = min([day for day in (first, min(every)) if day])
        last = max([day for day in (last, max(every)) if day])
    return first, last


def _waiting_states(doc, branches, first, last):
    """{branch: the step its sheet for these days stands at} of the sheets not yet verified."""
    if not branches:
        return {}
    kind = rules.WEEKLY if weekly_pay_rules.on_weekly_pay(doc) else rules.MONTHLY
    return {row.branch: row.get(approval.STATE_FIELD) or row.status for row in frappe.get_all(DOCTYPE, filters={
        "company": doc.get("company"), "branch": ["in", list(branches)], "docstatus": 0, "pay_kind": kind,
        "from_date": ["<=", last], "to_date": [">=", first]}, fields=["branch", "status", approval.STATE_FIELD],
        limit_page_length=0)}


def setup_workflows_on_migrate():
    workflows.setup_on_migrate(approval, "Attendance Verification workflow")
