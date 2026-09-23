# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Relations and Welfare on the site: disciplinary cases (5.3),
non-disciplinary concerns (5.4) and safety incidents.

The rules are in discipline_rules.py and grievance_rules.py, without a
Frappe import (scripts/verify_discipline.py). This reads and writes the
site.

  case_*      a disciplinary case: where on the ladder it starts, the
              investigation, the hearing before a panel who did not gather
              the evidence, and the sanction. A dismissal raises the
              involuntary exit (exits.py), so the termination process
              really follows.
  incident_*  a safety incident: the EHS report, the sick leave it becomes
              and the separation on medical grounds where it persists.
  concern_*   the non-disciplinary concern, on Frappe HR's own Employee
              Grievance: the HOD it is assigned to, the timeline the
              system watches, and the escalation when it is overdue.
  daily       the timelines both processes are watched by: an appeal
              window that lapses, a sanction that is spent, a concern
              past its date.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, today

from hrms_addon.hrms_addon import discipline_rules as rules, grievance_rules, people

CASE = "Disciplinary Case"
INCIDENT = "Safety Incident"
CONCERN = "Employee Grievance"


# ── 1. The disciplinary case ──────────────────────────────────────────
def case_validate(doc, method=None):
    from hrms_addon.hrms_addon import discipline_approval as approval

    _fill_ladder(doc)
    _fill_hearing(doc)
    _fill_sanction(doc)
    _check_case_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _fill_ladder(doc):
    """Where this case starts: one rung above whatever still stands
    against the employee, or the bottom where nothing does. Gross
    misconduct may go straight to dismissal."""
    if not doc.get("employee"):
        return
    live = _live_sanctions(doc.employee, doc.name)
    doc.live_sanctions = "; ".join(
        "%s of %s" % (row["action"], frappe.utils.format_date(row["issued_on"])) for row in live
    ) or None
    doc.starts_at = rules.escalate(live, doc.get("severity"), today())
    if live and not doc.get("previous_case"):
        doc.previous_case = live[-1]["case"]


def _live_sanctions(employee, exclude):
    """The sanctions still standing against this employee, oldest first. A
    spent one is left out: after its validity the ladder starts again."""
    rows = frappe.get_all(CASE,
                          filters={"employee": employee, "docstatus": 1, "outcome": "Sanctioned",
                                   "name": ["!=", exclude or ""]},
                          fields=["name", "rung", "decided_on", "sanction_valid_until"],
                          order_by="decided_on asc", limit=50)
    live = []
    for row in rows:
        if not row.rung:
            continue
        if row.sanction_valid_until and getdate(row.sanction_valid_until) < getdate(today()):
            continue
        live.append({"case": row.name, "action": row.rung, "issued_on": row.decided_on,
                     "validity_months": None})
    return [row for row in live
            if not rules.sanction_spent(row["issued_on"], row["action"], today())]


def _fill_hearing(doc):
    """How much notice the hearing was given, said in hours so it can be
    seen at a glance."""
    if doc.get("hearing_on") and doc.get("hearing_notified_on"):
        seconds = (get_datetime(doc.hearing_on) - get_datetime(doc.hearing_notified_on)).total_seconds()
        doc.hearing_notice_hours = round(seconds / 3600.0, 1)
    for row in doc.get("panel") or []:
        if row.employee and not row.member:
            row.member = frappe.db.get_value("Employee", row.employee, "user_id")


def _fill_sanction(doc):
    """What the sanction comes to: how long it stands, and the dates a
    suspension runs for.

    The save that decides the case is also the save that submits it, and
    the decision is stamped later in the same save, so on that one pass
    the day of the decision stands in for a stamp not yet written.
    """
    from hrms_addon.hrms_addon import discipline_approval as approval

    decided_on = doc.get("decided_on")
    if not decided_on and doc.get("workflow_state") == approval.DECIDED:
        decided_on = today()
    if doc.get("action_type") and decided_on:
        months = cint(frappe.db.get_value("Disciplinary Action Type", doc.action_type,
                                          "validity_months"))
        if months:
            doc.sanction_valid_until = rules.add_months(decided_on, months)
    if doc.get("action_type") and not doc.get("suspension_days"):
        doc.suspension_days = cint(frappe.db.get_value("Disciplinary Action Type", doc.action_type,
                                                       "suspension_days"))
    if doc.get("rung") == rules.SUSPENSION and doc.get("suspension_days"):
        start = doc.get("suspension_from") or decided_on or today()
        dates = rules.suspension_dates(start, doc.suspension_days)
        doc.suspension_from, doc.suspension_to = dates["from"], dates["to"]
        doc.report_back_on = dates["report_back"]


def _case_facts(doc):
    return {
        "employee": doc.get("employee"), "misconduct_type": doc.get("misconduct_type"),
        "incident_date": doc.get("incident_date"), "allegation": doc.get("allegation"),
        "reported_by": doc.get("reported_by"), "severity": doc.get("severity"), "today": today(),
    }


