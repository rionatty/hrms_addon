# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR calendar: leave and training drawn the way Frappe HR's shift
roster is, the people (or the departments) down the side, the days across,
each day's leave or session a block in its cell.

The HR Calendar page, the Annual Leave Plan and the Monthly Training
Schedule all draw it (public/js/hr_calendar_view.js). One call (month)
fills it; the others add, move, change and remove blocks, each through the
rules and approvals that already stand: planned leave goes straight onto a
plan HR are still drawing up, and on an approved plan it is asked to move
(a Leave Plan Change, for the supervisor and then the head of department);
a session goes onto the month's draft schedule, and a booked one moves
with its people told.

Who sees what follows the leave plan (leave.own_place).
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import calendar_rules as rules, leave, leave_rules, people, training, training_rules
from hrms_addon.hrms_addon import leave_plan_change_approval as change_approval

PLAN, ROW, APPLICATION, CHANGE = "Annual Leave Plan", "Annual Leave Plan Employee", "Leave Application", \
    "Leave Plan Change"
EVENT, EVENT_EMPLOYEE = "Training Event", "Training Event Employee"
SCHEDULE, LINE = "Monthly Training Schedule", "Training Schedule Line"
CALENDAR, ENTRY = "Training Calendar", "Training Calendar Entry"
HR_ROLES = leave.HR_ROLES
# the page's own roles (page/hr_calendar/hr_calendar.json): Training Event
# is HR's to read, and this only shows when and where a session is
OPENS_TO = {"HR User", "HR Manager", "System Manager", "Head of Department", "Supervisor", "Employee"}
# a move asked for and not yet approved, refused or cancelled
WAITING = (change_approval.DRAFT, change_approval.PENDING_SUPERVISOR, change_approval.PENDING_HOD)
PEOPLE_LIMIT = 300
NAMES_SHOWN = 60
NO_DEPARTMENT = ""


@frappe.whitelist()
def month(view="leave", year=None, month=None, branch=None, department=None, everyone=0, plan=None, schedule=None):
    """Everything the calendar shows for one month, in one answer."""
    roles = _roles()
    if not OPENS_TO & roles:
        frappe.throw(_("You may not open the calendar."), frappe.PermissionError)
    plan_doc = schedule_doc = None
    if plan:
        plan_doc = frappe.get_doc(PLAN, plan)
        plan_doc.check_permission("read")
        year = plan_doc.year
    if schedule:
        schedule_doc = frappe.get_doc(SCHEDULE, schedule)
        schedule_doc.check_permission("read")
        year, month = schedule_doc.year, rules.month_number(schedule_doc.month)
    year, number = rules.month_of(year, month, getdate(today()))
    start, end = rules.month_window(year, number)
    view = "training" if view == "training" else "leave"
    out = {"view": view, "year": year, "month": number, "title": rules.month_title(year, number),
           "branch": branch, "department": department, "plan": plan, "schedule": schedule,
           "hr": 1 if HR_ROLES & roles else 0, "everyone": cint(everyone)}
    if not (plan_doc or schedule_doc):
        own = leave.own_place(frappe.session.user)
        if own is not None:
            if not own:
                return dict(out, restricted=1, **_nothing(year, number))
            branch, department = own.branch, own.department
            out.update(branch=branch, department=department, restricted=1)
    if view == "training":
        out.update(_training(year, number, start, end, branch, department, cint(everyone), roles, schedule_doc))
    else:
        out.update(_leave(year, number, start, end, branch, department, cint(everyone), roles, plan_doc))
    return out


def _nothing(year, number):
    return {"days": rules.days(year, number, {}, getdate(today())), "rows": [], "blocks": {}, "cells": {},
            "counts": {"off": {}, "planned": {}}, "most_off": 0, "undated": [], "in_all": 0, "capped": 0}


