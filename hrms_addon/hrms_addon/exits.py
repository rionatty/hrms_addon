# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The two exits on the site: voluntary (4.5) and involuntary (4.6).

The rules are in exit_rules.py, without a Frappe import
(scripts/verify_exits.py). This reads and writes the site.

Frappe HR ships the Employee Separation and the Exit Interview, so both
exits are carried on them: the separation is the umbrella that knows which
chart is being followed and how far it has got, and the interview carries
the three signatures of 4.5 step 4. The Clearance Form (LPL/HR/22) is the
one document they do not have, and it is signed by different people on
each chart (clearance_approval.py).

  separation_*  the exit itself: the notice the Act asks for, whether it
                was served, and the letter an involuntary exit carries.
  interview_*   the exit interview through Supervisor, HOD and HR Officer.
  clearance_*   the ten boxes, the tools of work they pull in, and the
                chain each exit signs them through.
  daily         a notice period running out, and an exit waiting on its
                clearance.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import exit_rules as rules, people

SEPARATION = "Employee Separation"
INTERVIEW = "Exit Interview"
CLEARANCE = "Clearance Form"


# ── 1. The separation ─────────────────────────────────────────────────
def separation_validate(doc, method=None):
    if not doc.get("custom_exit_type"):
        doc.custom_exit_type = rules.VOLUNTARY
    _fill_notice(doc)
    _link_children(doc)
    errors = rules.separation_errors(_facts(doc))
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Separation"))


def _fill_notice(doc):
    """The notice the Act asks for at this length of service, and whether
    it was served — which is what the settlement deducts for."""
    joined = doc.get("custom_date_of_joining")
    leaving = doc.get("custom_relieving_date")
    served = rules.months_served(joined, leaving or today())
    doc.custom_notice_days = rules.notice_days(served)
    if doc.get("custom_exit_type") == rules.VOLUNTARY:
        given = doc.get("custom_notice_given")
        answer = rules.notice_served(given, leaving, doc.custom_notice_days)
    else:
        # the company gives the notice on an involuntary exit, so nothing
        # is short on the employee's side
        answer = {"served": True, "short": 0}
    doc.custom_notice_served = 1 if answer["served"] else 0
    doc.custom_notice_short_days = answer["short"]


def _facts(doc):
    return {
        "exit_type": doc.get("custom_exit_type"), "reason": doc.get("custom_reason"),
        "notice_given": doc.get("custom_notice_given"),
        "relieving_date": doc.get("custom_relieving_date"),
        "date_of_joining": doc.get("custom_date_of_joining"),
        "termination_date": doc.get("custom_termination_date"),
        "letter_signed_on": doc.get("custom_letter_signed_on"),
    }


def _link_children(doc):
    """What the exit has reached: the interview, the clearance and the
    settlement, each found by its own link back."""
    if not doc.name:
        return
    for field, doctype in (("custom_exit_interview", INTERVIEW), ("custom_clearance", CLEARANCE),
                           ("custom_settlement", "Full and Final Statement")):
        if doc.get(field):
            continue
        found = frappe.get_all(doctype, filters={"custom_separation" if doctype != CLEARANCE
                                                 else "separation": doc.name, "docstatus": ["<", 2]},
                               pluck="name", limit=1)
        if found:
            doc.set(field, found[0])


def separation_on_submit(doc, method=None):
    """Step 7 of 4.6: the employee's status is updated and the Payroll
    Officer told to prepare the final pay."""
    _make_inactive(doc)
    users = people.people_for("Payroll Officer", doc.get("custom_branch"), doc.get("department"))
    users += people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                      _("{0} leaves on {1}. Prepare the final salary and the terminal benefits.").format(
                          doc.get("employee_name") or doc.employee,
                          frappe.utils.format_date(doc.get("custom_relieving_date"))))


def _make_inactive(doc):
    """Step 2 of the cessation chart: the system makes the employee
    inactive and takes them off the payroll."""
    if not doc.get("employee") or not doc.get("custom_relieving_date"):
        return
    if getdate(doc.custom_relieving_date) > getdate(today()):
        return  # still serving: this runs again from the daily job
    employee = frappe.get_doc("Employee", doc.employee)
    if employee.status == "Left":
        doc.custom_status_updated = 1
        return
    employee.status = "Left"
    employee.relieving_date = doc.custom_relieving_date
    employee.reason_for_leaving = doc.get("custom_reason")
    employee.flags.ignore_permissions = True
    employee.flags.ignore_mandatory = True
    employee.save()
    doc.custom_status_updated = 1


