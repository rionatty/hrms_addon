# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee suspension on the site: Luuka's Suspension Letter as a record
of its own (Disciplinary Grievancy, test case 6).

The rules are in suspension_rules.py and the signatures in
suspension_approval.py, both without a Frappe import
(scripts/verify_suspension.py). This reads and writes the site.

  suspension_*  the record: its dates, what it needs, its signatures (the
                HR Manager, then the General Manager). Approved, each day
                is marked on the attendance as unpaid leave and the
                employee is Suspended while it runs; cancelled, both are
                undone
  from_case     a Disciplinary Case decided at the Suspension rung raises
                one for the HR Officer to check and send on (discipline.py)
  daily         a suspension whose first day has come suspends the
                employee; one whose report-back day has come makes them
                Active again and tells HR and the supervisor
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import people, suspension_approval as approval, suspension_rules as rules, workflows

DOCTYPE = "Employee Suspension"
CASE = "Disciplinary Case"
ATTENDANCE = "Attendance"


# ── 1. The record ─────────────────────────────────────────────────────
def suspension_validate(doc, method=None):
    _fill_dates(doc)
    _check_step(doc)
    if doc.docstatus == 0:
        doc.status = doc.get(approval.STATE_FIELD) or approval.DRAFT


def _fill_dates(doc):
    """To, and the day they report back, from the first day and the days."""
    dates = rules.suspension_dates(doc.get("from_date"), doc.get("days"))
    doc.to_date, doc.report_back_on = dates["to"], dates["report_back"]


def _facts(doc):
    employee = frappe.db.get_value("Employee", doc.employee, ["date_of_joining", "relieving_date", "status"],
                                   as_dict=True) if doc.get("employee") else None
    employee = employee or {}
    return {
        "employee": doc.get("employee"), "nature_of_offence": doc.get("nature_of_offence"),
        "days": doc.get("days"), "from_date": doc.get("from_date"),
        "date_of_joining": employee.get("date_of_joining"), "relieving_date": employee.get("relieving_date"),
        "employee_status": employee.get("status"), "clashes": _clashes(doc),
    }


def _clashes(doc):
    """The employee's other suspensions, not cancelled, whose days this
    one's fall on."""
    if not (doc.get("employee") and doc.get("from_date") and doc.get("to_date")):
        return []
    others = frappe.get_all(DOCTYPE, filters={"employee": doc.employee, "docstatus": ["!=", 2],
                                              "name": ["!=", doc.name or ""]},
                            fields=["name", "from_date", "to_date"])
    return [row.name for row in others if rules.overlaps(doc.from_date, doc.to_date, row.from_date, row.to_date)]


def _check_step(doc):
    """A step of the workflow: what it needs, the signature it leaves, and
    who is told."""
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"),
            "errors": rules.suspension_errors(_facts(doc)) if new_state != approval.DRAFT else []})
        if errors:
            frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state:
        _tell_step(doc, old_state, new_state, before)


def _tell_step(doc, old_state, new_state, before):
    """Whoever signs next is told and given it to do, and it is off the list
    of whoever had it; HR are told of a return."""
    branch = doc.get("branch")
    if old_state in approval.ROLE_WAITING:
        people.withdraw(doc.doctype, doc.name, people.people_for(approval.ROLE_WAITING[old_state], branch))
    elif old_state == approval.DRAFT:
        # the HR Officer a disciplinary case asked to send it on has done so
        people.withdraw(doc.doctype, doc.name, people.hr_officers(branch, doc.get("department")))
    who = doc.get("employee_name") or doc.get("employee")
    if new_state in approval.ROLE_WAITING:
        users = people.people_for(approval.ROLE_WAITING[new_state], branch)
        message = _("Suspension of {0} for {1} days from {2}: your signature is needed.").format(
            who, cint(doc.days), frappe.utils.format_date(doc.from_date))
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)
    elif new_state == approval.DRAFT and old_state in approval.PENDING_STATES:
        hr = {before.get("prepared_by")} | set(people.hr_officers(branch, doc.get("department")))
        people.notify(sorted(user for user in hr if user), doc.doctype, doc.name,
                      _("The suspension of {0} came back: {1}").format(who, doc.get("return_remarks") or ""))


