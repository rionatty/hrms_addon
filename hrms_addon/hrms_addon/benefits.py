# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Benefits Administration on the site (4.7), on Frappe HR's Expense Claim.

The rules are in benefits_rules.py, without a Frappe import
(scripts/verify_benefits.py). This reads and writes the site.

LPL/HR/27 is the paper: badge, section, what is claimed and when, the
reason, the supervisor's line saying whether it is genuine, the Section
Manager, and the remarks for the Human Resource Manager. The claim itself
is Frappe HR's Expense Claim, so the accounting that follows is theirs.

  claim_*    the claim through Supervisor, HOD, HR and General Manager,
             then Accounts; a standard claim held to the amount Luuka pay.
  birthdays  the second recommendation of the test script: whose birthday
             falls this week, told to the HR Officer and the supervisor.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import benefits_rules as rules, pay, people

DOCTYPE = "Expense Claim"


# ── 1. The claim ──────────────────────────────────────────────────────
def claim_validate(doc, method=None):
    from hrms_addon.hrms_addon import claim_approval as approval

    _check_step(doc)
    state = doc.get("workflow_state")
    doc.custom_claim_status = state or doc.get("custom_claim_status") or approval.DRAFT
    if state:
        # their own approval_status is what their controller reads
        doc.approval_status = approval.upstream_approval(state)


def _facts(doc):
    row = (doc.get("expenses") or [None])[0]
    claim_type = row.expense_type if row else None
    settings = _type_settings(claim_type)
    employee = doc.get("employee")
    facts = {
        "claim_details": doc.get("custom_claim_details"), "reason": doc.get("custom_reason"),
        "amount": doc.get("total_claimed_amount"), "claim_type": claim_type,
        "standard_amount": settings.get("standard_amount"), "is_standard": settings.get("is_standard"),
        "requires_evidence": settings.get("requires_evidence"), "evidence": doc.get("custom_evidence"),
        "percent_of_gross": settings.get("percent_of_gross"), "max_times": settings.get("max_times"),
        "for_gender": settings.get("for_gender"), "relations": settings.get("relations"),
        "relation": doc.get("custom_relation"),
    }
    if employee and settings.get("percent_of_gross"):
        facts["gross_pay"] = pay.monthly_gross(employee)
    if employee and settings.get("max_times"):
        facts["times_before"] = _times_before(employee, claim_type, doc.name)
    if employee and settings.get("for_gender"):
        facts["gender"] = frappe.db.get_value("Employee", employee, "gender")
    return facts


def _times_before(employee, claim_type, exclude):
    """How many of this benefit the employee has already been paid. A claim
    that was refused or cancelled was not paid."""
    claims = frappe.get_all(DOCTYPE, filters={"employee": employee, "docstatus": 1,
                                              "name": ["!=", exclude or ""]},
                            pluck="name", limit_page_length=0)
    if not claims:
        return 0
    return len(set(frappe.get_all("Expense Claim Detail",
                                  filters={"parenttype": DOCTYPE, "parent": ["in", claims],
                                           "expense_type": claim_type},
                                  pluck="parent", limit_page_length=0)))


def _type_settings(claim_type):
    if not claim_type:
        return {}
    wanted = ["custom_is_standard", "custom_standard_amount", "custom_requires_evidence"]
    newer = ["custom_percent_of_gross", "custom_max_times", "custom_for_gender", "custom_relations"]
    meta = frappe.get_meta("Expense Claim Type")
    wanted += [field for field in newer if meta.has_field(field)]
    row = frappe.db.get_value("Expense Claim Type", claim_type, wanted, as_dict=True) or {}
    return {"is_standard": row.get("custom_is_standard"),
            "standard_amount": row.get("custom_standard_amount"),
            "requires_evidence": row.get("custom_requires_evidence"),
            "percent_of_gross": row.get("custom_percent_of_gross"),
            "max_times": row.get("custom_max_times"),
            "for_gender": row.get("custom_for_gender"),
            "relations": row.get("custom_relations")}


