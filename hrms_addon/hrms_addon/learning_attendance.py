# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance and scheduling on the site; learning_attendance_rules.py has the
rules (scripts/verify_learning_attendance.py).

  Training Venue        the rooms and halls of each plant, with their seats
  Training Event        Frappe HR's session: its venue and seats, the waiting
                        list that moves up as seats come free, and a clash
                        check (trainer, venue, employee) on every save; a row
                        of Training Attendance per participant per day kept
                        with it, and Frappe HR's own Present or Absent kept in
                        step with those rows, which is what the training rules
                        read
  Training Attendance   marked by hand, at the sign-in table (QR code or
                        employee number, page training-sign-in), or by the
                        employee on their phone; confirmed by the supervisor
  register / withdraw   an employee (or their supervisor, or HR) takes a seat
                        or a place on the waiting list, or gives it up
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, today

from hrms_addon.hrms_addon import learning_attendance_rules as rules

DOCTYPE, EVENT, EVENT_EMPLOYEE = "Training Attendance", "Training Event", "Training Event Employee"
VENUE, WAITLIST, TRAINER = "Training Venue", "Training Event Waitlist", "Training Event Trainer"
HR_ROLES = ("HR Manager", "HR User", "System Manager")
ROW_FIELDS = ["name", "training_event", "employee", "session_date", "status", "time_in", "time_out", "hours"]
INSERT_FIELDS = ("name", "creation", "modified", "owner", "modified_by", "docstatus", "training_event",
                 "training_program", "session_date", "day_number", "employee", "employee_name", "branch",
                 "department", "work_section", "supervisor", "status", "method", "marked_by", "marked_on")


def settings():
    from hrms_addon.hrms_addon import learning

    return learning.settings()


def _roles(user=None):
    return set(frappe.get_roles(user or frappe.session.user))


def _is_hr():
    return bool(_roles() & set(HR_ROLES))


# ── The venue ─────────────────────────────────────────────────────────
def venue_validate(doc):
    doc.venue_name = (doc.venue_name or "").strip()
    if cint(doc.get("capacity")) < 0:
        frappe.throw(_("Seats cannot be less than nought."), title=_(VENUE))


# ── The session ───────────────────────────────────────────────────────
def event_validate(doc, method=None):
    """Its venue and seats; the waiting list moved into seats that came free;
    the clash check while it is still to be held."""
    if doc.get("custom_venue"):
        venue = frappe.db.get_value(VENUE, doc.custom_venue, ["venue_name", "capacity"], as_dict=True)
        if venue:
            doc.location = venue.venue_name
            if not cint(doc.get("custom_capacity")) and cint(venue.capacity):
                doc.custom_capacity = cint(venue.capacity)
    elif doc.get("location") and frappe.db.exists(VENUE, doc.location):
        doc.custom_venue = doc.location
    if doc.docstatus == 0 and doc.get("event_status") != "Cancelled":
        _seat_the_waiting(doc)
        _check_clashes(doc)
    left = rules.seats_left(doc.get("custom_capacity"), len([row for row in doc.get("employees") or [] if row.employee]))
    doc.custom_seats_left = left if left is not None else 0


def _seat_the_waiting(doc):
    """Those waiting take the seats that are free, the earliest first."""
    taken = len([row for row in doc.get("employees") or [] if row.employee])
    seats = rules.seats_left(doc.get("custom_capacity"), taken)
    moved = []
    have = {row.employee for row in doc.get("employees") or []}
    for row in rules.next_in([dict(row.as_dict(), _row=row) for row in doc.get("custom_waitlist") or []], seats):
        line = row["_row"]
        if line.employee not in have:
            doc.append("employees", {"employee": line.employee, "employee_name": line.employee_name,
                                     "department": line.department})
            have.add(line.employee)
            moved.append(line.employee)
        line.status, line.moved_in_on = rules.MOVED_IN, now_datetime()
    doc.flags.moved_in = moved


