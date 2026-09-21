# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance and shift management on the site: Luuka's three forms, the
26-to-25 cycle, and the register they print.

The rules are in attendance_rules.py, without a Frappe import
(scripts/verify_attendance.py); the machines are in devices.py.

  off_duty_*   LPL/HR/25, signed by the Supervisor then the Section
               Manager, with remarks for the HR Manager. An approved
               request marks the day off on the attendance, so the payroll
               reconciliation stops treating it as an absence — which is
               what the Payroll Officer does by hand today (Reward &
               Compensation, 4.9).
  overtime_*   LPL/HR/14: the sheet of names, sections and durations, a
               requesting officer, an authoriser, and the food coupons HR
               issues afterwards.
  gate_pass_*  leaving the premises before the hours are done, and the
               hours away when the employee comes back.
  register     the Employee Attendance Form (LPL/HR/07) over a cycle: a
               row per employee, a column per day from the 26th to the
               25th, and the day and night tallies underneath.
  daily        the two things the minutes ask for: top management marked
               present without punching, and a gate pass nobody closed.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, time_diff_in_hours, today

from hrms_addon.hrms_addon import attendance_rules as rules, people

CASUAL = "casual"


# ── LPL/HR/25: the day off ────────────────────────────────────────────
def off_duty_validate(doc, method=None):
    if not doc.get("request_date"):
        doc.request_date = today()
    if not doc.get("section") and doc.get("employee"):
        doc.section = frappe.db.get_value("Employee", doc.employee, "department")
    _check_off_duty_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or "Draft"
    if doc.docstatus == 1 and doc.status not in ("Approved", "Rejected"):
        doc.status = "Approved"


def _off_duty_facts(doc):
    return {
        "employee": doc.get("employee"), "off_date": doc.get("off_date"), "reason": doc.get("reason"),
        "kind": doc.get("kind"),
        "date_of_joining": frappe.db.get_value("Employee", doc.employee, "date_of_joining")
        if doc.get("employee") else None,
    }


def _check_off_duty_step(doc):
    """The two signatures the paper carries, stamped as each is given."""
    from hrms_addon.hrms_addon import off_duty_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_SUPERVISOR and old_state in (None, approval.DRAFT):
            errors = rules.off_duty_errors(_off_duty_facts(doc)) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Off Duty Request"))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_off_duty(doc, new_state)


def _tell_off_duty(doc, state):
    from hrms_addon.hrms_addon import off_duty_approval as approval

    role = approval.ROLE_WAITING[state]
    users = people.people_for(role, doc.get("branch"), doc.get("department"))
    message = _("Off-duty request from {0} for {1}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.format_date(doc.get("off_date")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message, date=doc.get("off_date"))


def off_duty_on_submit(doc, method=None):
    """Approved: the day is marked off on the attendance, so it is no longer
    read as an absence."""
    doc.db_set("status", "Approved", update_modified=False)
    _mark_off_duty(doc)
    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    people.notify([user], doc.doctype, doc.name,
                  _("Your off-duty request for {0} was approved ({1}).").format(
                      frappe.utils.format_date(doc.off_date), doc.kind))


def _mark_off_duty(doc):
    """The day's Attendance says the employee was off duty, not absent."""
    name = frappe.db.get_value("Attendance", {"employee": doc.employee, "attendance_date": doc.off_date,
                                              "docstatus": ["!=", 2]}, "name")
    if not name:
        return
    attendance = frappe.get_doc("Attendance", name)
    if attendance.docstatus == 1 and attendance.status == "Absent":
        # a submitted attendance only moves by amendment, so say so rather
        # than pretending it changed
        frappe.msgprint(_("{0} is already submitted as Absent. Amend it to record the off duty.").format(name),
                        indicator="orange", alert=True)
    elif attendance.docstatus == 0:
        attendance.db_set("status", "On Leave" if doc.kind == "Annual Leave" else "Absent", update_modified=False)
    doc.db_set("attendance", name, update_modified=False)


def off_duty_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)


# ── LPL/HR/14: the overtime ───────────────────────────────────────────
def overtime_validate(doc, method=None):
    doc.title = " ".join(str(part) for part in (doc.get("overtime_date"), doc.get("section")) if part)
    if not doc.get("requested_on"):
        doc.requested_on = today()
    for row in doc.get("employees") or []:
        if row.employee and not row.employment:
            row.employment = _employment(row.employee)
        if row.employee and not row.section:
            row.section = doc.get("section") or frappe.db.get_value("Employee", row.employee, "department")
    doc.total_hours = sum(flt(row.hours) for row in doc.get("employees") or [])
    # what sort of day it is, and so what it is worth (overtime.py)
    from hrms_addon.hrms_addon import overtime

    overtime.fill_day_and_rate(doc)
    counted = rules.coupons([row.as_dict() for row in doc.get("employees") or []])
    doc.coupons_permanent = counted.get("Permanent", 0)
    doc.coupons_casual = counted.get("Casual", 0)
    if doc.docstatus == 0:
        doc.status = "Draft"
    errors = rules.overtime_errors({
        "overtime_date": doc.get("overtime_date"), "requested_by": doc.get("requested_by"),
        "section": doc.get("section"),
        "employees": [row.as_dict() for row in doc.get("employees") or []],
    })
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Overtime Request"))


