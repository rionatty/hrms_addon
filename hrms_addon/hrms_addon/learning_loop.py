# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Closing the loop, and reaching people: the training the rules ask for
taken into the client's own request chain (Training Requisition, Training
Needs Assessment approved by the HR Manager then the General Manager,
Training Calendar approved by the General Manager, Monthly Training
Schedule, Training Event), and what sets refreshers off. The rules are in
learning_rules.py (scripts/verify_learning.py).

  raise_requisitions    the requirements due and overdue, not yet booked or
                        asked for, grouped by training, plant and section
                        into draft requisitions for the heads of department
                        to send on; each requirement shows Requested, then
                        Booked once a session takes the employee
  renewal_requisitions  a certificate's first alert asks for its renewal the
                        same way, through the training that renews it
  Learning Trigger      a process change, new equipment, an audit finding, a
                        complaint or a defect recorded by HR sets off the
                        refreshers that ask for it, for everyone it reaches
  incident_on_submit    a safety incident does the same for the person it
                        happened to (and their section or department where
                        the rule reaches that far)
  daily                 those back from a long absence
  message_employees     the day's lines by SMS to employees with no user of
                        their own, where the settings ask for it and the SMS
                        gateway is set up; another channel (WhatsApp) plugs
                        in through the hook learning_message_senders
  CPD Log               continuing professional development: the hours and
                        points of each activity, checked by HR
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import learning, learning_rules as rules, people

REQUIREMENT, REQUISITION, CERTIFICATE = ("Employee Training Requirement", "Training Requisition",
                                         "Employee Certification")
TRIGGER, CPD = "Learning Trigger", "CPD Log"
GAPS, RENEWAL = "Training Gaps", "Certificate Renewal"
HR_ROLES = ("HR Manager", "HR User", "System Manager")
HEAD_ROLE = "Head of Department"
# the requisition's training method for the programme's way of delivery
METHODS = {"Classroom": "Internal", "On the Job": "On the Job", "Online": "Online", "External": "External",
           "Toolbox Talk": "On the Job"}
# more groups than this are raised in the background
INLINE_GROUPS = 20


# ── Requirements into requisitions ────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def raise_requisitions(company=None, branch=None, department=None, work_section=None, training_program=None,
                       overdue_only=0):
    """Draft Training Requisitions from the gaps the user may see: one per
    training, plant and section. Returns {"requisitions", "employees"}, or
    {"queued": 1} when there are many to raise."""
    frappe.has_permission(REQUISITION, "create", throw=True)
    filters = {"status": ["in", [rules.OVERDUE] if cint(overdue_only) else [rules.DUE_SOON, rules.OVERDUE]],
               "training_program": ["is", "set"], "booking_status": ["is", "not set"]}
    for field, value in (("company", company), ("branch", branch), ("department", department),
                         ("work_section", work_section), ("training_program", training_program)):
        if value:
            filters[field] = value
    rows = frappe.get_list(REQUIREMENT, filters=filters,
                           fields=["name", "employee", "employee_name", "designation", "department", "branch",
                                   "work_section", "training_program", "status", "due_date", "booking_status",
                                   "company"], limit_page_length=0)
    groups = rules.gap_groups(rows)
    if not groups:
        return {"requisitions": [], "employees": 0}
    if len(groups) > INLINE_GROUPS:
        frappe.enqueue("hrms_addon.hrms_addon.learning_loop.raise_groups", queue="long", timeout=3600,
                       job_id="learning_gap_requisitions::%s" % frappe.session.user, deduplicate=True,
                       enqueue_after_commit=True, groups=groups, user=frappe.session.user)
        return {"queued": 1, "groups": len(groups), "employees": sum(len(group["rows"]) for group in groups)}
    return raise_groups(groups, frappe.session.user)