# ── Leave ─────────────────────────────────────────────────────────────
def _leave(year, number, start, end, branch, department, everyone, roles, plan_doc=None):
    is_hr = bool(HR_ROLES & roles)
    me = _my_employee()
    if plan_doc:
        order = list(dict.fromkeys(row.employee for row in plan_doc.get("employees") or [] if row.employee))
        found = {person.name: person for person in _employees(order)}
        everybody = [found[name] for name in order if name in found]
        plans = {plan_doc.name: _plan_info(plan_doc)}
    else:
        everybody = _people(branch, department)
        plans = _plans(year, drafts=bool(leave.SEES_EVERY_PLAN & roles))
    names = [person.name for person in everybody]
    rows = _planned_rows(names, plans, start, end)
    waiting = _waiting_moves(names)
    moving_rows = {move.plan_row for move in waiting}
    blocks = []
    for row in rows:
        state = plans[row.parent]["state"]
        applied = bool(row.leave_application) and leave._still_applied(row.leave_application)
        mode = rules.leave_move_mode(is_hr, row.employee == me, state, applied, row.name in moving_rows)
        blocks.append({
            "key": "row:" + row.name, "row": row.employee, "from": _iso(row.planned_from), "to": _iso(row.planned_to),
            "kind": rules.PLANNED, "title": _("Planned"), "subtitle": _plan_note(state, row.planned_days),
            "link": [PLAN, row.parent], "plan": row.parent, "plan_row": row.name, "state": state, "move": mode,
            "days": flt(row.planned_days),
            "apply": 1 if state == rules.PLAN_APPROVED and not applied and (is_hr or row.employee == me) else 0,
        })
    for application in _applications(names, start, end):
        blocks.append(application)
    for move in waiting:
        if getdate(move.new_from) <= end and getdate(move.new_to) >= start:
            blocks.append({
                "key": "chg:" + move.name, "row": move.employee, "from": _iso(move.new_from), "to": _iso(move.new_to),
                "kind": rules.MOVING, "title": _("Moving here"), "subtitle": _(move.approval_status or "Draft"),
                "link": [CHANGE, move.name]})
    with_leave = {block["row"] for block in blocks}
    shown = everybody if (plan_doc or everyone) else [person for person in everybody if person.name in with_leave]
    lists = _holiday_lists(shown, start, end)
    holidays = {person.name: lists.get(_holiday_list(person), {}) for person in shown}
    header = rules.common_holidays(list(holidays.values())) if shown else _company_holidays(start, end)
    days = rules.days(year, number, header, getdate(today()))
    on_view = {person.name for person in shown}
    blocks = [block for block in blocks if block["row"] in on_view]
    cells = rules.pick_cells(blocks, holidays, days, one_per_day=True)
    on_plans = _on_plans(list(plans), [person.name for person in shown])
    return {
        "days": days, "blocks": {block["key"]: block for block in blocks}, "cells": cells,
        "rows": [{"key": person.name, "title": person.employee_name or person.name,
                  "subtitle": person.designation or person.department or "",
                  "add": rules.leave_add_mode(is_hr, person.name == me,
                                              (_plan_for(person, plans, on_plans) or {}).get("state"))}
                 for person in shown],
        "counts": rules.off_counts(cells, blocks, days),
        "most_off": cint(plan_doc.get("most_off")) if plan_doc else _most_off(year, branch, department),
        "in_all": len(everybody), "capped": 0 if plan_doc else int(len(everybody) >= PEOPLE_LIMIT), "undated": [],
    }


def _plan_note(state, days):
    if state == rules.PLAN_DRAFT:
        return _("Draft plan")
    if state == rules.PLAN_PENDING:
        return _("Waiting approval")
    return _("{0} day(s)").format("%g" % flt(days))


def _plan_info(doc):
    return frappe._dict(name=doc.name, state=rules.plan_state(doc.docstatus, doc.get("status")),
                        company=doc.get("company"), branch=doc.get("branch"), department=doc.get("department"))


def _plans(year, drafts=True):
    """The year's plans in view: {name: info}; a plan being drawn up only
    for those who see every plan."""
    return {doc.name: _plan_info(doc) for doc in frappe.get_all(
        PLAN, filters={"year": cint(year), "docstatus": ["in", [0, 1] if drafts else [1]]},
        fields=["name", "docstatus", "status", "company", "branch", "department"])}


def _planned_rows(names, plans, start, end):
    if not (names and plans):
        return []
    return frappe.get_all(ROW, filters={"parent": ["in", list(plans)], "parenttype": PLAN, "employee": ["in", names],
                                        "planned_from": ["<=", end], "planned_to": [">=", start]},
                          fields=["name", "parent", "employee", "planned_from", "planned_to", "planned_days",
                                  "leave_application"])