def _check_clashes(doc):
    """Another session at the same time with the same venue or trainer is
    refused (or said, where Learning Settings allow it); an employee booked on
    both is said."""
    if not (doc.get("start_time") and doc.get("end_time")):
        return
    others = frappe.get_all(EVENT, filters={"name": ["!=", doc.name or ""], "docstatus": ["<", 2],
                                            "event_status": ["!=", "Cancelled"],
                                            "start_time": ["<", str(doc.end_time)], "end_time": [">", str(doc.start_time)]},
                            fields=["name", "event_name", "start_time", "end_time", "custom_venue", "location"],
                            limit_page_length=0)
    if not others:
        return
    names = [other.name for other in others]
    mine = {row.employee for row in doc.get("employees") or [] if row.employee}
    trainers, members = {}, {}
    for row in frappe.get_all(TRAINER, filters={"parenttype": EVENT, "parent": ["in", names]},
                              fields=["parent", "employee", "trainer_email", "trainer_name"], limit_page_length=0):
        trainers.setdefault(row.parent, []).append(row)
    if mine:
        for row in frappe.get_all(EVENT_EMPLOYEE, filters={"parenttype": EVENT, "parent": ["in", names],
                                                           "employee": ["in", list(mine)]},
                                  fields=["parent", "employee"], limit_page_length=0):
            members.setdefault(row.parent, set()).add(row.employee)
    session = {"name": doc.name, "start": doc.start_time, "end": doc.end_time,
               "venue": doc.get("custom_venue") or doc.get("location"),
               "trainers": rules.trainer_keys([row.as_dict() for row in doc.get("custom_trainers") or []]),
               "employees": mine}
    found = rules.clashes(session, [{"name": other.name, "start": other.start_time, "end": other.end_time,
                                     "venue": other.custom_venue or other.location,
                                     "trainers": rules.trainer_keys(trainers.get(other.name)),
                                     "employees": members.get(other.name, set())} for other in others])
    hard = []
    if found["venue"]:
        hard.append(_("{0} is booked for {1} at the same time.").format(session["venue"], ", ".join(found["venue"])))
    if found["trainer"]:
        hard.append(_("The trainer is booked for {0} at the same time.").format(", ".join(found["trainer"])))
    if hard:
        if cint(settings().get("block_clashes")):
            frappe.throw("<br>".join(hard), title=_("Clash"))
        frappe.msgprint("<br>".join(hard), title=_("Clash"), indicator="orange")
    if found["employees"]:
        names_of = dict(frappe.get_all("Employee", filters={"name": ["in", list(found["employees"])]},
                                       fields=["name", "employee_name"], as_list=True, limit_page_length=0))
        lines = ["%s: %s" % (names_of.get(employee) or employee, ", ".join(events))
                 for employee, events in sorted(found["employees"].items())[:10]]
        more = len(found["employees"]) - len(lines)
        frappe.msgprint("<br>".join(lines + ([_("And {0} more.").format(more)] if more > 0 else [])),
                        title=_("Booked on Another Session at the Same Time"), indicator="orange")


def event_on_update(doc, method=None):
    """A row of attendance for each participant on each day; Frappe HR's grid
    marks taken into the rows; those moved in from the waiting list told."""
    sync_rows(doc)
    moved = doc.flags.get("moved_in") or []
    if moved:
        _tell_moved_in(doc, moved)
        doc.flags.moved_in = []
    write_summary(doc.name)


def event_on_submit(doc, method=None):
    """Held: a day nobody marked is a no-show."""
    open_rows = frappe.get_all(DOCTYPE, filters={"training_event": doc.name, "status": ["in", list(rules.OPEN)]},
                               pluck="name", limit_page_length=0)
    for start in range(0, len(open_rows), 500):
        frappe.db.set_value(DOCTYPE, {"name": ["in", open_rows[start:start + 500]]},
                            {"status": rules.NO_SHOW, "marked_by": frappe.session.user, "marked_on": now_datetime()},
                            update_modified=False)
    sync_event(doc.name)
    write_summary(doc.name)