def _check_case_step(doc):
    from hrms_addon.hrms_addon import discipline_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks")})
        if new_state == approval.INVESTIGATING and old_state in (None, approval.DRAFT):
            errors = rules.case_errors(_case_facts(doc)) + errors
        if old_state == approval.INVESTIGATING and new_state != approval.DRAFT:
            errors += rules.investigation_errors({
                "investigating_officer": doc.get("investigating_officer"),
                "investigation_report": doc.get("investigation_report"),
                "recommendation": doc.get("recommendation")})
        if old_state == approval.CHARGED and new_state == approval.HEARING:
            errors += rules.hearing_errors({
                "hearing_on": doc.get("hearing_on"), "notified_on": doc.get("hearing_notified_on"),
                "panel": [row.as_dict() for row in doc.get("panel") or []],
                "investigating_officer": doc.get("investigating_officer")})
        if old_state == approval.HEARING and new_state == approval.DECIDED:
            errors += rules.decision_errors({
                "outcome": doc.get("outcome"), "hearing_minutes": doc.get("hearing_minutes"),
                "employee_response": doc.get("employee_response"),
                "action_type": doc.get("rung"), "suspension_days": doc.get("suspension_days")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Disciplinary Case"))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_case(doc, new_state)


def _tell_case(doc, state):
    from hrms_addon.hrms_addon import discipline_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"), doc.get("department"))
    supervisor = doc.get("reported_by")
    if supervisor and state == approval.CHARGED:
        users = list(users) + [supervisor]
    if not users:
        return
    message = _("Disciplinary case against {0}: {1}.").format(
        doc.get("employee_name") or doc.employee, doc.get("misconduct_type") or "")
    people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message, date=getdate(doc.get("hearing_on"))
                  if doc.get("hearing_on") else None)


def case_on_submit(doc, method=None):
    """Decided. A dismissal opens the termination process; a sanction is
    told to the supervisor; everything is told to the employee."""
    if rules.ends_in_termination(doc.get("outcome"), doc.get("rung")):
        _raise_separation(doc)
    _tell_decided(doc)


def case_on_cancel(doc, method=None):
    doc.status = "Cancelled"


def _raise_separation(doc):
    """The chart's "Termination? Yes → Follow Involuntary Termination
    Process". One already open for this employee is left alone."""
    existing = frappe.db.get_value("Employee Separation",
                                   {"employee": doc.employee, "docstatus": ["<", 2]}, "name")
    if existing:
        doc.db_set("separation", existing, update_modified=False)
        return existing
    try:
        exit_doc = frappe.get_doc({
            "doctype": "Employee Separation", "employee": doc.employee, "company": doc.company,
            "department": doc.get("department"), "designation": doc.get("designation"),
            "boarding_status": "Pending", "custom_exit_type": "Involuntary",
            "custom_reason": "Dismissal", "custom_relieving_date": doc.get("decided_on") or today(),
            "custom_termination_date": doc.get("decided_on") or today(),
            "custom_termination_reason": _("Disciplinary case {0}: {1}").format(
                doc.name, doc.get("misconduct_type") or ""),
        })
        exit_doc.flags.ignore_permissions = True
        exit_doc.flags.ignore_mandatory = True
        exit_doc.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: separation from a disciplinary case")
        return None
    doc.db_set("separation", exit_doc.name, update_modified=False)
    return exit_doc.name


def _tell_decided(doc):
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    if doc.get("reported_by"):
        users.append(doc.reported_by)
    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    if user:
        users.append(user)
    if not users:
        return
    people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                  _("Disciplinary case {0} is decided: {1}{2}.").format(
                      doc.name, doc.get("outcome") or "",
                      " (%s)" % doc.rung if doc.get("rung") else ""))


@frappe.whitelist(methods=["POST"])
def file_appeal(case, grounds, authority):
    """An appeal, heard by someone who has not already acted in the case."""
    doc = frappe.get_doc(CASE, case)
    doc.check_permission("write")
    if doc.docstatus != 1:
        frappe.throw(_("An appeal follows a decided case."))
    errors = rules.appeal_errors({
        "appeals_authority": authority, "appeal_grounds": grounds,
        "investigating_officer": doc.get("investigating_officer"), "decided_by": doc.get("decided_by"),
        "panel": [row.as_dict() for row in doc.panel]})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Appeal"))
    doc.db_set({"appeal_filed": 1, "appeal_grounds": grounds, "appeals_authority": authority})
    people.notify([authority], CASE, doc.name,
                  _("{0} has appealed disciplinary case {1}.").format(
                      doc.get("employee_name") or doc.employee, doc.name))
    return doc.name