def _waiting_moves(names):
    if not names:
        return []
    return frappe.get_all(CHANGE, filters={"employee": ["in", names], "docstatus": 0,
                                           "approval_status": ["in", list(WAITING)]},
                          fields=["name", "plan_row", "employee", "new_from", "new_to", "approval_status"])


def _on_plans(plans, names):
    """{employee: [plans they have a row on]}."""
    found = {}
    if plans and names:
        for row in frappe.get_all(ROW, filters={"parent": ["in", plans], "parenttype": PLAN, "employee": ["in", names]},
                                  fields=["parent", "employee"]):
            found.setdefault(row.employee, [])
            if row.parent not in found[row.employee]:
                found[row.employee].append(row.parent)
    return found


def _plan_for(person, plans, on_plans):
    """The year's plan a click on this person's row works with: one they are
    on, else the one drawn up for their plant and department; one still
    being drawn up first."""
    mine = [plans[name] for name in on_plans.get(person.name, []) if name in plans]
    if not mine:
        mine = [info for info in plans.values()
                if (info.company or None) in (None, person.get("company"))
                and (info.branch or None) in (None, person.get("branch"))
                and (info.department or None) in (None, person.get("department"))]
    for state in (rules.PLAN_DRAFT, rules.PLAN_PENDING, rules.PLAN_APPROVED):
        for info in mine:
            if info.state == state:
                return info
    return None


def _applications(names, start, end):
    if not names:
        return []
    out = []
    for row in frappe.get_all(APPLICATION,
                              filters={"employee": ["in", names], "docstatus": ["in", [0, 1]],
                                       "from_date": ["<=", end], "to_date": [">=", start]},
                              fields=["name", "employee", "from_date", "to_date", "leave_type", "status", "docstatus"]):
        kind = rules.leave_kind(row.docstatus, row.status)
        if kind:
            out.append({"key": "app:" + row.name, "row": row.employee, "from": _iso(row.from_date),
                        "to": _iso(row.to_date), "kind": kind, "title": row.leave_type,
                        "subtitle": _("Approved") if kind == rules.APPROVED else _("Applied"),
                        "link": [APPLICATION, row.name]})
    return out


def _most_off(year, branch, department):
    """The tightest Most Off at Once of the year's approved plans in view."""
    filters = {"docstatus": 1, "year": cint(year)}
    if branch:
        filters["branch"] = branch
    if department:
        filters["department"] = department
    values = [cint(value) for value in frappe.get_all(PLAN, filters=filters, pluck="most_off") if cint(value)]
    return min(values) if values else 0


@frappe.whitelist(methods=["POST"])
def leave_info(employee, year):
    """What the employee has for the year and has planned, for the dialog."""
    leave._may_act_for(employee)
    entitled, brought = leave._available(employee, cint(year))
    plans = list(_plans(year))
    planned = sum(flt(row.planned_days) for row in frappe.get_all(
        ROW, filters={"parent": ["in", plans or [""]], "parenttype": PLAN, "employee": employee},
        fields=["planned_days"]))
    available = flt(entitled) + flt(brought)
    return {"entitled": flt(entitled), "brought_forward": flt(brought), "available": available,
            "planned": planned, "left": max(available - planned, 0)}


@frappe.whitelist(methods=["POST"])
def save_leave(employee=None, from_date=None, to_date=None, plan_row=None, reason=None, plan=None):
    """New planned leave for the employee (on `plan`, or the year's plan HR are
    drawing up for them, made if there is none), or `plan_row` moved: straight
    on a plan being drawn up, asked for on an approved one. Without `to_date`
    a moved leave keeps its leave days."""
    if not from_date:
        frappe.throw(_("Pick the first day."))
    first = getdate(from_date)
    if plan_row:
        return _move_leave(plan_row, first, getdate(to_date) if to_date else None, reason)
    if not HR_ROLES & _roles():
        frappe.throw(_("Only HR put leave on the plan. Apply for leave instead."), frappe.PermissionError)
    if not (employee and to_date):
        frappe.throw(_("Pick the employee and the last day."))
    last = getdate(to_date)
    person = frappe.db.get_value("Employee", employee, ["name", "company", "branch", "department"], as_dict=True)
    if not person:
        frappe.throw(_("Choose the employee."))
    if plan:
        doc = frappe.get_doc(PLAN, plan)
    else:
        plans = _plans(first.year)
        info = _plan_for(person, plans, _on_plans(list(plans), [employee]))
        if info and info.state == rules.PLAN_APPROVED:
            frappe.throw(_("The {0} plan is approved. Apply for leave, or move the planned leave.").format(first.year))
        if info and info.state == rules.PLAN_PENDING:
            frappe.throw(_("The {0} plan is waiting for approval. It can be changed once it is returned.").format(
                first.year))
        doc = frappe.get_doc(PLAN, info.name) if info else frappe.get_doc({
            "doctype": PLAN, "year": first.year, "company": person.company, "branch": person.branch,
            "department": person.department, "posting_date": today()})
    _drawing_up_or_throw(doc)
    if first.year != cint(doc.year):
        frappe.throw(_("The {0} plan takes days in {0} only.").format(doc.year))
    undated = next((row for row in doc.get("employees") or []
                    if row.employee == employee and not (row.planned_from or row.planned_to)), None)
    if undated:
        undated.planned_from, undated.planned_to = first, last
    else:
        doc.append("employees", {"employee": employee, "planned_from": first, "planned_to": last})
    _check_employee(doc, employee)
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return doc.name


