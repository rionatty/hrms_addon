# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The two exits on the site: voluntary (4.5) and involuntary (4.6).

The rules are in exit_rules.py, without a Frappe import
(scripts/verify_exits.py). This reads and writes the site.

Frappe HR ships the Employee Separation and the Exit Interview, so both
exits are carried on them: the separation is the umbrella that knows which
chart is being followed and how far it has got, and the interview carries
the three signatures of 4.5 step 4. The Clearance Form (LPL/HR/22) is the
one document they do not have, and it is signed by different people on
each chart (clearance_approval.py).

  separation_*  the exit itself: the notice the Act asks for, whether it
                was served, and the letter an involuntary exit carries.
  interview_*   the exit interview through Supervisor, HOD and HR Officer.
  clearance_*   the ten boxes, the tools of work they pull in, and the
                chain each exit signs them through.
  daily         a notice period running out, and an exit waiting on its
                clearance.
  reinstate     the minutes' §6.2: an employee who left by mistake is
                brought back by the Executive Director, and only by them.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import exit_rules as rules, pay, people

SEPARATION = "Employee Separation"
INTERVIEW = "Exit Interview"
CLEARANCE = "Clearance Form"


# ── 1. The separation ─────────────────────────────────────────────────
def separation_validate(doc, method=None):
    if not doc.get("custom_exit_type"):
        doc.custom_exit_type = rules.VOLUNTARY
    _fill_notice(doc)
    _link_children(doc)
    errors = rules.separation_errors(_facts(doc))
    if errors and doc.docstatus == 1:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Employee Separation"))


def _fill_notice(doc):
    """The notice the Act asks for at this length of service, and whether
    it was served — which is what the settlement deducts for."""
    joined = doc.get("custom_date_of_joining")
    leaving = doc.get("custom_relieving_date")
    served = rules.months_served(joined, leaving or today())
    doc.custom_notice_days = rules.notice_days(served)
    if doc.get("custom_exit_type") == rules.VOLUNTARY:
        given = doc.get("custom_notice_given")
        answer = rules.notice_served(given, leaving, doc.custom_notice_days)
    else:
        # the company gives the notice on an involuntary exit, so nothing
        # is short on the employee's side
        answer = {"served": True, "short": 0}
    doc.custom_notice_served = 1 if answer["served"] else 0
    doc.custom_notice_short_days = answer["short"]


def _facts(doc):
    return {
        "exit_type": doc.get("custom_exit_type"), "reason": doc.get("custom_reason"),
        "notice_given": doc.get("custom_notice_given"),
        "relieving_date": doc.get("custom_relieving_date"),
        "date_of_joining": doc.get("custom_date_of_joining"),
        "termination_date": doc.get("custom_termination_date"),
        "letter_signed_on": doc.get("custom_letter_signed_on"),
    }


def _link_children(doc):
    """What the exit has reached: the interview, the clearance and the
    settlement, each found by its own link back."""
    if not doc.name:
        return
    for field, doctype in (("custom_exit_interview", INTERVIEW), ("custom_clearance", CLEARANCE),
                           ("custom_settlement", "Full and Final Statement")):
        if doc.get(field):
            continue
        found = frappe.get_all(doctype, filters={"custom_separation" if doctype != CLEARANCE
                                                 else "separation": doc.name, "docstatus": ["<", 2]},
                               pluck="name", limit=1)
        if found:
            doc.set(field, found[0])


def separation_on_submit(doc, method=None):
    """Step 7 of 4.6: the employee's status is updated and the Payroll
    Officer told to prepare the final pay."""
    _make_inactive(doc)
    users = people.people_for("Payroll Officer", doc.get("custom_branch"), doc.get("department"))
    users += people.hr_officers(doc.get("custom_branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                      _("{0} leaves on {1}. Prepare the final salary and the terminal benefits.").format(
                          doc.get("employee_name") or doc.employee,
                          frappe.utils.format_date(doc.get("custom_relieving_date"))))


def _make_inactive(doc):
    """Step 2 of the cessation chart: the system makes the employee
    inactive and takes them off the payroll."""
    if not doc.get("employee") or not doc.get("custom_relieving_date"):
        return
    if getdate(doc.custom_relieving_date) > getdate(today()):
        return  # still serving: this runs again from the daily job
    employee = frappe.get_doc("Employee", doc.employee)
    if employee.status == "Left":
        doc.custom_status_updated = 1
        return
    employee.status = "Left"
    employee.relieving_date = doc.custom_relieving_date
    employee.reason_for_leaving = doc.get("custom_reason")
    employee.flags.ignore_permissions = True
    employee.flags.ignore_mandatory = True
    employee.save()
    doc.custom_status_updated = 1


