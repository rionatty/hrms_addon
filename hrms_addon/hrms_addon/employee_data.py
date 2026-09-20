# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Where the pay goes, and internship placements, on the site.

The rules are in employee_data_rules.py, without a Frappe import
(scripts/verify_positions.py).

  Employee Data Change Request   LPL/HR/34 and LPL/HR/33: the employee gives
                                 the new bank account or phone number, the
                                 old one is read off their record, and the
                                 Employee is written to only once HR
                                 approves — so there is a record of who
                                 asked, who approved and when
  Intern Placement               the Intern Placement Letter: the plant is
                                 chosen per intern, not always Kawempe
"""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import employee_data_rules as rules, people

EMPLOYEE_FIELDS = sorted({source for fields in rules.FIELDS.values() for _field, source, _label in fields})


# ── 1. The change request ─────────────────────────────────────────────
def request_validate(doc, method=None):
    if not doc.get("request_date"):
        doc.request_date = today()
    _fill_current(doc)
    if doc.docstatus == 0:
        doc.status = "Draft"
    if doc.docstatus == 1 and not doc.get("status"):
        doc.status = "Pending HR"
    errors = rules.request_errors(_facts(doc))
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors),
                     title=_("{0} Change Request").format(doc.get("change_type") or ""))


def _fill_current(doc):
    """The details on record today, kept on the request so the paper still
    reads "from this account to that one" after the master has moved on."""
    if not doc.employee or doc.docstatus != 0:
        return
    employee = frappe.db.get_value("Employee", doc.employee, EMPLOYEE_FIELDS, as_dict=True) or {}
    for field, value in rules.current_values(doc.get("change_type"), employee).items():
        doc.set(rules.CURRENT % field, value)
    for change_type in rules.CHANGE_TYPES:
        if change_type == doc.get("change_type"):
            continue
        for field, _source, _label in rules.fields_for(change_type):
            doc.set(rules.CURRENT % field, None)
            doc.set(rules.NEW % field, None)


def _facts(doc):
    fields = [field for field, _source, _label in rules.fields_for(doc.get("change_type"))]
    return {
        "change_type": doc.get("change_type"), "employee": doc.get("employee"),
        "current": {field: doc.get(rules.CURRENT % field) for field in fields},
        "new": {field: doc.get(rules.NEW % field) for field in fields},
    }


def request_on_submit(doc, method=None):
    """Submitted, the request waits for HR; approving is a separate step, so
    the employee's own submit never writes to their record."""
    doc.db_set("status", "Pending HR", update_modified=False)
    officers = people.hr_officers(doc.get("branch"), doc.get("department"))
    message = _("{0} change requested by {1}.").format(doc.get("change_type"), doc.get("employee_name") or doc.employee)
    people.notify(officers, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, officers, message)


@frappe.whitelist(methods=["POST"])
def approve(name):
    """HR approves: the new details are written to the Employee."""
    doc = frappe.get_doc("Employee Data Change Request", name)
    doc.check_permission("submit")
    if doc.docstatus != 1:
        frappe.throw(_("Submit the request first."))
    if doc.status == "Approved":
        return doc.status
    errors = rules.request_errors(_facts(doc))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Change Request"))
    fields = [field for field, _source, _label in rules.fields_for(doc.change_type)]
    update = rules.employee_update(doc.change_type, {field: doc.get(rules.NEW % field) for field in fields})
    if update:
        frappe.db.set_value("Employee", doc.employee, update, update_modified=False)
    doc.db_set({"status": "Approved", "approved_by": frappe.session.user, "approved_on": today(), "applied": 1},
               update_modified=False)
    people.notify([frappe.db.get_value("Employee", doc.employee, "user_id")], doc.doctype, doc.name,
                  _("Your {0} change has been effected.").format((doc.change_type or "").lower()))
    return doc.status


@frappe.whitelist(methods=["POST"])
def reject(name, reason):
    doc = frappe.get_doc("Employee Data Change Request", name)
    doc.check_permission("submit")
    if doc.get("applied"):
        frappe.throw(_("The change has been written to the employee's record already; cancel the request instead."))
    doc.db_set({"status": "Rejected", "hr_remarks": reason, "approved_by": frappe.session.user,
                "approved_on": today()}, update_modified=False)
    people.notify([frappe.db.get_value("Employee", doc.employee, "user_id")], doc.doctype, doc.name,
                  _("Your {0} change request was not approved: {1}").format((doc.change_type or "").lower(), reason))
    return doc.status


def request_on_cancel(doc, method=None):
    """The details that were there before go back, where this request is
    what changed them."""
    if doc.get("applied"):
        fields = [field for field, _source, _label in rules.fields_for(doc.change_type)]
        back = rules.employee_update(doc.change_type, {field: doc.get(rules.CURRENT % field) for field in fields})
        if back:
            frappe.db.set_value("Employee", doc.employee, back, update_modified=False)
    doc.db_set({"status": "Cancelled", "applied": 0}, update_modified=False)


# ── 2. The internship placement ───────────────────────────────────────
def placement_validate(doc, method=None):
    if doc.get("supervisor") and not doc.get("supervisor_designation"):
        doc.supervisor_designation = frappe.db.get_value("Employee", doc.supervisor, "designation")
    if not doc.get("company"):
        doc.company = frappe.db.get_single_value("Global Defaults", "default_company")
    if doc.docstatus == 0:
        doc.status = "Draft"
    errors = rules.placement_errors({
        "intern_name": doc.get("intern_name"), "school": doc.get("school"), "applied_on": doc.get("applied_on"),
        "start_date": doc.get("start_date"), "end_date": doc.get("end_date"), "department": doc.get("department"),
        "branch": doc.get("branch"), "supervisor_designation": doc.get("supervisor_designation"),
    })
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Intern Placement"))


def placement_on_submit(doc, method=None):
    doc.db_set("status", "Placed", update_modified=False)
    if not doc.get("supervisor"):
        return
    user = frappe.db.get_value("Employee", doc.supervisor, "user_id")
    message = _("{0} from {1} is placed with you from {2} to {3}.").format(
        doc.intern_name, doc.school, frappe.utils.format_date(doc.start_date), frappe.utils.format_date(doc.end_date))
    people.notify([user], doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, [user], message, date=doc.start_date)


def placement_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)