def _employment(employee):
    """Permanent or Casual, from the employee's Employment Type."""
    kind = (frappe.db.get_value("Employee", employee, "employment_type") or "").lower()
    return "Casual" if CASUAL in kind else "Permanent"


def overtime_on_submit(doc, method=None):
    """Requested: whoever authorises overtime for the plant is told."""
    doc.db_set("status", "Requested", update_modified=False)
    approvers = people.people_for("Production Manager", doc.get("branch"), doc.get("department")) \
        or people.people_for("Head of Department", doc.get("branch"), doc.get("department"))
    message = _("Overtime for {0} on {1}: {2} employee(s), {3} hours.").format(
        doc.get("section") or doc.get("department") or "", frappe.utils.format_date(doc.overtime_date),
        len(doc.get("employees") or []), doc.total_hours)
    people.notify(approvers, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, approvers, message, date=doc.overtime_date)


def overtime_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)


@frappe.whitelist(methods=["POST"])
def authorise_overtime(name, remarks=None):
    """The authorising officer signs LPL/HR/14."""
    doc = frappe.get_doc("Overtime Request", name)
    doc.check_permission("submit")
    if doc.docstatus != 1:
        frappe.throw(_("Submit the overtime request first."))
    if doc.status == "Authorised":
        return doc.status
    doc.db_set({"status": "Authorised", "authorised_by": frappe.session.user, "authorised_on": today(),
                "authority_remarks": remarks or doc.get("authority_remarks")}, update_modified=False)
    officers = people.hr_officers(doc.get("branch"), doc.get("department"))
    people.notify(officers, doc.doctype, doc.name,
                  _("Overtime authorised for {0}: {1} permanent and {2} casual coupon(s) to "
                    "issue, and the cost to check before payroll.").format(
                      frappe.utils.format_date(doc.overtime_date), doc.coupons_permanent,
                      doc.coupons_casual))
    return doc.status


@frappe.whitelist(methods=["POST"])
def reject_overtime(name, reason):
    doc = frappe.get_doc("Overtime Request", name)
    doc.check_permission("submit")
    doc.db_set({"status": "Rejected", "authority_remarks": reason, "authorised_by": frappe.session.user,
                "authorised_on": today()}, update_modified=False)
    return doc.status


@frappe.whitelist(methods=["POST"])
def issue_coupons(name):
    """HR use only: the food coupons LPL/HR/14 ends with."""
    doc = frappe.get_doc("Overtime Request", name)
    doc.check_permission("write")
    if doc.status != "Authorised":
        frappe.throw(_("Coupons are issued once the overtime is authorised."))
    doc.db_set({"coupons_issued": 1, "coupons_by": frappe.session.user, "coupons_on": today()},
               update_modified=False)
    return {"permanent": doc.coupons_permanent, "casual": doc.coupons_casual}


# ── the gate pass ─────────────────────────────────────────────────────
def gate_pass_validate(doc, method=None):
    if not doc.get("section") and doc.get("employee"):
        doc.section = frappe.db.get_value("Employee", doc.employee, "department")
    if doc.get("out_time") and doc.get("actual_return"):
        doc.hours_away = round(time_diff_in_hours(doc.actual_return, doc.out_time), 2)
    if doc.docstatus == 0:
        doc.status = "Draft"
    errors = rules.gate_pass_errors({
        "employee": doc.get("employee"), "pass_date": doc.get("pass_date"), "out_time": doc.get("out_time"),
        "expected_return": doc.get("expected_return"), "reason": doc.get("reason"),
    })
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Gate Pass"))


def gate_pass_on_submit(doc, method=None):
    doc.db_set({"status": "Issued", "authorised_by": frappe.session.user, "authorised_on": today()},
               update_modified=False)


def gate_pass_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)


@frappe.whitelist(methods=["POST"])
def record_return(name, came_back=None):
    """The employee is back through the gate."""
    doc = frappe.get_doc("Gate Pass", name)
    doc.check_permission("write")
    back = get_datetime(came_back or frappe.utils.now())
    doc.db_set({"actual_return": back, "status": "Returned",
                "hours_away": round(time_diff_in_hours(back, doc.out_time), 2)}, update_modified=False)
    return doc.status