def separation_on_cancel(doc, method=None):
    doc.custom_status_updated = 0


# ── 2. The exit interview ─────────────────────────────────────────────
def interview_validate(doc, method=None):
    from hrms_addon.hrms_addon import exit_interview_approval as approval

    _check_interview_step(doc)
    doc.custom_exit_status = doc.get("workflow_state") or doc.get("custom_exit_status") or approval.DRAFT


def _check_interview_step(doc):
    from hrms_addon.hrms_addon import exit_interview_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("custom_return_remarks"),
            "interview_summary": doc.get("interview_summary"),
            **{field: doc.get(field) for field, _who in approval.REMARK_FIELDS.values()},
        })
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Exit Interview"))
        if new_state != approval.DRAFT:
            doc.custom_return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.get("custom_branch"),
                                  doc.get("department"))
        message = _("Exit interview for {0}.").format(doc.get("employee_name") or doc.employee)
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)


def interview_on_submit(doc, method=None):
    """Step 5 follows: the employee serves the notice period, and the HR
    Officer is told to call them for the handover at the end of it."""
    if doc.get("custom_separation"):
        frappe.db.set_value(SEPARATION, doc.custom_separation, "custom_exit_interview", doc.name,
                            update_modified=False)


def interview_on_cancel(doc, method=None):
    doc.custom_exit_status = "Cancelled"


# ── 3. The Clearance Form (LPL/HR/22) ─────────────────────────────────
def clearance_validate(doc, method=None):
    from hrms_addon.hrms_addon import clearance_approval as approval

    _fill_clearance(doc)
    _check_clearance_step(doc)
    doc.approval_status = doc.get("workflow_state") or doc.get("approval_status") or approval.DRAFT


def _fill_clearance(doc):
    if doc.get("date_of_joining") and doc.get("leaving_date"):
        doc.days_worked = rules.days_worked(doc.date_of_joining, doc.leaving_date)
    for row in doc.get("items") or []:
        row.section_name = rules.SECTION_NAMES.get(row.section)
        if row.get("returned") and row.get("not_applicable"):
            row.not_applicable = 0
    # a box an item was added to has a line to be signed on
    have = {row.section for row in doc.get("sections") or []}
    for code in rules.used_sections([row.as_dict() for row in doc.get("items") or []]):
        if code not in have:
            doc.append("sections", {"section": code})
    for row in doc.get("sections") or []:
        row.section_name = rules.SECTION_NAMES.get(row.section)
    for field, value in _progress(doc).items():
        doc.set(field, value)


def _progress(doc):
    """What the form says of itself: the cost of what is not returned, the
    boxes done and whether that is all of them."""
    items = [row.as_dict() for row in doc.get("items") or []]
    signatures = [row.as_dict() for row in doc.get("sections") or []]
    return {"outstanding_cost": rules.outstanding_cost(items),
            "boxes_cleared": ", ".join(rules.cleared_sections(items, signatures)) or None,
            "complete": 1 if rules.clearance_complete(items, signatures) else 0}


def _check_clearance_step(doc):
    from hrms_addon.hrms_addon import clearance_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        items = [row.as_dict() for row in doc.get("items") or []]
        signatures = [row.as_dict() for row in doc.get("sections") or []]
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"), "exit_type": doc.get("exit_type"),
            "unsigned": [rules.box_label(code) for code in rules.unsigned_sections(items, signatures)],
        })
        leaving_draft = new_state and new_state != approval.DRAFT and old_state in (None, approval.DRAFT)
        if leaving_draft or approval.hr_approves(doc.get("exit_type"), old_state, new_state):
            # the employee accounts for every item before sending the form
            # up, and it is still so when HR pass it on
            errors = rules.clearance_errors({"rows": items}) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Clearance Form"))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        users = people.people_for(approval.ROLE_WAITING[new_state], doc.get("branch"),
                                  doc.get("department"))
        message = _("Clearance for {0} ({1} exit).").format(
            doc.get("employee_name") or doc.employee, (doc.get("exit_type") or "").lower())
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message)


def clearance_on_submit(doc, method=None):
    """Step 9: the cessation of employment follows."""
    if doc.get("separation"):
        frappe.db.set_value(SEPARATION, doc.separation, "custom_clearance", doc.name,
                            update_modified=False)
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    users += people.people_for("Accounts User", doc.get("branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                      _("{0} is cleared. Draw up the full and final settlement.").format(
                          doc.get("employee_name") or doc.employee))


