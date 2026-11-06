# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The safety incident on the site (Luuka's review list of 5 Nov 2026, items
11 to 17).

The rules are in safety_rules.py and the signatures in safety_approval.py,
without a Frappe import (scripts/verify_safety.py). This reads and writes the
site.

  incident_*    the Safety Incident's events, from its controller: the step
                taken and who may take it, the two reports' signatures, where
                the employee stands, and who is told by name
  ehs_officer   the plant's EHS Officer, as the incident names them: whoever
                holds the role for the employee's plant today, never picked by
                hand (review item 12)
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, format_date, getdate, today

from hrms_addon.hrms_addon import people, safety_approval as approval, safety_rules as rules

DOCTYPE = approval.DOCTYPE
INCIDENT_FIELDS = ("employee", "incident_on", "nature", "manageable", "hospital", "day_off_required", "sick_from",
                   "sick_days", "compensation_required", "compensation_amount")


# ── 1. Each save ──────────────────────────────────────────────────────
def incident_validate(doc, method=None):
    """A save while the incident is a draft or being approved, and the save
    that records it."""
    _take_step(doc)
    _set_status(doc)


def incident_before_update_after_submit(doc, method=None):
    """A save once the incident is recorded: the investigation's steps, and
    the reports that follow."""
    _take_step(doc)
    _set_status(doc)


def _take_step(doc):
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD) or approval.DRAFT
    if approval.officer_fixed(old_state, new_state):
        doc.ehs_officer = ehs_officer(doc.get("branch"))
    errors = rules.incident_errors({field: doc.get(field) for field in INCIDENT_FIELDS}) \
        if new_state != approval.DRAFT else []
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
    doc.status = rules.incident_status(doc.docstatus, doc.get("day_off_required"), doc.get("sick_leave"),
                                       doc.get("sickness_persists"), doc.get("separation"))


# ── 2. After each save ────────────────────────────────────────────────
def incident_on_update(doc, method=None):
    # the save that records the incident is told in incident_on_submit,
    # which Frappe runs straight after this one
    if doc.docstatus == 0:
        _tell_step(doc)


def incident_on_submit(doc, method=None):
    """Recorded. Where a day off is needed the sick leave is raised, and
    where the sickness persists the separation on medical grounds."""
    if doc.get("day_off_required") and not doc.get("sick_leave"):
        _raise_sick_leave(doc)
    if doc.get("sickness_persists") and not doc.get("separation"):
        _separate_on_medical_grounds(doc)
    # the leave and the separation are raised after this save validated,
    # so where the employee stands is said again now that they exist
    status = rules.incident_status(doc.docstatus, doc.get("day_off_required"), doc.get("sick_leave"),
                                   doc.get("sickness_persists"), doc.get("separation"))
    if status != doc.get("status"):
        doc.db_set("status", status, update_modified=False)
    _tell_step(doc)


def incident_on_update_after_submit(doc, method=None):
    _tell_step(doc)


def incident_on_cancel(doc, method=None):
    # on_cancel runs after the write: a field set here would not be saved
    doc.db_set("status", rules.CANCELLED, update_modified=False)
    people.withdraw(DOCTYPE, doc.name, [doc.get("ehs_officer")])


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


# ── 3. What the accident becomes ──────────────────────────────────────
def _raise_sick_leave(doc):
    """Step 6: the HR Officer creates the employee's sick leave."""
    leave_type = rules.SICK_LEAVE
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


# ── 4. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the incident's approval by the plant's EHS Officer."""
    from hrms_addon.hrms_addon import workflows

    workflows.setup_on_migrate(approval, "Safety Incident workflow")
