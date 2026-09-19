# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Onboarding, the Frappe side of Luuka's To-Be induction process.

The rules are in onboarding_rules.py and the workflow in onboarding_approval.py
(no Frappe import, tested by scripts/verify_onboarding.py). This wires them
into Frappe HR's Employee Onboarding:

  validate                    the defaults an onboarding takes from its
                              candidate (onboarding_defaults), the workflow
                              step's checks and the HR Manager's stamp, and,
                              as the onboarding starts (it is submitted then),
                              each activity handed to its own people
  before_update_after_submit  every later step is an update after submit, and
                              Frappe runs no validate then: the same checks,
                              and activities added after the start handed out
  after_tasks                 on_submit / on_update_after_submit, once Frappe
                              HR made the tasks: the task shared with anyone
                              else the activity went to, and each of them
                              allowed to complete it
  get_onboarding_defaults     the form fills itself from the candidate
  add_placement               Create Employee: branch, employment type, offer date
  seed_onboarding             Luuka's templates and Workplace Rules, once

WHY THE ROLE IS CLEARED

Frappe HR assigns an activity's task to its user and to EVERY enabled holder
of its role (hrms/controllers/employee_boarding_controller.py), in every
branch. So each role is resolved first (onboarding_rules.activity_assignees)
and the activity keeps the first person as its user and no role; anyone else
it resolved to is added in after_tasks. frappe.flags carries that list across
Frappe HR's reload in on_submit, keyed by onboarding and activity row.
"""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import onboarding_approval as approval
from hrms_addon.hrms_addon import onboarding_rules as rules
from hrms_addon.hrms_addon import workflows

# {onboarding: {activity idx: [users]}} for after_tasks, within one request
_ASSIGNEES = "hrms_addon_onboarding_assignees"
# What onboarding_defaults may fill in on save. The template is left to the
# form: choosing one there loads its activities (Frappe HR's form script).
_SERVER_DEFAULTS = ("job_offer", "company", "department", "designation", "custom_branch", "custom_head_of_department",
                    "custom_hr_officer", "holiday_list")


def validate(doc, method=None):
    """Employee Onboarding validate (save and start), after Frappe HR's own."""
    _apply_defaults(doc)
    _check_step(doc)
    if doc.docstatus == 1:  # validate runs for a submit, never an update after one: the onboarding starts
        _resolve_assignees(doc)


def before_update_after_submit(doc, method=None):
    """Every step after the start (Submit for Approval, Approve, Return)."""
    _check_step(doc)
    _resolve_assignees(doc)


def after_tasks(doc, method=None):
    """on_submit and on_update_after_submit, after Frappe HR's (which made the
    tasks): the other people an activity went to get its task too, and all of
    them may complete it."""
    from frappe.desk.form.assign_to import _add
    from frappe.share import add_docshare

    resolved = (frappe.flags.get(_ASSIGNEES) or {}).pop(doc.name, {})
    for activity in doc.activities:
        users = resolved.get(activity.idx)
        if not users or not activity.task:
            continue
        for user in users[1:]:
            _add(
                {
                    "assign_to": [user],
                    "doctype": "Task",
                    "name": activity.task,
                    "description": activity.description or activity.activity_name,
                    "notify": doc.notify_users_by_email,
                },
                ignore_permissions=True,
            )
        # Frappe shares a task read-only with an assignee who cannot open
        # Tasks (a Head of Department); completing it needs write
        for user in users:
            if not frappe.has_permission("Task", "write", activity.task, user=user):
                add_docshare("Task", activity.task, user, write=1, flags={"ignore_share_permission": True})


def _apply_defaults(doc):
    if not doc.get("job_applicant"):
        return
    values = onboarding_defaults(doc.job_applicant, doc.get("job_offer"))
    for field in _SERVER_DEFAULTS:
        if not doc.get(field) and values.get(field):
            doc.set(field, values[field])
    if not doc.get("custom_hr_officer"):
        doc.custom_hr_officer = frappe.session.user  # nobody holds HR User for the branch
    if not doc.get("boarding_begins_on") and doc.get("date_of_joining"):
        doc.boarding_begins_on = doc.date_of_joining


