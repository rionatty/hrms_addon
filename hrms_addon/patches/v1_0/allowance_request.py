# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The allowance moves off Frappe HR's Travel Request onto its own
Allowance Request.

1. The allowances the minutes name, as Allowance Types (made once).
2. Each allowance made on a Travel Request is copied onto an Allowance
   Request where it stood: its lines, advance, signatures and payment. It
   was signed and paid on the Travel Request, so the copy asks nobody
   again and pays nothing again. A cancelled one is left where it is.
3. The "Allowance Application" workflow comes off Travel Request, and so do
   the allowance's fields on Travel Request, on its costing lines and on
   Expense Claim Type: Travel Request is Frappe HR's own again.

Nothing here stops the migrate. A request that will not copy is logged and
the rest go on, and then the old fields stay, so nothing it held is lost.
"""

import frappe
from frappe.utils import flt, getdate

TRAVEL = "Travel Request"
REQUEST = "Allowance Request"
OLD_WORKFLOW = "Allowance Application"
STATES = ("Draft", "Pending Supervisor", "Pending HR Officer", "Pending General Manager", "Pending Accounts",
          "Paid", "Rejected")
# what the allowance kept on Frappe HR's documents; the fixtures carry none of them now
OLD_FIELDS = (
    *("Travel Request-custom_%s" % name for name in (
        "lpl_section", "badge_no", "grade", "department", "branch", "lpl_cb", "start_date", "start_time",
        "end_date", "end_time", "allowance_status", "totals_section", "total", "advance", "less_advance",
        "totals_cb", "balance_due", "qualifies", "eligibility_remarks", "approval_section", "supervisor_remarks",
        "supervisor_by", "supervisor_on", "approval_cb", "hr_remarks", "hr_by", "hr_on", "approval_cb2",
        "gm_remarks", "gm_by", "gm_on", "return_remarks", "payment_section", "paid_amount", "paid_on",
        "payment_cb", "payment_reference", "accounts_remarks", "accounts_by", "accounts_on", "destination",
        "currency", "per_diem_rate", "scale_remarks")),
    *("Travel Request Costing-custom_%s" % name for name in ("days", "rate", "remarks", "from_scale")),
    "Expense Claim Type-custom_is_allowance_line",
)
# copied as they are: the signatures and the payment
KEPT = ("supervisor_remarks", "supervisor_by", "supervisor_on", "hr_remarks", "hr_by", "hr_on", "gm_remarks",
        "gm_by", "gm_on", "return_remarks", "accounts_remarks", "accounts_by", "accounts_on", "start_date",
        "start_time", "end_date", "end_time", "destination", "advance", "less_advance", "paid_on", "paid_amount")


def execute():
    if not frappe.db.exists("DocType", REQUEST):
        return
    from hrms_addon.hrms_addon import allowances

    allowances.seed_allowance_types()
    failed = _copy_requests()
    _remove_workflow()
    if failed:
        print("HRMS Addon: %d allowance(s) on Travel Request could not be copied (see the Error Log); "
              "their fields stay on Travel Request." % failed)
        return
    _remove_fields()


def _copy_requests():
    if not frappe.db.has_column(TRAVEL, "custom_allowance_status"):
        return 0
    failed = 0
    for name in frappe.get_all(TRAVEL, filters={"custom_allowance_status": ["is", "set"], "docstatus": ["<", 2]},
                               pluck="name", order_by="creation asc"):
        if frappe.db.exists(REQUEST, {"travel_request": name}):
            continue
        frappe.db.savepoint("hrms_addon_allowance_copy")
        try:
            _copy(frappe.get_doc(TRAVEL, name))
        except Exception:
            frappe.db.rollback(save_point="hrms_addon_allowance_copy")
            frappe.log_error(title="HRMS Addon: the allowance on %s was not copied" % name)
            failed += 1
    return failed


def _copy(travel):
    from hrms_addon.hrms_addon import allowances

    state = travel.get("workflow_state") or travel.get("custom_allowance_status")
    state = state if state in STATES else "Draft"
    person = frappe.db.get_value("Employee", travel.employee, ["employee_name", "company", "department", "branch",
                                                              "grade", "attendance_device_id"], as_dict=True) or {}
    company = travel.get("company") or person.get("company")
    lines = []
    for row in travel.get("costings") or []:
        if not row.get("expense_type"):
            continue
        _ensure_type(row.expense_type)
        days = flt(row.get("custom_days"))
        rate = flt(row.get("custom_rate")) or (flt(row.get("total_amount")) / days if days else flt(row.get("total_amount")))
        lines.append({"allowance_type": row.expense_type, "days": days, "rate": rate,
                      "remarks": row.get("custom_remarks") or row.get("comments")})
    doc = frappe.get_doc({
        "doctype": REQUEST, "employee": travel.employee, "employee_name": person.get("employee_name"),
        "badge_no": person.get("attendance_device_id"), "grade": person.get("grade"),
        "department": person.get("department"), "branch": person.get("branch"), "company": company,
        "company_currency": frappe.get_cached_value("Company", company, "default_currency") if company else None,
        "posting_date": getdate(travel.creation), "travel_request": travel.name,
        "purpose": "; ".join(part for part in (travel.get("purpose_of_travel"), travel.get("description")) if part)
        or "Travel",
        "cost_center": travel.get("cost_center"), "reference_no": travel.get("custom_payment_reference"),
        **{field: travel.get("custom_" + field) for field in KEPT},
        "workflow_state": state, "lines": lines, "docstatus": 1 if travel.docstatus == 1 else 0,
    })
    doc.flags[allowances.MOVED] = True
    doc.flags.ignore_permissions = doc.flags.ignore_mandatory = doc.flags.ignore_links = True
    doc.insert()


def _ensure_type(name):
    """A line the old form had that is not one of the minutes' allowances."""
    if frappe.db.exists("Allowance Type", name):
        return
    kind = frappe.get_doc({"doctype": "Allowance Type", "allowance_type": name, "needs_trip": 1,
                           "paid_through": "Accounts"})
    kind.flags.ignore_permissions = kind.flags.ignore_mandatory = kind.flags.ignore_validate = True
    kind.insert()


def _remove_workflow():
    for name in frappe.get_all("Workflow", filters={"document_type": TRAVEL}, pluck="name"):
        if name == OLD_WORKFLOW or frappe.db.get_value("Workflow", name, "workflow_name") == OLD_WORKFLOW:
            frappe.delete_doc("Workflow", name, ignore_permissions=True, force=True)


def _remove_fields():
    for name in OLD_FIELDS:
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
    frappe.clear_cache(doctype=TRAVEL)