def raise_groups(groups, user=None, source=GAPS):
    """A draft requisition for each group; its requirements show Requested."""
    made, employees = [], 0
    for group in groups:
        name = _requisition(group, user or frappe.session.user, source)
        if not name:
            continue
        names = [row["name"] for row in group["rows"] if row.get("name")]
        for start in range(0, len(names), 500):
            frappe.db.set_value(REQUIREMENT, {"name": ["in", names[start:start + 500]]},
                                {"requisition": name, "booking_status": rules.REQUESTED}, update_modified=False)
        made.append(name)
        employees += len(group["rows"])
        frappe.db.commit()
    if user and made and len(groups) > INLINE_GROUPS:
        people.notify([user], REQUISITION, made[0],
                      _("{0} training requisitions drafted from the training gaps, for {1} employees.").format(
                          len(made), employees))
    return {"requisitions": made, "employees": employees}


def _requisition(group, user, source):
    """The draft requisition for one group, put on the department head's list."""
    rows = group["rows"]
    if not group.get("branch") or not group.get("department"):
        return None
    programme = frappe.db.get_value("Training Program", group["training_program"],
                                    ["name", "custom_delivery_mode", "custom_duration_hours", "custom_cost_per_person"],
                                    as_dict=True) or frappe._dict(name=group["training_program"])
    soonest = min((getdate(row["due_date"]) for row in rows if row.get("due_date")), default=getdate(today()))
    doc = frappe.new_doc(REQUISITION)
    doc.update({
        "requested_by": user, "requester_name": frappe.utils.get_fullname(user),
        "department": group["department"], "branch": group["branch"], "request_date": today(),
        "priority": "High" if any(row.get("status") == rules.OVERDUE for row in rows) else "Medium",
        "preferred_month": _month(soonest), "preferred_year": soonest.year, "source": source,
        "justification": rules.gap_text(rows, today()),
    })
    doc.append("topics", {
        "topic": programme.name, "required_skills": rules.gap_text(rows, today()),
        "method": METHODS.get(programme.get("custom_delivery_mode") or "", "Internal"),
        "budget": flt(programme.get("custom_cost_per_person")) * len(rows),
        "duration": _("{0} hours").format("%g" % flt(programme.custom_duration_hours))
        if flt(programme.get("custom_duration_hours")) else None,
    })
    for row in rows:
        doc.append("target_employees", {"employee": row["employee"], "employee_name": row.get("employee_name"),
                                        "designation": row.get("designation"), "department": row.get("department")})
    doc.flags.ignore_permissions = True
    doc.insert()
    heads = people.people_for(HEAD_ROLE, group["branch"], group["department"])
    if heads:
        people.assign(REQUISITION, doc.name, heads,
                      _("Training needed: {0} for {1} employees. Review and submit the requisition.").format(
                          programme.name, len(rows)))
    return doc.name


def _month(day):
    from hrms_addon.hrms_addon import training_rules

    return training_rules.MONTHS[getdate(day).month - 1]


def renewal_requisitions(certificates):
    """At a certificate's first alert: a draft requisition for its renewal,
    through the training that renews it, one per training, plant and section
    for the day's certificates. The certificate and the requirement it meets
    point at the requisition."""
    certs = frappe.get_all(CERTIFICATE, filters={"name": ["in", list(certificates)], "renewal_requisition": ["is", "not set"]},
                           fields=["name", "employee", "employee_name", "certification", "branch", "department",
                                   "designation", "expiry_date", "company"], limit_page_length=0)
    renew = learning._renewal_programmes([cert.certification for cert in certs])
    staff = learning._employees({cert.employee for cert in certs})
    rows, by_employee = [], {}
    day = getdate(today())
    for cert in certs:
        programme, person = renew.get(cert.certification), staff.get(cert.employee)
        if not programme or not person or person.status != rules.ACTIVE:
            continue
        rows.append({"name": None, "certificate": cert.name, "employee": cert.employee,
                     "employee_name": cert.employee_name, "designation": person.designation,
                     "department": person.department, "branch": person.branch,
                     "work_section": person.get("work_section"), "training_program": programme,
                     "status": rules.OVERDUE if cert.expiry_date and getdate(cert.expiry_date) < day else rules.DUE_SOON,
                     "due_date": cert.expiry_date, "certification": cert.certification})
        by_employee.setdefault((cert.employee, cert.certification), cert.name)
    made = []
    for group in rules.gap_groups(rows):
        name = _requisition(group, "Administrator", RENEWAL)
        if not name:
            continue
        made.append(name)
        for row in group["rows"]:
            frappe.db.set_value(CERTIFICATE, row["certificate"], "renewal_requisition", name, update_modified=False)
            frappe.db.set_value(REQUIREMENT, {"employee": row["employee"], "certification": row["certification"],
                                              "status": ["!=", rules.NOT_APPLICABLE]},
                                {"requisition": name, "booking_status": rules.REQUESTED}, update_modified=False)
    return made