def sync_rows(doc):
    """The session's attendance rows as its participants and days now are:
    one for each, those of a participant taken off (or a day no longer in it)
    gone while nobody has marked them, and a mark HR made on Frappe HR's grid
    carried into the days still open."""
    if not doc.get("start_time"):
        return
    days = rules.session_days(doc.start_time, doc.end_time)
    participants = {row.employee: row for row in doc.get("employees") or [] if row.employee}
    existing = frappe.get_all(DOCTYPE, filters={"training_event": doc.name}, fields=ROW_FIELDS, limit_page_length=0)
    stale = [row.name for row in existing if row.status in rules.OPEN
             and (row.employee not in participants or getdate(row.session_date) not in days)]
    for start in range(0, len(stale), 500):
        frappe.db.delete(DOCTYPE, {"name": ["in", stale[start:start + 500]]})
    have = {(row.employee, str(getdate(row.session_date))): row for row in existing if row.name not in stale}
    missing = [(employee, day) for employee in participants for day in days if (employee, str(day)) not in have]
    if missing:
        _insert_rows(doc, missing, participants)
    # a mark on Frappe HR's grid fills the days nobody has marked here
    open_by_employee = {}
    for (employee, _day), row in have.items():
        open_by_employee.setdefault(employee, []).append(row)
    for employee, row in participants.items():
        status = rules.from_event(row.get("attendance"))
        mine = open_by_employee.get(employee, [])
        if status and mine and all(item.status in rules.OPEN for item in mine):
            frappe.db.set_value(DOCTYPE, {"name": ["in", [item.name for item in mine]]},
                                {"status": status, "method": rules.MANUAL, "marked_by": frappe.session.user,
                                 "marked_on": now_datetime()}, update_modified=False)


def _insert_rows(doc, missing, participants):
    """The rows written as they are, many at once: nothing about them is typed."""
    facts = _employee_facts(list({employee for employee, _day in missing}))
    days = rules.session_days(doc.start_time, doc.end_time)
    user, stamp = frappe.session.user, now_datetime()
    values = []
    for employee, day in missing:
        person = facts.get(employee) or {}
        status = rules.from_event(participants[employee].get("attendance")) or rules.INVITED
        values.append((frappe.generate_hash(length=12), stamp, stamp, user, user, 0, doc.name,
                       doc.get("training_program"), day, days.index(day) + 1, employee,
                       person.get("employee_name") or participants[employee].get("employee_name"),
                       person.get("branch"), person.get("department"), person.get("custom_work_section"),
                       person.get("reports_to"), status, rules.MANUAL if status != rules.INVITED else None,
                       user if status != rules.INVITED else None, stamp if status != rules.INVITED else None))
    for start in range(0, len(values), 500):
        frappe.db.bulk_insert(DOCTYPE, fields=list(INSERT_FIELDS), values=values[start:start + 500],
                              ignore_duplicates=True)


def _employee_facts(employees):
    fields = ["name", "employee_name", "branch", "department", "reports_to", "user_id"]
    if frappe.get_meta("Employee").has_field("custom_work_section"):
        fields.append("custom_work_section")
    return {row.name: row for row in frappe.get_all("Employee", filters={"name": ["in", employees or [""]]},
                                                    fields=fields, limit_page_length=0)}