def _move_leave(plan_row, first, last, reason):
    row = frappe.db.get_value(ROW, plan_row, ["name", "parent", "employee", "planned_from", "planned_to",
                                              "planned_days", "leave_application"], as_dict=True)
    if not row:
        frappe.throw(_("Choose the planned leave to move."))
    plan = frappe.db.get_value(PLAN, row.parent, ["docstatus", "status"], as_dict=True)
    state = rules.plan_state(plan.docstatus, plan.status)
    is_hr = bool(HR_ROLES & _roles())
    is_self = row.employee == _my_employee()
    applied = bool(row.leave_application) and leave._still_applied(row.leave_application)
    moving = bool(frappe.get_all(CHANGE, filters={"plan_row": row.name, "docstatus": 0,
                                                  "approval_status": ["in", list(WAITING)]}, limit=1))
    mode = rules.leave_move_mode(is_hr, is_self, state, applied, moving)
    if not mode:
        frappe.throw(_why_not(state, is_hr, is_self, applied, moving), frappe.PermissionError)
    last = last or _keep_days(row, first)
    if mode == rules.MOVE_DIRECT:
        doc = frappe.get_doc(PLAN, row.parent)
        _drawing_up_or_throw(doc)
        target = next(line for line in doc.employees if line.name == row.name)
        target.planned_from, target.planned_to = first, last
        _check_employee(doc, row.employee)
        doc.save()
        return {"plan": doc.name}
    if not (reason or "").strip():
        frappe.throw(_("Say why the leave is moving."))
    name = leave.request_change(row.name, first, last, reason)
    try:
        change = frappe.get_doc(CHANGE, name)
        change.workflow_state = change_approval.PENDING_SUPERVISOR
        change.save()
    except Exception:
        # the request is refused whole: no draft left behind to block the next move
        frappe.delete_doc(CHANGE, name, ignore_permissions=True, force=True)
        raise
    return {"change": name}


def _why_not(state, is_hr, is_self, applied, moving):
    if state == rules.PLAN_PENDING:
        return _("The plan is waiting for approval. Its dates change once it is returned.")
    if state == rules.PLAN_DRAFT:
        return _("Only HR change a plan being drawn up.")
    if applied:
        return _("A leave is already applied for on these dates. Cancel that application first.")
    if moving:
        return _("A move of this leave is already waiting for approval.")
    if not (is_hr or is_self):
        return _("Only the employee or HR can do this.")
    return _("This leave cannot be moved.")


def _keep_days(row, first):
    """The last day of the leave moved to `first`, as many leave days long as
    it was: the holidays on the employee's list passed over, as the Leave
    Application counts them."""
    include = leave.annual_counts_holidays()
    days = flt(row.planned_days) or leave_rules.leave_days(
        row.planned_from, row.planned_to, leave.holidays_between(row.employee, row.planned_from, row.planned_to),
        include)
    if not days:
        return rules.shifted(row.planned_from, row.planned_to, first)[1]
    return leave_rules.end_after(first, days, leave.holidays_between(row.employee, first, add_days(first, 400)),
                                 include)


