# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance Improvement Plans on the site (test case 7).

The rules are in pip_rules.py, without a Frappe import
(scripts/verify_performance.py).

A plan is raised by the management review for anyone below the pass mark
(appraisals.py), or by HR on its own. It is agreed with the employee, run
for a period, reviewed while it runs, and closed with an outcome. The
supervisor and HR are reminded when a review date comes and when the plan
is about to end, so it is not forgotten — which is what the recommendation
asks for: "guiding the employee and holding them accountable".
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import people, pip_rules as rules


def plan_validate(doc, method=None):
    if doc.get("start_date") and not doc.get("end_date"):
        doc.end_date = rules.end_date(doc.start_date, doc.get("months"))
    if doc.get("appraisal") and doc.get("appraisal_score") in (None, 0):
        doc.appraisal_score = flt(frappe.db.get_value("Appraisal", doc.appraisal, "custom_total_score"))
    if not doc.get("supervisor") and doc.get("employee"):
        doc.supervisor = frappe.db.get_value("Employee", doc.employee, "reports_to")
    doc.suggested_outcome = rules.suggested_outcome([row.as_dict() for row in doc.get("reviews") or []])
    if doc.docstatus == 0:
        doc.status = rules.AGREED if (doc.get("employee_agreed_on") and doc.get("supervisor_agreed_on")) else rules.DRAFT
    errors = rules.plan_errors({
        "employee": doc.get("employee"), "supervisor": doc.get("supervisor"), "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"), "objectives": [row.as_dict() for row in doc.get("objectives") or []],
    })
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Performance Improvement Plan"))
    if doc.docstatus == 1:
        closing = rules.close_errors({
            "reviews": [row.as_dict() for row in doc.get("reviews") or []], "outcome": doc.get("outcome"),
            "remarks": doc.get("outcome_remarks"), "end_date": doc.get("end_date"),
            "new_end_date": doc.get("new_end_date"),
        })
        if closing:
            frappe.throw("<br>".join(_(message) for message in closing),
                         title=_("Closing the Performance Improvement Plan"))


def plan_on_submit(doc, method=None):
    """Submitting closes the plan: the outcome stands."""
    doc.db_set({"status": rules.CLOSED, "closed_by": frappe.session.user, "closed_on": today()},
               update_modified=False)
    told = [frappe.db.get_value("Employee", doc.supervisor, "user_id")] if doc.get("supervisor") else []
    told += people.hr_officers(doc.get("branch"), doc.get("department"))
    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    people.notify([user for user in told + [user] if user], doc.doctype, doc.name,
                  _("The improvement plan for {0} is closed: {1}.").format(
                      doc.get("employee_name") or doc.employee, doc.get("outcome")))
    if doc.get("outcome") == rules.EXTENDED and doc.get("new_end_date"):
        _extend(doc)


def _extend(doc):
    """An extension is a fresh plan running on from this one, so each period
    keeps its own reviews and its own outcome."""
    fresh = frappe.new_doc("Performance Improvement Plan")
    fresh.update({
        "employee": doc.employee, "supervisor": doc.supervisor, "appraisal": doc.get("appraisal"),
        "appraisal_score": doc.get("appraisal_score"), "performance_review": doc.get("performance_review"),
        "start_date": getdate(doc.end_date), "end_date": doc.new_end_date,
        "reason": _("Extension of {0}.").format(doc.name),
        "objectives": [{"area": row.area, "expected_standard": row.expected_standard, "support": row.support,
                        "measure": row.measure} for row in doc.get("objectives") or []
                       if row.progress != rules.MET],
    })
    fresh.flags.ignore_permissions = True
    fresh.flags.ignore_mandatory = True
    fresh.insert()
    frappe.msgprint(_("Extended as {0}.").format(fresh.name), indicator="blue", alert=True)


def plan_on_cancel(doc, method=None):
    doc.db_set("status", rules.CANCELLED, update_modified=False)