def sync_event(training_event, employees=None):
    """Frappe HR's Present or Absent for each participant, from their days:
    what the training rules and the reports read. Returns who changed."""
    filters = {"training_event": training_event}
    lines_filters = {"parenttype": EVENT, "parent": training_event}
    if employees:
        filters["employee"] = ["in", list(employees)]
        lines_filters["employee"] = ["in", list(employees)]
    days = {}
    for row in frappe.get_all(DOCTYPE, filters=filters, fields=["employee", "status"], limit_page_length=0):
        days.setdefault(row.employee, []).append(row.status)
    changed = []
    for line in frappe.get_all(EVENT_EMPLOYEE, filters=lines_filters, fields=["name", "employee", "attendance"],
                               limit_page_length=0):
        wanted = rules.event_attendance(days.get(line.employee))
        if wanted and wanted != line.attendance:
            frappe.db.set_value(EVENT_EMPLOYEE, line.name, "attendance", wanted, update_modified=False)
            changed.append(line.employee)
    if changed and frappe.db.get_value(EVENT, training_event, "docstatus") == 1:
        # the session was held: what its people have done, and the certificate it gives
        from hrms_addon.hrms_addon import learning

        learning.sync_certificates(training_event)
        learning.refresh_later(changed)
    return changed


def write_summary(training_event):
    """The session's own figures: registered, came, the attendance and no-show
    rates, the seats left."""
    rows = frappe.get_all(DOCTYPE, filters={"training_event": training_event}, fields=["employee", "status", "hours"],
                          limit_page_length=0)
    event = frappe.db.get_value(EVENT, training_event, ["start_time", "end_time", "custom_capacity"], as_dict=True)
    if not event:
        return {}
    count = len(rules.session_days(event.start_time, event.end_time)) or 1
    found = rules.figures([dict(row, days=count) for row in rows])
    left = rules.seats_left(event.custom_capacity, found["invited"])
    frappe.db.set_value(EVENT, training_event, {
        "custom_registered": found["registered"], "custom_attended": found["attended"],
        "custom_attendance_rate": found["attendance_rate"] or 0, "custom_no_show_rate": found["no_show_rate"] or 0,
        "custom_seats_left": left if left is not None else 0}, update_modified=False)
    return found


def _tell_moved_in(doc, employees):
    from hrms_addon.hrms_addon import people

    users = dict(frappe.get_all("Employee", filters={"name": ["in", employees]}, fields=["name", "user_id"],
                                as_list=True, limit_page_length=0))
    when = frappe.utils.format_datetime(doc.start_time) if doc.get("start_time") else ""
    message = _("A seat came free: you are booked for {0} on {1} at {2}.").format(
        doc.get("course") or doc.get("training_program") or doc.name, when, doc.get("location") or "")
    told = [user for user in users.values() if user]
    if told:
        people.notify(told, EVENT, doc.name, message)
    texts = {employee: [message] for employee, user in users.items() if not user}
    if texts:
        from hrms_addon.hrms_addon import learning_loop

        learning_loop.message_employees(texts)


# ── The day's row ─────────────────────────────────────────────────────
def attendance_validate(doc):
    """A day's attendance: the employee's place, a day the session runs, who
    marked it and when, the hours, and the supervisor's confirmation."""
    event = frappe.db.get_value(EVENT, doc.training_event, ["start_time", "end_time", "training_program", "docstatus",
                                                             "event_status"], as_dict=True)
    if not event:
        frappe.throw(_("Pick the session."), title=_(DOCTYPE))
    days = rules.session_days(event.start_time, event.end_time)
    if getdate(doc.session_date) not in days:
        frappe.throw(_("{0} does not run on {1}.").format(doc.training_event, frappe.utils.format_date(doc.session_date)),
                     title=_(DOCTYPE))
    doc.day_number = days.index(getdate(doc.session_date)) + 1
    doc.training_program = event.training_program
    before = doc.get_doc_before_save()
    if doc.is_new() or (before and before.get("employee") != doc.employee):
        person = _employee_facts([doc.employee]).get(doc.employee) or {}
        doc.employee_name = person.get("employee_name")
        doc.branch, doc.department = person.get("branch"), person.get("department")
        doc.work_section, doc.supervisor = person.get("custom_work_section"), person.get("reports_to")
    if doc.status not in rules.STATUSES:
        frappe.throw(_("Status is one of: {0}.").format(", ".join(rules.STATUSES)), title=_(DOCTYPE))
    was = before.get("status") if before else None
    if rules.marked_status(was, doc.status):
        doc.marked_by, doc.marked_on = frappe.session.user, now_datetime()
        doc.method = doc.get("method") or rules.MANUAL
    if doc.get("time_in") and doc.get("time_out"):
        doc.hours = rules.hours_between(doc.time_in, doc.time_out)
    elif doc.status in rules.CAME and not flt(doc.get("hours")):
        doc.hours = rules.day_hours(*rules.day_window(event.start_time, event.end_time, doc.session_date))
    elif doc.status not in rules.CAME:
        doc.hours = 0
    if cint(doc.get("supervisor_confirmed")) != cint(before.get("supervisor_confirmed") if before else 0):
        if not (_is_hr() or _supervisor_user(doc.supervisor) == frappe.session.user):
            frappe.throw(_("Only their supervisor or HR confirm it."), frappe.PermissionError)
        doc.confirmed_by, doc.confirmed_on = (frappe.session.user, now_datetime()) if cint(doc.supervisor_confirmed) \
            else (None, None)


