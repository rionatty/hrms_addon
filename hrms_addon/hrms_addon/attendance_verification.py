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
  days_to_mark,       the Mark Attendance button of a sheet with HR: the days
  mark_days           on it nobody marked, of its own people only, marked
                      Present or as picked; many go to the background
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
from frappe.utils import cint, flt, getdate, now_datetime, today

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
    # a weekly sheet's Hours Worked: the hours the weekly payroll pays for the days worked
    weekly = doc.get("pay_kind") == rules.WEEKLY
    standard = _full_day() if weekly else None
    # and the weeks Casual Hours Sheets give the casuals paid by the hour: their hours, overtime and days, not the
    # attendance's, as the weekly payroll pays them (casual_hours.for_verification; Luuka, 12 Nov 2026: "for casuals
    # the attendance verification should be from casual hours sheet")
    if weekly:
        from hrms_addon.hrms_addon import casual_hours

        sheets = casual_hours.for_verification([employee for employee in employees if rules.by_the_hour(found[employee])],
                                               start, end)
    else:
        sheets = {"people": {}, "sheets": {}}
    rows, issues = [], []
    for line in lines:
        person = found[line["employee"]]
        statuses = {day: row.status for day, row in (marked.get(line["employee"]) or {}).items()}
        # a Per Piece casual is paid for their pieces: their days are verified, and their hours are nought
        hours = {day: row.get("working_hours") for day, row in (marked.get(line["employee"]) or {}).items()} \
            if weekly and rules.by_the_hour(person) else None
        given = sheets["people"].get(line["employee"]) or {}
        covered = given.get("covered") or set()
        open_days = [day for day in days if day not in covered]
        figures = rules.person_figures(person, line["days"], line["clock"], statuses,
                                       sum(value for day, value in (overtime.get(line["employee"]) or {}).items()
                                           if day not in covered), open_days, hours, standard)
        if covered:
            inside = rules.person_figures(person, line["days"], line["clock"], statuses, 0, sorted(covered))
            counted = rules.person_figures(person, line["days"], line["clock"], statuses, 0,
                                           sorted(given.get("counted") or ()))
            figures = rules.with_hours_sheet(figures, inside, given, counted)
        rows.append(dict(figures, employee=person.name, employee_name=person.employee_name,
                         department=person.department))
        issues += rules.person_issues(dict(person, employee=person.name), line["days"], line["clock"], open_days)
    issues += _waiting(found, start, end)
    # a sheet's figures are not yet what the payroll pays until its General Manager approves it
    issues += [line for line in (rules.hours_sheet_issue(name, sheet, start, end)
                                 for name, sheet in sorted(sheets["sheets"].items())) if line]
    issues.sort(key=lambda row: (str(row["from_date"]), row.get("employee_name") or "", row["issue"]))
    return {"rows": rows, "issues": issues}


def _full_day():
    """A full day's hours, as the weekly payroll pays a day marked with none (weekly_pay.days_to_pay)."""
    from hrms_addon.hrms_addon import output_pay, output_rules

    return flt(output_pay.settings().get("standard_hours")) or output_rules.STANDARD_HOURS


PERSON_FIELDS = ("name", "employee_name", "branch", "department", "designation", "employment_type", "relieving_date",
                 "holiday_list", "status", "attendance_device_id", "default_shift", "date_of_joining",
                 "custom_pay_category")


def _people(doc):
    """{employee: row} of the branch's active people the sheet is for, by name (rules.on_sheet): on a monthly sheet,
    those with a salary structure assigned by its last day; on a weekly one, every weekly casual."""
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
    """{employee: {date: the overtime hours their attendance carries that day}}: what overtime sent to payroll, or
    an attendance upload, wrote there. By the day, so that a day a Casual Hours Sheet gives is left to the sheet."""
    hours = {}
    for row in frappe.get_all(ATTENDANCE, filters={
            "employee": ["in", employees], "docstatus": 1, "attendance_date": ["between", [start, end]],
            "actual_overtime_duration": [">", 0]}, fields=["employee", "attendance_date", "actual_overtime_duration"],
            limit_page_length=0):
        theirs = hours.setdefault(row.employee, {})
        day = getdate(row.attendance_date)
        theirs[day] = theirs.get(day, 0.0) + float(row.actual_overtime_duration or 0)
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


# ── 2b. Marking the days nobody marked ────────────────────────────────
# Luuka, 8 Nov 2026: "add button to mark attendance and it only filter by those number of employee and those dates".
# The days are read again from the sheet as it stands, and only those picked that are still not marked are marked:
# nobody off the sheet, no day off it, and no day already marked. A few are marked at once; more in the background,
# and the sheet reads its figures again once they are.
MARK_AT_ONCE = 150
MARK_JOB = "hrms_addon.hrms_addon.attendance_verification.mark_job"


def _with_hr(doc):
    """Days are marked on a sheet with HR, by somebody who may mark attendance."""
    doc.check_permission("write")
    if doc.docstatus != 0 or (doc.get(approval.STATE_FIELD) or approval.DRAFT) != approval.DRAFT:
        frappe.throw(_("Days are marked while the sheet is with HR."), title=_(DOCTYPE))
    if not (frappe.has_permission(ATTENDANCE, "create") and frappe.has_permission(ATTENDANCE, "submit")):
        frappe.throw(_("You may not mark attendance."), frappe.PermissionError, title=_(DOCTYPE))