def clearance_on_cancel(doc, method=None):
    # on_cancel runs after the document is written, so this is written here
    doc.db_set("approval_status", "Cancelled", update_modified=False)


# ── 3a. The ten boxes, signed ─────────────────────────────────────────
def _box_roles(code):
    """Who signs a box: its own roles, and the Responsible Role of the Tool
    Provider it stands for (IT, Stores, EHS, HR, the department)."""
    roles = list(rules.BOX_ROLES.get(code, ()))
    provider = rules.BOX_PROVIDERS.get(code)
    if provider:
        role = frappe.db.get_value("Tool Provider", provider, "responsible_role")
        if role and role not in roles:
            roles.append(role)
    return tuple(roles)


def _own_form(doc):
    """Whether the user is the employee this form clears."""
    return bool(doc.get("employee")) and frappe.db.get_value(
        "Employee", doc.employee, "user_id") == frappe.session.user


def _box_facts(doc, code):
    from hrms_addon.hrms_addon import clearance_approval as approval

    items = [row.as_dict() for row in doc.get("items") or []]
    row = next((row for row in doc.get("sections") or [] if row.section == code), None)
    return {
        "section": code, "docstatus": doc.docstatus, "roles": frappe.get_roles(), "box_roles": _box_roles(code),
        "own_form": _own_form(doc), "signed": bool(row and row.get("signed_by")),
        "is_signer": bool(row and row.get("signed_by") == frappe.session.user),
        "in_use": code in rules.used_sections(items), "waiting": rules.unaccounted(items).get(code) or [],
        "open": approval.open_for_signing(doc.get("exit_type"), doc.get("workflow_state")),
    }


@frappe.whitelist()
def clearance_boxes(name):
    """Where each box stands, and what this user may do with it."""
    doc = frappe.get_doc(CLEARANCE, name)
    doc.check_permission("read")
    items = [row.as_dict() for row in doc.get("items") or []]
    signed = {row.section: row for row in doc.get("sections") or [] if row.get("signed_by")}
    boxes = []
    for code in rules.used_sections(items):
        facts = _box_facts(doc, code)
        row = signed.get(code)
        boxes.append({
            "section": code, "label": rules.box_label(code), "waiting": facts["waiting"],
            "signed_by": frappe.utils.get_fullname(row.signed_by) if row else None,
            "signed_on": row.signed_on if row else None,
            "can_sign": not rules.sign_errors(facts), "can_unsign": not rules.unsign_errors(facts),
        })
    return boxes


@frappe.whitelist(methods=["POST"])
def sign_boxes(name, sections, remarks=None):
    """A department signs its box, or HR sign it on the department's behalf
    from the signed paper. Returns the boxes signed."""
    doc = frappe.get_doc(CLEARANCE, name)
    doc.check_permission("read")
    wanted = _codes(sections)
    errors = [message for code in wanted for message in rules.sign_errors(_box_facts(doc, code))]
    if not wanted:
        errors.append("Choose the boxes to sign.")
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Clearance Form"))
    for row in doc.get("sections") or []:
        if row.section in wanted:
            values = {"signed_by": frappe.session.user, "signed_on": today()}
            if (remarks or "").strip():
                values["remarks"] = remarks.strip()
            row.db_set(values, update_modified=False)
    _store_progress(doc)
    return wanted


@frappe.whitelist(methods=["POST"])
def unsign_box(name, section):
    """A signature put on the wrong box, taken off before HR approve."""
    doc = frappe.get_doc(CLEARANCE, name)
    doc.check_permission("read")
    errors = rules.unsign_errors(_box_facts(doc, section))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Clearance Form"))
    for row in doc.get("sections") or []:
        if row.section == section:
            row.db_set({"signed_by": None, "signed_on": None}, update_modified=False)
    _store_progress(doc)
    return section


def _codes(sections):
    """The boxes a call names: a list, or the JSON of one as the desk posts it."""
    import json

    if isinstance(sections, str):
        sections = json.loads(sections) if sections.strip().startswith("[") else [sections]
    return [code for code in dict.fromkeys(sections or []) if code]


def _store_progress(doc):
    doc.db_set(_progress(doc), update_modified=False)


