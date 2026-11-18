# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Flight risk as a history, and what is done about it (the talent
blueprint, section 9: "Top-talent flight risk | Alert HR and Council for
retention action"). The rules are in succession_rules.py
(scripts/verify_succession_risk.py).

  assessment_*        a Flight Risk Assessment, insert only: the placement,
                      the successor rows naming the employee and the roles
                      they hold take its risk; top talent at a watched level
                      is told to HR and the council once a level, with the
                      critical roles it touches
  placement_changed   a flight risk changed on a placement's form is kept as
                      an assessment too
  retention_validate  a placement's retention actions: each says what is
                      done and, once closed, how it went
"""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import people, succession_rules as rules, talent_jobs, talent_masters as masters

ASSESSMENT, PLACEMENT, POSITION, CANDIDATE = (
    "Flight Risk Assessment", "Talent Placement", "Succession Position", "Succession Candidate")


def assessment_validate(doc):
    if not doc.is_new():
        frappe.throw(_("A flight risk assessment is kept as it was made. Record a new one."), title=_(ASSESSMENT))
    doc.assessed_by = frappe.session.user
    if not doc.get("placement"):
        found = frappe.get_all(PLACEMENT, filters={"employee": doc.employee, "docstatus": ["<", 2]},
                               pluck="name", order_by="creation desc", limit=1)
        doc.placement = found[0] if found else None
    before = frappe.get_all(ASSESSMENT, filters={"employee": doc.employee}, pluck="risk",
                            order_by="assessed_on desc, creation desc", limit=1)
    doc.previous_risk = before[0] if before else None
    doc.roles_affected = roles_touched(doc.employee) or None


def roles_touched(employee):
    """The critical roles a person holds, and those they are named to
    succeed with their readiness: one line."""
    held = frappe.get_all(POSITION, filters={"incumbent": employee, "docstatus": ["<", 2]}, pluck="designation")
    named = frappe.db.sql("""
        select position.designation, candidate.readiness
        from `tabSuccession Candidate` candidate
        join `tabSuccession Position` position on position.name = candidate.parent
        where candidate.parenttype = 'Succession Position' and candidate.employee = %(employee)s
          and position.docstatus < 2""", {"employee": employee}, as_dict=True)
    parts = [_("Holds {0}").format(role) for role in held if role]
    parts += [_("Successor for {0} ({1})").format(row.designation, _(row.readiness or "")) for row in named]
    return "; ".join(parts)


def assessment_after_insert(doc):
    """The risk taken everywhere it is read, and told where it must be."""
    placement = frappe.db.get_value(PLACEMENT, doc.placement, ["name", "top_talent", "risk_alerted", "branch",
                                                               "department", "box", "box_name"], as_dict=True) \
        if doc.get("placement") else None
    if placement:
        frappe.db.set_value(PLACEMENT, placement.name, {
            "flight_risk": doc.risk, "impact_of_loss": doc.get("impact_of_loss"), "risk_notes": doc.get("notes"),
            "risk_assessed_on": doc.assessed_on}, update_modified=False)
    frappe.db.sql("""update `tabSuccession Candidate` set flight_risk = %(risk)s
                     where parenttype = 'Succession Position' and employee = %(employee)s""",
                  {"risk": doc.risk, "employee": doc.employee})
    from hrms_addon.hrms_addon import succession_risk

    for name in frappe.get_all(POSITION, filters={"incumbent": doc.employee, "docstatus": ["<", 2]}, pluck="name"):
        succession_risk.refresh_position(name)
    watched = masters.watched_risks()
    if not placement:
        return
    if doc.risk not in watched:
        frappe.db.set_value(PLACEMENT, placement.name, "risk_alerted", None, update_modified=False)
        return
    if not rules.alert_needed(placement.top_talent, doc.risk, watched, placement.risk_alerted):
        return
    users = list(people.hr_officers(placement.branch, placement.department))
    users += list(people.people_for("Talent Council", placement.branch, placement.department))
    roles = doc.get("roles_affected")
    message = _("{0} is top talent and assessed {1} flight risk. Retention action is the council's to take.").format(
        doc.employee_name or doc.employee, str(doc.risk).lower())
    if roles:
        message += " " + _("Critical roles: {0}.").format(roles)
    talent_jobs.tell(users, PLACEMENT, placement.name, message)
    frappe.db.set_value(PLACEMENT, placement.name, {"risk_alerted": doc.risk, "risk_notified": 1},
                        update_modified=False)
    doc.db_set("alerted", 1, update_modified=False)


def assessment_on_trash(doc):
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("A flight risk assessment is kept."), frappe.PermissionError)


def placement_changed(doc):
    """A placement's flight risk set or changed on its form: kept as an
    assessment, as one made on its own would be."""
    if doc.flags.get("from_assessment") or not doc.get("flight_risk"):
        return None
    before = doc.get_doc_before_save()
    if before and before.get("flight_risk") == doc.flight_risk and \
            before.get("impact_of_loss") == doc.get("impact_of_loss"):
        return None
    entry = frappe.get_doc({"doctype": ASSESSMENT, "employee": doc.employee, "placement": doc.name,
                            "assessed_on": today(), "risk": doc.flight_risk,
                            "impact_of_loss": doc.get("impact_of_loss"), "notes": doc.get("risk_notes")})
    entry.flags.ignore_permissions = True
    entry.insert()
    return entry.name


def retention_validate(doc):
    errors = rules.retention_errors([row.as_dict() for row in doc.get("retention_actions") or []])
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Retention Actions"))


@frappe.whitelist()
def history(employee):
    """The employee's flight risk over time, for the talent card."""
    if not frappe.has_permission(ASSESSMENT, "read"):
        return []
    return frappe.get_list(ASSESSMENT, filters={"employee": employee},
                           fields=["name", "assessed_on", "risk", "previous_risk", "assessed_by", "alerted"],
                           order_by="assessed_on desc, creation desc", limit_page_length=20)