@frappe.whitelist()
def days_to_mark(name):
    """The sheet's people with days nobody marked, each with those days, and every such day."""
    doc = frappe.get_doc(DOCTYPE, name)
    _with_hr(doc)
    found = sorted(rules.days_to_mark(_read(doc)["issues"]).values(),
                   key=lambda person: (person["employee_name"] or "", person["employee"]))
    return {
        "people": [dict(person, days=[str(day) for day in person["days"]],
                        clocked=[str(day) for day in person["clocked"]]) for person in found],
        "days": [str(day) for day in sorted({day for person in found for day in person["days"]})],
        "statuses": list(rules.MARK_STATUSES),
    }


@frappe.whitelist(methods=["POST"])
def mark_days(name, status, employees=None, days=None, leave_type=None):
    """Marks the picked days of the picked people that nobody marked: at once for a few, else in the background."""
    doc = frappe.get_doc(DOCTYPE, name)
    _with_hr(doc)
    leave_type = leave_type if status in rules.MARK_TAKES_LEAVE_TYPE and leave_type else None
    errors = rules.mark_errors(status, leave_type,
                               bool(leave_type) and bool(frappe.db.exists("Leave Type", leave_type)))
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))
    picked = rules.chosen_days(rules.days_to_mark(_read(doc)["issues"]), frappe.parse_json(employees) or [],
                               frappe.parse_json(days) or [])
    if not picked:
        frappe.throw(_("None of the days picked is still not marked. Press Get Attendance to read the sheet again."),
                     title=_(DOCTYPE))
    if len(picked) <= MARK_AT_ONCE:
        return _mark(doc.name, status, leave_type, picked)
    job = frappe.enqueue(MARK_JOB, queue="long", timeout=7200, job_id="hrms_addon_verification_mark::%s" % doc.name,
                         deduplicate=True, name=doc.name, status=status, leave_type=leave_type,
                         picked=[[employee, str(day)] for employee, day in picked], user=frappe.session.user)
    if job is None:
        frappe.throw(_("Days of this sheet are being marked already. You will be told when that is done."),
                     title=_(DOCTYPE))
    return {"queued": len(picked)}


def mark_job(name, status, leave_type, picked, user=None):
    """The background job: the days marked, the sheet read again, and whoever asked told."""
    done = _mark(name, status, leave_type, [(employee, getdate(day)) for employee, day in picked], commit=True)
    title = frappe.db.get_value(DOCTYPE, name, "title") or name
    people.notify([user] if user else [], DOCTYPE, name,
                  "%s: %s" % (title, " ".join(_(line) for line in rules.mark_summary(done["marked"], done["problems"]))))
    return done


def _mark(name, status, leave_type, picked, commit=False):
    """Each day marked and submitted as Upload Attendance marks one, or why not; then the sheet's figures read
    again, while it is still with HR."""
    from hrms_addon.hrms_addon import attendance_upload

    found = {row.name: row for row in frappe.get_all(
        "Employee", filters={"name": ["in", sorted({employee for employee, _day in picked})]},
        fields=["name", "company", "employee_name"], limit_page_length=0)}
    marked, problems = 0, []
    for number, (employee, day) in enumerate(picked, 1):
        person = found.get(employee)
        why = _("No such employee.") if not person else attendance_upload._mark_day(
            {"employee": employee, "attendance_date": day, "status": status, "leave_type": leave_type, "shift": None},
            found)
        if why:
            problems.append(rules.mark_problem((person or {}).get("employee_name") or employee, day, why))
        else:
            marked += 1
        if commit and number % 100 == 0:
            frappe.db.commit()
    doc = frappe.get_doc(DOCTYPE, name)
    read_again = doc.docstatus == 0 and (doc.get(approval.STATE_FIELD) or approval.DRAFT) == approval.DRAFT
    if read_again:
        try:
            doc.save()
        except Exception:
            # the days stay marked; the figures come again with Get Attendance
            frappe.log_error(title="HRMS Addon: %s not read again after marking" % name)
            read_again = False
    if commit:
        frappe.db.commit()
    return {"marked": marked, "problems": problems, "read_again": read_again,
            "summary": [_(line) for line in rules.mark_summary(marked, problems)]}


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
        # a week a Casual Hours Sheet gives, its plant's General Manager approved on the sheet (casual_hours.py)
        days = {doc.employee: [getdate(row.attendance_date) for row in doc.get("custom_weekly_days") or []
                               if row.get("attendance_date") and not row.get("hours_sheet")]}
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
    other pays every day of its dates (None). A Per Piece casual on it is paid for their bags, not their days:
    none of their days is paid (piece_pay.py)."""
    if not weekly_pay_rules.on_weekly_pay(doc):
        return None
    from hrms_addon.hrms_addon import weekly_pay

    names = [row["employee"] for row in found]
    hourly = set(frappe.get_all("Employee", filters={"name": ["in", names],
                                                     "custom_pay_category": weekly_pay_rules.WEEKLY},
                                pluck="name", limit_page_length=0)) if names else set()
    paid = weekly_pay.days_to_pay([name for name in names if name in hourly], doc.get("start_date"),
                                  doc.get("end_date"), doc.get("company"))
    return {name: [getdate(day["attendance_date"]) for day in paid.get(name) or []] for name in names}


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