@frappe.whitelist(methods=["POST"])
def draw_up_clearance(separation):
    """The ten boxes LPL/HR/22 prints, with the employee's own tools of
    work already on them (step 6: the handover), and, for the holder of a
    critical role, who the work is handed over to (their succession plan)."""
    from hrms_addon.hrms_addon import talent, talent_rules

    exit_doc = frappe.get_doc(SEPARATION, separation)
    exit_doc.check_permission("read")
    if exit_doc.get("custom_clearance"):
        return exit_doc.custom_clearance
    form = frappe.new_doc(CLEARANCE)
    form.update({
        "employee": exit_doc.employee, "company": exit_doc.company, "separation": separation,
        "exit_type": exit_doc.get("custom_exit_type") or rules.VOLUNTARY,
        "leaving_date": exit_doc.get("custom_relieving_date"),
        "notice_date": exit_doc.get("custom_notice_given"),
        "leave_balance": _leave_balance(exit_doc.employee, exit_doc.get("custom_relieving_date")),
        "salary": pay.monthly_gross(exit_doc.employee),
    })
    handover = talent.handover_for(exit_doc.employee)
    for row in rules.default_rows(form.exit_type):
        if handover and row["section"] == "A" and row["item"] == talent_rules.HANDOVER_ITEM:
            row = dict(row, remarks=handover, drawn_remarks=handover)
        form.append("items", row)
    for tool in _tools(exit_doc.employee):
        issued = _issued(tool)
        form.append("items", {"section": "A", "section_name": rules.SECTION_NAMES["A"],
                              "item": tool.tool, "returned": 0, "tool": tool.tool,
                              "remarks": issued, "drawn_remarks": issued})
    for code, name, _items in rules.SECTIONS:
        form.append("sections", {"section": code, "section_name": name})
    form.flags.ignore_permissions = True
    form.flags.ignore_mandatory = True
    form.insert()
    frappe.db.set_value(SEPARATION, separation, "custom_clearance", form.name, update_modified=False)
    return form.name


def _tools(employee):
    """The tools of work still out with the employee. They are rows on the
    Employee itself (custom_employee_tools), issued at onboarding, and one
    with a returned date has already come back."""
    return frappe.get_all("Employee Tool",
                          filters={"parent": employee, "parenttype": "Employee",
                                   "parentfield": "custom_employee_tools",
                                   "returned_on": ["is", "not set"]},
                          fields=["name", "tool", "brand", "serial_no", "number_plate"], limit=100)


def _issued(tool):
    """What identifies the tool issued: its brand, serial number and plate.
    The form is drawn up with it as the row's remark, which is why that
    remark does not say the tool is accounted for (rules.accounted)."""
    return ", ".join(part for part in (tool.get("brand"), tool.get("serial_no"),
                                       tool.get("number_plate")) if part) or None


def _leave_balance(employee, on=None):
    """The Annual Leave the employee can still take on their last day: what
    the days worked have earned, less what is taken. It is the figure the
    settlement pays out, so no other leave type and no earlier year is in
    it."""
    from hrms_addon.hrms_addon import leave_accrual, leave_rules

    on = getdate(on or today())
    found = leave_accrual.accrual(employee, leave_rules.ANNUAL, on)
    if found:
        return max(flt(found.available), 0.0)
    # leave given at the start of the year, not earned by the days worked
    return max(flt(leave_accrual._hrms_figures(employee, leave_rules.ANNUAL, on).balance), 0.0)


# ── 4. The watching ───────────────────────────────────────────────────
def daily():
    _close_notice_periods()
    _chase_clearance()
    _remind_notice()


def _close_notice_periods():
    """An employee whose last day has come is made inactive and taken off
    the payroll, whether or not anyone remembered to submit the exit."""
    rows = frappe.get_all(SEPARATION,
                          filters={"docstatus": 1, "custom_status_updated": ["!=", 1],
                                   "custom_relieving_date": ["<=", today()]},
                          fields=["name"], limit=200)
    for row in rows:
        doc = frappe.get_doc(SEPARATION, row.name)
        _make_inactive(doc)
        doc.db_set("custom_status_updated", doc.get("custom_status_updated") or 0)
    frappe.db.commit()


def _chase_clearance():
    """An exit whose notice has run out with no clearance form drawn up."""
    rows = frappe.get_all(SEPARATION,
                          filters={"docstatus": 1, "custom_clearance": ["is", "not set"],
                                   "custom_relieving_date": ["<=", add_days(today(), 7)]},
                          fields=["name", "employee", "employee_name", "custom_branch", "department",
                                  "custom_relieving_date"], limit=200)
    for row in rows:
        users = people.hr_officers(row.custom_branch, row.department)
        if not users:
            continue
        people.assign(SEPARATION, row.name, users,
                      _("{0} leaves on {1} and has no clearance form. Draw up LPL/HR/22.").format(
                          row.employee_name or row.employee,
                          frappe.utils.format_date(row.custom_relieving_date)),
                      date=row.custom_relieving_date)
    frappe.db.commit()


