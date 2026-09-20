# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Contract, the Frappe side of Luuka's To-Be contract management.

The rules are in contract_rules.py (no Frappe import, tested by
scripts/verify_contracts.py):

  validate          the end from the Employment Type's usual length, the
                    duration, no two live contracts at once, and the signed
                    copy before it is submitted
  on_submit         the Employee's Contract End Date; a renewal marks the
                    contract it renews Renewed
  on_cancel         both undone
  make_renewal      Renew: a draft from the day after the end, for the
                    Employment Type's usual length (a year by default)
  mark_not_renewed  Do Not Renew: HR is told to follow the termination process
  daily             the scheduler: each contract's status, and the HR
                    Officer told a year, a quarter and a month before its end
  draft_for_new_employee  made when the HR Manager approves an onboarding
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, getdate, today

from hrms_addon.hrms_addon import contract_rules as rules
from hrms_addon.hrms_addon import people

LIVE = (rules.ACTIVE, rules.EXPIRING, rules.EXPIRED)
# a contract not renewed still runs to its End Date
IN_FORCE = LIVE + (rules.NOT_RENEWED,)


def _usual_months(employment_type):
    return cint(frappe.db.get_value("Employment Type", employment_type, "custom_contract_months")) if employment_type else 0


def validate(doc):
    months = _usual_months(doc.get("employment_type"))
    if not doc.get("end_date") and months and doc.get("start_date") and doc.is_new():
        doc.end_date = rules.end_for(doc.start_date, months)
    doc.months = round((date_diff(doc.end_date, doc.start_date) + 1) / 30.4375) if doc.get("end_date") and doc.get("start_date") else 0
    others = frappe.get_all(
        "Employee Contract",
        filters={"employee": doc.employee, "docstatus": 1, "name": ["!=", doc.name], "status": ["in", IN_FORCE],
                 "renewed_by": ("is", "not set")},
        fields=["name", "start_date", "end_date"],
    )
    # the contract this one renews ends the day before it starts: not an overlap
    others = [other for other in others if other.name != doc.get("renewal_of")]
    errors = rules.contract_errors({
        "start_date": doc.start_date,
        "end_date": doc.get("end_date"),
        "open_ended": not months,
        "submitting": doc.docstatus == 1,
        "signed_on": doc.get("signed_on"),
        "signed_contract": doc.get("signed_contract"),
        "overlaps": rules.overlaps(doc.start_date, doc.get("end_date"), others) if doc.get("start_date") else [],
    }, today())
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Contract"))
    doc.status = rules.contract_status(doc.docstatus, doc.get("end_date"), today())


def on_submit(doc):
    frappe.db.set_value("Employee", doc.employee, "contract_end_date", doc.get("end_date"))
    if doc.get("renewal_of"):
        frappe.db.set_value("Employee Contract", doc.renewal_of, {"renewed_by": doc.name, "status": rules.RENEWED},
                            update_modified=False)


def on_cancel(doc):
    doc.db_set("status", rules.CANCELLED, update_modified=False)
    if doc.get("renewal_of") and frappe.db.get_value("Employee Contract", doc.renewal_of, "renewed_by") == doc.name:
        # back to where it stood: Not Renewed if HR had decided so (the reason is kept)
        end, reason = frappe.db.get_value("Employee Contract", doc.renewal_of, ["end_date", "decision_remarks"])
        status = rules.contract_status(1, end, today(), not_renewed=bool(reason))
        frappe.db.set_value("Employee Contract", doc.renewal_of, {"renewed_by": None, "status": status}, update_modified=False)
    latest = frappe.get_all("Employee Contract", filters={"employee": doc.employee, "docstatus": 1},
                            fields=["end_date"], order_by="start_date desc", limit=1)
    frappe.db.set_value("Employee", doc.employee, "contract_end_date", latest[0].end_date if latest else None)


@frappe.whitelist(methods=["POST"])
def make_renewal(contract):
    """Renew: the draft renewal (an existing one if already made)."""
    old = frappe.get_doc("Employee Contract", contract)
    old.check_permission("write")
    if old.docstatus != 1 or not old.end_date:
        frappe.throw(_("Only a submitted contract with an End Date can be renewed."))
    if old.get("renewed_by"):
        return old.renewed_by
    draft = frappe.db.get_value("Employee Contract", {"renewal_of": old.name, "docstatus": 0}, "name")
    if draft:
        return draft
    start, end = rules.renewal_dates(old.end_date, _usual_months(old.employment_type))
    renewal = frappe.copy_doc(old)
    renewal.update({"start_date": start, "end_date": end, "renewal_of": old.name, "signed_on": None,
                    "signed_contract": None, "decision_remarks": None, "alerts_sent": None})
    renewal.insert()
    return renewal.name


