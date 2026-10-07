# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The non-disciplinary grievance on the site (5.4; the test sheet's Non
Disciplinary cases 1 to 11), on Frappe HR's own Employee Grievance.

The stages are in grievance_approval.py and the timeline in
grievance_rules.py, both without a Frappe import
(scripts/verify_grievances.py). This reads and writes the site.

  grievance_validate  a step: what it needs, who may take it, what it
                      writes, and who is told and given it to do. A save
                      that takes no step: who may change what, and a new
                      handler is given it in place of the one before
  grievance_on_discard  a draft thrown away is Cancelled on the workflow
  grievance_on_trash  once raised, only the HR Manager deletes one
  daily               the timeline: at risk, the head of the employee's
                      department hears of it as well as the handler; past
                      its date, HR
  holders_of          the Handler and Appeal Heard By pickers
  setup_on_migrate    the workflow, and the decision fields at level one
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, format_date, get_fullname, today

from hrms_addon.hrms_addon import grievance_approval as approval, grievance_rules as rules, people, workflows

DOCTYPE = approval.DOCTYPE
# the fields whose change on a save that takes no step is checked
# (grievance_approval.change_errors)
WATCHED = approval.STATEMENT_FIELDS + ("custom_assigned_hod", "custom_appeals_authority", "custom_due_on")


# ── 1. Each save ──────────────────────────────────────────────────────
def grievance_validate(doc, method=None):
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD) or approval.DRAFT
    if doc.docstatus == 1 and new_state not in approval.FILED:
        frappe.throw(_("A grievance is filed by its own buttons: Accept, Decide Appeal or Mark Invalid."),
                     title=_(DOCTYPE))
    changed = [field for field in WATCHED if before is not None and cstr(before.get(field)) != cstr(doc.get(field))]
    _fill_handler(doc, before, old_state, new_state)
    if before is not None and old_state != new_state:
        _take_step(doc, before, old_state, new_state)
    elif before is not None and changed:
        _check_changes(doc, before, new_state, changed)
    doc.status = approval.FRAPPE_STATUS.get(new_state) or doc.get("status")
    doc.custom_overdue = 1 if rules.overdue(doc.get("custom_due_on"), today(), new_state) else 0


def grievance_on_discard(doc, method=None):
    """A draft thrown away is Cancelled on the workflow too, as Frappe HR
    makes its status (Frappe leaves the state where it was)."""
    doc.db_set(approval.STATE_FIELD, approval.CANCELLED, update_modified=False)


def grievance_on_trash(doc, method=None):
    errors = approval.delete_errors(doc.get(approval.STATE_FIELD), frappe.get_roles())
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))


def _fill_handler(doc, before, old_state, new_state):
    """While HR have it, the handler is the Grievance Type's usual one until
    they name another; a change of type brings that type's usual handler."""
    if not (new_state == approval.OPEN or (old_state == approval.OPEN and new_state == approval.UNDER_REVIEW)):
        return
    current = doc.get("custom_assigned_hod")
    old_type = before.get("grievance_type") if before else None
    retyped = old_type and old_type != doc.get("grievance_type") and current == _usual_handler(old_type)
    if not current or retyped:
        doc.custom_assigned_hod = _usual_handler(doc.get("grievance_type")) or current


def _take_step(doc, before, old_state, new_state):
    if new_state == approval.APPEALED and not doc.get("custom_appeals_authority"):
        doc.custom_appeals_authority = rules.appeal_authority(_authorities(doc), _involved(doc))
    facts = _facts(doc)
    errors = approval.step_errors(old_state, new_state, facts)
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))
    day = today()
    due = rules.due_on(day, _timeline_days(doc.get("grievance_type")))
    for field, value in approval.step_changes(old_state, new_state, facts, day, due).items():
        doc.set(field, value)
    _tell_step(doc, before, old_state, new_state)


