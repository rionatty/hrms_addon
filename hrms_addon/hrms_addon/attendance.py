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
  late_notice_*  the minutes' recommendation: an employee who says before
               the shift starts that they will be late, acknowledged by
               their supervisor, is given a full day and is not counted
               late. attendance_validate applies it to the day's
               Attendance however it is marked.
  attendance_validate  what Frappe HR's reading of a day does not say:
               the minutes late and early, a clock-in with no clock-out
               (told to the employee and their supervisor that day), and
               that a day off somebody clocked in on is never an absence.
  daily        the two things the minutes ask for: top management marked
               present without punching, and a gate pass nobody closed.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, time_diff_in_hours, today

from hrms_addon.hrms_addon import attendance_rules as rules, people

CASUAL = "casual"
SHIFT = "Shift Type"
# who reads everybody's attendance: the register and the board are HR's
HR_ROLES = ("HR User", "HR Manager", "System Manager")
# the automatic attendance is caught up over this many days, for a day
# the scheduler did not run
AUTOMATIC_DAYS = 3


def only_hr():
    """The register and the board show everybody's attendance. Frappe HR
    lets every employee read Attendance (their own), so being allowed to
    read it does not make somebody HR."""
    if not set(frappe.get_roles()) & set(HR_ROLES):
        frappe.throw(_("Only HR read the attendance register."), frappe.PermissionError)


# ── A shift's own hours ───────────────────────────────────────────────
def all_shift_hours():
    """{Shift Type: its hours} (attendance_rules.shift_hours): how long
    each shift is and how many of its hours are overtime."""
    return {row.name: rules.shift_hours({"shift_hours": row.get("custom_shift_hours"),
                                         "overtime_hours": row.get("custom_overtime_hours")})
            for row in frappe.get_all(SHIFT, fields=["name", "custom_shift_hours", "custom_overtime_hours"],
                                      limit_page_length=0)}


def shift_hours_of(shift, known=None):
    """One shift's hours. A day with no shift, or a shift that gives none,
    is the twelve with two of overtime."""
    known = all_shift_hours() if known is None else known
    return known.get(shift) or rules.shift_hours(None)


def shift_on(employee, day):
    """The shift an employee works on a day: the one their attendance
    carries, else their shift assignment for the day, else their default."""
    marked = frappe.db.get_value("Attendance", {"employee": employee, "attendance_date": getdate(day),
                                                "docstatus": ["!=", 2]}, "shift")
    if marked:
        return marked
    rows = frappe.get_all("Shift Assignment",
                          filters={"employee": employee, "docstatus": 1, "status": "Active",
                                   "start_date": ["<=", getdate(day)]},
                          fields=["shift_type", "end_date"], order_by="start_date desc")
    assigned = next((row.shift_type for row in rows
                     if not row.end_date or getdate(row.end_date) >= getdate(day)), None)
    return assigned or frappe.db.get_value("Employee", employee, "default_shift")


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
    """The form filed. Approved, the day is what LPL/HR/25 classified it as
    (attendance_rules.off_duty_day): a paid day off marked on the
    attendance, a day of the employee's own leave approved and taken off
    the balance, or nothing where it was not granted. Refused, it is
    refused, and the employee is told why."""
    from hrms_addon.hrms_addon import off_duty_approval as approval

    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    if doc.get("workflow_state") == approval.REJECTED:
        doc.db_set("status", approval.REJECTED, update_modified=False)
        # whoever refused wrote last
        said = next((doc.get(field) for field, _who in reversed(list(approval.REMARK_FIELDS.values()))
                     if doc.get(field)), None)
        people.notify([user], doc.doctype, doc.name, _("Your off-duty request for {0} was refused{1}").format(
            frappe.utils.format_date(doc.off_date), ": %s" % said if said else "."))
        return
    doc.db_set("status", "Approved", update_modified=False)
    day = rules.off_duty_day(doc.kind)
    if day["apply"]:
        from hrms_addon.hrms_addon import leave

        doc.db_set("leave_application", leave.approve_for_off_duty(doc, day["apply"]), update_modified=False)
    elif day["mark"]:
        _mark_off_duty(doc, day["mark"])
    people.notify([user], doc.doctype, doc.name,
                  _("Your off-duty request for {0} was approved ({1}).").format(
                      frappe.utils.format_date(doc.off_date), doc.kind))