# ── LPL/HR/07: the register ───────────────────────────────────────────
@frappe.whitelist()
def register(year, month, branch=None, department=None, section=None):
    """The Employee Attendance Form over a cycle: the days it rules, a row
    per employee with a code in each cell, and the tallies underneath."""
    year, month = cint(year), cint(month)
    start, end = rules.cycle_window(year, month)
    days = rules.cycle_days(year, month)
    filters = {"status": "Active"}
    for field, value in (("branch", branch), ("department", department)):
        if value:
            filters[field] = value
    employees = frappe.get_all("Employee", filters=filters,
                               fields=["name", "employee_name", "employment_type", "department", "branch",
                                       "attendance_device_id"],
                               order_by="employee_name asc")
    if not employees:
        return {"days": [str(day) for day in days], "rows": [], "tallies": {}, "from": str(start), "to": str(end)}
    marked = _attendance_between([employee.name for employee in employees], start, end)
    off_duty = _off_duty_between([employee.name for employee in employees], start, end)
    rows = []
    for employee in employees:
        by_day = {}
        for day in days:
            found = marked.get((employee.name, day)) or {}
            by_day[day] = rules.register_code({
                "status": found.get("status"), "shift": found.get("shift"),
                "leave_type": found.get("leave_type"),
                "off_duty": (employee.name, day) in off_duty,
            })
        rows.append({
            "employee": employee.name, "employee_name": employee.employee_name,
            "badge_no": employee.attendance_device_id,
            "employment": "Casual" if CASUAL in (employee.employment_type or "").lower() else "Permanent",
            "department": employee.department, "days": by_day,
            "overtime": round(sum(flt((marked.get((employee.name, day)) or {}).get("overtime"))
                                  for day in days), 2),
        })
    counted = rules.tallies(rows, days)
    return {
        "from": str(start), "to": str(end), "days": [str(day) for day in days],
        "rows": [dict(row, days={str(day): code for day, code in row["days"].items()}) for row in rows],
        "tallies": {name: {str(day): count for day, count in per_day.items()} for name, per_day in counted.items()},
        "legend": rules.CODE_MEANING,
    }


def _attendance_between(employees, start, end):
    found = {}
    for row in frappe.get_all(
            "Attendance",
            filters={"employee": ["in", employees], "attendance_date": ["between", (start, end)],
                     "docstatus": ["!=", 2]},
            fields=["employee", "attendance_date", "status", "shift", "leave_type", "working_hours"]):
        found[(row.employee, getdate(row.attendance_date))] = {
            "status": row.status, "shift": row.shift, "leave_type": row.leave_type,
            "overtime": rules.overtime_hours(row.working_hours),
        }
    return found


def _off_duty_between(employees, start, end):
    return {(row.employee, getdate(row.off_date)) for row in frappe.get_all(
        "Off Duty Request",
        filters={"employee": ["in", employees], "off_date": ["between", (start, end)], "docstatus": 1,
                 "status": "Approved"},
        fields=["employee", "off_date"])}


# ── what the minutes ask the system to watch ──────────────────────────
def daily():
    """Top management marked present without punching, and a gate pass
    nobody closed."""
    day = add_days(today(), -1)
    _mark_automatic(day)
    _chase_open_passes()
    frappe.db.commit()


def _mark_automatic(day):
    """"Top management officials should be given automatic attendance" —
    both minutes ask for it."""
    holidays = set()
    for employee in frappe.get_all("Employee", filters={"status": "Active", "custom_automatic_attendance": 1},
                                   fields=["name", "company", "holiday_list", "default_shift"]):
        if frappe.db.exists("Attendance", {"employee": employee.name, "attendance_date": day,
                                           "docstatus": ["!=", 2]}):
            continue
        if employee.holiday_list and (employee.holiday_list, day) not in holidays:
            if frappe.db.exists("Holiday", {"parent": employee.holiday_list, "holiday_date": day}):
                holidays.add((employee.holiday_list, day))
                continue
        attendance = frappe.get_doc({
            "doctype": "Attendance", "employee": employee.name, "attendance_date": day, "status": "Present",
            "company": employee.company, "shift": employee.default_shift,
        })
        attendance.flags.ignore_permissions = True
        attendance.flags.ignore_validate = True
        attendance.insert()
        attendance.submit()


def _chase_open_passes():
    """A gate pass whose day has passed and nobody recorded a return."""
    for name in frappe.get_all("Gate Pass",
                               filters={"docstatus": 1, "status": "Issued", "pass_date": ["<", today()]},
                               pluck="name"):
        doc = frappe.get_doc("Gate Pass", name)
        doc.db_set("status", "Not Returned", update_modified=False)
        officers = people.hr_officers(doc.get("branch"), doc.get("department"))
        people.notify(officers, doc.doctype, doc.name,
                      _("{0} left on a gate pass on {1} and no return was recorded.").format(
                          doc.get("employee_name") or doc.employee, frappe.utils.format_date(doc.pass_date)))


def setup_workflows_on_migrate():
    """after_migrate: the off-duty request's two signatures (workflows.py)."""
    from hrms_addon.hrms_addon import off_duty_approval, workflows

    workflows.setup_on_migrate(off_duty_approval, "Off Duty Request workflow")
