# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Promotions, changes of designation and salary reviews, on the site.

The rules are in position_rules.py and the signatures in
position_approval.py, both without a Frappe import
(scripts/verify_positions.py). This is what reads and writes the site:

  1  the form is drawn up: the employee's current position, supervisor,
     running contract and gross salary are read in, and for a promotion the
     preamble's education and work experience are offered from the
     employee's bio-data
  2  it is signed by the Supervisor, the HR Manager, the General Manager and
     the Executive Director; a Return sends it back to Draft with every
     signature cleared
  3  the Executive Director's approval submits it, and that applies the
     change: the Employee master, a Salary Structure Assignment from the
     effective date, and the contract amended or replaced as chosen
  4  cancelling puts back what was there before

WHY THE OLD VALUES ARE KEPT ON THE DOCUMENT

The letter is printed months later and must still read "from X to Y". The
Employee master will by then hold Y, so the document keeps what was true
when the change was approved.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import people, position_approval as approval, position_rules as rules, workflows

LETTER_ROLE_SETTING = "executive_director"


# ── 1. The form ───────────────────────────────────────────────────────
def change_validate(doc, method=None):
    _fill_current(doc)
    doc.new_salary_in_words = rules.in_words(doc.get("new_salary"))
    old_state, new_state = _check_step(doc)
    if new_state == approval.DRAFT and old_state in approval.PENDING_STATES:
        doc.status = approval.DRAFT
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _fill_current(doc):
    """What the employee holds today, kept on the document so the letter
    still reads "from X to Y" long after the master has moved on."""
    if not doc.employee:
        return
    if doc.docstatus == 1:
        return  # what was approved stands
    employee = frappe.db.get_value(
        "Employee", doc.employee, ["designation", "reports_to", "date_of_joining", "branch", "department", "company"],
        as_dict=True) or {}
    if not doc.get("current_designation"):
        doc.current_designation = employee.get("designation")
    if not doc.get("current_supervisor"):
        doc.current_supervisor = employee.get("reports_to")
    contract = _running_contract(doc.employee, doc.get("effective_date"))
    doc.contract = contract.get("name") if contract else None
    if not doc.get("current_salary"):
        doc.current_salary = flt(contract.get("base_salary")) if contract else _last_salary(doc.employee)
    if doc.get("change_type") == rules.DESIGNATION_CHANGE and not doc.get("new_salary"):
        # the letter restates the pay: unchanged unless HR says otherwise
        doc.new_salary = doc.get("current_salary")


def _running_contract(employee, on=None):
    """The employee's live contract covering `on` (today by default)."""
    day = getdate(on or today())
    rows = frappe.get_all(
        "Employee Contract",
        filters={"employee": employee, "docstatus": 1, "status": ["not in", ("Renewed", "Not Renewed", "Cancelled")]},
        fields=["name", "base_salary", "start_date", "end_date"], order_by="start_date desc")
    for row in rows:
        if row.start_date and getdate(row.start_date) > day:
            continue
        if row.end_date and getdate(row.end_date) < day:
            continue
        return row
    return rows[0] if rows else None


def _last_salary(employee):
    row = frappe.db.get_value("Salary Structure Assignment", {"employee": employee, "docstatus": 1},
                              "base", order_by="from_date desc")
    return flt(row)


def _facts(doc):
    return {
        "change_type": doc.get("change_type"), "employee": doc.get("employee"),
        "effective_date": doc.get("effective_date"), "date_of_joining": doc.get("date_of_joining"),
        "current_designation": doc.get("current_designation"), "new_designation": doc.get("new_designation"),
        "current_salary": doc.get("current_salary"), "new_salary": doc.get("new_salary"),
        "new_supervisor": doc.get("new_supervisor"), "contract_action": doc.get("contract_action"),
        "contract": doc.get("contract"), "contract_end": doc.get("contract_end"),
        "job_description": doc.get("job_description"), "desired_position": doc.get("desired_position"),
        "experience": [row.as_dict() for row in doc.get("experience") or []],
        "appraisal_score": doc.get("appraisal_score"),
        "certification": ", ".join(row.certification for row in doc.get("education") or [] if row.get("certification")),
        "institution": ", ".join(row.institution for row in doc.get("education") or [] if row.get("institution")),
        "return_remarks": doc.get("return_remarks"),
        **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
    }