def _check_step(doc):
    """The workflow step this save makes, if any: its checks, then the HR
    Manager's stamp (recorded on approval, a typed one reverts)."""
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, _facts(doc))
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Onboarding"))
    current = {field: before.get(field) for field in approval.STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)


def _facts(doc):
    employee = doc.get("employee")
    return {
        "head_of_department": doc.get("custom_head_of_department"),
        "activities": len(doc.get("activities") or []),
        # Frappe HR dates the tasks by the Employee's holiday list, else this one
        "holiday_list": doc.get("holiday_list") or employee,
        "employee": employee,
        "rules_signed_on": doc.get("custom_rules_signed_on"),
        "bio_data_signed_on": frappe.db.get_value("Employee", employee, "custom_bio_data_signed_on") if employee else None,
        "hrm_remarks": doc.get("custom_hrm_remarks"),
    }


def _resolve_assignees(doc):
    """Each activity not yet a task goes to this onboarding's own people: its
    named user, else its role resolved by rules.activity_assignees, else the
    HR Officer. The activity keeps the first of them and loses its role."""
    named = {rules.HR_OFFICER_ROLE: doc.get("custom_hr_officer"), rules.HOD_ROLE: doc.get("custom_head_of_department")}
    holders, resolved = {}, {}
    for activity in doc.activities:
        if activity.get("task") or not (activity.role or activity.user):
            continue
        if activity.user:
            users = [activity.user]
        else:
            if activity.role not in holders:
                holders[activity.role] = _holders(activity.role)
            users = rules.activity_assignees(
                activity.role, named, holders[activity.role], doc.get("custom_branch"), doc.get("department")
            ) or [doc.get("custom_hr_officer")]
        activity.user, activity.role = users[0], None
        resolved[activity.idx] = [user for user in users if user]
    if resolved:
        frappe.flags.setdefault(_ASSIGNEES, {})[doc.name] = resolved


def _holders(role):
    """[{"user", "branches", "departments"}] for the enabled users holding
    `role`, with the Branch and Department User Permissions limiting them."""
    users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", distinct=True)
    if not users:
        return []
    users = frappe.get_all(
        "User",
        filters=[["name", "in", users], ["name", "not in", ["Administrator", "Guest"]], ["enabled", "=", 1]],
        pluck="name",
    )
    limits = {user: {"Branch": set(), "Department": set()} for user in users}
    if users:
        for perm in frappe.get_all(
            "User Permission",
            filters={"user": ["in", users], "allow": ["in", ["Branch", "Department"]]},
            fields=["user", "allow", "for_value"],
        ):
            limits[perm.user][perm.allow].add(perm.for_value)
    return [{"user": user, "branches": limits[user]["Branch"], "departments": limits[user]["Department"]}
            for user in sorted(users)]


@frappe.whitelist()
def get_onboarding_defaults(job_applicant, job_offer=None):
    """For the form: what a new onboarding for this candidate starts with."""
    frappe.has_permission("Employee Onboarding", "create", throw=True)
    return onboarding_defaults(job_applicant, job_offer)