# ── 2. The safety incident ────────────────────────────────────────────
def incident_validate(doc, method=None):
    errors = grievance_rules.incident_errors({
        "employee": doc.get("employee"), "incident_on": doc.get("incident_on"),
        "nature": doc.get("nature"), "manageable": doc.get("manageable"),
        "hospital": doc.get("hospital"), "day_off_required": doc.get("day_off_required"),
        "sick_from": doc.get("sick_from"), "sick_days": doc.get("sick_days"),
        "compensation_required": doc.get("compensation_required"),
        "compensation_amount": doc.get("compensation_amount")})
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Safety Incident"))
    doc.status = grievance_rules.incident_status(
        doc.docstatus, doc.get("day_off_required"), doc.get("sick_leave"),
        doc.get("sickness_persists"), doc.get("separation"))


def incident_on_submit(doc, method=None):
    """Recorded. Where a day off is needed the sick leave is raised, and
    where the sickness persists the separation on medical grounds."""
    if doc.get("day_off_required") and not doc.get("sick_leave"):
        _raise_sick_leave(doc)
    if doc.get("sickness_persists") and not doc.get("separation"):
        _separate_on_medical_grounds(doc)
    # the leave and the separation are raised after this save validated,
    # so where the incident stands is said again now that they exist
    status = grievance_rules.incident_status(
        doc.docstatus, doc.get("day_off_required"), doc.get("sick_leave"),
        doc.get("sickness_persists"), doc.get("separation"))
    if status != doc.get("status"):
        doc.db_set("status", status, update_modified=False)
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if users:
        people.notify(users, doc.doctype, doc.name,
                      _("Safety incident for {0} on {1}.").format(
                          doc.get("employee_name") or doc.employee,
                          frappe.utils.format_date(getdate(doc.get("incident_on")))))


def incident_on_cancel(doc, method=None):
    doc.status = "Cancelled"


def _raise_sick_leave(doc):
    """Step 6: the HR Officer creates the employee's sick leave."""
    leave_type = grievance_rules.SICK_LEAVE
    if not frappe.db.exists("Leave Type", leave_type):
        return None
    start = getdate(doc.get("sick_from") or getdate(doc.get("incident_on")))
    days = cint(doc.get("sick_days")) or 1
    try:
        leave = frappe.get_doc({
            "doctype": "Leave Application", "employee": doc.employee, "company": doc.company,
            "leave_type": leave_type, "from_date": start,
            "to_date": add_days(start, days - 1), "total_leave_days": days,
            "description": _("Sick leave from safety incident {0}: {1}").format(doc.name,
                                                                                doc.get("nature") or ""),
            "custom_medical_certificate": doc.get("doctor_report") or doc.get("ehs_report"),
        })
        leave.flags.ignore_permissions = True
        leave.flags.ignore_mandatory = True
        leave.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: sick leave from a safety incident")
        return None
    doc.db_set("sick_leave", leave.name, update_modified=False)
    return leave.name


def _separate_on_medical_grounds(doc):
    """The chart's last box: the sickness persists past the sick leave, so
    the separation is on medical grounds."""
    existing = frappe.db.get_value("Employee Separation",
                                   {"employee": doc.employee, "docstatus": ["<", 2]}, "name")
    if existing:
        doc.db_set("separation", existing, update_modified=False)
        return existing
    try:
        exit_doc = frappe.get_doc({
            "doctype": "Employee Separation", "employee": doc.employee, "company": doc.company,
            "department": doc.get("department"), "boarding_status": "Pending",
            "custom_exit_type": "Involuntary", "custom_reason": "Medical Grounds",
            "custom_relieving_date": today(), "custom_termination_date": today(),
            "custom_termination_reason": _("Safety incident {0}: {1}").format(doc.name,
                                                                              doc.get("nature") or ""),
        })
        exit_doc.flags.ignore_permissions = True
        exit_doc.flags.ignore_mandatory = True
        exit_doc.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: separation on medical grounds")
        return None
    doc.db_set("separation", exit_doc.name, update_modified=False)
    return exit_doc.name


# ── 3. The non-disciplinary concern (5.4) ─────────────────────────────
def concern_validate(doc, method=None):
    """Frappe HR's Employee Grievance, carrying Luuka's concern: the HOD
    it is assigned to and the date it is due back."""
    if doc.get("custom_assigned_hod") and not doc.get("custom_due_on"):
        doc.custom_due_on = grievance_rules.due_on(
            doc.get("date") or today(), _timeline_days(doc.get("grievance_type")))
    doc.custom_overdue = 1 if grievance_rules.overdue(doc.get("custom_due_on"), today(),
                                                      doc.get("status")) else 0
    errors = grievance_rules.concern_errors({
        "employee": doc.get("raised_by"), "grievance_type": doc.get("grievance_type"),
        "description": doc.get("description"), "assigned_hod": doc.get("custom_assigned_hod"),
        "status": doc.get("status"), "resolution": doc.get("resolution_detail"),
        "outcome_accepted": doc.get("custom_outcome_accepted"),
        "appeal_filed": doc.get("custom_appeal_filed"),
        "appeals_authority": doc.get("custom_appeals_authority"),
        "handler": doc.get("custom_assigned_hod")})
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Grievance"))
    if doc.get("custom_appeal_filed") and not doc.get("custom_appealed_on"):
        doc.custom_appealed_on = today()


