# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave encashment on the site (Reward and Compensation, §4.5), on Frappe
HR's own Leave Encashment.

The rules are in encashment_rules.py and encashment_approval.py, without a
Frappe import (scripts/verify_encashment.py). This reads and writes the
site.

Frappe HR's controller already holds an encashment to the accumulated
balance, and pays it on submit through an Additional Salary on the
payroll. What is added here: the six desks the minutes give, the leave
that was worked through and why, and the amount from the salary — their
controller pays nothing unless a per-day amount is set on the salary
structure, so where none is, a day's pay is the gross over the working
days of a month, as it is for the untaken leave on a final settlement.

  encashment_*   the application through its desks, and the employee told
                 what is paid.
  setup_on_migrate  the workflow, and the earning component the payroll
                 pays it under.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, today

from hrms_addon.hrms_addon import encashment_rules as rules, people

DOCTYPE = "Leave Encashment"
COMPONENT = "Leave Encashment"


# ── 1. The application ────────────────────────────────────────────────
def encashment_validate(doc, method=None):
    """After Frappe HR's own validate, which has read the balance and
    priced the days where a per-day amount is set."""
    from hrms_addon.hrms_addon import encashment_approval as approval

    _price(doc)
    _check_step(doc)
    doc.custom_encashment_status = doc.get("workflow_state") or doc.get("custom_encashment_status") \
        or approval.DRAFT


def _price(doc):
    days = flt(doc.get("encashment_days"))
    if not days:
        doc.custom_per_day = 0
        return
    if flt(doc.get("encashment_amount")) > 0:
        # a per-day amount on the salary structure, which Frappe HR used
        doc.custom_per_day = round(flt(doc.encashment_amount) / days, 2)
        return
    gross = _gross_pay(doc.employee) if doc.get("employee") else 0
    doc.custom_per_day = rules.per_day(gross)
    doc.encashment_amount = rules.amount(gross, days)


def _gross_pay(employee):
    rows = frappe.get_all("Salary Structure Assignment", filters={"employee": employee, "docstatus": 1},
                          fields=["base"], order_by="from_date desc", limit=1)
    return flt(rows[0].base) if rows else 0


def _check_step(doc):
    from hrms_addon.hrms_addon import encashment_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_SUPERVISOR and old_state in (None, approval.DRAFT):
            errors = rules.application_errors(_facts(doc)) + errors
            doc.custom_days_requested = flt(doc.get("encashment_days"))
        elif new_state not in (approval.DRAFT, approval.REJECTED, approval.CANCELLED):
            errors += rules.management_errors({"days": doc.get("encashment_days"),
                                               "requested": doc.get("custom_days_requested")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Leave Encashment"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    elif new_state in approval.MANAGEMENT or new_state == approval.PENDING_ACCOUNTS:
        # the days may be cut on these desks, never raised
        errors = rules.management_errors({"days": doc.get("encashment_days"),
                                          "requested": doc.get("custom_days_requested")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Leave Encashment"))
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)


def _facts(doc):
    facts = {"employee": doc.get("employee"), "days": doc.get("encashment_days"),
             "balance": doc.get("leave_balance"), "reason": doc.get("custom_reason")}
    if doc.get("custom_leave_application"):
        leave = frappe.db.get_value("Leave Application", doc.custom_leave_application,
                                    ["employee", "status", "docstatus", "total_leave_days"], as_dict=True) or {}
        facts.update({"leave_employee": leave.get("employee") or "",
                      "leave_status": leave.get("status") if cint(leave.get("docstatus")) == 1 else None,
                      "leave_days": leave.get("total_leave_days")})
    return facts


def _tell(doc, state):
    from hrms_addon.hrms_addon import encashment_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("custom_branch"), doc.get("department"))
    if not users:
        return
    message = _("Leave encashment for {0}: {1} day(s), {2}.").format(
        doc.get("employee_name") or doc.employee, flt(doc.get("encashment_days")),
        frappe.utils.fmt_money(doc.get("encashment_amount")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def encashment_on_submit(doc, method=None):
    """Processed: the employee is told what is paid, and when."""
    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    if not user:
        return
    people.notify([user], doc.doctype, doc.name,
                  _("Your {0} day(s) of leave are encashed at {1}, paid with the payroll of {2}.").format(
                      flt(doc.get("encashment_days")), frappe.utils.fmt_money(doc.get("encashment_amount")),
                      frappe.utils.format_date(doc.get("encashment_date"), "MMMM yyyy")))


def encashment_on_cancel(doc, method=None):
    doc.db_set("custom_encashment_status", "Cancelled", update_modified=False)


# ── 2. Wiring ─────────────────────────────────────────────────────────
def setup_on_migrate():
    """after_migrate: the six desks, and the component the payroll pays an
    encashment under. Frappe HR refuses to submit one for a leave type
    with no earning component."""
    from hrms_addon.hrms_addon import encashment_approval, workflows

    workflows.setup_on_migrate(encashment_approval, "Leave Encashment workflow")
    try:
        ensure_earning_component()
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="HRMS Addon: leave encashment component")


def ensure_earning_component():
    """The Leave Encashment earning, set on every leave type that may be
    encashed and has none."""
    if not frappe.db.exists("Salary Component", COMPONENT):
        frappe.get_doc({"doctype": "Salary Component", "salary_component": COMPONENT, "type": "Earning",
                        "salary_component_abbr": "LENC", "depends_on_payment_days": 0,
                        "description": "Leave days paid instead of taken."}
                       ).insert(ignore_permissions=True)
    types = frappe.get_all("Leave Type", filters={"allow_encashment": 1}, fields=["name", "earning_component"])
    for row in types:
        if not row.earning_component:
            frappe.db.set_value("Leave Type", row.name, "earning_component", COMPONENT)
    return [row.name for row in types if not row.earning_component]