def _drawing_up_or_throw(doc):
    if rules.plan_state(doc.docstatus, doc.get("status")) != rules.PLAN_DRAFT:
        frappe.throw(_("The plan is no longer being drawn up. Move its leave instead."))
    if not HR_ROLES & _roles():
        frappe.throw(_("Only HR change a plan being drawn up."), frappe.PermissionError)


def _check_employee(doc, employee):
    """The employee's planned leave on the plan, as the plan will check it
    when it is sent: no overlap, within the year, within what they have."""
    leave._fill_plan_rows(doc)
    rows = [row.as_dict() for row in doc.get("employees") or []
            if row.employee == employee and row.planned_from and row.planned_to]
    errors = leave_rules.plan_errors({"year": doc.get("year"), "rows": rows})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(PLAN))


@frappe.whitelist(methods=["POST"])
def remove_leave(plan_row):
    """Planned leave taken off a plan being drawn up."""
    parent = frappe.db.get_value(ROW, plan_row, "parent")
    if not parent:
        frappe.throw(_("Choose the planned leave."))
    doc = frappe.get_doc(PLAN, parent)
    _drawing_up_or_throw(doc)
    doc.set("employees", [row for row in doc.employees if row.name != plan_row])
    doc.save()
    return doc.name


@frappe.whitelist(methods=["POST"])
def apply_leave(employee, from_date, to_date, leave_type=None):
    """A Leave Application for the days picked, for the employee to check and
    send; planned leave with these very dates is applied for from the plan."""
    leave._may_act_for(employee)
    leave_type = leave_type or leave_rules.ANNUAL
    first, last = getdate(from_date), getdate(to_date)
    if last < first:
        frappe.throw(_("The leave ends before it starts."))
    if leave_type == leave_rules.ANNUAL:
        approved = frappe.get_all(PLAN, filters={"docstatus": 1, "year": first.year}, pluck="name")
        same = frappe.get_all(ROW, filters={"parent": ["in", approved or [""]], "parenttype": PLAN,
                                            "employee": employee, "planned_from": first, "planned_to": last},
                              pluck="name", limit=1)
        if same:
            return leave.apply_from_plan(same[0])
    doc = frappe.get_doc({"doctype": APPLICATION, "employee": employee, "leave_type": leave_type,
                          "from_date": first, "to_date": last,
                          "company": frappe.db.get_value("Employee", employee, "company")})
    doc.insert()
    return doc.name


# ── Training ──────────────────────────────────────────────────────────
def _training(year, number, start, end, branch, department, everyone, roles, schedule_doc=None):
    is_hr = bool(HR_ROLES & roles)
    header = _company_holidays(start, end)
    days = rules.days(year, number, header, getdate(today()))
    if schedule_doc:
        draft = schedule_doc.docstatus == 0
        blocks = [_line_block(line, schedule_doc.name, is_hr and draft) for line in schedule_doc.get("lines") or []
                  if line.training_date and not line.get("training_event")]
        booked = [line.training_event for line in schedule_doc.get("lines") or [] if line.get("training_event")]
        blocks += _events(start, end, None, None, is_hr, only=booked) if booked else []
    else:
        blocks = _events(start, end, branch, department, is_hr) + _draft_lines(start, end, branch, department, is_hr)
    blocks = [block for block in blocks if block["from"] and block["to"]]
    keys = {block["row"] for block in blocks}
    if everyone:
        keys |= set(_departments(department))
    if schedule_doc:
        keys |= {line.department or NO_DEPARTMENT for line in schedule_doc.get("lines") or []}
    if is_hr and not keys:
        keys = {department or NO_DEPARTMENT}
    order = sorted(keys, key=lambda key: (key == NO_DEPARTMENT, key))
    count = {}
    for block in blocks:
        count[block["row"]] = count.get(block["row"], 0) + 1
    cells = rules.pick_cells(blocks, {key: header for key in order}, days, one_per_day=False)
    return {
        "days": days, "blocks": {block["key"]: block for block in blocks}, "cells": cells,
        "rows": [{"key": key, "title": key or _("All departments"),
                  "subtitle": _("{0} session(s)").format(count.get(key, 0)),
                  "add": "session" if is_hr and (not schedule_doc or schedule_doc.docstatus == 0) else None}
                 for key in order],
        "counts": {"off": {}, "planned": {}}, "most_off": 0, "in_all": len(order), "capped": 0,
        "undated": _undated(year, number) if is_hr and (not schedule_doc or schedule_doc.docstatus == 0) else [],
    }