# ── What sets refreshers off ──────────────────────────────────────────
def trigger_validate(doc):
    if doc.trigger_type not in rules.RECORDED_TRIGGERS:
        frappe.throw(_("Type is one of: {0}.").format(", ".join(rules.RECORDED_TRIGGERS)), title=_(TRIGGER))
    if not (doc.get("branch") or doc.get("department") or doc.get("work_section") or doc.get("skill")):
        frappe.throw(_("Say whom it concerns: a plant, a department, a section or a skill."), title=_(TRIGGER))
    if doc.get("work_section") and not doc.get("branch"):
        doc.branch = frappe.db.get_value("Work Section", doc.work_section, "branch")
    if getdate(doc.trigger_date) > getdate(today()):
        frappe.throw(_("It cannot be dated ahead."), title=_(TRIGGER))
    doc.set_off_rules = ", ".join(sorted(frappe.get_all("Training Rule", filters={"enabled": 1,
                                                                                    "trigger": doc.trigger_type},
                                                        pluck="name")))[:140] or None


def trigger_on_submit(doc):
    frappe.enqueue("hrms_addon.hrms_addon.learning_loop.set_off", queue="long", timeout=3600,
                   job_id="learning_trigger::%s" % doc.name, deduplicate=True, enqueue_after_commit=True,
                   trigger_name=doc.name)
    doc.db_set("status", "Setting Off", update_modified=False)


def set_off(trigger_name):
    """The background job: everyone the trigger concerns asked again."""
    doc = frappe.get_doc(TRIGGER, trigger_name)
    employees = concerned(doc)
    asked = learning.trigger(doc.trigger_type, employees, doc.trigger_date,
                             note="%s %s" % (doc.trigger_type, doc.name))
    doc.db_set({"employees_concerned": len(employees), "employees_asked": len(asked), "status": "Set Off"},
               update_modified=False, commit=True)
    return asked


def concerned(doc):
    """The active employees a trigger concerns: of its plant, department and
    section, and assessed in its skill where it names one."""
    filters = {"status": rules.ACTIVE}
    if doc.get("company"):
        filters["company"] = doc.company
    for field, column in (("branch", "branch"), ("department", "department"), ("work_section", "custom_work_section")):
        if doc.get(field):
            filters[column] = doc.get(field)
    employees = frappe.get_all("Employee", filters=filters, pluck="name", limit_page_length=0)
    if doc.get("skill"):
        assessed = set(frappe.get_all("Competency Assessment", filters={"skill": doc.skill, "status": ["!=", "Superseded"]},
                                      pluck="employee", limit_page_length=0))
        employees = [employee for employee in employees if employee in assessed]
    return employees


def incident_on_submit(doc, method=None):
    """A safety incident recorded: the refreshers it sets off, for the person
    it happened to (and as far as each rule reaches), in the background."""
    if not doc.get("employee"):
        return
    frappe.enqueue("hrms_addon.hrms_addon.learning.trigger", queue="short", enqueue_after_commit=True,
                   kind=rules.SAFETY_INCIDENT, employees=[doc.employee],
                   day=str(getdate(doc.get("incident_on") or today())),
                   note=" ".join(part for part in (rules.SAFETY_INCIDENT, doc.name, doc.get("severity")) if part))


