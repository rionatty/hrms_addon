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
  link_onboarding             Employee on_update: the candidate's onboarding
                              learns its Employee (see WHY THE EMPLOYEE IS LINKED)
  seed_onboarding             Luuka's templates and Workplace Rules, once

WHY THE ROLE IS CLEARED

Frappe HR assigns an activity's task to its user and to EVERY enabled holder
of its role (hrms/controllers/employee_boarding_controller.py), in every
branch. So each role is resolved first (onboarding_rules.activity_assignees)
and the activity keeps the first person as its user and no role; anyone else
it resolved to is added in after_tasks. frappe.flags carries that list across
Frappe HR's reload in on_submit, keyed by onboarding and activity row.

WHY THE EMPLOYEE IS LINKED

Frappe HR writes the new Employee onto its onboarding only while the
onboarding's tasks are not all done (hrms/overrides/employee_master.py,
boarding_status != Completed). An Employee created after they are stayed
unknown to its onboarding, which then could not go to the HR Manager. So the
Employee links itself (link_onboarding), and a step finds one not linked by
the candidate (_link_employee).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import contracts, people, probation, reviews, workflows
from hrms_addon.hrms_addon import onboarding_approval as approval
from hrms_addon.hrms_addon import onboarding_rules as rules
from hrms_addon.hrms_addon import probation_rules

# {onboarding: {activity idx: [users]}} for after_tasks, within one request
_ASSIGNEES = "hrms_addon_onboarding_assignees"
# What onboarding_defaults may fill in on save. The template is left to the
# form: choosing one there loads its activities (Frappe HR's form script).
_SERVER_DEFAULTS = ("job_offer", "company", "department", "designation", "custom_branch", "custom_head_of_department",
                    "custom_hr_officer", "holiday_list", "custom_supervisor", "custom_base_salary")


def validate(doc, method=None):
    """Employee Onboarding validate (save and start), after Frappe HR's own."""
    _apply_defaults(doc)
    _medical_check(doc)
    _check_step(doc)
    if doc.docstatus == 1:  # validate runs for a submit, never an update after one: the onboarding starts
        _request_tools(doc)
        _resolve_assignees(doc)


def before_update_after_submit(doc, method=None):
    """Every step after the start (Submit for Approval, Approve, Return)."""
    _link_employee(doc)
    _medical_check(doc)
    old_state, new_state = _check_step(doc)
    if new_state != old_state and new_state == approval.PENDING_HRM:
        _draft_salary(doc)
    if new_state != old_state and new_state == approval.APPROVED:
        _approve(doc)
    _request_tools(doc)
    _resolve_assignees(doc)


def on_cancel(doc, method=None):
    """A cancelled onboarding drops the salary structure it drafted; one
    already approved is payroll's, and stays."""
    name = doc.get("custom_salary_structure_assignment")
    if name and frappe.db.get_value("Salary Structure Assignment", name, "docstatus") == 0:
        frappe.delete_doc("Salary Structure Assignment", name, ignore_permissions=True)


def link_onboarding(employee, method=None):
    """Employee on_update: its candidate's started onboarding, if it has no
    Employee yet, gets this one, whether or not its tasks are all done."""
    if not employee.get("job_applicant"):
        return
    onboarding = frappe.db.get_value(
        "Employee Onboarding",
        {"job_applicant": employee.job_applicant, "docstatus": 1, "employee": ("is", "not set")},
        "name",
    )
    if onboarding:
        frappe.db.set_value("Employee Onboarding", onboarding, "employee", employee.name, update_modified=False)


def _link_employee(doc):
    """An onboarding whose Employee was never linked (created before this app
    linked them): found by the candidate. Employee is not allow_on_submit, so
    it is written straight to the database, as Frappe HR does; the check for
    changes after submit compares with a fresh copy, and sees none."""
    if doc.get("employee") or not doc.get("job_applicant"):
        return
    employee = frappe.db.get_value("Employee", {"job_applicant": doc.job_applicant}, "name")
    if employee:
        doc.db_set("employee", employee, update_modified=False)


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
    if not doc.get("custom_salary_from") and doc.get("date_of_joining"):
        doc.custom_salary_from = doc.date_of_joining
    if doc.docstatus == 0 and not doc.get("custom_tools") and doc.get("designation"):
        for row in _default_tools(doc.designation):
            doc.append("custom_tools", row)


def _default_tools(designation):
    """The tools every new employee gets, then the Job Title's own."""
    every = [(name, 1) for name in frappe.get_all("Tool of Work", filters={"all_staff": 1}, pluck="name",
                                                   order_by="tool_name asc")]
    own = [(row.tool, row.qty) for row in frappe.get_all(
        "Designation Tool", filters={"parent": designation, "parenttype": "Designation", "parentfield": "custom_tools"},
        fields=["tool", "qty"], order_by="idx asc")]
    return rules.default_tools(every, own)


def _check_step(doc):
    """The workflow step this save makes, if any: its checks, then the HR
    Manager's stamp (recorded on approval, a typed one reverts). Returns
    (old state, new state)."""
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
    return old_state, new_state