def attendance_on_update(doc):
    sync_event(doc.training_event, [doc.employee])
    write_summary(doc.training_event)


def attendance_on_trash(doc):
    write_summary(doc.training_event)


def _supervisor_user(supervisor):
    return frappe.db.get_value("Employee", supervisor, "user_id") if supervisor else None


# ── Registration ──────────────────────────────────────────────────────
def _who(employee=None):
    """The employee the user acts for: themselves, or anyone for HR, or a
    member of their team for a supervisor."""
    own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    employee = employee or own
    if not employee:
        frappe.throw(_("Pick the employee."), title=_("Registration"))
    if employee != own and not _is_hr():
        boss = frappe.db.get_value("Employee", employee, "reports_to")
        if not boss or _supervisor_user(boss) != frappe.session.user:
            frappe.throw(_("You register yourself or your own team."), frappe.PermissionError)
    return employee


@frappe.whitelist(methods=["POST"])
def register(training_event, employee=None):
    """A seat on the session, or a place on its waiting list when it is full.
    Returns {"status", "seats_left"}."""
    employee = _who(employee)
    event = frappe.get_doc(EVENT, training_event)
    errors = rules.registration_errors(event.as_dict(), today())
    if errors:
        frappe.throw(_(errors[0]), title=_("Registration"))
    if any(row.employee == employee for row in event.get("employees") or []):
        _mark_registered(event.name, employee)
        return {"status": rules.REGISTERED, "seats_left": event.get("custom_seats_left")}
    waiting = [row for row in event.get("custom_waitlist") or [] if row.employee == employee and row.status == rules.WAITING]
    if waiting:
        return {"status": rules.WAITING, "seats_left": 0}
    person = frappe.db.get_value("Employee", employee, ["employee_name", "department", "status"], as_dict=True)
    if not person or person.status != "Active":
        frappe.throw(_("{0} is not an active employee.").format(employee), title=_("Registration"))
    place = rules.admit(event.get("custom_capacity"), len([row for row in event.employees if row.employee]))
    if place == rules.REGISTERED:
        event.append("employees", {"employee": employee, "employee_name": person.employee_name,
                                   "department": person.department})
    else:
        event.append("custom_waitlist", {"employee": employee, "employee_name": person.employee_name,
                                         "department": person.department, "requested_on": now_datetime(),
                                         "requested_by": frappe.session.user, "status": rules.WAITING})
    event.flags.ignore_permissions = True
    event.save()
    if place == rules.REGISTERED:
        _mark_registered(event.name, employee)
    return {"status": place, "seats_left": frappe.db.get_value(EVENT, event.name, "custom_seats_left")}


def _mark_registered(training_event, employee):
    frappe.db.set_value(DOCTYPE, {"training_event": training_event, "employee": employee, "status": rules.INVITED},
                        "status", rules.REGISTERED, update_modified=False)
    write_summary(training_event)