def separation_on_cancel(doc, method=None):
    doc.custom_status_updated = 0


# ── 2. The exit interview ─────────────────────────────────────────────
def interview_validate(doc, method=None):
    from hrms_addon.hrms_addon import exit_interview_approval as approval

    _check_interview_step(doc)
    doc.custom_exit_status = doc.get("workflow_state") or doc.get("custom_exit_status") or approval.DRAFT


def _check_interview_step(doc):
    from hrms_addon.hrms_addon import exit_interview_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            "interview_summary": doc.get("interview_summary"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Exit Interview"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.get("custom_branch"),
                                  doc.get("department"))
        message = _("Exit interview for {0}.").format(doc.get("employee_name") or doc.employee)
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)


def interview_on_submit(doc, method=None):
    """Step 5 follows: the employee serves the notice period, and the HR
    Officer is told to call them for the handover at the end of it."""
    if doc.get("custom_separation"):
        frappe.db.set_value(SEPARATION, doc.custom_separation, "custom_exit_interview", doc.name,
                            update_modified=False)


def interview_on_cancel(doc, method=None):
    doc.custom_exit_status = "Cancelled"


# ── 3. The Clearance Form (LPL/HR/22) ─────────────────────────────────
def clearance_validate(doc, method=None):
    from hrms_addon.hrms_addon import clearance_approval as approval

    _fill_clearance(doc)
    _check_clearance_step(doc)
    doc.approval_status = doc.get("workflow_state") or doc.get("approval_status") or approval.DRAFT


def _fill_clearance(doc):
    if doc.get("date_of_joining") and doc.get("leaving_date"):
        doc.days_worked = rules.days_worked(doc.date_of_joining, doc.leaving_date)
    for row in doc.get("items") or []:
        row.section_name = rules.SECTION_NAMES.get(row.section)
    for row in doc.get("sections") or []:
        row.section_name = rules.SECTION_NAMES.get(row.section)
    items = [row.as_dict() for row in doc.get("items") or []]
    signatures = [row.as_dict() for row in doc.get("sections") or []]
    doc.outstanding_cost = rules.outstanding_cost(items)
    cleared = rules.cleared_sections(items, signatures)
    doc.boxes_cleared = ", ".join(cleared) or None
    doc.complete = 1 if rules.clearance_complete(items, signatures) else 0


def _check_clearance_step(doc):
    from hrms_addon.hrms_addon import clearance_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"), "complete": doc.get("complete"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state and new_state != approval.DRAFT and old_state in (None, approval.DRAFT):
            errors = rules.clearance_errors({"rows": [row.as_dict() for row in doc.get("items") or []]}) \
                + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Clearance Form"))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.get("branch"),
                                  doc.get("department"))
        message = _("Clearance for {0} ({1} exit).").format(
            doc.get("employee_name") or doc.employee, (doc.get("exit_type") or "").lower())
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)


def clearance_on_submit(doc, method=None):
    """Step 9: the cessation of employment follows."""
    if doc.get("separation"):
        frappe.db.set_value(SEPARATION, doc.separation, "custom_clearance", doc.name,
                            update_modified=False)
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    users += people.people_for("Accounts User", doc.get("branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                      _("{0} is cleared. Draw up the full and final settlement.").format(
                          doc.get("employee_name") or doc.employee))


def clearance_on_cancel(doc, method=None):
    doc.approval_status = "Cancelled"