def onboarding_defaults(job_applicant, job_offer=None):
    """{field: value} an onboarding takes from its candidate: the accepted
    Job Offer, the company, Job Title and Branch offered, the Job Opening's
    department, the Head of Department who approved the requisition (else
    the branch's), the branch HR Officer, the company's holiday list, and the
    template (onboarding_rules.pick_template). Blank values are left out."""
    applicant = frappe.db.get_value("Job Applicant", job_applicant, ["job_title", "designation"], as_dict=True)
    if not applicant:
        return {}
    job_offer = job_offer or _accepted_offer(job_applicant)
    opening = frappe._dict()
    if applicant.job_title:
        opening = frappe.db.get_value(
            "Job Opening", applicant.job_title,
            ["company", "department", "designation", "location", "job_requisition"], as_dict=True,
        ) or opening
    offer = frappe._dict()
    if job_offer:
        offer = frappe.db.get_value("Job Offer", job_offer, ["company", "designation", "custom_branch"], as_dict=True) or offer

    company = offer.company or opening.company
    branch, department = offer.custom_branch or opening.location, opening.department
    designation = offer.designation or opening.designation or applicant.designation
    hod = frappe.db.get_value("Job Requisition", opening.job_requisition, "custom_hod") if opening.job_requisition else None
    category = frappe.db.get_value("Department", department, "custom_position_category") if department else None
    values = {
        "job_offer": job_offer,
        "company": company,
        "department": department,
        "designation": designation,
        "custom_branch": branch,
        "custom_head_of_department": hod or _first(
            rules.activity_assignees(rules.HOD_ROLE, {}, _holders(rules.HOD_ROLE), branch, department)
        ),
        "custom_hr_officer": _first(
            rules.activity_assignees(rules.HR_OFFICER_ROLE, {}, _holders(rules.HR_OFFICER_ROLE), branch, department)
        ),
        "holiday_list": frappe.get_cached_value("Company", company, "default_holiday_list") if company else None,
        "employee_onboarding_template": rules.pick_template(
            frappe.get_all("Employee Onboarding Template", fields=["name", "title", "company", "department", "designation"]),
            company, department, designation, category,
        ),
    }
    return {field: value for field, value in values.items() if value}


def _accepted_offer(job_applicant):
    """The candidate's submitted Job Offer: the accepted one, else the only one."""
    offers = frappe.get_all(
        "Job Offer", filters={"job_applicant": job_applicant, "docstatus": 1}, fields=["name", "status"],
        order_by="creation desc",
    )
    accepted = [offer.name for offer in offers if offer.status == "Accepted"]
    if accepted:
        return accepted[0]
    return offers[0].name if len(offers) == 1 else None


def _first(users):
    return users[0] if users else None


def add_placement(employee, source_doctype, source_name):
    """Create Employee, from the onboarding or the Job Offer: the Branch, the
    Job Opening's Employment Type and the offer's date (Employee's Offer
    Date), where the new Employee has none."""
    source = frappe.db.get_value(source_doctype, source_name, ["custom_branch", "job_applicant"], as_dict=True) or frappe._dict()
    offer = source_name if source_doctype == "Job Offer" else frappe.db.get_value(source_doctype, source_name, "job_offer")
    opening = frappe.db.get_value("Job Applicant", source.job_applicant, "job_title") if source.job_applicant else None
    placed = frappe.db.get_value("Job Opening", opening, ["location", "employment_type"], as_dict=True) if opening else None
    placed = placed or frappe._dict()
    values = {
        "branch": source.custom_branch or placed.location,
        "employment_type": placed.employment_type,
        "scheduled_confirmation_date": frappe.db.get_value("Job Offer", offer, "offer_date") if offer else None,
    }
    for field, value in values.items():
        if value and not employee.get(field):
            employee.set(field, value)
    return employee


def setup_workflow_on_migrate():
    """after_migrate: the onboarding workflow (workflows.py)."""
    workflows.setup_on_migrate(approval, "Employee Onboarding workflow")


def seed_onboarding():
    """Luuka's onboarding templates and Workplace Rules and Regulations, once:
    HR's to change afterwards, so a template (by title) or the rules already
    there are left as they are."""
    for role in sorted({activity[1] for activities in rules.TEMPLATES.values() for activity in activities}):
        # Head of Department comes with the requisition workflow, which a
        # fresh install only builds on its first migrate
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    for title in rules.TEMPLATES:
        if frappe.db.exists("Employee Onboarding Template", {"title": title}):
            continue
        frappe.get_doc({
            "doctype": "Employee Onboarding Template",
            "title": title,
            "company": company,
            "activities": rules.template_activities(title),
        }).insert(ignore_permissions=True)
    if not frappe.db.exists("Terms and Conditions", rules.WORKPLACE_RULES_TITLE):
        frappe.get_doc({
            "doctype": "Terms and Conditions",
            "title": rules.WORKPLACE_RULES_TITLE,
            "hr": 1,
            "selling": 0,
            "buying": 0,
            "terms": rules.WORKPLACE_RULES_HTML,
        }).insert(ignore_permissions=True)


def after_install():
    seed_onboarding()