def _mark_off_duty(doc, leave_type):
    """A paid day off on the attendance: On Leave, as the Off Duty leave
    type, so the day is paid and is not an absence. A day already marked
    absent is changed, as Frappe HR's own Attendance Request changes a
    marked day; one the employee worked, or is on leave for, is left."""
    found = frappe.db.get_value("Attendance", {"employee": doc.employee, "attendance_date": doc.off_date,
                                               "docstatus": ["!=", 2]},
                                ["name", "status", "leave_application"], as_dict=True)
    action = rules.off_duty_marking(found)
    if action == "create":
        attendance = frappe.get_doc({
            "doctype": "Attendance", "employee": doc.employee, "attendance_date": doc.off_date,
            "status": "On Leave", "leave_type": leave_type,
            "company": frappe.db.get_value("Employee", doc.employee, "company")})
        attendance.flags.ignore_permissions = True
        muted = frappe.flags.mute_messages
        # Frappe HR says "no leave record found" of a day given this way
        frappe.flags.mute_messages = True
        try:
            attendance.insert()
            attendance.submit()
        finally:
            frappe.flags.mute_messages = muted
        name = attendance.name
    else:
        name = found.name
        if action == "change":
            attendance = frappe.get_doc("Attendance", name)
            attendance.db_set({"status": "On Leave", "leave_type": leave_type}, update_modified=False)
            attendance.add_comment("Info", _("A paid day off, not an absence: {0}.").format(doc.name))
    doc.db_set("attendance", name, update_modified=False)


def off_duty_on_cancel(doc, method=None):
    """Cancelled: what the form gave is taken back. The leave it raised is
    cancelled, which returns the day to the balance, and the day it marked
    off comes off the attendance for the clock to read again."""
    doc.db_set("status", "Cancelled", update_modified=False)
    application = doc.get("leave_application")
    if application and frappe.db.get_value("Leave Application", application, "docstatus") == 1:
        leave = frappe.get_doc("Leave Application", application)
        leave.flags.ignore_permissions = True
        leave.cancel()
    marked = doc.get("attendance")
    if marked:
        found = frappe.db.get_value("Attendance", marked, ["docstatus", "status", "leave_type"], as_dict=True)
        if found and found.docstatus == 1 and found.status == "On Leave" \
                and found.leave_type == rules.OFF_DUTY_LEAVE_TYPE:
            attendance = frappe.get_doc("Attendance", marked)
            attendance.flags.ignore_permissions = True
            attendance.flags.ignore_links = True
            attendance.cancel()


def seed_off_duty_leave_type():
    """The Leave Type a paid day off is marked as. Paid, and asked of no
    allocation: nobody applies for it (leave.application_validate). One
    already there is left as Luuka have set it."""
    name = rules.OFF_DUTY_LEAVE_TYPE
    if frappe.db.exists("Leave Type", {"leave_type_name": name}):
        return None
    doc = frappe.get_doc({"doctype": "Leave Type", "leave_type_name": name, "is_lwp": 0})
    doc.insert(ignore_permissions=True)
    return doc.name


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

    closed = overtime.fill_day_and_rate(doc) or []
    counted = rules.coupons([row.as_dict() for row in doc.get("employees") or []])
    doc.coupons_permanent = counted.get("Permanent", 0)
    doc.coupons_casual = counted.get("Casual", 0)
    if doc.docstatus == 0:
        doc.status = "Draft"
    errors = rules.overtime_errors({
        "overtime_date": doc.get("overtime_date"), "requested_by": doc.get("requested_by"),
        "section": doc.get("section"),
        "employees": [row.as_dict() for row in doc.get("employees") or []],
        "full_shift": rules.longest_shift(all_shift_hours().values()),
    })
    # somebody no Overtime Type is open to: said when the request is raised, not when it is costed
    errors += closed
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
    _let_authorise(doc, approvers)


def _let_authorise(doc, users):
    """Whoever is asked to authorise the overtime can. The Authorise button
    and the method behind it ask for the right to submit, which the role of
    the one asked may not carry on a site, and Frappe shares an assigned
    document read-only."""
    from frappe.share import add_docshare

    for user in sorted({user for user in users or [] if user}):
        if not frappe.has_permission(doc.doctype, "submit", doc.name, user=user):
            add_docshare(doc.doctype, doc.name, user, read=1, write=1, submit=1,
                         flags={"ignore_share_permission": True})