@frappe.whitelist(methods=["POST"])
def withdraw(training_event, employee=None):
    """The seat or the place on the waiting list given up; the first waiting
    takes the seat."""
    employee = _who(employee)
    event = frappe.get_doc(EVENT, training_event)
    if event.docstatus != 0:
        frappe.throw(_("This session is closed."), title=_("Registration"))
    for row in event.get("custom_waitlist") or []:
        if row.employee == employee and row.status == rules.WAITING:
            row.status = rules.WITHDRAWN
    if frappe.get_all(DOCTYPE, filters={"training_event": event.name, "employee": employee,
                                        "status": ["not in", list(rules.OPEN)]}, pluck="name", limit=1):
        frappe.throw(_("Their attendance is marked: it stays."), title=_("Registration"))
    event.set("employees", [row for row in event.employees if row.employee != employee])
    event.flags.ignore_permissions = True
    event.save()
    return {"status": rules.WITHDRAWN, "seats_left": frappe.db.get_value(EVENT, event.name, "custom_seats_left")}


# ── The sign-in table ─────────────────────────────────────────────────
def _may_mark(event):
    """HR, or a trainer of the session."""
    if _is_hr():
        return True
    user = frappe.session.user
    own = frappe.db.get_value("Employee", {"user_id": user}, "name")
    for row in event.get("custom_trainers") or []:
        if (own and row.get("employee") == own) or (row.get("trainer_email") or "").strip().lower() == user.lower():
            return True
    frappe.throw(_("Only HR or the session's trainer take its attendance."), frappe.PermissionError)


def _resolve(code):
    """The employee a code names: their ID, their employee number or their
    clock number."""
    code = rules.code_of(code)
    if not code:
        frappe.throw(_("Scan or type the employee number."), title=_("Sign In"))
    if frappe.db.exists("Employee", code):
        return code
    for field in ("employee_number", "attendance_device_id"):
        found = frappe.db.get_value("Employee", {field: code}, "name")
        if found:
            return found
    frappe.throw(_("No employee {0}.").format(code), title=_("Sign In"))


@frappe.whitelist()
def sessions_today():
    """Today's sessions the user takes attendance for, with how far each is."""
    day = getdate(today())
    events = frappe.get_list(EVENT, filters={"docstatus": ["<", 2], "event_status": ["!=", "Cancelled"],
                                             "start_time": ["<=", str(day) + " 23:59:59"],
                                             "end_time": [">=", str(day) + " 00:00:00"]},
                             fields=["name", "event_name", "training_program", "start_time", "end_time", "location",
                                     "custom_capacity"], order_by="start_time asc", limit_page_length=50)
    if not _is_hr():
        own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        mine = set(frappe.get_all(TRAINER, filters={"parenttype": EVENT, "parent": ["in", [e.name for e in events] or [""]]},
                                  or_filters={"employee": own or "", "trainer_email": frappe.session.user},
                                  pluck="parent", limit_page_length=0))
        events = [event for event in events if event.name in mine]
    for event in events:
        event.update(roll_counts(event.name, day))
    return events


def roll_counts(training_event, day):
    from hrms_addon.hrms_addon import queries

    counts = {row.status: row.n for row in frappe.get_all(
        DOCTYPE, filters={"training_event": training_event, "session_date": str(getdate(day))},
        fields=["status", queries.aggregate("COUNT", "*", "n")], group_by="status", limit_page_length=0)}
    came = sum(counts.get(status, 0) for status in rules.CAME)
    return {"expected": sum(counts.values()), "signed_in": came,
            "late": counts.get(rules.LATE, 0), "not_in": sum(counts.get(status, 0) for status in rules.OPEN)}