# ── 2. Approved: the days marked, the employee suspended ──────────────
def suspension_on_submit(doc, method=None):
    """Approved by the General Manager: each day is marked on the
    attendance, the people concerned are told, and the suspension starts
    at once if its first day has come."""
    marked = _mark_days(doc)
    status = rules.running_status(today(), doc.from_date, doc.report_back_on, approval.APPROVED)
    doc.db_set({"status": status, "days_marked": marked}, update_modified=False)
    _move_employee(doc, status)
    _tell_approved(doc)


def _mark_days(doc):
    """Each day of the suspension on the employee's attendance, as leave of
    its leave type: unpaid, unless it is a suspension with pay. A day
    already submitted stays as it is, and the record says which."""
    days = rules.days_between(doc.from_date, doc.to_date)
    if not days:
        return 0
    leave_type = rules.leave_type_for(doc.get("without_pay"))
    existing = {getdate(row.attendance_date): row for row in frappe.get_all(
        ATTENDANCE, filters={"employee": doc.employee, "docstatus": ["!=", 2],
                             "attendance_date": ["between", [days[0], days[-1]]]},
        fields=["name", "docstatus", "status", "leave_type", "attendance_date"])}
    plan = rules.day_plan(days, existing)
    company = doc.get("company") or frappe.db.get_value("Employee", doc.employee, "company")
    muted = frappe.flags.mute_messages
    # Frappe HR says "no leave record found" of every day it is given this way
    frappe.flags.mute_messages = True
    try:
        for day in plan["create"]:
            attendance = frappe.get_doc({"doctype": ATTENDANCE, "employee": doc.employee, "attendance_date": day,
                                         "status": "On Leave", "leave_type": leave_type, "company": company})
            attendance.flags.ignore_permissions = True
            attendance.insert()
            attendance.submit()
        for name in plan["update"]:
            attendance = frappe.get_doc(ATTENDANCE, name)
            attendance.update({"status": "On Leave", "leave_type": leave_type})
            attendance.flags.ignore_permissions = True
            attendance.submit()
    finally:
        frappe.flags.mute_messages = muted
    if plan["kept"]:
        doc.add_comment("Info", _("Already on the attendance, left as they are: {0}").format(
            ", ".join("%s %s" % (frappe.utils.format_date(day), status or "") for day, status in plan["kept"])))
    return len(plan["create"]) + len(plan["update"])


def _unmark_days(doc):
    """The days a suspension marked, taken off the attendance."""
    days = rules.days_between(doc.from_date, doc.to_date)
    if not days:
        return 0
    names = frappe.get_all(ATTENDANCE, filters={
        "employee": doc.employee, "docstatus": 1, "status": "On Leave", "leave_type": ["in", list(rules.LEAVE_TYPES)],
        "attendance_date": ["between", [days[0], days[-1]]]}, pluck="name")
    for name in names:
        attendance = frappe.get_doc(ATTENDANCE, name)
        attendance.flags.ignore_permissions = True
        attendance.cancel()
    return len(names)


def _move_employee(doc, status):
    """The employee's status as the suspension now stands: Suspended while
    it runs, Active again after (suspension_rules.employee_status_after)."""
    current = frappe.db.get_value("Employee", doc.employee, "status")
    others = frappe.get_all(DOCTYPE, filters={"employee": doc.employee, "docstatus": 1,
                                              "status": rules.IN_PROGRESS, "name": ["!=", doc.name]},
                            pluck="name", limit=1)
    new = rules.employee_status_after(status, current, bool(others))
    if new:
        frappe.db.set_value("Employee", doc.employee, "status", new, update_modified=False)


def _concerned(doc):
    """HR, the supervisor and the employee."""
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    supervisor = frappe.db.get_value("Employee", doc.employee, "reports_to")
    if supervisor:
        users.append(frappe.db.get_value("Employee", supervisor, "user_id"))
    users.append(frappe.db.get_value("Employee", doc.employee, "user_id"))
    return list(dict.fromkeys(user for user in users if user))