def _check_changes(doc, before, state, changed):
    errors = approval.change_errors(state, changed, _facts(doc))
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_(DOCTYPE))
    if "custom_due_on" in changed:
        doc.custom_escalation = rules.NOT_ESCALATED
    who = doc.get("employee_name") or doc.get("raised_by")
    if state == approval.UNDER_REVIEW and "custom_assigned_hod" in changed:
        people.withdraw(DOCTYPE, doc.name, [before.get("custom_assigned_hod")])
        _let_act([doc.custom_assigned_hod], doc)
        _give([doc.custom_assigned_hod], doc, _("Grievance {0} from {1}: {2}. Due by {3}.").format(
            doc.name, who, _subject(doc), format_date(doc.get("custom_due_on"))), date=doc.get("custom_due_on"))
    if state == approval.APPEALED and "custom_appeals_authority" in changed:
        people.withdraw(DOCTYPE, doc.name, [before.get("custom_appeals_authority")])
        _let_act([doc.custom_appeals_authority], doc, submit=True)
        _give([doc.custom_appeals_authority], doc, _("Appeal on grievance {0} of {1}: {2}. Due by {3}.").format(
            doc.name, who, _short(doc.get("custom_appeal_grounds")), format_date(doc.get("custom_due_on"))),
            date=doc.get("custom_due_on"))


def _facts(doc):
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    handler, authority = doc.get("custom_assigned_hod"), doc.get("custom_appeals_authority")
    return {
        "user": user, "is_hr": bool(roles & set(approval.HR)), "is_hrm": approval.HRM in roles,
        "raiser": _user_of(doc.get("raised_by")),
        "handler": handler, "handler_roles": frappe.get_roles(handler) if handler else [],
        "authority": authority, "authority_roles": frappe.get_roles(authority) if authority else [],
        "involved": _involved(doc),
        "subject": doc.get("subject"), "description": doc.get("description"),
        "grievance_type": doc.get("grievance_type"), "meeting_notes": doc.get("custom_meeting_notes"),
        "cause": doc.get("cause_of_grievance"), "outcome": doc.get("resolution_detail"),
        "remedy": doc.get("custom_remedy"), "remarks": doc.get("custom_return_remarks"),
        "appeal_grounds": doc.get("custom_appeal_grounds"), "appeal_outcome": doc.get("custom_appeal_outcome"),
    }


def _involved(doc):
    """Who has acted in the grievance: the employee who raised it, whoever
    drew it up, routed it, handled it and resolved it."""
    return [user for user in (_user_of(doc.get("raised_by")), doc.get("owner"), doc.get("custom_reported_to"),
                              doc.get("custom_assigned_hod"), doc.get("resolved_by")) if user]


def _authorities(doc):
    """Who may hear an appeal, in order: the plant's General Manager, the
    HR Manager, the Executive Director."""
    users = []
    for role in approval.AUTHORITIES:
        users += people.people_for(role, doc.get("custom_branch"))
    return list(dict.fromkeys(users))