def _facts(doc):
    employee = doc.get("employee")
    structure, supervisor = doc.get("custom_salary_structure"), doc.get("custom_supervisor")
    return {
        "head_of_department": doc.get("custom_head_of_department"),
        "activities": len(doc.get("activities") or []),
        # Frappe HR dates the tasks by the Employee's holiday list, else this one
        "holiday_list": doc.get("holiday_list") or employee,
        "employee": employee,
        "rules_signed_on": doc.get("custom_rules_signed_on"),
        "bio_data_signed_on": frappe.db.get_value("Employee", employee, "custom_bio_data_signed_on") if employee else None,
        "hrm_remarks": doc.get("custom_hrm_remarks"),
        "supervisor": supervisor,
        "supervisor_is_employee": bool(supervisor and supervisor == employee),
        "salary_structure": structure,
        "base_salary": flt(doc.get("custom_base_salary")),
        "salary_from": str(doc.custom_salary_from) if doc.get("custom_salary_from") else None,
        "date_of_joining": str(doc.date_of_joining) if doc.get("date_of_joining") else None,
        "tax_slab_needed": structure if structure and not doc.get("custom_income_tax_slab") and _deducts_tax(structure) else None,
        "tools_pending": rules.pending_tools([{"tool": row.tool, "status": row.status} for row in doc.get("custom_tools") or []]),
        "training_required": doc.get("custom_training_required"),
        "training_missing": rules.training_missing(doc.as_dict()),
        "medical_certificate_missing": bool(doc.get("custom_medical_check") and not doc.get("custom_medical_certificate")),
    }


def _medical_check(doc):
    """Whether the job needs a doctor's check before joining, from its JD: the
    health question the interview no longer asks. Kept on the onboarding, so
    the certificate's place shows."""
    needed = doc.get("designation") and frappe.db.get_value("Designation", doc.designation, "custom_medical_check")
    doc.custom_medical_check = 1 if needed else 0


def _deducts_tax(structure):
    from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import get_tax_component

    return bool(get_tax_component(structure))


def _request_tools(doc):
    """The tools not yet asked for: one activity per provider, handed to that
    provider's people in the branch like any other activity; the tools are
    then Requested."""
    rows = [row for row in doc.get("custom_tools") or [] if not row.status and row.tool]
    if not rows:
        return
    tools = {tool.name: tool for tool in frappe.get_all(
        "Tool of Work", filters={"name": ["in", [row.tool for row in rows]]}, fields=["name", "provider", "before_day_one"])}
    providers = dict(frappe.get_all("Tool Provider", fields=["name", "responsible_role"], as_list=True))
    requests = rules.tool_requests(
        [{"tool": row.tool, "provider": (tools.get(row.tool) or {}).get("provider"), "qty": row.qty, "status": row.status,
          "before_day_one": (tools.get(row.tool) or {}).get("before_day_one")} for row in rows],
        providers,
    )
    for activity in requests:
        doc.append("activities", activity)
    for row in rows:
        row.status = rules.TOOL_REQUESTED


def _draft_salary(doc):
    """Step 5: the Salary Structure Assignment, drafted from the Salary
    section when the onboarding goes to the HR Manager, and brought up to
    date with it until approved. Returns it."""
    name = doc.get("custom_salary_structure_assignment")
    if not (name and frappe.db.exists("Salary Structure Assignment", name)):
        # one HR already made from the Employee: Frappe HR allows one per date
        name = frappe.db.get_value("Salary Structure Assignment", {
            "employee": doc.employee, "from_date": doc.custom_salary_from, "docstatus": ["!=", 2]}, "name")
    if name:
        assignment = frappe.get_doc("Salary Structure Assignment", name)
        if assignment.docstatus != 0:
            doc.custom_salary_structure_assignment = assignment.name
            return assignment
    else:
        assignment = frappe.new_doc("Salary Structure Assignment")
    assignment.update({
        "employee": doc.employee,
        "company": doc.company,
        "salary_structure": doc.custom_salary_structure,
        "currency": frappe.db.get_value("Salary Structure", doc.custom_salary_structure, "currency"),
        "from_date": doc.custom_salary_from,
        "base": flt(doc.custom_base_salary),
        "variable": flt(doc.get("custom_variable_pay")),
        "income_tax_slab": doc.get("custom_income_tax_slab"),
    })
    assignment.flags.ignore_permissions = True
    assignment.save()
    doc.custom_salary_structure_assignment = assignment.name
    return assignment


def _approve(doc):
    """The HR Manager approved (steps 5 to 7 and after): the salary structure
    submitted, the Employee reporting to the supervisor with the tools issued
    and on probation, the training scheduled if required, the 30-60-90 reviews
    and the probation evaluation made, and the contract drafted."""
    assignment = _draft_salary(doc)
    if assignment.docstatus == 0:
        assignment.flags.ignore_permissions = True
        assignment.submit()
    probation_end = probation_rules.probation_end(doc.date_of_joining, probation.settings().probation_months)
    _update_employee(doc, probation_end)
    if doc.get("custom_training_required"):
        _schedule_training(doc)
    reviews.create_reviews(doc.employee, doc.date_of_joining, doc.name, doc.custom_hr_officer)
    if not frappe.db.exists("Probation Evaluation", {"employee": doc.employee, "docstatus": ["!=", 2]}):
        probation.create_evaluation(doc.employee, probation_end, onboarding=doc.name, hr_officer=doc.custom_hr_officer)
    contracts.draft_for_new_employee(doc.employee, doc.custom_hr_officer, flt(doc.get("custom_base_salary")), doc.name)