# ── 4a. Serving notice ────────────────────────────────────────────────
NOTICE_FIELDS = ["name", "docstatus", "employee", "employee_name", "company", "department", "designation",
                 "custom_branch", "custom_exit_type", "custom_reason", "custom_notice_given", "custom_notice_days",
                 "custom_relieving_date", "custom_notice_short_days", "custom_exit_interview", "custom_clearance",
                 "custom_settlement", "custom_notice_reminders", "custom_notice_told"]


@frappe.whitelist()
def notice_for(employee, notice_given=None, last_day=None):
    """The notice an employee owes and where it stands today, for the
    separation's form: the days required, the last day they run to from
    the day the letter was given, and the days served and left."""
    frappe.has_permission("Employee", "read", employee, throw=True)
    joined = frappe.db.get_value("Employee", employee, "date_of_joining")
    suggested = rules.suggested_last_day(joined, notice_given) if notice_given else None
    until = last_day or suggested
    return dict(rules.notice_progress(notice_given, until, today()),
                required_days=rules.notice_days(rules.months_served(joined, until or today())),
                suggested_last_day=suggested)


def exit_steps(rows):
    """{separation: (interview status, clearance status, settlement status,
    the steps still to do)} for separations read with NOTICE_FIELDS."""
    from hrms_addon.hrms_addon import clearance_approval, exit_interview_approval, settlement_approval

    def statuses(doctype, field, status_field):
        names = [row.get(field) for row in rows if row.get(field)]
        if not names:
            return {}
        return dict(frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", status_field],
                                   as_list=True, limit_page_length=0))

    interviews = statuses(INTERVIEW, "custom_exit_interview", "custom_exit_status")
    clearances = statuses(CLEARANCE, "custom_clearance", "approval_status")
    settlements_ = statuses("Full and Final Statement", "custom_settlement", "custom_settlement_status")
    out = {}
    for row in rows:
        interview = interviews.get(row.get("custom_exit_interview"))
        clearance = clearances.get(row.get("custom_clearance"))
        settlement = settlements_.get(row.get("custom_settlement"))
        steps = rules.outstanding_steps({
            "exit_type": row.get("custom_exit_type"), "submitted": row.get("docstatus") == 1,
            "interview_done": interview == exit_interview_approval.APPROVED,
            "clearance_done": clearance == clearance_approval.CLEARED,
            "settlement_done": settlement == settlement_approval.SCHEDULED})
        out[row.get("name")] = (interview, clearance, settlement, steps)
    return out


def _remind_notice(day=None):
    """The people an exit touches are reminded as its last day comes: HR at
    every point, the supervisor and head of department for the handover,
    the employee for their tools and clearance, payroll for the final pay
    (rules.REMINDERS). Each point is sent once; an exit entered late gets
    one reminder for the points it has already passed.

    Until the separation is submitted only HR are reminded: a draft may be
    a dismissal nobody has been told of. What HR were sent and what the
    others were sent are remembered apart, so the others get their one
    reminder for the points passed once the exit is submitted
    (rules.reminder_plan)."""
    from hrms_addon.hrms_addon import contract_rules

    day = getdate(day or today())
    rows = frappe.get_all(SEPARATION,
                          filters={"docstatus": ["<", 2],
                                   "custom_relieving_date": ["between", [day, add_days(day, max(rules.REMINDER_DAYS))]]},
                          fields=NOTICE_FIELDS, limit_page_length=0)
    steps = exit_steps(rows) if rows else {}
    points = list(rules.REMINDER_DAYS)
    for row in rows:
        plan = rules.reminder_plan({
            "hr_due": contract_rules.alerts_due(row.custom_relieving_date, day, points, row.custom_notice_reminders),
            "others_due": contract_rules.alerts_due(row.custom_relieving_date, day, points, row.custom_notice_told),
            "submitted": row.docstatus == 1, "reason": row.custom_reason})
        if not (plan["hr_sent"] or plan["others_sent"]):
            continue
        facts = {"employee_name": row.employee_name or row.employee,
                 "last_day": frappe.utils.format_date(row.custom_relieving_date),
                 "days_left": (getdate(row.custom_relieving_date) - day).days, "steps": steps[row.name][3]}
        told = set()
        for who in plan["audience"]:
            users = [user for user in _notice_people(who, row) if user not in told]
            if not users:
                continue
            template, values = rules.reminder_text(who, facts)
            doctype, name = _notice_document(who, row)
            people.notify(users, doctype, name, _(template).format(*values))
            told.update(users)
        frappe.db.set_value(SEPARATION, row.name, {
            "custom_notice_reminders": contract_rules.record_alerts(row.custom_notice_reminders, plan["hr_sent"]),
            "custom_notice_told": contract_rules.record_alerts(row.custom_notice_told, plan["others_sent"]),
        }, update_modified=False)
    frappe.db.commit()