# ── 2. Who is told ────────────────────────────────────────────────────
def _tell_step(doc, before, old_state, new_state):
    """Whoever has the grievance now is told and given it to do, and it is
    off the list of whoever had it. The employee hears of each turn."""
    hr = _hr(doc)
    raiser = _user_of(doc.get("raised_by"))
    who = doc.get("employee_name") or doc.get("raised_by")
    handler, authority = doc.get("custom_assigned_hod"), doc.get("custom_appeals_authority")
    due = format_date(doc.get("custom_due_on")) if doc.get("custom_due_on") else ""
    if old_state == approval.OPEN:
        people.withdraw(DOCTYPE, doc.name, hr)
    elif old_state == approval.UNDER_REVIEW:
        people.withdraw(DOCTYPE, doc.name, [before.get("custom_assigned_hod")])
    elif old_state == approval.RESOLVED:
        people.withdraw(DOCTYPE, doc.name, [raiser] if raiser else hr)
    elif old_state == approval.APPEALED:
        people.withdraw(DOCTYPE, doc.name, [before.get("custom_appeals_authority")])

    if new_state == approval.OPEN and old_state == approval.UNDER_REVIEW:
        _give(hr, doc, _("Grievance {0} of {1} came back from {2}: {3}").format(
            doc.name, who, _name(before.get("custom_assigned_hod")), _short(doc.get("custom_return_remarks"))))
    elif new_state == approval.OPEN:
        _tell([raiser], doc, _("Your grievance {0} is received. HR will route it to who handles it.").format(
            doc.name))
        _give(hr, doc, _("Grievance {0} from {1}: {2}. Route it to its handler.").format(doc.name, who, _subject(doc)))
    elif new_state == approval.UNDER_REVIEW:
        if old_state == approval.RESOLVED:
            message = _("Grievance {0} of {1} is not resolved: {2}. Due by {3}.").format(
                doc.name, who, _short(doc.get("custom_return_remarks")), due)
        else:
            message = _("Grievance {0} from {1}: {2}. Due by {3}.").format(doc.name, who, _subject(doc), due)
        _let_act([handler], doc)
        _give([handler], doc, message, date=doc.get("custom_due_on"))
        _tell([raiser], doc, _("Your grievance {0} is with {1}. A response is due by {2}.").format(
            doc.name, _name(handler), due))
    elif new_state == approval.RESOLVED:
        _tell([raiser], doc, _("Your grievance {0} is resolved: {1}").format(
            doc.name, _short(doc.get("resolution_detail"))))
        _tell(hr, doc, _("Grievance {0} of {1} is resolved.").format(doc.name, who))
        _give([raiser] if raiser else hr, doc, _("Grievance {0}: accept the outcome, or appeal it.").format(doc.name))
    elif new_state == approval.CLOSED:
        _tell([handler] + hr, doc, _("Grievance {0} of {1} is closed: the outcome is accepted.").format(doc.name, who))
    elif new_state == approval.APPEALED:
        _let_act([authority], doc, submit=True)
        _give([authority], doc, _("Appeal on grievance {0} of {1}: {2}. Due by {3}.").format(
            doc.name, who, _short(doc.get("custom_appeal_grounds")), due), date=doc.get("custom_due_on"))
        _tell(hr, doc, _("{0} appealed grievance {1}. {2} hears it.").format(who, doc.name, _name(authority)))
    elif new_state == approval.APPEAL_DECIDED:
        _tell([raiser, handler] + hr, doc, _("The appeal on grievance {0} is decided: {1}").format(
            doc.name, _short(doc.get("custom_appeal_outcome"))))
    elif new_state == approval.INVALID:
        _tell([raiser], doc, _("Your grievance {0} is not taken up: {1}").format(
            doc.name, _short(doc.get("resolution_detail"))))


def _tell(users, doc, message):
    people.notify(_unique(users), DOCTYPE, doc.name, message)


def _give(users, doc, message, date=None):
    users = _unique(users)
    people.notify(users, DOCTYPE, doc.name, message)
    people.assign(DOCTYPE, doc.name, users, message, date=date)


def _let_act(users, doc, submit=False):
    """Whoever is given the grievance can act on it: Frappe shares an
    assigned document read-only with someone their User Permissions keep
    out, and the handler writes the findings, who hears an appeal files the
    decision."""
    from frappe.share import add_docshare

    for user in _unique(users):
        if not frappe.has_permission(DOCTYPE, "submit" if submit else "write", doc.name, user=user):
            add_docshare(DOCTYPE, doc.name, user, write=1, submit=1 if submit else 0,
                         flags={"ignore_share_permission": True})


# ── 3. The timeline ───────────────────────────────────────────────────
def daily():
    """Case 10: a grievance at risk goes one level up the chain, to the
    head of the employee's department; one past its date goes to HR. Each
    level is told once, and the Overdue box follows the date."""
    day = today()
    rows = frappe.get_all(DOCTYPE, filters={"docstatus": 0, approval.STATE_FIELD: ["in", list(approval.TIMED)],
                                            "custom_due_on": ["is", "set"]},
                          fields=["name", approval.STATE_FIELD, "custom_due_on", "custom_escalation", "custom_overdue",
                                  "custom_assigned_hod", "custom_appeals_authority", "custom_branch",
                                  "custom_department", "raised_by", "employee_name"],
                          limit_page_length=0)
    for row in rows:
        state = row.get(approval.STATE_FIELD)
        level = rules.escalation(row.custom_due_on, day, state)
        changes = {}
        overdue = 1 if rules.overdue(row.custom_due_on, day, state) else 0
        if cint(row.custom_overdue) != overdue:
            changes["custom_overdue"] = overdue
        if rules.escalates(row.custom_escalation, level):
            _escalate(row, state, level)
            changes["custom_escalation"] = level
        if changes:
            frappe.db.set_value(DOCTYPE, row.name, changes, update_modified=False)
    frappe.db.commit()


