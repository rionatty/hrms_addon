# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent pools (the talent blueprint, section 5.1, stage 5: "Talent Council
| Confirm pools"; section 6: "Add Successor rows from finalised talent
pool"). The rules are in succession_rules.py (scripts/verify_succession_risk.py).

  pool_validate       members as their placements have them, the history
                      kept (a confirmed member is exited, never taken off)
  get_members         the review's finalised placements in the boxes the
                      pool draws from, proposed as members
  confirm_members     the council confirms the members proposed
  pool_members        a pool's confirmed members, for nominating successors
  nominate_from_pool  successors added to a critical role from a pool,
                      each suggested the readiness their box draws
"""

import frappe
from frappe import _
from frappe.utils import cint, today

from hrms_addon.hrms_addon import succession_rules as rules, talent_masters as masters

POOL, PLACEMENT, POSITION, BOX = "Talent Pool", "Talent Placement", "Succession Position", "Nine Box"
CONFIRMERS = ("Talent Council", "HR Manager", "System Manager")


def pool_validate(doc):
    before = doc.get_doc_before_save()
    errors = rules.member_errors([row.as_dict() for row in before.get("members") or []] if before else [],
                                 [row.as_dict() for row in doc.get("members") or []])
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(POOL))
    latest = _latest([row.employee for row in doc.get("members") or [] if row.get("employee")])
    for row in doc.get("members") or []:
        found = latest.get(row.employee) or {}
        if not row.get("placement"):
            row.placement = found.get("name")
        row.box = found.get("box") or row.get("box")
        if not row.get("entered_on"):
            row.entered_on = today()
        if not row.get("nominated_by"):
            row.nominated_by = frappe.session.user
        if row.get("status") == rules.EXITED and not row.get("exited_on"):
            row.exited_on = today()
    doc.active_members = len([row for row in doc.get("members") or [] if row.get("status") != rules.EXITED])
    doc.confirmed_members = len([row for row in doc.get("members") or [] if row.get("status") == rules.CONFIRMED])


def _latest(employees):
    """{employee: {"name", "box"}} of each one's latest finalised placement."""
    employees = sorted({name for name in employees if name})
    if not employees:
        return {}
    out = {}
    for row in frappe.get_all(PLACEMENT, filters={"employee": ["in", employees], "docstatus": 1},
                              fields=["name", "employee", "box", "finalised_on", "creation"],
                              order_by="finalised_on desc, creation desc", limit_page_length=0):
        out.setdefault(row.employee, row)
    return out


def _boxes(doc):
    names = [row.nine_box for row in doc.get("eligible_boxes") or [] if row.get("nine_box")]
    if not names:
        return []
    return [cint(row.box) for row in frappe.get_all(BOX, filters={"name": ["in", names]}, fields=["box"])]


@frappe.whitelist(methods=["POST"])
def get_members(pool):
    """The review's finalised placements in the pool's boxes, company and
    plant, proposed as members. Returns how many came in."""
    doc = frappe.get_doc(POOL, pool)
    doc.check_permission("write")
    from hrms_addon.hrms_addon import talent_reports

    review = doc.get("talent_review") or talent_reports.latest_review()
    if not review:
        frappe.throw(_("There is no talent review to draw the pool from."), title=_(POOL))
    filters = {"talent_review": review, "docstatus": 1, "company": doc.company}
    if doc.get("branch"):
        filters["branch"] = doc.branch
    placed = frappe.get_all(PLACEMENT, filters=filters, fields=["name", "employee", "box"], order_by="box desc",
                            limit_page_length=0)
    new = rules.members_to_add(placed, [row.as_dict() for row in doc.members], _boxes(doc))
    for row in new:
        doc.append("members", {"employee": row.employee, "placement": row.name, "box": row.box,
                               "status": rules.PROPOSED, "entered_on": today(), "nominated_by": frappe.session.user})
    if not doc.get("talent_review"):
        doc.talent_review = review
    doc.save()
    return len(new)


@frappe.whitelist(methods=["POST"])
def confirm_members(pool):
    """The council confirms the members proposed."""
    frappe.only_for(CONFIRMERS)
    doc = frappe.get_doc(POOL, pool)
    doc.check_permission("write")
    count = 0
    for row in doc.members:
        if row.status == rules.PROPOSED:
            row.status, row.confirmed_on = rules.CONFIRMED, today()
            count += 1
    doc.status = "Confirmed"
    doc.confirmed_by, doc.confirmed_on = frappe.session.user, today()
    doc.save()
    return count


@frappe.whitelist()
def pool_members(pool, designation=None):
    """The pool's confirmed members, with the readiness their box suggests."""
    doc = frappe.get_doc(POOL, pool)
    doc.check_permission("read")
    if designation and not rules.pool_fits([row.designation for row in doc.target_roles], designation):
        frappe.throw(_("{0} is not grown for {1}.").format(doc.pool_name, designation), title=_(POOL))
    return [{"employee": row.employee, "employee_name": row.employee_name, "designation": row.designation,
             "branch": row.branch, "readiness": masters.suggested_readiness(row.box) or rules.EMERGING}
            for row in doc.members if row.status == rules.CONFIRMED]


@frappe.whitelist(methods=["POST"])
def nominate_from_pool(position, pool, employees):
    """Successors added to a critical role from a pool's confirmed members.
    Returns how many were added."""
    doc = frappe.get_doc(POSITION, position)
    doc.check_permission("write")
    if not doc.has_permlevel_access_to("candidates", permission_type="write"):
        frappe.throw(_("You may not name successors."), frappe.PermissionError)
    members = {row["employee"]: row for row in pool_members(pool, doc.designation)}
    chosen = [name for name in frappe.parse_json(employees) or [] if name in members]
    have = {row.employee for row in doc.candidates}
    latest = _latest(chosen)
    added = 0
    for employee in chosen:
        if employee in have or employee == doc.get("incumbent"):
            continue
        doc.append("candidates", {"employee": employee, "readiness": members[employee]["readiness"],
                                  "talent_pool": pool, "placement": (latest.get(employee) or {}).get("name"),
                                  "nominated_by": frappe.session.user})
        added += 1
    if added:
        doc.save()
    return added
