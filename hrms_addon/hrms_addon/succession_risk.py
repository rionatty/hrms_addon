# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A critical role's risk and its bench in depth, on the site. The rules
are in succession_rules.py (scripts/verify_succession_risk.py).

  fill             on every save of a Succession Position: the impact from
                   its criticality rows, the probability of losing its
                   holder (an exit raised, a retirement near, the flight
                   risk last assessed), the risk and its level; each
                   successor's latest box and flight risk, the other roles
                   they are named for, their rank; the bench counted
  refresh_position the same, written straight to a role (an exit, a flight
                   risk assessed, a factor reweighed)
  latest_boxes     each employee's newest finalised placement, newest first
                   and without a cut-off
  named_for        how many live roles name each employee
  daily            every live role read again: a retirement comes nearer
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, today

from hrms_addon.hrms_addon import succession_rules as rules, talent_masters as masters

POSITION, CANDIDATE, PLACEMENT, FACTOR = (
    "Succession Position", "Succession Candidate", "Talent Placement", "Criticality Factor")


def fill(doc):
    errors = rules.factor_errors([row.as_dict() for row in doc.get("criticality") or []])
    errors += rules.candidate_errors([row.as_dict() for row in doc.get("candidates") or []], doc.get("incumbent"),
                                     [name for name in frappe.get_all("Readiness Level", pluck="name")] or None)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(POSITION))
    weights = {row.name: flt(row.weight) for row in frappe.get_all(FACTOR, fields=["name", "weight"])}
    impact = rules.impact([row.as_dict() for row in doc.get("criticality") or []], weights)
    probability, reasons = rules.loss_probability(_holder_facts(doc), today(), masters.settings())
    risk = rules.role_risk(probability, impact)
    doc.impact_score = impact
    doc.loss_probability = round(probability * 100, 1)
    doc.role_risk = risk
    doc.risk_reasons = "; ".join(reasons)
    doc.risk_level = rules.risk_level(risk, doc.get("risk_level"))
    _fill_candidates(doc)


def _holder_facts(doc):
    holder = doc.get("incumbent")
    facts = {"holder": holder, "exit_due": doc.get("retirement_or_exit_due")}
    if holder:
        facts["retirement"] = frappe.db.get_value("Employee", holder, "date_of_retirement")
        facts["flight_risk"] = latest_risk([holder]).get(holder)
    return facts


def latest_risk(employees):
    """{employee: their latest assessed flight risk}, the placement's where
    nobody has assessed them."""
    employees = sorted({name for name in employees if name})
    if not employees:
        return {}
    out = {}
    for row in frappe.get_all("Flight Risk Assessment", filters={"employee": ["in", employees]},
                              fields=["employee", "risk"], order_by="assessed_on desc, creation desc",
                              limit_page_length=0):
        out.setdefault(row.employee, row.risk)
    for employee, row in latest_boxes(employees).items():
        out.setdefault(employee, row.get("flight_risk"))
    return out


def _fill_candidates(doc):
    rows = doc.get("candidates") or []
    employees = [row.employee for row in rows if row.get("employee")]
    boxes = latest_boxes(employees)
    risks = latest_risk(employees)
    named = named_for(employees, exclude=doc.name)
    for row, rank in rules.next_ranks([row for row in rows]):
        row.rank = rank
    for row in rows:
        found = boxes.get(row.employee) or {}
        row.latest_box = found.get("box")
        row.box_name = found.get("box_name") or row.get("box_name")
        row.flight_risk = risks.get(row.employee)
        row.other_roles = named.get(row.employee, 0)
        if not row.get("placement") and found.get("name"):
            row.placement = found.get("name")
        if not row.get("readiness") and found.get("box"):
            row.readiness = masters.suggested_readiness(found.get("box"))
    successors = [row for row in rows if row.get("readiness") != rules.GAP]
    doc.successors = len(successors)
    doc.two_or_more = 1 if len(successors) >= 2 else 0


def latest_boxes(employees):
    """{employee: their newest finalised placement}: box, name, colour and
    flight risk. Newest first and without a cut-off, so a new placement is
    never lost behind old ones."""
    employees = sorted({name for name in employees if name})
    if not employees:
        return {}
    rows = frappe.db.sql("""
        select name, employee, box, box_name, box_colour, flight_risk, top_talent
        from `tabTalent Placement`
        where docstatus = 1 and employee in %(employees)s
        order by finalised_on desc, creation desc""", {"employees": employees}, as_dict=True)
    out = {}
    for row in rows:
        out.setdefault(row.employee, row)
    return out


def named_for(employees, exclude=None):
    """{employee: how many other live roles name them as a successor}."""
    employees = sorted({name for name in employees if name})
    if not employees:
        return {}
    rows = frappe.db.sql("""
        select candidate.employee, count(distinct candidate.parent) as roles
        from `tabSuccession Candidate` candidate
        join `tabSuccession Position` position on position.name = candidate.parent
        where candidate.parenttype = 'Succession Position' and position.docstatus < 2
          and candidate.employee in %(employees)s and candidate.parent != %(exclude)s
        group by candidate.employee""", {"employees": employees, "exclude": exclude or ""}, as_dict=True)
    return {row.employee: cint(row.roles) for row in rows}


def refresh_position(name):
    """A role read again and written straight in, confirmed or not."""
    if not name:
        return
    doc = frappe.get_doc(POSITION, name)
    if doc.docstatus == 2:
        return
    try:
        fill(doc)
    except frappe.ValidationError:
        frappe.clear_last_message()
        return
    doc.db_update()
    doc.update_child_table("candidates")


def factor_on_update(doc):
    """A factor reweighed: every role scored on it read again, in the
    background."""
    frappe.enqueue("hrms_addon.hrms_addon.succession_risk.refresh_positions", queue="long", timeout=1800,
                   job_id="hrms_addon_talent::factor::%s" % doc.name, deduplicate=True, enqueue_after_commit=True,
                   factor=doc.name)


def refresh_positions(factor=None):
    filters = {"docstatus": ["<", 2]}
    names = frappe.get_all(POSITION, filters=filters, pluck="name", limit_page_length=0)
    if factor:
        scored = set(frappe.get_all("Role Criticality", filters={"factor": factor, "parenttype": POSITION},
                                    pluck="parent", limit_page_length=0))
        names = [name for name in names if name in scored]
    for number, name in enumerate(names, 1):
        refresh_position(name)
        if number % 100 == 0:
            frappe.db.commit()
    frappe.db.commit()


def daily():
    """Every live role read again: the holder's retirement comes nearer, a
    successor's box changes with a review finalised."""
    refresh_positions()


def overlap(company=None, branches=None):
    """Successors named for more than one live role: [{"employee",
    "employee_name", "roles": [designations]}]."""
    condition, values = "", {}
    if company:
        condition += " and position.company = %(company)s"
        values["company"] = company
    if branches:
        condition += " and position.branch in %(branches)s"
        values["branches"] = list(branches)
    rows = frappe.db.sql("""
        select candidate.employee, candidate.employee_name, position.designation, position.name as position
        from `tabSuccession Candidate` candidate
        join `tabSuccession Position` position on position.name = candidate.parent
        where candidate.parenttype = 'Succession Position' and position.docstatus < 2 {condition}
        order by candidate.employee_name asc""".format(condition=condition), values, as_dict=True)
    found = rules.overlap([{"employee": row.employee, "position": row.designation or row.position} for row in rows])
    names = {row.employee: row.employee_name for row in rows}
    return [{"employee": employee, "employee_name": names.get(employee), "roles": roles}
            for employee, roles in sorted(found.items(), key=lambda item: -len(item[1]))]
