# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The safety incident on the site (Luuka's review list of 5 Nov 2026, items
11 to 17).

The rules are in safety_rules.py and the signatures in safety_approval.py,
without a Frappe import (scripts/verify_safety.py). This reads and writes the
site.

  incident_*    the Safety Incident's events, from its controller: the step
                taken and who may take it, the two reports' signatures, the
                doctor's reports, where the employee stands, and who is told
                by name
  ehs_officer   the plant's EHS Officer, as the incident names them: whoever
                holds the role for the employee's plant today, never picked by
                hand (review item 12)
  separate_on_medical_grounds
                the HR Manager's decision on the doctor's recommendation
                (item 17), with Luuka's letter on the separation
  daily         a rest that ended yesterday with no report since: the
                doctor's next word is asked for
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, format_date, getdate, today

from hrms_addon.hrms_addon import people, safety_approval as approval, safety_rules as rules

DOCTYPE = approval.DOCTYPE
REPORTS = "medical_reports"
INCIDENT_FIELDS = ("employee", "incident_on", "nature", "manageable", "hospital", "compensation_required",
                   "compensation_amount")


# ── 1. Each save ──────────────────────────────────────────────────────
def incident_validate(doc, method=None):
    """A save while the incident is a draft or being approved, and the save
    that records it."""
    _take_step(doc)
    _set_status(doc)


def incident_before_update_after_submit(doc, method=None):
    """A save once the incident is recorded: the investigation's steps, and
    the doctor's reports that follow."""
    _take_step(doc)
    _set_status(doc)


def _take_step(doc):
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD) or approval.DRAFT
    if approval.officer_fixed(old_state, new_state):
        doc.ehs_officer = ehs_officer(doc.get("branch"))
    for row in doc.get(REPORTS) or []:
        row.rest_to = rules.rest_to(row.get("rest_from"), row.get("rest_days")) \
            if row.get("recommendation") == rules.REST else None
    rows = _rows(doc)
    errors = []
    if new_state != approval.DRAFT:
        errors += rules.incident_errors({field: doc.get(field) for field in INCIDENT_FIELDS})
        errors += rules.report_errors(rows, doc.get("incident_on"))
    if before is not None:
        errors += rules.fixed_row_errors(_rows(before), rows)
    errors += approval.step_errors(old_state, new_state, _step_facts(doc))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(DOCTYPE))
    # the signatures as they were saved, never as the form sends them
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)


def ehs_officer(branch):
    """The plant's EHS Officer: who holds the role for the plant, else one
    who serves every plant (people.people_for)."""
    officers = people.people_for(approval.EHS, branch)
    return officers[0] if officers else None


def _rows(doc):
    return [row.as_dict() for row in doc.get(REPORTS) or []]


def _step_facts(doc):
    user = frappe.session.user
    return {
        "user": user, "is_hrm": approval.HRM in frappe.get_roles(user),
        "ehs_officer": doc.get("ehs_officer"), "branch": doc.get("branch"),
        "incident_report": doc.get("ehs_report"), "investigation_report": doc.get("investigation_report"),
        "root_cause": doc.get("root_cause"), "findings": doc.get("findings"),
        "return_remarks": doc.get("return_remarks"), "investigation_remarks": doc.get("investigation_remarks"),
    }


def _set_status(doc):
    doc.status = rules.incident_status(doc.docstatus, _rows(doc), doc.get("manageable"), doc.get("separation"))


# ── 2. After each save ────────────────────────────────────────────────
def incident_on_update(doc, method=None):
    # the save that records the incident is told in incident_on_submit,
    # which Frappe runs straight after this one
    if doc.docstatus == 0:
        _tell_step(doc)


def incident_on_submit(doc, method=None):
    """Recorded: every doctor's report on it sets going what it gives."""
    _follow_reports(doc, set())
    _tell_step(doc)


def incident_on_update_after_submit(doc, method=None):
    before = doc.get_doc_before_save()
    _follow_reports(doc, {row.name for row in (before.get(REPORTS) or [])} if before else set())
    _tell_step(doc)


def incident_on_cancel(doc, method=None):
    # on_cancel runs after the write: a field set here would not be saved
    doc.db_set("status", rules.CANCELLED, update_modified=False)
    people.withdraw(DOCTYPE, doc.name, [doc.get("ehs_officer")])