def daily():
    """Those back from a long absence today."""
    long_absences()
    frappe.db.commit()


def long_absences(day=None):
    """Employees whose approved leave ended yesterday after so many days
    away: the refreshers a long absence sets off, each rule at its own
    number of days."""
    day = getdate(day or today())
    least = [cint(value) for value in frappe.get_all("Training Rule", filters={"enabled": 1,
                                                                                "trigger": rules.LONG_ABSENCE},
                                                     pluck="absence_days") if cint(value) > 0]
    if not least:
        return []
    back = frappe.get_all("Leave Application", filters={"docstatus": 1, "status": "Approved",
                                                        "to_date": str(rules.add_days(day, -1)),
                                                        "total_leave_days": [">=", min(least)]},
                          fields=["employee", "total_leave_days"], limit_page_length=0)
    away = {}
    for row in back:
        away[row.employee] = max(away.get(row.employee, 0), flt(row.total_leave_days))
    if not away:
        return []
    return learning.trigger(rules.LONG_ABSENCE, list(away), day, note=rules.LONG_ABSENCE, days_away=away)


# ── Reaching people with no user ──────────────────────────────────────
def message_employees(texts):
    """{employee: [lines]}: one message each, by SMS where the settings ask
    for it and the gateway is set up, and to every channel registered under
    the hook learning_message_senders (sender(employee, number, message))."""
    senders = frappe.get_hooks("learning_message_senders") or []
    sms = cint(frappe.db.get_single_value(learning.SETTINGS, "send_sms")) and \
        frappe.db.get_single_value("SMS Settings", "sms_gateway_url")
    if not texts or not (sms or senders):
        return 0
    numbers = dict(frappe.get_all("Employee", filters={"name": ["in", list(texts)]}, fields=["name", "cell_number"],
                                  as_list=True, limit_page_length=0))
    sent = 0
    for employee, lines in texts.items():
        number = (numbers.get(employee) or "").strip()
        if not number:
            continue
        message = _("Luuka training: {0}").format(" ".join(lines[:3]) + (" ..." if len(lines) > 3 else ""))[:300]
        try:
            if sms:
                from frappe.core.doctype.sms_settings.sms_settings import _send_sms

                _send_sms([number], message, success_msg=False)
            for sender in senders:
                frappe.get_attr(sender)(employee, number, message)
            sent += 1
        except Exception:
            frappe.log_error(title="Learning: message to %s" % employee)
    return sent


# ── CPD Log ───────────────────────────────────────────────────────────
def cpd_validate(doc):
    roles = set(frappe.get_roles())
    own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not roles & set(HR_ROLES) and doc.employee != own:
        frappe.throw(_("You log your own CPD."), frappe.PermissionError)
    if flt(doc.hours) <= 0:
        frappe.throw(_("Enter the hours."), title=_(CPD))
    if getdate(doc.activity_date) > getdate(today()):
        frappe.throw(_("It cannot be dated ahead."), title=_(CPD))
    if doc.get("employee_certification"):
        doc.certification = frappe.db.get_value(CERTIFICATE, doc.employee_certification, "certification")
    before = doc.get_doc_before_save()
    was = (before.get("status") if before else None) or "Unverified"
    if (doc.get("status") or "Unverified") != was:
        if not roles & set(HR_ROLES):
            frappe.throw(_("Only HR check CPD."), frappe.PermissionError)
        doc.verified_by, doc.verified_on = (None, None) if doc.status == "Unverified" else (frappe.session.user, today())


def cpd_hours(employee, certification, since=None):
    """The CPD hours an employee logged for a certification since a day,
    HR's refusals aside."""
    filters = {"employee": employee, "certification": certification, "docstatus": 1, "status": ["!=", "Rejected"]}
    if since:
        filters["activity_date"] = [">=", str(getdate(since))]
    return round(sum(flt(value) for value in frappe.get_all(CPD, filters=filters, pluck="hours")), 1)