@frappe.whitelist()
def roll(training_event, day=None):
    """The day's list at the sign-in table: everyone booked, who is in and when."""
    event = frappe.get_doc(EVENT, training_event)
    event.check_permission("read")
    day = getdate(day or today())
    rows = frappe.get_all(DOCTYPE, filters={"training_event": training_event, "session_date": str(day)},
                          fields=["name", "employee", "employee_name", "department", "status", "time_in", "time_out",
                                  "method", "supervisor_confirmed"], order_by="employee_name asc", limit_page_length=0)
    return {"event": {"name": event.name, "title": event.event_name, "start_time": event.start_time,
                      "end_time": event.end_time, "location": event.location, "docstatus": event.docstatus,
                      "walk_in": cint(event.get("custom_allow_walk_in"))},
            "day": str(day), "rows": rows, "counts": roll_counts(training_event, day)}


@frappe.whitelist(methods=["POST"])
def sign_in(training_event, code, method=None, sign_out=0):
    """One person signed in (or out) at the table: Attended, or Late when they
    come after the start; a walk-in added where the session takes them."""
    event = frappe.get_doc(EVENT, training_event)
    _may_mark(event)
    employee = _resolve(code)
    now = now_datetime()
    day = now.date()
    if day not in rules.session_days(event.start_time, event.end_time):
        frappe.throw(_("This session does not run today."), title=_("Sign In"))
    name = frappe.db.get_value(DOCTYPE, {"training_event": event.name, "employee": employee, "session_date": str(day)},
                               "name")
    if not name:
        if any(row.employee == employee for row in event.employees):
            sync_rows(event)
        elif cint(event.get("custom_allow_walk_in")) and event.docstatus == 0:
            if rules.admit(event.get("custom_capacity"), len(event.employees)) != rules.REGISTERED:
                frappe.throw(_("No seat is left."), title=_("Sign In"))
            person = frappe.db.get_value("Employee", employee, ["employee_name", "department"], as_dict=True)
            event.append("employees", {"employee": employee, "employee_name": person.employee_name,
                                       "department": person.department})
            event.flags.ignore_permissions = True
            event.save()
        else:
            frappe.throw(_("{0} is not booked for this session.").format(
                frappe.db.get_value("Employee", employee, "employee_name") or employee), title=_("Sign In"))
        name = frappe.db.get_value(DOCTYPE, {"training_event": event.name, "employee": employee,
                                             "session_date": str(day)}, "name")
    doc = frappe.get_doc(DOCTYPE, name)
    if cint(sign_out):
        if doc.status not in rules.CAME:
            frappe.throw(_("{0} has not signed in.").format(doc.employee_name), title=_("Sign Out"))
        doc.time_out = now.time().replace(microsecond=0)
    elif doc.status in rules.CAME:
        return _signed(doc, _("Already signed in."))
    else:
        begins, _ends = rules.day_window(event.start_time, event.end_time, day)
        doc.status = rules.LATE if rules.is_late(begins, now, settings().get("late_after_minutes")) else rules.ATTENDED
        doc.time_in = now.time().replace(microsecond=0)
        doc.method = method if method in rules.METHODS else rules.NUMBER
    doc.flags.ignore_permissions = True
    doc.save()
    return _signed(doc)


def _signed(doc, message=None):
    image = frappe.db.get_value("Employee", doc.employee, "image")
    return {"employee": doc.employee, "employee_name": doc.employee_name, "image": image, "status": doc.status,
            "time_in": str(doc.time_in or ""), "time_out": str(doc.time_out or ""), "hours": doc.hours,
            "message": message}