def overtime_on_cancel(doc, method=None):
    """Cancelled: what it wrote for payroll is taken back with it."""
    from hrms_addon.hrms_addon import overtime

    overtime.take_back(doc)
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
def reject_overtime(name, reason=None):
    from hrms_addon.hrms_addon import overtime_rules

    doc = frappe.get_doc("Overtime Request", name)
    doc.check_permission("submit")
    errors = overtime_rules.reject_errors(doc.get("status") if doc.docstatus == 1 else None, reason)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Overtime Request"))
    doc.db_set({"status": "Rejected", "authority_remarks": reason, "authorised_by": frappe.session.user,
                "authorised_on": today()}, update_modified=False)
    # the signature above is now whoever refused: who authorised it before stays on the record
    doc.add_comment("Info", _("Refused: {0}").format(reason))
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
    only_hr()
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
    hours = all_shift_hours()
    for row in frappe.get_all(
            "Attendance",
            filters={"employee": ["in", employees], "attendance_date": ["between", (start, end)],
                     "docstatus": ["!=", 2]},
            fields=["employee", "attendance_date", "status", "shift", "leave_type", "working_hours"]):
        found[(row.employee, getdate(row.attendance_date))] = {
            "status": row.status, "shift": row.shift, "leave_type": row.leave_type,
            "overtime": rules.overtime_hours(row.working_hours, shift_hours_of(row.shift, hours)["standard"]),
        }
    return found


def _off_duty_between(employees, start, end):
    return {(row.employee, getdate(row.off_date)) for row in frappe.get_all(
        "Off Duty Request",
        filters={"employee": ["in", employees], "off_date": ["between", (start, end)], "docstatus": 1,
                 "status": "Approved", "kind": ["in", list(rules.OFF_DUTY_GIVEN)]},
        fields=["employee", "off_date"])}


# ── The late arrival notice ───────────────────────────────────────────
def late_notice_validate(doc, method=None):
    from hrms_addon.hrms_addon import late_notice_approval as approval

    _fill_shift(doc)
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {"supervisor_remarks": doc.get("supervisor_remarks")})
        if new_state == approval.PENDING_SUPERVISOR:
            errors = rules.late_notice_errors({
                "employee": doc.get("employee"), "arrival_date": doc.get("arrival_date"),
                "expected_time": doc.get("expected_time"), "reason": doc.get("reason"),
                "shift_start": doc.get("shift_start")}) + errors
            # the notice is given when it is sent
            doc.notified_on = frappe.utils.now_datetime()
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Late Arrival Notice"))
    doc.in_advance = 1 if rules.notified_in_advance(doc.get("notified_on"), doc.get("arrival_date"),
                                                    doc.get("shift_start")) else 0
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    doc.status = new_state or doc.get("status") or approval.DRAFT
    if old_state != new_state and new_state == approval.PENDING_SUPERVISOR:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.get("branch"), doc.get("department"))
        if users:
            message = _("{0} will arrive late on {1}, at about {2}: {3}").format(
                doc.get("employee_name") or doc.employee, frappe.utils.format_date(doc.arrival_date),
                str(doc.expected_time)[:5], doc.reason)
            people.notify(users, doc.doctype, doc.name, message)
            people.assign(doc.doctype, doc.name, users, message)


def _fill_shift(doc):
    """The shift the employee works that day, and when it starts: the
    shift assignment for the day, else their default shift."""
    if not (doc.get("employee") and doc.get("arrival_date")):
        return
    rows = frappe.get_all("Shift Assignment",
                          filters={"employee": doc.employee, "docstatus": 1, "status": "Active",
                                   "start_date": ["<=", doc.arrival_date]},
                          fields=["shift_type", "end_date"], order_by="start_date desc")
    shift = next((row.shift_type for row in rows
                  if not row.end_date or getdate(row.end_date) >= getdate(doc.arrival_date)), None)
    shift = shift or frappe.db.get_value("Employee", doc.employee, "default_shift")
    doc.shift = shift
    doc.shift_start = frappe.db.get_value("Shift Type", shift, "start_time") if shift else None