def _follow_reports(doc, known):
    """What the doctor's reports set going: a sick leave for each rest, and,
    when the latest report is new, word of light duty to whoever the
    employee works under, or of a finding of unfit for work to HR."""
    rows = list(doc.get(REPORTS) or [])
    for row in rows:
        if row.get("recommendation") == rules.REST and not row.get("leave_application"):
            _raise_sick_leave(doc, row)
    latest = rules.latest_report(rows)
    if latest is None or latest.get("name") in known:
        return
    who = doc.get("employee_name") or doc.get("employee")
    if latest.get("recommendation") == rules.LIGHT_DUTY:
        _tell(_line_managers(doc), doc, _("{0} is back on light duty from {1}, on the doctor's report: {2}").format(
            who, format_date(getdate(latest.get("report_date"))), latest.get("light_duties") or ""))
    elif latest.get("recommendation") == rules.UNFIT:
        _tell(people.people_for(approval.HRM, doc.get("branch"), doc.get("department"))
              + people.hr_officers(doc.get("branch"), doc.get("department")), doc,
              _("The doctor finds {0} unfit for work: the HR Manager decides on a separation on medical "
                "grounds.").format(who))


def _line_managers(doc):
    """Who the employee works under: who they report to, the head of their
    department, and HR."""
    users = []
    manager = frappe.db.get_value("Employee", doc.employee, "reports_to")
    if manager:
        users.append(frappe.db.get_value("Employee", manager, "user_id"))
    users += people.people_for("Head of Department", doc.get("branch"), doc.get("department"))
    users += people.hr_officers(doc.get("branch"), doc.get("department"))
    return users


def _tell_step(doc):
    """The plant's EHS Officer and HR, told by name what waits for them."""
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    officer, earlier = doc.get("ehs_officer"), before.get("ehs_officer") if before else None
    about = _("{0}'s accident of {1}").format(doc.get("employee_name") or doc.get("employee"),
                                              format_date(getdate(doc.get("incident_on"))))
    hr = people.hr_officers(doc.get("branch"), doc.get("department"))
    if old_state == new_state:
        if earlier and officer != earlier and new_state in (approval.PENDING_EHS, approval.RECORDED):
            # the plant has another EHS Officer now: what waited for the last one is theirs
            people.withdraw(DOCTYPE, doc.name, [earlier])
            _give([officer], doc, _("Approve the incident report on {0}.").format(about)
                  if new_state == approval.PENDING_EHS
                  else _("Investigate {0} and submit the investigation report.").format(about))
        return
    if new_state == approval.PENDING_EHS:
        _give([officer], doc, _("Approve the incident report on {0}.").format(about))
    elif new_state == approval.PENDING_HR:
        people.withdraw(DOCTYPE, doc.name, [earlier, officer])
        _tell(hr, doc, _("Acknowledge the incident report on {0}.").format(about))
    elif new_state == approval.RECORDED and old_state == approval.PENDING_HR:
        _give([officer], doc, _("Investigate {0} and submit the investigation report.").format(about))
    elif new_state == approval.RECORDED and old_state == approval.INVESTIGATED:
        _give([officer], doc, _("The investigation report on {0} was returned: {1}").format(
            about, doc.get("investigation_remarks") or ""))
    elif new_state == approval.INVESTIGATED:
        people.withdraw(DOCTYPE, doc.name, [earlier, officer])
        _tell(hr, doc, _("Acknowledge the investigation report on {0}.").format(about))
    elif new_state == approval.CLOSED:
        _tell([doc.get("investigated_by") or officer], doc,
              _("HR have acknowledged the investigation report on {0}.").format(about))
    elif new_state == approval.DRAFT:
        people.withdraw(DOCTYPE, doc.name, [earlier, officer])
        _tell([doc.get("owner")], doc, _("The incident report on {0} was returned: {1}").format(
            about, doc.get("return_remarks") or ""))


def _tell(users, doc, message):
    people.notify(_unique(users), DOCTYPE, doc.name, message)


def _give(users, doc, message):
    users = _unique(users)
    people.notify(users, DOCTYPE, doc.name, message)
    people.assign(DOCTYPE, doc.name, users, message)


def _unique(users):
    return list(dict.fromkeys(user for user in users if user))