def _tell_approved(doc):
    people.notify(_concerned(doc), doc.doctype, doc.name, _(
        "{0} is suspended {1} from {2} to {3}, and reports back to the HR Office on {4}.").format(
        doc.get("employee_name") or doc.employee, _("without pay") if doc.get("without_pay") else _("with pay"),
        frappe.utils.format_date(doc.from_date), frappe.utils.format_date(doc.to_date),
        frappe.utils.format_date(doc.report_back_on)))


def suspension_on_cancel(doc, method=None):
    """Cancelled: the days come off the attendance, and the employee is
    Active again if this was what suspended them."""
    _unmark_days(doc)
    doc.db_set("status", rules.CANCELLED, update_modified=False)
    _move_employee(doc, rules.CANCELLED)
    people.notify(_concerned(doc), doc.doctype, doc.name,
                  _("The suspension of {0} is cancelled.").format(doc.get("employee_name") or doc.employee))


# ── 3. From the disciplinary case ─────────────────────────────────────
def from_case(case):
    """A case decided at the Suspension rung raises the suspension, with
    the case's days, for the HR Officer to check and send on. One already
    raised for the case is left alone."""
    if frappe.db.exists(DOCTYPE, {"disciplinary_case": case.name, "docstatus": ["!=", 2]}):
        return None
    doc = frappe.new_doc(DOCTYPE)
    doc.update({
        "employee": case.employee, "disciplinary_case": case.name, "date": today(),
        "nature_of_offence": case.get("misconduct_type") or case.get("allegation"),
        "days": cint(case.get("suspension_days")) or rules.DEFAULT_DAYS,
        "from_date": case.get("suspension_from") or today(), "without_pay": 1,
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    case.db_set("employee_suspension", doc.name, update_modified=False)
    users = people.hr_officers(case.get("branch"), case.get("department"))
    message = _("Disciplinary case {0} decided a suspension for {1}: check the letter and send it to the HR "
                "Manager.").format(case.name, doc.get("employee_name") or doc.employee)
    people.notify(users, DOCTYPE, doc.name, message)
    people.assign(DOCTYPE, doc.name, users, message)
    return doc.name


# ── 4. The days as they come ──────────────────────────────────────────
def daily():
    """A suspension whose first day has come suspends the employee; one
    whose report-back day has come makes them Active again, and HR and the
    supervisor are told they are due back."""
    day = today()
    for row in frappe.get_all(DOCTYPE, filters={"docstatus": 1, "status": ["in", [rules.APPROVED, rules.IN_PROGRESS]]},
                              fields=["name", "status", "from_date", "report_back_on"], limit_page_length=0):
        status = rules.running_status(day, row.from_date, row.report_back_on, row.status)
        if status == row.status:
            continue
        doc = frappe.get_doc(DOCTYPE, row.name)
        doc.db_set("status", status, update_modified=False)
        _move_employee(doc, status)
        if status == rules.COMPLETED:
            people.notify(_concerned(doc), DOCTYPE, doc.name,
                          _("{0}'s suspension has ended: they report back to the HR Office today.").format(
                              doc.get("employee_name") or doc.employee))
    frappe.db.commit()


# ── 5. Wiring ─────────────────────────────────────────────────────────
def seed_leave_types():
    """The two leave types a suspension's days are marked as. One already
    there is left as it is."""
    made = []
    for name, values in rules.LEAVE_TYPES.items():
        if frappe.db.exists("Leave Type", name):
            continue
        doc = frappe.new_doc("Leave Type")
        doc.leave_type_name = name
        doc.update(values)
        doc.insert(ignore_permissions=True)
        made.append(name)
    return made


def setup_workflows_on_migrate():
    """after_migrate: the suspension's workflow and the General Manager's
    right to file it (workflows.py)."""
    workflows.setup_on_migrate(approval, "Employee Suspension workflow")