def _events(start, end, branch, department, is_hr, only=None):
    """The Training Events in the month, each a block on the days it runs."""
    filters = {"docstatus": ["in", [0, 1]], "event_status": ["!=", "Cancelled"],
               "start_time": ["<", add_days(end, 1)], "end_time": [">=", start]}
    if only:
        filters["name"] = ["in", only]
    events = frappe.get_all(EVENT, filters=filters,
                            fields=["name", "event_name", "course", "event_status", "location", "trainer_name",
                                    "start_time", "end_time", "docstatus", "custom_branch", "custom_department"])
    if not events:
        return []
    rows = frappe.get_all(EVENT_EMPLOYEE, filters={"parent": ["in", [event.name for event in events]],
                                                   "parenttype": EVENT},
                          fields=["parent", "employee", "employee_name", "department"])
    places = {row.name: row for row in frappe.get_all(
        "Employee", filters={"name": ["in", [row.employee for row in rows] or [""]]},
        fields=["name", "branch", "department"])}
    by_event = {}
    for row in rows:
        by_event.setdefault(row.parent, []).append(row)
    out = []
    for event in events:
        status = rules.session_status(event.event_status, event.docstatus)
        if not status:
            continue
        mine = by_event.get(event.name, [])
        where = {(places.get(row.employee) or {}).get("department") or row.department for row in mine} - {None, ""}
        plants = {(places.get(row.employee) or {}).get("branch") for row in mine} - {None, ""}
        home = event.get("custom_department") or (list(where)[0] if len(where) == 1 else NO_DEPARTMENT)
        if department and home != department and department not in where:
            continue
        if branch and event.get("custom_branch") != branch and branch not in plants:
            continue
        out.append({
            "key": "evt:" + event.name, "row": home, "from": _iso(event.start_time), "to": _iso(event.end_time),
            "kind": status, "title": event.course or event.event_name, "start": rules.clock(event.start_time),
            "subtitle": _hours(event.start_time, event.end_time), "link": [EVENT, event.name],
            "venue": event.location, "trainer": event.trainer_name, "people": len(mine),
            "names": [row.employee_name or row.employee for row in mine][:NAMES_SHOWN],
            "move": 1 if is_hr and event.docstatus == 0 and status == rules.SCHEDULED else 0})
    return out


def _draft_lines(start, end, branch, department, is_hr):
    """Sessions on a schedule still being drawn up: dated, not yet booked."""
    drafts = [doc.name for doc in frappe.get_all(SCHEDULE, filters={"docstatus": 0}, fields=["name", "branch"])
              if not branch or not doc.branch or doc.branch == branch]
    if not drafts:
        return []
    filters = {"parent": ["in", drafts], "parenttype": SCHEDULE,
               "training_date": ["between", [start, end]], "training_event": ["is", "not set"]}
    if department:
        filters["department"] = department
    return [_line_block(line, line.parent, is_hr) for line in frappe.get_all(
        LINE, filters=filters, fields=["name", "parent", "course", "training_date", "start_time", "end_time", "venue",
                                       "trainer", "target_group", "department", "calendar_entry"])]


def _line_block(line, schedule, can_change):
    starts = rules.clock(line.get("start_time")) or rules.clock(training_rules.SESSION_STARTS)
    ends = rules.clock(line.get("end_time")) or rules.clock(training_rules.SESSION_ENDS)
    return {
        "key": "line:" + line.name, "row": line.get("department") or NO_DEPARTMENT, "from": _iso(line.training_date),
        "to": _iso(line.training_date), "kind": rules.PLANNED_SESSION, "title": line.course, "start": starts,
        "subtitle": "%s - %s" % (starts, ends), "link": [SCHEDULE, schedule], "schedule": schedule,
        "venue": line.get("venue"), "trainer": line.get("trainer"), "target": line.get("target_group"),
        "department": line.get("department"), "start_time": starts, "end_time": ends, "people": 0, "names": [],
        "move": 1 if can_change else 0}