@frappe.whitelist(methods=["POST"])
def mark_not_renewed(contract, remarks):
    """Do Not Renew: recorded, and the HR Officer told to follow the
    termination process with the Expiry of Contract letter."""
    doc = frappe.get_doc("Employee Contract", contract)
    doc.check_permission("write")
    if doc.docstatus != 1 or doc.get("renewed_by"):
        frappe.throw(_("Only a submitted contract not yet renewed can be marked Not Renewed."))
    if not (remarks or "").strip():
        frappe.throw(_("Say why the contract is not renewed."))
    doc.db_set({"status": rules.NOT_RENEWED, "decision_remarks": remarks.strip()})
    doc.add_comment("Info", _("Not renewed: {0}").format(remarks.strip()))
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    message = _("The contract of {0} ending {1} is not renewed: print the Expiry of Contract letter and follow the "
                "termination process.").format(doc.employee_name, doc.end_date)
    people.assign("Employee Contract", doc.name, users, message, date=doc.end_date)
    people.notify(users, "Employee Contract", doc.name, message)


def daily():
    """Scheduler: every live contract's status, and its expiry alerts."""
    from hrms_addon.hrms_addon import probation

    alert_days = probation.settings().alert_days
    day = getdate(today())
    contracts = frappe.get_all(
        "Employee Contract",
        filters={"docstatus": 1, "status": ["in", LIVE]},
        fields=["name", "employee", "employee_name", "branch", "department", "end_date", "status", "alerts_sent", "renewed_by"],
    )
    # nobody is asked to renew the contract of an employee who has left
    gone = set(frappe.get_all("Employee", filters={"name": ["in", [c.employee for c in contracts]], "status": ["!=", "Active"]},
                              pluck="name")) if contracts else set()
    for contract in contracts:
        updates = {}
        status = rules.contract_status(1, contract.end_date, day, renewed=bool(contract.renewed_by))
        if status != contract.status:
            updates["status"] = status
        due = [] if contract.employee in gone else rules.alerts_due(contract.end_date, day, alert_days, contract.alerts_sent)
        if due:
            left = rules.days_left(contract.end_date, day)
            users = people.hr_officers(contract.branch, contract.department)
            message = _("The contract of {0} ends on {1}, in {2} days: decide whether to renew it (Renew or Do Not "
                        "Renew on the contract).").format(contract.employee_name, contract.end_date, left)
            people.notify(users, "Employee Contract", contract.name, message)
            people.assign("Employee Contract", contract.name, users, message, date=contract.end_date)
            updates["alerts_sent"] = rules.record_alerts(contract.alerts_sent, due)
        if updates:
            frappe.db.set_value("Employee Contract", contract.name, updates, update_modified=False)


def draft_for_new_employee(employee, hr_officer=None, base_salary=None, onboarding=None):
    """The new employee's contract, drafted when the HR Manager approves the
    onboarding (unless there is one): from the joining date, for the
    Employment Type's usual length. It keeps the onboarding it came from, so
    each is reachable from the other. None when there is nothing to draft."""
    if frappe.db.exists("Employee Contract", {"employee": employee, "docstatus": ["!=", 2]}):
        return None
    placed = frappe.db.get_value("Employee", employee, ["employment_type", "date_of_joining", "branch", "department"],
                                 as_dict=True)
    if not placed or not placed.employment_type:
        return None
    contract = frappe.new_doc("Employee Contract")
    contract.update({"employee": employee, "employment_type": placed.employment_type,
                     "start_date": placed.date_of_joining, "base_salary": base_salary, "onboarding": onboarding})
    contract.insert(ignore_permissions=True)
    users = [hr_officer] if hr_officer else people.hr_officers(placed.branch, placed.department)
    people.assign("Employee Contract", contract.name, users,
                  _("Contract of {0}: print it for the employee to sign, attach the signed copy and submit.").format(
                      contract.employee_name))
    return contract