@frappe.whitelist(methods=["POST"])
def draw_up_clearance(separation):
    """The ten boxes LPL/HR/22 prints, with the employee's own tools of
    work already on them (step 6: the handover)."""
    exit_doc = frappe.get_doc(SEPARATION, separation)
    exit_doc.check_permission("read")
    if exit_doc.get("custom_clearance"):
        return exit_doc.custom_clearance
    form = frappe.new_doc(CLEARANCE)
    form.update({
        "employee": exit_doc.employee, "company": exit_doc.company, "separation": separation,
        "exit_type": exit_doc.get("custom_exit_type") or rules.VOLUNTARY,
        "leaving_date": exit_doc.get("custom_relieving_date"),
        "notice_date": exit_doc.get("custom_notice_given"),
        "leave_balance": _leave_balance(exit_doc.employee),
        "salary": _gross_pay(exit_doc.employee),
    })
    for row in rules.default_rows(form.exit_type):
        form.append("items", row)
    for tool in _tools(exit_doc.employee):
        form.append("items", {"section": "A", "section_name": rules.SECTION_NAMES["A"],
                              "item": tool.tool, "returned": 0, "tool": tool.tool,
                              "remarks": tool.serial_no})
    for code, name, _items in rules.SECTIONS:
        form.append("sections", {"section": code, "section_name": name})
    form.flags.ignore_permissions = True
    form.flags.ignore_mandatory = True
    form.insert()
    frappe.db.set_value(SEPARATION, separation, "custom_clearance", form.name, update_modified=False)
    return form.name


def _tools(employee):
    """The tools of work still out with the employee. They are rows on the
    Employee itself (custom_employee_tools), issued at onboarding, and one
    with a returned date has already come back."""
    return frappe.get_all("Employee Tool",
                          filters={"parent": employee, "parenttype": "Employee",
                                   "parentfield": "custom_employee_tools",
                                   "returned_on": ["is", "not set"]},
                          fields=["name", "tool", "serial_no"], limit=100)


def _leave_balance(employee):
    rows = frappe.get_all("Leave Allocation",
                          filters={"employee": employee, "docstatus": 1},
                          pluck="total_leaves_allocated")
    taken = frappe.get_all("Leave Application",
                           filters={"employee": employee, "docstatus": 1, "status": "Approved"},
                           pluck="total_leave_days")
    return flt(sum(flt(value) for value in rows)) - flt(sum(flt(value) for value in taken))


def _gross_pay(employee):
    rows = frappe.get_all("Salary Structure Assignment", filters={"employee": employee, "docstatus": 1},
                          fields=["base"], order_by="from_date desc", limit=1)
    return flt(rows[0].base) if rows else 0


# ── 4. The watching ───────────────────────────────────────────────────
def daily():
    _close_notice_periods()
    _chase_clearance()


def _close_notice_periods():
    """An employee whose last day has come is made inactive and taken off
    the payroll, whether or not anyone remembered to submit the exit."""
    rows = frappe.get_all(SEPARATION,
                          filters={"docstatus": 1, "custom_status_updated": ["!=", 1],
                                   "custom_relieving_date": ["<=", today()]},
                          fields=["name"], limit=200)
    for row in rows:
        doc = frappe.get_doc(SEPARATION, row.name)
        _make_inactive(doc)
        doc.db_set("custom_status_updated", doc.get("custom_status_updated") or 0)
    frappe.db.commit()


def _chase_clearance():
    """An exit whose notice has run out with no clearance form drawn up."""
    rows = frappe.get_all(SEPARATION,
                          filters={"docstatus": 1, "custom_clearance": ["is", "not set"],
                                   "custom_relieving_date": ["<=", add_days(today(), 7)]},
                          fields=["name", "employee", "employee_name", "custom_branch", "department",
                                  "custom_relieving_date"], limit=200)
    for row in rows:
        users = people.hr_officers(row.custom_branch, row.department)
        if not users:
            continue
        people.assign(SEPARATION, row.name, users,
                      _("{0} leaves on {1} and has no clearance form. Draw up LPL/HR/22.").format(
                          row.employee_name or row.employee,
                          frappe.utils.format_date(row.custom_relieving_date)),
                      date=row.custom_relieving_date)
    frappe.db.commit()


# ── 5. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the interview's three signatures and the clearance's
    two chains."""
    from hrms_addon.hrms_addon import clearance_approval, exit_interview_approval, workflows

    workflows.setup_on_migrate(exit_interview_approval, "Exit Interview workflow")
    workflows.setup_on_migrate(clearance_approval, "Clearance Form workflow")