# ── 3. What the doctor's reports become ───────────────────────────────
def _raise_sick_leave(doc, row):
    """The rest the doctor gave, as the employee's sick leave (step 6 of the
    chart: the HR Officer creates it)."""
    if not frappe.db.exists("Leave Type", rules.SICK_LEAVE):
        return None
    start, days = getdate(row.get("rest_from")), cint(row.get("rest_days"))
    try:
        leave = frappe.get_doc({
            "doctype": "Leave Application", "employee": doc.employee, "company": doc.company,
            "leave_type": rules.SICK_LEAVE, "from_date": start, "to_date": add_days(start, days - 1),
            "total_leave_days": days,
            "description": _("Sick leave from safety incident {0}, on the doctor's report of {1}: {2}").format(
                doc.name, format_date(getdate(row.get("report_date"))), doc.get("nature") or ""),
            "custom_medical_certificate": row.get("report") or doc.get("ehs_report"),
        })
        leave.flags.ignore_permissions = True
        leave.flags.ignore_mandatory = True
        leave.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: sick leave from a safety incident")
        return None
    row.db_set("leave_application", leave.name, update_modified=False)
    doc.db_set("sick_leave", leave.name, update_modified=False)
    return leave.name


@frappe.whitelist(methods=["POST"])
def separate_on_medical_grounds(incident, last_day=None):
    """The HR Manager's decision on the doctor's recommendation (item 17:
    "Termination comes on doctor's recommendation"): the employee is
    separated on medical grounds, their last day of work the one given, by
    default the end of the last rest the doctor gave. Luuka's Termination on
    Medical Grounds letter prints from the separation."""
    doc = frappe.get_doc(DOCTYPE, incident)
    doc.check_permission("write")
    rows = _rows(doc)
    errors = rules.separation_errors(doc.docstatus, rows, doc.get("separation"), frappe.get_roles())
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(DOCTYPE))
    last = getdate(last_day) if last_day else rules.last_day_of_work(rows, today())
    name = _separate(doc, last)
    if not name:
        frappe.throw(_("The separation could not be made: see the Error Log."), title=_(DOCTYPE))
    doc.db_set({"separation": name, "status": rules.SEPARATED}, update_modified=False)
    _tell(people.hr_officers(doc.get("branch"), doc.get("department")), doc,
          _("{0} is separated on medical grounds, the last day of work {1}: {2}.").format(
              doc.get("employee_name") or doc.employee, format_date(last), name))
    return name


def _separate(doc, last_day):
    """The separation on medical grounds; an employee already on their way
    out keeps the one separation they have."""
    existing = frappe.db.get_value("Employee Separation",
                                   {"employee": doc.employee, "docstatus": ["<", 2]}, "name")
    if existing:
        return existing
    try:
        exit_doc = frappe.get_doc({
            "doctype": "Employee Separation", "employee": doc.employee, "company": doc.company,
            "department": doc.get("department"), "boarding_status": "Pending",
            "custom_exit_type": "Involuntary", "custom_reason": "Medical Grounds",
            "custom_relieving_date": last_day, "custom_termination_date": today(),
            "custom_termination_reason": _("On the doctor's recommendation, after safety incident {0}: {1}").format(
                doc.name, doc.get("nature") or ""),
        })
        exit_doc.flags.ignore_permissions = True
        exit_doc.flags.ignore_mandatory = True
        exit_doc.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: separation on medical grounds")
        return None
    return exit_doc.name


# ── 4. The doctor's next word ─────────────────────────────────────────
def daily():
    """A rest the doctor gave that ended yesterday, with no report since:
    the plant's EHS Officer and HR are asked for the doctor's next report."""
    for name in frappe.get_all(DOCTYPE, filters={"docstatus": 1, "status": rules.ON_SICK_LEAVE}, pluck="name",
                               limit_page_length=0):
        doc = frappe.get_doc(DOCTYPE, name)
        ended = rules.rest_ended(_rows(doc), today())
        if not ended:
            continue
        _tell([doc.get("ehs_officer")] + people.hr_officers(doc.get("branch"), doc.get("department")), doc,
              _("{0}'s rest ended on {1}: add the doctor's next report (back at work, light duty, more rest or "
                "unfit for work).").format(doc.get("employee_name") or doc.employee, format_date(ended)))


# ── 5. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the incident's approval by the plant's EHS Officer."""
    from hrms_addon.hrms_addon import workflows

    workflows.setup_on_migrate(approval, "Safety Incident workflow")