def _update_employee(doc, probation_end):
    """Step 7 and the tools register: Reports To, the tools issued (for the
    clearance when the employee leaves) and the probation."""
    employee = frappe.get_doc("Employee", doc.employee)
    if doc.get("custom_supervisor"):
        employee.reports_to = doc.custom_supervisor
    have = {(row.tool, row.onboarding) for row in employee.get("custom_employee_tools") or []}
    for row in doc.get("custom_tools") or []:
        if row.status == rules.TOOL_ISSUED and (row.tool, doc.name) not in have:
            employee.append("custom_employee_tools", {
                "tool": row.tool, "qty": row.qty, "serial_no": row.serial_no, "issued_on": row.issued_on,
                "onboarding": doc.name, "remarks": row.remarks,
            })
    if not employee.get("custom_probation_end_date"):
        employee.custom_probation_end_date = probation_end
        employee.custom_probation_status = probation_rules.ON_PROBATION
    employee.flags.ignore_permissions = True
    employee.save()


def _schedule_training(doc):
    """"Training Required?" Yes: the Training Event for the new employee, and
    the supervisor's task to evaluate it (an activity like the others)."""
    if doc.get("custom_training_event"):
        return
    start, end = rules.training_window(doc.custom_training_start, doc.custom_training_days)
    program = doc.get("custom_training_program")
    introduction = (doc.get("custom_training_scope") or "").strip() or (
        frappe.db.get_value("Training Program", program, "description") if program else "") or "Induction training"
    event = frappe.get_doc({
        "doctype": "Training Event",
        "event_name": "%s: %s (%s)" % ((doc.employee_name or "")[:50], (program or "Induction training")[:50], doc.name),
        "training_program": program,
        "event_status": "Scheduled",
        "type": doc.get("custom_training_type") or "Workshop",
        "company": doc.company,
        "trainer_name": doc.custom_trainer_name,
        "trainer_email": doc.get("custom_trainer_email"),
        "location": doc.custom_training_location,
        "start_time": start,
        "end_time": end,
        "introduction": introduction,
        "employees": [{"employee": doc.employee}],
    })
    event.insert(ignore_permissions=True)
    doc.custom_training_event = event.name
    activity = rules.training_evaluation_activity(doc.boarding_begins_on, doc.custom_training_start, doc.custom_training_days)
    supervisor_user = frappe.db.get_value("Employee", doc.custom_supervisor, "user_id") if doc.get("custom_supervisor") else None
    activity.update({"user": supervisor_user, "role": None if supervisor_user else rules.HOD_ROLE})
    doc.append("activities", activity)


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
                holders[activity.role] = people.holders(activity.role)
            users = rules.activity_assignees(
                activity.role, named, holders[activity.role], doc.get("custom_branch"), doc.get("department")
            ) or [doc.get("custom_hr_officer")]
        activity.user, activity.role = users[0], None
        resolved[activity.idx] = [user for user in users if user]
    if resolved:
        frappe.flags.setdefault(_ASSIGNEES, {})[doc.name] = resolved


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
    if hod in ("Administrator", "Guest"):
        hod = None  # tasks go to people, as in Frappe HR's own assignment
    requisition = frappe._dict()
    if opening.job_requisition:
        requisition = frappe.db.get_value("Job Requisition", opening.job_requisition,
                                          ["custom_supervisor", "expected_compensation"], as_dict=True) or requisition
    # the Supervisor who signed the requisition, as an Employee (Reports To)
    supervisor = None
    if requisition.custom_supervisor and requisition.custom_supervisor not in ("Administrator", "Guest"):
        supervisor = frappe.db.get_value("Employee", {"user_id": requisition.custom_supervisor, "status": "Active"}, "name")
    category = frappe.db.get_value("Department", department, "custom_position_category") if department else None
    values = {
        "job_offer": job_offer,
        "company": company,
        "department": department,
        "designation": designation,
        "custom_branch": branch,
        "custom_head_of_department": hod or _first(
            rules.activity_assignees(rules.HOD_ROLE, {}, people.holders(rules.HOD_ROLE), branch, department)
        ),
        "custom_hr_officer": _first(
            rules.activity_assignees(rules.HR_OFFICER_ROLE, {}, people.holders(rules.HR_OFFICER_ROLE), branch, department)
        ),
        "custom_supervisor": supervisor,
        # the requisition's Recommended Salary, as the base to confirm
        "custom_base_salary": flt(requisition.expected_compensation) or None,
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


# The Employee's Connections, and those of the other standard documents this
# app hangs things off, moved to connections.py — one place that answers
# "what of ours is reached from where".


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