def _notice_document(who, row):
    """What a reminder opens. Only HR can read an Employee Separation, so
    the others are sent to a record they can: the employee to their own
    Clearance Form once it is drawn up, everybody else to the Employee."""
    if who == rules.HR:
        return SEPARATION, row.name
    if who == rules.EMPLOYEE and row.get("custom_clearance"):
        return CLEARANCE, row.custom_clearance
    return "Employee", row.employee


def _notice_people(who, row):
    """The users a reminder goes to."""
    if who == rules.HR:
        return people.hr_officers(row.custom_branch, row.department)
    if who == rules.PAYROLL:
        return people.people_for("Payroll Officer", row.custom_branch, row.department)
    if who == rules.EMPLOYEE:
        user = frappe.db.get_value("Employee", row.employee, "user_id")
        return [user] if user else []
    boss = frappe.db.get_value("Employee", row.employee, "reports_to")
    users = [frappe.db.get_value("Employee", boss, "user_id")] if boss else []
    users += people.people_for("Head of Department", row.custom_branch, row.department)
    return [user for user in dict.fromkeys(users) if user]


# ── 5. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the interview's three signatures and the clearance's
    two chains."""
    from hrms_addon.hrms_addon import clearance_approval, exit_interview_approval, workflows

    workflows.setup_on_migrate(exit_interview_approval, "Exit Interview workflow")
    workflows.setup_on_migrate(clearance_approval, "Clearance Form workflow")


# ── Reinstatement (minutes §6.2) ──────────────────────────────────────
def employee_validate(doc, method=None):
    """Nobody moves an employee who has left back to active by editing the
    record: the Executive Director reinstates them, with a reason."""
    if doc.is_new() or frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate \
            or frappe.session.user == "Administrator":
        return
    before = doc.get_doc_before_save()
    errors = rules.status_change_errors(before.get("status") if before else None, doc.get("status"),
                                        reinstating=bool(doc.flags.get("reinstating")))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Reinstatement"))


@frappe.whitelist(methods=["POST"])
def reinstate(employee, reason):
    """The Executive Director brings back an employee who left by mistake:
    active again, the leaving date cleared, their login back, the exit
    that put them out never applied again, and HR and payroll told."""
    doc = frappe.get_doc("Employee", employee)
    errors = rules.reinstatement_errors({"status": doc.status, "roles": frappe.get_roles(), "reason": reason})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Reinstatement"))
    left_on = doc.get("relieving_date")
    # Frappe refuses an active employee whose login is disabled
    if doc.get("user_id") and not frappe.db.get_value("User", doc.user_id, "enabled"):
        frappe.db.set_value("User", doc.user_id, "enabled", 1)
    doc.status = "Active"
    doc.relieving_date = None
    doc.reason_for_leaving = None
    doc.flags.reinstating = True
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.save()
    doc.add_comment("Info", _("Reinstated by {0}, Executive Director: {1}").format(frappe.session.user, reason))
    exits_found = frappe.get_all(SEPARATION, filters={"employee": employee, "docstatus": 1}, pluck="name")
    for name in exits_found:
        # the daily job makes an employee inactive from a separation it has
        # not applied yet: this one is not to be applied again
        frappe.db.set_value(SEPARATION, name, "custom_status_updated", 1, update_modified=False)
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    users += people.people_for("Payroll Officer", doc.get("branch"), doc.get("department"))
    if users:
        people.notify(list(dict.fromkeys(users)), "Employee", employee,
                      _("{0} was reinstated by the Executive Director: {1}. They had been marked as leaving on "
                        "{2}.{3}").format(
                          doc.get("employee_name") or employee, reason, frappe.utils.format_date(left_on),
                          (" " + _("Cancel the exit raised by mistake: {0}.").format(", ".join(exits_found)))
                          if exits_found else ""))
    return doc.status