def late_notice_on_submit(doc, method=None):
    """Acknowledged: a day already marked is given in full now; one not yet
    marked is given in full when it is (attendance_validate)."""
    doc.db_set("status", "Acknowledged", update_modified=False)
    if doc.get("in_advance"):
        _give_full_day(doc)
    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    if user:
        said = (_("Your late arrival on {0} was acknowledged: the day counts in full.") if doc.get("in_advance")
                else _("Your late arrival on {0} was acknowledged, but it was not notified before the shift "
                       "started, so the day counts as punched."))
        people.notify([user], doc.doctype, doc.name, said.format(frappe.utils.format_date(doc.arrival_date)))


def _give_full_day(doc):
    name = frappe.db.get_value("Attendance", {"employee": doc.employee, "attendance_date": doc.arrival_date,
                                              "docstatus": ["!=", 2]}, "name")
    if not name:
        return
    attendance = frappe.get_doc("Attendance", name)
    status, late_entry = rules.full_day(attendance.status, attendance.get("late_entry"), True,
                                        on_leave=bool(attendance.get("leave_application")))
    if (status, late_entry) != (attendance.status, cint(attendance.get("late_entry"))):
        # as Frappe HR's own Attendance Request changes a marked day
        values = {"status": status, "late_entry": late_entry}
        if status != "Half Day" and frappe.get_meta("Attendance").has_field("half_day_status"):
            values["half_day_status"] = None
        if not late_entry and frappe.get_meta("Attendance").has_field("custom_late_minutes"):
            values["custom_late_minutes"] = 0
        attendance.db_set(values, update_modified=False)
        attendance.add_comment("Info", _("A full day: the late arrival was notified in advance ({0}).").format(
            doc.name))
    doc.db_set("attendance", name, update_modified=False)


def late_notice_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)


def attendance_validate(doc, method=None):
    """However the day is marked — from the punches, by hand, or by an
    attendance request — it is read once more for what Frappe HR's own
    reading does not say:

      a day off somebody clocked in on is a day they came in, never an
        absence (work on a rest day or a holiday is the special overtime)
      a late arrival acknowledged in advance is a full day, not a late one
      the minutes late and early, once past the shift's grace
      a clock-in with no clock-out is said to be that, and the employee
        and their supervisor are told the day it is marked
    """
    if doc.docstatus == 2 or not (doc.get("employee") and doc.get("attendance_date")):
        return
    shift = _shift_row(doc.get("shift"))
    punched = bool(doc.get("in_time") or flt(doc.get("working_hours")))
    if punched and doc.status in ("Absent", "Half Day") and _is_holiday(doc.employee, doc.attendance_date, shift):
        doc.status = rules.on_a_holiday(doc.status, True, punched)
        if doc.get("half_day_status"):
            doc.half_day_status = None
    notice = frappe.db.get_value("Late Arrival Notice", {"employee": doc.employee, "docstatus": 1,
                                                         "arrival_date": doc.attendance_date, "in_advance": 1},
                                 "name")
    if notice:
        status, late_entry = rules.full_day(doc.status, doc.get("late_entry"), True,
                                            on_leave=bool(doc.get("leave_application")))
        doc.status, doc.late_entry = status, late_entry
        if status != "Half Day" and doc.get("half_day_status"):
            doc.half_day_status = None
        # the name is set before validate on insert, and a failed insert rolls
        # this back with it
        if doc.name:
            frappe.db.set_value("Late Arrival Notice", notice, "attendance", doc.name, update_modified=False)
    doc.custom_late_minutes, doc.custom_early_minutes = _minutes_off(doc, shift)
    missing = rules.clock_out_missing(doc.status, doc.get("in_time"), doc.get("out_time"))
    doc.custom_clock_out_missing = 1 if missing else 0
    before = doc.get_doc_before_save()
    if missing and doc.docstatus == 1 and (before is None or before.docstatus == 0):
        _tell_clock_out_missing(doc)


def _shift_row(shift):
    if not shift:
        return None
    return frappe.db.get_value(SHIFT, shift, ["start_time", "end_time", "late_entry_grace_period",
                                              "early_exit_grace_period", "holiday_list"], as_dict=True)