def _timeline_days(grievance_type):
    days = frappe.db.get_value("Grievance Type", grievance_type, "custom_timeline_days") \
        if grievance_type else None
    return cint(days) or grievance_rules.DEFAULT_TIMELINE_DAYS


def concern_on_submit(doc, method=None):
    """Step 3: the HOD it is assigned to is told, and it goes on their
    list of things to do."""
    if not doc.get("custom_assigned_hod"):
        return
    message = _("Concern from {0}: {1}").format(
        doc.get("employee_name") or doc.get("raised_by"), doc.get("subject") or doc.get("grievance_type"))
    people.notify([doc.custom_assigned_hod], doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, [doc.custom_assigned_hod], message,
                  date=doc.get("custom_due_on"))


def concern_on_cancel(doc, method=None):
    pass


# ── 4. The timelines both processes are watched by ────────────────────
def daily():
    _close_appeal_windows()
    _chase_concerns()
    _end_suspensions()


def _close_appeal_windows():
    """A decided case nobody appealed closes itself once the window has
    lapsed, and a spent sanction stops standing against the employee."""
    rows = frappe.get_all(CASE,
                          filters={"docstatus": 1, "status": "Decided", "appeal_filed": ["!=", 1]},
                          fields=["name", "decided_on", "appeal_window_days"], limit=200)
    for row in rows:
        if not rules.appeal_window_closed(row.decided_on, today(), row.appeal_window_days):
            continue
        frappe.db.set_value(CASE, row.name, {"status": "Closed", "appeal_closed_on": today()},
                            update_modified=False)
    frappe.db.commit()


def _chase_concerns():
    """Step 5: the system watches the timeline and tells the HOD when the
    concern is due, then escalates it when it is overdue."""
    rows = frappe.get_all(CONCERN,
                          filters={"docstatus": 1, "status": ["not in", ("Resolved", "Closed",
                                                                        "Invalid")],
                                   "custom_due_on": ["<=", add_days(today(), 2)]},
                          fields=["name", "subject", "raised_by", "employee_name", "custom_due_on",
                                  "custom_assigned_hod"], limit=200)
    for row in rows:
        users = [row.custom_assigned_hod] if row.custom_assigned_hod else []
        if grievance_rules.overdue(row.custom_due_on, today(), None):
            users += people.people_for("HR Manager", None, None)
        users = [user for user in users if user]
        if not users:
            continue
        message = _("Concern {0} for {1} is due on {2}.").format(
            row.name, row.employee_name or row.raised_by,
            frappe.utils.format_date(row.custom_due_on))
        people.notify(list(dict.fromkeys(users)), CONCERN, row.name, message)
    frappe.db.commit()


def _end_suspensions():
    """An employee whose suspension ends today is expected back, and the
    HR Officer is told."""
    rows = frappe.get_all(CASE, filters={"docstatus": 1, "report_back_on": today()},
                          fields=["name", "employee", "employee_name", "branch", "department"],
                          limit=100)
    for row in rows:
        users = people.hr_officers(row.branch, row.department)
        if not users:
            continue
        people.notify(users, CASE, row.name,
                      _("{0}'s suspension ends today; they report back to the HR Office.").format(
                          row.employee_name or row.employee))
    frappe.db.commit()


# ── 5. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the disciplinary case's four desks."""
    from hrms_addon.hrms_addon import discipline_approval, workflows

    workflows.setup_on_migrate(discipline_approval, "Disciplinary Case workflow")


def seed_discipline_masters():
    """The ladder and the misconduct Luuka's HR manual lists. An existing
    one is left exactly as they have set it up."""
    made = []
    for name, rung, months, days in grievance_rules.ACTION_TYPES:
        if frappe.db.exists("Disciplinary Action Type", name):
            continue
        doc = frappe.new_doc("Disciplinary Action Type")
        doc.update({"action_name": name, "rung": rung, "validity_months": months,
                    "suspension_days": days})
        doc.insert(ignore_permissions=True)
        made.append(name)
    for name, severity in grievance_rules.MISCONDUCT:
        if frappe.db.exists("Misconduct Type", name):
            continue
        doc = frappe.new_doc("Misconduct Type")
        doc.update({"misconduct_name": name, "severity": severity})
        doc.insert(ignore_permissions=True)
        made.append(name)
    return made