def _escalate(row, state, level):
    appeal = state == approval.APPEALED
    users = []
    for who in rules.told_at(level, appeal):
        if who == rules.HANDLER:
            users.append(row.custom_appeals_authority if appeal else row.custom_assigned_hod)
        elif who == rules.DEPARTMENT_HEAD:
            users += rules.department_heads(people.holders(approval.HOD), row.custom_branch, row.custom_department)
        elif who == rules.HR:
            users += people.hr_officers(row.custom_branch, row.custom_department)
    what = _("The appeal on grievance {0} of {1}") if appeal else _("Grievance {0} of {1}")
    what = what.format(row.name, row.employee_name or row.raised_by)
    if level == rules.AT_RISK:
        message = _("{0} is due on {1}.").format(what, format_date(row.custom_due_on))
    else:
        message = _("{0} was due on {1} and is not settled.").format(what, format_date(row.custom_due_on))
    people.notify(_unique(users), DOCTYPE, row.name, message)


# ── 4. Helpers ────────────────────────────────────────────────────────
def _hr(doc):
    return people.hr_officers(doc.get("custom_branch"), doc.get("custom_department"))


def _user_of(employee):
    return frappe.db.get_value("Employee", employee, "user_id") if employee else None


def _usual_handler(grievance_type):
    return frappe.db.get_value("Grievance Type", grievance_type, "custom_default_handler") if grievance_type else None


def _timeline_days(grievance_type):
    days = frappe.db.get_value("Grievance Type", grievance_type, "custom_timeline_days") if grievance_type else None
    return cint(days) or rules.DEFAULT_TIMELINE_DAYS


def _name(user):
    return get_fullname(user) if user else ""


def _subject(doc):
    return doc.get("subject") or doc.get("grievance_type") or ""


def _short(text, limit=140):
    text = approval._text(text)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _unique(users):
    return list(dict.fromkeys(user for user in users or () if user))


@frappe.whitelist()
def holders_of(doctype, txt, searchfield, start, page_len, filters):
    """The Handler and Appeal Heard By pickers: the enabled users holding
    one of the roles the form names (filters["roles"])."""
    roles = list((filters or {}).get("roles") or ())
    users = frappe.get_all("Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent",
                           distinct=True) if roles else []
    if not users:
        return []
    like = "%%%s%%" % (txt or "")
    return frappe.get_all("User", filters=[["name", "in", users], ["enabled", "=", 1],
                                           ["name", "not in", ["Administrator", "Guest"]]],
                          or_filters=[["name", "like", like], ["full_name", "like", like]],
                          fields=["name", "full_name"], order_by="full_name asc", as_list=True,
                          start=cint(start), page_length=cint(page_len) or 20)


# ── 5. Wiring ─────────────────────────────────────────────────────────
def setup_on_migrate():
    """after_migrate: the workflow and the permissions it needs
    (workflows.py), and the decision fields at level one for those who
    decide (case 11). Never fails the deploy."""
    from hrms_addon.hrms_addon import security

    workflows.setup_on_migrate(approval, "Employee Grievance workflow")
    savepoint = "hrms_addon_grievance_level_one"
    frappe.db.savepoint(savepoint)
    try:
        # Frappe refuses a level above 0 to a role with nothing at 0, and one
        # refusal would undo every grant
        level_zero = set(frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE, "permlevel": 0}, pluck="role"))
        security.grant({DOCTYPE: {role: ptypes for role, ptypes in approval.LEVEL_ONE.items() if role in level_zero}},
                       permlevel=approval.LEVEL)
        frappe.clear_cache(doctype=DOCTYPE)
        frappe.db.commit()
    except Exception:
        try:
            frappe.db.rollback(save_point=savepoint)
        except Exception:
            pass
        frappe.log_error(title="HRMS Addon: Employee Grievance level one failed")
        print("HRMS Addon: Employee Grievance level one FAILED — see Error Log")