def holiday_list_of(employee, shift=None):
    """The holiday list an employee's days off are read from, as Frappe
    HR's attendance reads it: the shift's own where it has one, else the
    employee's, else the company's."""
    if shift and shift.get("holiday_list"):
        return shift.get("holiday_list")
    found = frappe.db.get_value("Employee", employee, ["holiday_list", "company"], as_dict=True) or {}
    if found.get("holiday_list"):
        return found.get("holiday_list")
    return frappe.db.get_value("Company", found.get("company"), "default_holiday_list") if found.get("company") else None


def _is_holiday(employee, day, shift=None):
    name = holiday_list_of(employee, shift)
    return bool(name and frappe.db.exists("Holiday", {"parent": name, "holiday_date": getdate(day)}))


def _minutes_off(doc, shift):
    """(late, early): the minutes past the shift's grace, on a day worked
    that Frappe HR marked late or left early."""
    if not shift or doc.status not in rules.WORKED:
        return 0, 0
    start, end = rules.shift_span(doc.attendance_date, shift.get("start_time"), shift.get("end_time"))
    late = rules.minutes_late(doc.get("in_time"), start, shift.get("late_entry_grace_period")) \
        if cint(doc.get("late_entry")) else 0
    early = rules.minutes_early(doc.get("out_time"), end, shift.get("early_exit_grace_period")) \
        if cint(doc.get("early_exit")) else 0
    return late, early


def _tell_clock_out_missing(doc):
    """The employee and their supervisor, the day it is marked: a day
    with no clock-out reads absent or half a day until somebody says what
    was worked, and that is easier the same week than at the payroll."""
    employee = frappe.db.get_value("Employee", doc.employee, ["user_id", "reports_to"], as_dict=True) or {}
    users = [employee.get("user_id")]
    if employee.get("reports_to"):
        users.append(frappe.db.get_value("Employee", employee.get("reports_to"), "user_id"))
    users = list(dict.fromkeys(user for user in users if user))
    if not users:
        return
    people.notify(users, doc.doctype, doc.name, _(
        "{0} clocked in at {1} on {2} and did not clock out, so the day reads {3}. An Attendance Request "
        "puts it right.").format(doc.get("employee_name") or doc.employee, str(doc.get("in_time"))[11:16],
                                 frappe.utils.format_date(doc.attendance_date), doc.status))


# ── what the minutes ask the system to watch ──────────────────────────
def daily():
    """Top management marked present without punching, and a gate pass
    nobody closed."""
    for back in range(AUTOMATIC_DAYS, 0, -1):
        _mark_automatic(add_days(today(), -back))
    _chase_open_passes()
    frappe.db.commit()


def _mark_automatic(day):
    """"Top management officials should be given automatic attendance" —
    both minutes ask for it."""
    kept, company_lists = {}, {}
    for employee in frappe.get_all("Employee", filters={"status": "Active", "custom_automatic_attendance": 1},
                                   fields=["name", "company", "holiday_list", "default_shift", "date_of_joining"]):
        if employee.date_of_joining and getdate(employee.date_of_joining) > getdate(day):
            continue
        if frappe.db.exists("Attendance", {"employee": employee.name, "attendance_date": day,
                                           "docstatus": ["!=", 2]}):
            continue
        # their own holiday list, else the company's: nobody is marked
        # present on a day off, whoever on the list was looked at first
        holidays = employee.holiday_list
        if not holidays and employee.company:
            if employee.company not in company_lists:
                company_lists[employee.company] = frappe.db.get_value("Company", employee.company,
                                                                      "default_holiday_list")
            holidays = company_lists[employee.company]
        if holidays:
            if (holidays, day) not in kept:
                kept[(holidays, day)] = bool(frappe.db.exists("Holiday", {"parent": holidays, "holiday_date": day}))
            if kept[(holidays, day)]:
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
    """after_migrate: the off-duty request's two signatures, and the late
    arrival notice the supervisor acknowledges (workflows.py)."""
    from hrms_addon.hrms_addon import late_notice_approval, off_duty_approval, workflows

    workflows.setup_on_migrate(off_duty_approval, "Off Duty Request workflow")
    try:
        seed_off_duty_leave_type()
    except Exception:
        frappe.log_error(title="HRMS Addon: seeding the Off Duty leave type")
    workflows.setup_on_migrate(late_notice_approval, "Late Arrival Notice workflow")