def _check_step(doc):
    """The workflow step, judged and signed."""
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    facts = _facts(doc)
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, facts)
        if new_state == approval.PENDING_SUPERVISOR and old_state in (None, approval.DRAFT):
            errors = rules.change_errors(facts) + rules.preamble_errors(facts) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(doc.get("change_type") or "Position Change"))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_approver(doc, new_state)
    return old_state, new_state


def _tell_approver(doc, state):
    """Whoever signs next is told, and the form put on their list."""
    role = {approval.PENDING_SUPERVISOR: approval.SUPERVISORS[0], approval.PENDING_HRM: approval.HRM,
            approval.PENDING_GM: approval.GM, approval.PENDING_ED: approval.ED}[state]
    users = people.people_for(role, doc.get("branch"), doc.get("department"))
    if state == approval.PENDING_SUPERVISOR and not users:
        users = people.people_for(approval.SUPERVISORS[1], doc.get("branch"), doc.get("department"))
    message = _("{0} for {1}: your comments and signature are needed.").format(
        doc.get("change_type") or _("Position change"), doc.get("employee_name") or doc.employee)
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


# ── 2. Approved: the change applied ───────────────────────────────────
def change_on_submit(doc, method=None):
    doc.db_set("status", approval.APPROVED, update_modified=False)
    _apply(doc)
    people.notify([frappe.db.get_value("Employee", doc.employee, "user_id")], doc.doctype, doc.name,
                  _("Your {0} has been approved, effective {1}.").format(
                      (doc.get("change_type") or "").lower(), frappe.utils.format_date(doc.effective_date)))


def _apply(doc):
    changes_designation, changes_salary = rules.changes(doc.get("change_type"))
    update = {}
    if changes_designation and doc.get("new_designation"):
        update["designation"] = doc.new_designation
    if doc.get("new_supervisor"):
        update["reports_to"] = doc.new_supervisor
    if update:
        frappe.db.set_value("Employee", doc.employee, update, update_modified=False)
    plan = rules.contract_plan(doc.get("contract_action"), doc.get("contract"), doc.get("effective_date"),
                               months=doc.get("new_contract_months"), end=doc.get("contract_end"))
    _apply_contract(doc, plan, changes_designation, changes_salary)
    if changes_salary and flt(doc.get("new_salary")):
        _assign_salary(doc)


def _apply_contract(doc, plan, changes_designation, changes_salary):
    if plan.get("amend"):
        update = {}
        if changes_designation and doc.get("new_designation"):
            update["designation"] = doc.new_designation
        if changes_salary and flt(doc.get("new_salary")):
            update["base_salary"] = flt(doc.new_salary)
        if update:
            # the contract is submitted; only fields marked allow_on_submit move
            frappe.db.set_value("Employee Contract", plan["amend"], update, update_modified=False)
        return
    if not plan.get("open"):
        return
    old = frappe.get_doc("Employee Contract", plan["close"])
    fresh = frappe.new_doc("Employee Contract")
    fresh.update({
        "employee": doc.employee, "company": old.company, "employment_type": old.employment_type,
        "start_date": plan["open"]["start_date"], "end_date": plan["open"]["end_date"],
        "designation": doc.get("new_designation") or old.designation,
        "base_salary": flt(doc.get("new_salary")) or flt(old.base_salary),
        "contract_template": old.get("contract_template"), "terms": old.get("terms"),
    })
    fresh.flags.ignore_permissions = True
    fresh.flags.ignore_mandatory = True
    fresh.insert()
    doc.db_set("new_contract", fresh.name, update_modified=False)
    frappe.db.set_value("Employee Contract", old.name, {"end_date": plan["closed_on"], "status": "Renewed",
                                                        "renewed_by": fresh.name}, update_modified=False)


def _assign_salary(doc):
    """A Salary Structure Assignment from the effective date, so payroll
    pays the new gross. One already there for the day is left alone."""
    structure = doc.get("salary_structure") or frappe.db.get_value(
        "Salary Structure Assignment", {"employee": doc.employee, "docstatus": 1}, "salary_structure",
        order_by="from_date desc")
    if not structure:
        frappe.msgprint(_("No salary structure for {0}: assign one so the new gross is paid.").format(doc.employee),
                        indicator="orange", alert=True)
        return
    existing = frappe.db.get_value("Salary Structure Assignment",
                                   {"employee": doc.employee, "from_date": doc.effective_date, "docstatus": ["!=", 2]},
                                   "name")
    if existing:
        doc.db_set("salary_structure_assignment", existing, update_modified=False)
        return
    assignment = frappe.new_doc("Salary Structure Assignment")
    assignment.update({"employee": doc.employee, "salary_structure": structure, "from_date": doc.effective_date,
                       "base": flt(doc.new_salary), "company": doc.get("company")})
    assignment.flags.ignore_permissions = True
    assignment.insert()
    assignment.submit()
    doc.db_set("salary_structure_assignment", assignment.name, update_modified=False)