def _undated(year, number):
    """What the training calendar plans for the month with no date yet: HR
    drag it onto a day."""
    rows = frappe.get_all(ENTRY, filters={"parenttype": CALENDAR, "planned_year": cint(year),
                                          "planned_month": rules.MONTHS[number - 1], "scheduled": ["!=", 1]},
                          fields=["name", "parent", "course", "trainer", "target_group", "section"])
    if not rows:
        return []
    live = set(frappe.get_all(CALENDAR, filters={"name": ["in", [row.parent for row in rows]],
                                                  "docstatus": ["in", [0, 1]]}, pluck="name"))
    placed = set(frappe.get_all(LINE, filters={"calendar_entry": ["in", [row.name for row in rows]],
                                               "parenttype": SCHEDULE}, pluck="calendar_entry"))
    return [{"key": "ent:" + row.name, "entry": row.name, "course": row.course, "trainer": row.trainer,
             "target": row.target_group, "section": row.section, "link": [CALENDAR, row.parent]}
            for row in rows if row.parent in live and row.name not in placed]


def _departments(department=None):
    if department:
        return [department]
    return frappe.get_all("Department", filters={"is_group": 0}, pluck="name", order_by="name asc",
                          limit_page_length=PEOPLE_LIMIT)


def _hours(starts, ends):
    return "%s - %s" % (rules.clock(starts), rules.clock(ends))