def _check_step(doc):
    from hrms_addon.hrms_addon import claim_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            "genuine": doc.get("custom_genuine"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if new_state == approval.PENDING_SUPERVISOR and old_state in (None, approval.DRAFT):
            errors = rules.claim_errors(_facts(doc)) + errors
        if old_state == approval.PENDING_SUPERVISOR and new_state != approval.DRAFT:
            errors += rules.genuine_errors({"genuine": doc.get("custom_genuine"),
                                            "supervisor_remarks": doc.get("custom_supervisor_remarks")})
        if old_state == approval.PENDING_ACCOUNTS and new_state == approval.PAID:
            errors += rules.payment_errors({"amount": doc.get("total_claimed_amount"),
                                            "sanctioned_amount": doc.get("total_sanctioned_amount"),
                                            "paid_amount": doc.get("total_sanctioned_amount"),
                                            "paid_on": doc.get("custom_paid_on")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Claim"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell(doc, new_state)


def _tell(doc, state):
    from hrms_addon.hrms_addon import claim_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("custom_branch"), doc.get("department"))
    message = _("Claim from {0}: {1}.").format(
        doc.get("employee_name") or doc.employee,
        frappe.utils.fmt_money(doc.get("total_claimed_amount")))
    people.notify(users, doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def claim_on_submit(doc, method=None):
    """Paid. The HR Officer is told, as step 3 of the chart asks."""
    users = people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    if not users:
        return
    people.notify(users, doc.doctype, doc.name,
                  _("{0}'s claim of {1} has been paid.").format(
                      doc.get("employee_name") or doc.employee,
                      frappe.utils.fmt_money(doc.get("total_sanctioned_amount"))))


def claim_on_cancel(doc, method=None):
    doc.custom_claim_status = "Cancelled"


# ── 2. Birthdays ──────────────────────────────────────────────────────
def daily():
    """A claim waiting on Accounts, and whose birthday is coming."""
    _tell_accounts()
    _tell_birthdays()


def _tell_accounts():
    from hrms_addon.hrms_addon import claim_approval as approval

    rows = frappe.get_all(DOCTYPE,
                          filters={"docstatus": 0, "custom_claim_status": approval.PENDING_ACCOUNTS},
                          fields=["name", "employee", "employee_name", "custom_branch", "department",
                                  "total_sanctioned_amount"], limit=200)
    for row in rows:
        users = people.people_for(approval.ACCOUNTS, row.custom_branch, row.department)
        if not users:
            continue
        people.assign(DOCTYPE, row.name, users,
                      _("{0}'s claim of {1} is waiting to be paid.").format(
                          row.employee_name or row.employee,
                          frappe.utils.fmt_money(row.total_sanctioned_amount)))
    frappe.db.commit()


def _tell_birthdays():
    """"System should be able to track birthdays and send notifications" —
    a week before, and on the day."""
    staff = frappe.get_all("Employee", filters={"status": "Active"},
                           fields=["name", "employee_name", "date_of_birth", "branch", "department",
                                   "reports_to", "user_id"], limit=5000)
    due = rules.birthdays_due(staff, today())
    if not due:
        return
    by_name = {row.name: row for row in staff}
    for name, ahead in due:
        row = by_name.get(name)
        if not row:
            continue
        users = people.hr_officers(row.branch, row.department)
        supervisor = frappe.db.get_value("Employee", row.reports_to, "user_id") if row.reports_to else None
        if supervisor:
            users = list(users) + [supervisor]
        if not users:
            continue
        turning = rules.age_on(row.date_of_birth, today())
        message = (_("{0}'s birthday is today.") if not ahead
                   else _("{0}'s birthday is in {1} day(s).")).format(row.employee_name or name, ahead)
        if turning:
            message += " " + _("Turning {0}.").format(turning + (0 if not ahead else 1))
        people.notify(list(dict.fromkeys(users)), "Employee", name, message)
    frappe.db.commit()


# ── 3. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the claim's five desks."""
    from hrms_addon.hrms_addon import claim_approval, workflows

    workflows.setup_on_migrate(claim_approval, "Employee Claim workflow")


def seed_standard_claims():
    """The standard claims Luuka pay, as Expense Claim Types. The amounts
    are Luuka's to set: these are created at nil and marked standard, so HR
    fill in what each is worth."""
    wanted = ((rules.WEDDING, "Wedding Gift"), (rules.BEREAVEMENT, rules.BEREAVEMENT_SUPPORT),
              (rules.BIRTH, "New Baby Gift"), (rules.SICKNESS, "Medical Support"),
              (rules.BIRTH, rules.MATERNITY_BENEFIT))
    made = []
    for occasion, name in wanted:
        if frappe.db.exists("Expense Claim Type", name):
            continue
        doc = frappe.new_doc("Expense Claim Type")
        doc.expense_type = name
        doc.custom_is_standard = 1
        doc.custom_occasion = occasion
        doc.description = _("A standard claim. Set its amount before use.")
        for field, value in minutes_values(name).items():
            doc.set(field, value)
        doc.insert(ignore_permissions=True)
        made.append(name)
    return made


def minutes_values(name):
    """What the minutes set a benefit's claim type to (§4.8)."""
    if name == rules.MATERNITY_BENEFIT:
        return {"custom_is_standard": 1, "custom_standard_amount": rules.MATERNITY_AMOUNT,
                "custom_max_times": rules.MATERNITY_TIMES, "custom_for_gender": rules.FEMALE,
                "custom_requires_evidence": 1,
                "description": _("UGX 350,000 for female employees, up to three times.")}
    if name == rules.BEREAVEMENT_SUPPORT:
        return {"custom_is_standard": 0, "custom_percent_of_gross": rules.BEREAVEMENT_PERCENT,
                "custom_relations": ", ".join(rules.BEREAVEMENT_RELATIONS),
                "description": _("70% of gross, for the loss of a mother, father or child.")}
    return {}