def change_on_cancel(doc, method=None):
    """What was there before is put back, as far as it can be."""
    doc.db_set("status", approval.CANCELLED, update_modified=False)
    update = {}
    if doc.get("new_designation") and doc.get("current_designation"):
        update["designation"] = doc.current_designation
    if doc.get("new_supervisor") and doc.get("current_supervisor"):
        update["reports_to"] = doc.current_supervisor
    if update:
        frappe.db.set_value("Employee", doc.employee, update, update_modified=False)
    if doc.get("contract") and doc.get("contract_action") == rules.AMEND:
        frappe.db.set_value("Employee Contract", doc.contract,
                            {"designation": doc.get("current_designation"), "base_salary": flt(doc.get("current_salary"))},
                            update_modified=False)
    for name in (doc.get("salary_structure_assignment"),):
        if name and frappe.db.get_value("Salary Structure Assignment", name, "docstatus") == 1:
            frappe.get_doc("Salary Structure Assignment", name).cancel()
    if doc.get("new_contract") and frappe.db.exists("Employee Contract", doc.new_contract):
        fresh = frappe.get_doc("Employee Contract", doc.new_contract)
        if fresh.docstatus == 1:
            fresh.cancel()
        else:
            frappe.delete_doc("Employee Contract", fresh.name, ignore_permissions=True)
        if doc.get("contract"):
            frappe.db.set_value("Employee Contract", doc.contract,
                                {"end_date": doc.get("contract_end"), "status": "Active", "renewed_by": None},
                                update_modified=False)


# ── 3. What the form offers ───────────────────────────────────────────
@frappe.whitelist()
def get_background(employee):
    """The preamble's sections 4 and 5 from the employee's bio-data: the
    professional qualifications and the jobs held before."""
    frappe.has_permission("Employee", doc=employee, throw=True)
    education = [
        {"certification": row.get("qualification") or row.get("course"), "institution": row.get("institution"),
         "field_of_study": row.get("specialization") or row.get("major"), "graduation_date": row.get("date_of_completion")}
        for row in _rows("Employee Education", employee, ("qualification", "school_univ", "level", "year_of_passing"))
    ]
    experience = [
        {"designation": row.get("designation"), "company": row.get("company_name"),
         "tenure": _tenure(row), "responsibilities": row.get("description")}
        for row in _rows("Employee External Work History", employee, ("company_name", "designation", "total_experience"))
    ]
    return {"education": [row for row in education if row["certification"]],
            "experience": [row for row in experience if row["designation"] or row["company"]]}


def _rows(doctype, employee, _fields):
    """Every column of a child table of the Employee, whatever upstream
    calls them: the two histories have been renamed more than once."""
    meta = frappe.get_meta(doctype)
    names = [field.fieldname for field in meta.fields if field.fieldtype not in ("Section Break", "Column Break")]
    if not names:
        return []
    return frappe.get_all(doctype, filters={"parent": employee, "parenttype": "Employee"},
                          fields=["name", *names], order_by="idx asc")


def _tenure(row):
    for key in ("total_experience", "tenure", "duration"):
        if row.get(key):
            return str(row[key])
    start, end = row.get("from_date"), row.get("to_date")
    if start:
        return "%s - %s" % (frappe.utils.format_date(start), frappe.utils.format_date(end) if end else _("to date"))
    return ""


@frappe.whitelist()
def letter_for(change_type):
    """Which letter this change prints."""
    return rules.LETTERS.get(change_type)


def setup_workflows_on_migrate():
    """after_migrate: the position change workflow, and the roles its
    signatories and the letters' witnesses need (workflows.py)."""
    workflows.setup_on_migrate(approval, "Employee Position Change workflow")


def daily():
    """An internship ending today is marked Completed, so the list of
    interns on site stays true."""
    day = today()
    for name in frappe.get_all("Intern Placement",
                               filters={"docstatus": 1, "status": "Placed", "end_date": ["<", day]}, pluck="name"):
        frappe.db.set_value("Intern Placement", name, "status", "Completed", update_modified=False)
    frappe.db.commit()


def in_words(amount):
    """Jinja: a gross salary written out for the letters."""
    return rules.in_words(amount)