def _hr_only():
    if not HR_ROLES & _roles():
        frappe.throw(_("Only HR change the training schedule."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def save_session(date=None, course=None, department=None, start_time=None, end_time=None, venue=None,
                 trainer=None, target_group=None, calendar_entry=None, line=None, schedule=None, branch=None):
    """A session put on the month's draft schedule (on `schedule`, else the
    month's draft for the plant, made if there is none), or `line` changed."""
    _hr_only()
    if not date:
        frappe.throw(_("Pick the day."))
    day = getdate(date)
    entry = frappe.db.get_value(ENTRY, calendar_entry, ["parent", "course", "trainer", "target_group",
                                                        "training_program"], as_dict=True) if calendar_entry else None
    values = {"course": course or (entry.course if entry else None), "training_date": day,
              "department": department or None, "start_time": start_time or None, "end_time": end_time or None,
              "venue": venue or None, "trainer": trainer or (entry.trainer if entry else None),
              "target_group": target_group or (entry.target_group if entry else None)}
    if entry:
        values.update(calendar_entry=calendar_entry, training_program=entry.training_program)
    if not values["course"]:
        frappe.throw(_("Say which course."))
    if line:
        doc = _schedule_of(line)
        _session_day_or_throw(doc, day)
        next(row for row in doc.lines if row.name == line).update(values)
    else:
        doc = frappe.get_doc(SCHEDULE, schedule) if schedule else _draft_schedule_for(day, branch)
        _draft_schedule_or_throw(doc)
        _session_day_or_throw(doc, day)
        doc.append("lines", values)
        if entry and not doc.get("training_calendar"):
            doc.training_calendar = entry.parent
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return doc.name


def _schedule_of(line):
    parent = frappe.db.get_value(LINE, line, "parent")
    if not parent:
        frappe.throw(_("Choose the session."))
    doc = frappe.get_doc(SCHEDULE, parent)
    _draft_schedule_or_throw(doc)
    return doc


def _draft_schedule_or_throw(doc):
    if doc.docstatus != 0:
        frappe.throw(_("{0} is submitted and its trainings booked. Move a training on the calendar instead.").format(
            doc.get("title") or doc.name))


def _session_day_or_throw(doc, day):
    if not rules.in_month(day, doc.year, rules.month_number(doc.month)):
        frappe.throw(_("{0} {1}'s schedule takes days in that month only.").format(doc.month, doc.year))


def _draft_schedule_for(day, branch=None):
    """The month's schedule being drawn up for the plant, else a new one."""
    month_name = rules.MONTHS[day.month - 1]
    base = {"docstatus": 0, "month": month_name, "year": day.year}
    found = frappe.get_all(SCHEDULE, filters=dict(base, branch=branch or ["is", "not set"]), pluck="name",
                           order_by="creation asc", limit=1)
    if not found and not branch:
        found = frappe.get_all(SCHEDULE, filters=base, pluck="name", order_by="creation asc", limit=1)
    if found:
        return frappe.get_doc(SCHEDULE, found[0])
    return frappe.get_doc({"doctype": SCHEDULE, "month": month_name, "year": day.year, "branch": branch or None,
                           "company": _default_company(), "prepared_by": frappe.session.user})


@frappe.whitelist(methods=["POST"])
def move_session(key, date, department=None):
    """A session dragged to another day: a line on a draft schedule (to another
    department's row too), or a booked training not yet held, its people told."""
    _hr_only()
    kind, _sep, name = str(key or "").partition(":")
    day = getdate(date)
    if kind == "line":
        doc = _schedule_of(name)
        _session_day_or_throw(doc, day)
        target = next(row for row in doc.lines if row.name == name)
        target.training_date = day
        if department is not None:
            target.department = department or None
        doc.save()
        return doc.name
    if kind == "evt":
        event = frappe.get_doc(EVENT, name)
        if rules.session_status(event.event_status, event.docstatus) != rules.SCHEDULED or event.docstatus != 0:
            frappe.throw(_("Only a training still to be held and not yet submitted is moved here. Open it to change it."))
        event.start_time, event.end_time = rules.shifted_session(event.start_time, event.end_time, day)
        event.save()
        booked = frappe.db.get_value(LINE, {"training_event": name}, "name")
        if booked:
            frappe.db.set_value(LINE, booked, "training_date", day, update_modified=False)
        _tell_moved(event)
        return event.name
    frappe.throw(_("Choose the session to move."))


def _tell_moved(event):
    when = "%s, %s at %s" % (event.course or event.event_name, frappe.utils.format_date(event.start_time),
                             frappe.utils.format_time(event.start_time))
    message = _("Training moved: {0} at {1}.").format(when, event.location or "")
    trainees = [user for user in frappe.get_all("Employee", filters={
        "name": ["in", [row.employee for row in event.get("employees") or []] or [""]]}, pluck="user_id") if user]
    people.notify(trainees, EVENT, event.name, message)
    training._tell_trainer(event, message)


@frappe.whitelist(methods=["POST"])
def remove_session(line):
    """A session taken off a draft schedule; a schedule left empty goes too."""
    _hr_only()
    doc = _schedule_of(line)
    rest = [row for row in doc.lines if row.name != line]
    if not rest:
        frappe.delete_doc(SCHEDULE, doc.name)
        return None
    doc.set("lines", rest)
    doc.save()
    return doc.name


# ── The people, their holidays ────────────────────────────────────────
def _roles():
    return set(frappe.get_roles())


def _my_employee():
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _people(branch, department):
    filters = {"status": "Active"}
    if branch:
        filters["branch"] = branch
    if department:
        filters["department"] = department
    return frappe.get_all("Employee", filters=filters,
                          fields=["name", "employee_name", "department", "designation", "holiday_list", "company",
                                  "branch"],
                          order_by="employee_name asc", limit_page_length=PEOPLE_LIMIT)


def _employees(names):
    if not names:
        return []
    return frappe.get_all("Employee", filters={"name": ["in", names]},
                          fields=["name", "employee_name", "department", "designation", "holiday_list", "company",
                                  "branch"])


def _holiday_list(person):
    return person.get("holiday_list") or _company_holiday_list(person.get("company"))


def _company_holiday_list(company=None):
    if company:
        return frappe.db.get_value("Company", company, "default_holiday_list")
    first = frappe.get_all("Company", fields=["default_holiday_list"], order_by="creation asc", limit_page_length=1)
    return first[0].default_holiday_list if first else None


def _holiday_lists(people_rows, start, end):
    """{holiday list: {date: description}} for the lists these people are on."""
    wanted = {name for name in (_holiday_list(person) for person in people_rows) if name}
    return {name: _list_holidays(name, start, end) for name in wanted}


def _list_holidays(name, start, end):
    return {getdate(row.holiday_date).isoformat():
            row.description or (_("Weekly off") if row.weekly_off else _("Holiday"))
            for row in frappe.get_all("Holiday", filters={"parent": name, "parenttype": "Holiday List",
                                                          "holiday_date": ["between", [start, end]]},
                                      fields=["holiday_date", "description", "weekly_off"])}


def _company_holidays(start, end):
    name = _company_holiday_list()
    return _list_holidays(name, start, end) if name else {}


def _default_company():
    company = frappe.defaults.get_user_default("Company")
    if company:
        return company
    first = frappe.get_all("Company", pluck="name", order_by="creation asc", limit_page_length=1)
    return first[0] if first else None


def _iso(value):
    return getdate(value).isoformat() if value else None
