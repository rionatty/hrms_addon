# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Succession Plan: a year's critical roles and their benches, reviewed
by the Talent Council as one (the talent blueprint, section 6). The workflow
is succession_plan_approval.py; each role keeps its own (succession_approval.py,
talent.py section 4).

  plan_validate    each role's bench as the role holds it, the plan's figures,
                   no role in two plans of a year, the step checked and stamped
  plan_on_update   sent to the council: every role still nominating goes with it
  plan_on_submit   finalised: the council confirms every role before it, and
                   each confirmation does what the role's own does (successors
                   developed, a gap raised to resourcing)
  get_positions    the year's roles for the plan's company, plant and department
  refresh_plan     a finalised plan's benches read again
"""

import frappe
from frappe import _
from frappe.utils import cint, today

from hrms_addon.hrms_addon import people, succession_plan_approval as approval

PLAN = "Succession Plan"
ROW = "Succession Plan Position"
POSITION = "Succession Position"
COUNCIL = "Talent Council"
FACTS = ("designation", "branch", "department", "incumbent_name", "risk_level", "single_person_role", "coverage",
         "ready_now", "ready_soon", "emerging")


def plan_validate(doc):
    _fill_rows(doc)
    _check_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _fill_rows(doc):
    """Each role's bench as the role holds it; nothing typed."""
    seen = set()
    taken = _in_other_plans([row.succession_position for row in doc.get("positions") or []], doc)
    for row in doc.get("positions") or []:
        if row.succession_position in seen:
            frappe.throw(_("{0} is in the plan twice.").format(row.succession_position), title=_(PLAN))
        seen.add(row.succession_position)
        if row.succession_position in taken:
            frappe.throw(_("{0} is already in {1}.").format(row.succession_position, taken[row.succession_position]),
                         title=_(PLAN))
        _read_role(row)
    _summarise(doc)


def _read_role(row):
    role = frappe.db.get_value(POSITION, row.succession_position,
                               list(FACTS) + ["workflow_state", "status", "docstatus"], as_dict=True)
    if not role:
        frappe.throw(_("{0} is not a succession position.").format(row.succession_position), title=_(PLAN))
    for field in FACTS:
        row.set(field, role.get(field))
    row.position_state = role.get("workflow_state") or role.get("status")


def _summarise(doc):
    for field, value in approval.summary([row.as_dict() for row in doc.get("positions") or []]).items():
        doc.set(field, value)


def _in_other_plans(positions, doc):
    """{role: the other plan of the year it is in}."""
    positions = [name for name in positions if name]
    if not positions:
        return {}
    rows = frappe.get_all(ROW, filters={"parenttype": PLAN, "succession_position": ["in", positions],
                                        "parent": ["!=", doc.name or ""]},
                          fields=["parent", "succession_position"], limit_page_length=0)
    live = set(frappe.get_all(PLAN, filters={"name": ["in", list({row.parent for row in rows})],
                                             "docstatus": ["!=", 2], "plan_year": doc.get("plan_year")},
                              pluck="name")) if rows else set()
    return {row.succession_position: row.parent for row in rows if row.parent in live}


def _check_step(doc):
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"),
            "positions": [{"succession_position": row.succession_position, "state": row.position_state}
                          for row in doc.get("positions") or []]})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(PLAN))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)


def plan_on_update(doc):
    """Sent to the council: every role still nominating goes with it, as one."""
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    if old_state == doc.get("workflow_state") or doc.get("workflow_state") != approval.COUNCIL_REVIEW:
        return
    _move(approval.to_send([{"succession_position": row.succession_position, "state": row.position_state}
                            for row in doc.get("positions") or []]), "Send to Council")
    _refresh(doc)
    users = people.people_for(COUNCIL, doc.get("branch"), doc.get("department"))
    if users:
        people.notify(users, PLAN, doc.name, _("{0} is with the council: {1} role(s), {2} of them a gap.").format(
            doc.get("title") or doc.name, cint(doc.total_positions), cint(doc.gaps)))


def plan_on_submit(doc):
    """Finalised: the council confirms every role before it."""
    _move(approval.to_confirm([{"succession_position": row.succession_position, "state": row.position_state}
                               for row in doc.get("positions") or []]), "Confirm")
    _refresh(doc)


def _move(positions, action):
    """Each role taken its own step, as the user taking the plan's: a role
    that refuses stops the plan's step with its own reason."""
    from frappe.model.workflow import apply_workflow

    for name in positions:
        apply_workflow(frappe.get_doc(POSITION, name), action)


def _refresh(doc):
    """The roles read again after they moved, written straight to the plan."""
    for row in doc.get("positions") or []:
        _read_role(row)
        row.db_update()
    _summarise(doc)
    for field in ("total_positions", "covered", "at_risk", "gaps", "single_person_roles", "ready_now"):
        doc.db_set(field, doc.get(field), update_modified=False)


@frappe.whitelist(methods=["POST"])
def get_positions(plan):
    """The year's critical roles for the plan's company, plant and
    department, not cancelled and in no other plan of the year. Returns how
    many were added."""
    doc = frappe.get_doc(PLAN, plan)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("The plan is already finalised."), title=_(PLAN))
    filters = {"company": doc.company, "docstatus": ["!=", 2], "review_year": doc.plan_year}
    for field in ("branch", "department"):
        if doc.get(field):
            filters[field] = doc.get(field)
    have = {row.succession_position for row in doc.get("positions") or []}
    candidates = [name for name in frappe.get_all(POSITION, filters=filters, pluck="name", order_by="name asc",
                                                  limit_page_length=0) if name not in have]
    taken = _in_other_plans(candidates, doc)
    added = 0
    for name in candidates:
        if name not in taken:
            doc.append("positions", {"succession_position": name})
            added += 1
    doc.save()
    return added


@frappe.whitelist(methods=["POST"])
def refresh_plan(plan):
    """A finalised plan's benches, read again from its roles."""
    doc = frappe.get_doc(PLAN, plan)
    doc.check_permission("read")
    _refresh(doc)
    return doc.total_positions