def plan_on_change(doc, method=None):
    """Raised, changed, closed or cancelled: the employee's appraisals say
    whether they are on a plan now."""
    mark_appraisals(doc.get("employee"))
    if doc.get("employee") != (doc.get_doc_before_save() or frappe._dict()).get("employee"):
        mark_appraisals((doc.get_doc_before_save() or frappe._dict()).get("employee"))


def plan_after_delete(doc, method=None):
    mark_appraisals(doc.get("employee"))


def open_plan(employee):
    """The employee's improvement plan still open (raised, agreed or under
    way), the latest if there are more; None when they are on none."""
    if not employee:
        return None
    found = frappe.get_all("Performance Improvement Plan", filters={
        "employee": employee, "docstatus": 0, "status": ["in", list(rules.OPEN)]},
        pluck="name", order_by="creation desc", limit=1)
    return found[0] if found else None


def mark_appraisals(employee):
    """Every appraisal of the employee says whether they are on an open
    plan, and which: the lists show them in red. Written straight in, so a
    completed appraisal shows it too."""
    if not employee:
        return
    plan = open_plan(employee)
    for row in frappe.get_all("Appraisal", filters={"employee": employee, "docstatus": ["!=", 2]},
                              fields=["name", "custom_on_pip", "custom_improvement_plan"]):
        if (row.custom_improvement_plan or None) != plan or bool(row.custom_on_pip) != bool(plan):
            frappe.db.set_value("Appraisal", row.name, {"custom_on_pip": 1 if plan else 0,
                                                        "custom_improvement_plan": plan}, update_modified=False)


@frappe.whitelist()
def open_plans(employees: list | str | None = None) -> dict:
    """{employee: improvement plan} of those listed who are on an open
    plan, for the lists that show them in red. Someone who may not read
    the plans learns only who is on one."""
    if isinstance(employees, str):
        employees = frappe.parse_json(employees)
    employees = [employee for employee in (employees or []) if employee][:500]
    if not employees:
        return {}
    readable = frappe.has_permission("Performance Improvement Plan", "read")
    found = {}
    for row in frappe.get_all("Performance Improvement Plan", filters={
            "employee": ["in", employees], "docstatus": 0, "status": ["in", list(rules.OPEN)]},
            fields=["name", "employee"], order_by="creation asc"):
        found[row.employee] = row.name if readable else 1
    return found


@frappe.whitelist(methods=["POST"])
def start(name):
    """Agreed and under way: the employee and the supervisor have signed."""
    doc = frappe.get_doc("Performance Improvement Plan", name)
    doc.check_permission("write")
    if not (doc.employee_agreed_on and doc.supervisor_agreed_on):
        frappe.throw(_("Both the employee and the supervisor must agree the plan before it starts."))
    doc.db_set("status", rules.IN_PROGRESS, update_modified=False)
    return doc.status


def daily():
    """A review date that has come, and a plan about to end, are put on the
    supervisor's list: the plan is an agreement, not a filing."""
    day = today()
    for name in frappe.get_all("Performance Improvement Plan",
                               filters={"docstatus": 0, "status": ["in", (rules.AGREED, rules.IN_PROGRESS)]},
                               pluck="name"):
        doc = frappe.get_doc("Performance Improvement Plan", name)
        due = rules.due_reviews([row.as_dict() for row in doc.get("objectives") or []], day)
        if not due and not (doc.end_date and getdate(doc.end_date) == getdate(day)):
            continue
        users = [frappe.db.get_value("Employee", doc.supervisor, "user_id")] if doc.supervisor else []
        users += people.hr_officers(doc.get("branch"), doc.get("department"))
        message = (_("The improvement plan for {0} ends today: record the reviews and close it.")
                   if doc.end_date and getdate(doc.end_date) == getdate(day)
                   else _("{1} point(s) of {0}'s improvement plan are due for review.")).format(
            doc.get("employee_name") or doc.employee, len(due))
        people.notify([user for user in users if user], doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, [user for user in users if user], message)
    frappe.db.commit()