@frappe.whitelist(methods=["POST"])
def self_sign_in(training_event):
    """An employee signs themselves in on their phone, on the day, from a
    little before the session starts until it ends."""
    own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    event = frappe.get_doc(EVENT, training_event)
    if not own or not any(row.employee == own for row in event.employees):
        frappe.throw(_("You are not booked for this session."), title=_("Sign In"))
    now = now_datetime()
    if not rules.own_window(event.start_time, event.end_time, now):
        frappe.throw(_("Sign in on the day, when the session starts."), title=_("Sign In"))
    name = frappe.db.get_value(DOCTYPE, {"training_event": event.name, "employee": own, "session_date": str(now.date())},
                               "name")
    if not name:
        sync_rows(event)
        name = frappe.db.get_value(DOCTYPE, {"training_event": event.name, "employee": own,
                                             "session_date": str(now.date())}, "name")
    doc = frappe.get_doc(DOCTYPE, name)
    if doc.status in rules.CAME:
        return _signed(doc, _("Already signed in."))
    begins, _ends = rules.day_window(event.start_time, event.end_time, now.date())
    doc.status = rules.LATE if rules.is_late(begins, now, settings().get("late_after_minutes")) else rules.ATTENDED
    doc.time_in, doc.method = now.time().replace(microsecond=0), rules.MOBILE
    doc.flags.ignore_permissions = True
    doc.save()
    return _signed(doc)


@frappe.whitelist(methods=["POST"])
def mark_many(training_event, day, rows):
    """Many people's day marked at once (Absent, Excused, No-show, Attended):
    rows [{"employee", "status"}]. Returns how many changed."""
    event = frappe.get_doc(EVENT, training_event)
    _may_mark(event)
    rows = json.loads(rows) if isinstance(rows, str) else (rows or [])
    wanted = {row.get("employee"): row.get("status") for row in rows if row.get("status") in rules.STATUSES}
    found = frappe.get_all(DOCTYPE, filters={"training_event": training_event, "session_date": str(getdate(day)),
                                             "employee": ["in", list(wanted) or [""]]},
                           fields=["name", "employee", "status"], limit_page_length=0)
    by_status = {}
    for row in found:
        if wanted.get(row.employee) and wanted[row.employee] != row.status:
            by_status.setdefault(wanted[row.employee], []).append(row.name)
    for status, names in by_status.items():
        frappe.db.set_value(DOCTYPE, {"name": ["in", names]},
                            {"status": status, "method": rules.MANUAL, "marked_by": frappe.session.user,
                             "marked_on": now_datetime()}, update_modified=False)
    sync_event(training_event, list(wanted))
    write_summary(training_event)
    return sum(len(names) for names in by_status.values())


@frappe.whitelist(methods=["POST"])
def confirm(names):
    """The supervisor confirms their team's days (HR anyone's)."""
    names = json.loads(names) if isinstance(names, str) else (names or [])
    rows = frappe.get_all(DOCTYPE, filters={"name": ["in", names or [""]]}, fields=["name", "supervisor"],
                          limit_page_length=0)
    hr = _is_hr()
    bosses = {}
    if not hr:
        bosses = dict(frappe.get_all("Employee", filters={"name": ["in", list({row.supervisor for row in rows
                                                                               if row.supervisor}) or [""]]},
                                     fields=["name", "user_id"], as_list=True, limit_page_length=0))
    mine = [row.name for row in rows if hr or bosses.get(row.supervisor) == frappe.session.user]
    if mine:
        frappe.db.set_value(DOCTYPE, {"name": ["in", mine]}, {"supervisor_confirmed": 1,
                                                              "confirmed_by": frappe.session.user,
                                                              "confirmed_on": now_datetime()}, update_modified=False)
    return len(mine)


# ── The monthly schedule ──────────────────────────────────────────────
def schedule_validate(doc, method=None):
    """Two lines sharing a venue or a trainer at the same time are said."""
    found = rules.line_clashes([{"course": line.course, "date": line.training_date, "start_time": line.get("start_time"),
                                 "end_time": line.get("end_time"), "venue": line.venue, "trainer": line.trainer}
                                for line in doc.get("lines") or []])
    if found:
        frappe.msgprint("<br>".join(_("{0} and {1} share a {2} at the same time.").format(first, second, _(field))
                                    for first, second, field in found[:10]),
                        title=_("Clash"), indicator="orange")
