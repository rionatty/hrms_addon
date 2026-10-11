# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A leave followed through (leave_follow_rules.py): the glue.

  1  the desk        who is asked to act on a leave today: an approver on
                     leave is stood in for by whoever relieves them, where
                     they may sign; a desk with nobody at it goes to the
                     level above. A leave that waits is reminded of, then
                     taken a level up (chase_approvals, daily).
  2  the cover       who else of the department is off in the same days,
                     said on the form and to whoever approves; who takes
                     over the work, told when the leave is approved.
  3  after approval  end_early (the employee came back, or was recalled):
                     the leave is cancelled and one for the days taken is
                     approved in its place, with its signatures, so Frappe
                     HR's own ledger gives the rest back. extend: a leave
                     of its own for the further days, approved as any is.
                     watch_returns (daily): the clock says who is back,
                     and who is not is counted as overdue.

leave.py calls in here from the Leave Application's own events, so the
form has one set of doc events.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from hrms_addon.hrms_addon import leave_follow_rules as rules, leave_rules, people

APPLICATION = "Leave Application"
SETTINGS = "Leave Management Settings"
# who may sign the workflow's own step for it (leave_approval.APPROVE_CHANGE)
HR_ROLES = ("HR User", "HR Manager")
WORKED = ("Present", "Half Day", "Work From Home")


def settings():
    """Leave Management Settings, as far as following a leave goes."""
    stored = {}
    if frappe.db.exists("DocType", SETTINGS):
        stored = dict(frappe.db.get_singles_dict(SETTINGS) or {})
    return frappe._dict(rules.settings_from(stored))


def settings_errors(doc):
    return rules.settings_errors(rules.settings_from({key: doc.get(key) for key in rules.DEFAULTS}))


def _only_hr():
    if not set(frappe.get_roles()) & set(HR_ROLES):
        frappe.throw(_("Only HR change a leave after it is approved."), frappe.PermissionError)


# ── 1. The desk ───────────────────────────────────────────────────────
def away_today(users, day=None):
    """{user: {"until", "stand_in"}} for those of the users on approved
    leave today: until when, and the login of whoever relieves them."""
    day = getdate(day or today())
    out = {}
    for user in users or []:
        employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
        if not employee:
            continue
        leave = frappe.get_all(APPLICATION, filters={"employee": employee, "docstatus": 1, "status": "Approved",
                                                     "from_date": ["<=", day], "to_date": [">=", day]},
                               fields=["to_date", "custom_reliever"], order_by="to_date desc", limit=1)
        if not leave:
            continue
        reliever = leave[0].get("custom_reliever")
        out[user] = {"until": leave[0].to_date,
                     "stand_in": frappe.db.get_value("Employee", reliever, "user_id") if reliever else None}
    return out


def desk(doc, state):
    """Who is asked to act on a leave at this desk today
    (rules.at_the_desk), and who of its people are away. A stand-in is
    given the access to sign: Frappe shares an assigned document read-only
    with somebody their User Permissions keep out."""
    from hrms_addon.hrms_addon import leave_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("custom_branch"), doc.get("department"))
    away = away_today(users)
    signing = {step["allowed"] for step in approval.TRANSITIONS
               if step["state"] == state and step["action"] == approval.APPROVE}
    stand_ins = {row["stand_in"] for row in away.values() if row.get("stand_in")}
    stand_ins_away = away_today(stand_ins - set(users))
    able = {user for user in stand_ins if signing & set(frappe.get_roles(user))}
    found = rules.at_the_desk(users, dict(stand_ins_away, **away), able)
    _let_sign(found["standing_in"], doc)
    return found, away


def _let_sign(users, doc):
    from frappe.share import add_docshare

    for user in users or ():
        if not frappe.has_permission(APPLICATION, "submit", doc.name, user=user):
            add_docshare(APPLICATION, doc.name, user, write=1, submit=1, flags={"ignore_share_permission": True})


def level_above(doc, state):
    """Who hears of a leave its desk has not moved, or has nobody at."""
    from hrms_addon.hrms_addon import leave_approval as approval

    role = rules.LEVEL_ABOVE.get(approval.ROLE_WAITING[state])
    if not role:
        return []
    if role == people.HR_OFFICER:
        return list(people.hr_officers(doc.get("custom_branch"), doc.get("department")))
    return list(people.people_for(role, doc.get("custom_branch"), doc.get("department")))


def _who_is_away(away):
    return ", ".join(_("{0} (on leave until {1})").format(
        frappe.db.get_value("User", user, "full_name") or user, frappe.utils.format_date(row["until"]))
        for user, row in sorted(away.items()))


def arrived(doc, state):
    """The leave has reached a desk: the day is kept, for how long it waits
    there, and the desk is told. Called as the step is saved."""
    from hrms_addon.hrms_addon import leave_approval as approval

    doc.custom_at_desk_since = today()
    doc.custom_chased = None
    found, away = desk(doc, state)
    message = _("Leave application from {0}: {1} to {2}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.format_date(doc.get("from_date")),
        frappe.utils.format_date(doc.get("to_date")))
    if doc.get("custom_cover"):
        message += " " + _("Others off the same days: {0}").format(doc.custom_cover.replace("\n", " "))
    own = [user for user in found["ask"] if user not in found["standing_in"]]
    if own:
        people.notify(own, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, own, message, date=doc.get("from_date"))
    for stand_in, who in found["standing_in"].items():
        theirs = message + " " + _("You stand in for {0}, who is on leave until {1}.").format(
            frappe.db.get_value("User", who, "full_name") or who, frappe.utils.format_date(away[who]["until"]))
        people.notify([stand_in], doc.doctype, doc.name, theirs)
        people.assign(doc.doctype, doc.name, [stand_in], theirs, date=doc.get("from_date"))
    if found["empty"]:
        # nobody is at the desk, and nobody stands in who may sign
        above = level_above(doc, state)
        theirs = message + " " + _("Nobody is at the {0}'s desk to sign it: {1}.").format(
            _(approval.REMARK_FIELDS[state][1]), _who_is_away(away) or _("no one holds the role for this department"))
        people.notify(above, doc.doctype, doc.name, theirs)
        people.assign(doc.doctype, doc.name, above, theirs, date=doc.get("from_date"))


def left_the_desk(doc):
    doc.custom_at_desk_since = None
    doc.custom_chased = None


def chase_approvals():
    """Daily: a leave still on its desk after the days in Leave Management
    Settings. First the desk is reminded (whoever is at it today, a
    stand-in included); then the level above is told. Each is said once.
    Returns [(leave, what was done)]."""
    from hrms_addon.hrms_addon import leave_approval as approval

    kept = settings()
    if not (kept.remind_after_days or kept.escalate_after_days):
        return []
    done = []
    for row in frappe.get_all(
            APPLICATION, limit_page_length=0,
            filters={"docstatus": 0, "workflow_state": ["in", list(approval.PENDING_STATES)]},
            fields=["name", "workflow_state", "custom_at_desk_since", "custom_chased", "modified", "from_date"]):
        # one that reached its desk before the day was kept is counted from when it last moved
        since = row.custom_at_desk_since or getdate(row.modified)
        due = rules.chase(since, today(), row.custom_chased, kept.remind_after_days, kept.escalate_after_days)
        if not due:
            continue
        doc = frappe.get_doc(APPLICATION, row.name)
        state = row.workflow_state
        found, _away = desk(doc, state)
        above = level_above(doc, state)
        users = list(dict.fromkeys(found["ask"] + above)) if due == rules.ESCALATED or found["empty"] \
            else found["ask"]
        message = _("{0}'s leave, {1} to {2}, has waited {3} day(s) for the {4}.").format(
            doc.get("employee_name") or doc.employee, frappe.utils.format_date(doc.from_date),
            frappe.utils.format_date(doc.to_date), rules.days_waiting(since, today()),
            _(approval.REMARK_FIELDS[state][1]))
        people.notify(users, APPLICATION, row.name, message)
        people.assign(APPLICATION, row.name, users, message, date=row.from_date)
        frappe.db.set_value(APPLICATION, row.name, {"custom_chased": due, "custom_at_desk_since": since},
                            update_modified=False)
        done.append((row.name, due))
    frappe.db.commit()
    return done


# ── 2. The cover ──────────────────────────────────────────────────────
def most_off(doc, kept=None):
    """The most of one department that may be off at once: Leave
    Management Settings', else the approved Annual Leave Plan's own for
    the year the leave starts in (its plant's, where the plan has one)."""
    kept = kept or settings()
    if kept.most_off:
        return cint(kept.most_off)
    if not doc.get("from_date"):
        return 0
    year, branch = str(getdate(doc.from_date).year), doc.get("custom_branch")
    for plan in frappe.get_all("Annual Leave Plan", filters={"docstatus": 1},
                               fields=["year", "branch", "most_off"], order_by="modified desc", limit_page_length=0):
        if str(plan.year) == year and cint(plan.most_off) and (not plan.branch or not branch or plan.branch == branch):
            return cint(plan.most_off)
    return 0


def others_off(doc):
    """Who else of the department is off in the days of this leave: leave
    approved, and leave on a desk waiting to be."""
    from hrms_addon.hrms_addon import leave_approval as approval

    if not (doc.get("department") and doc.get("from_date") and doc.get("to_date")):
        return []
    rows = frappe.get_all(
        APPLICATION, limit_page_length=0,
        filters={"department": doc.department, "docstatus": ["<", 2],
                 "custom_leave_status": ["in", list(approval.PENDING_STATES) + [approval.APPROVED]],
                 "from_date": ["<=", doc.to_date], "to_date": [">=", doc.from_date]},
        fields=["name", "employee", "employee_name", "department", "from_date", "to_date", "custom_branch"])
    branch = doc.get("custom_branch")
    return [row for row in rows if row.name != doc.name and row.employee != doc.employee
            and (not branch or not row.custom_branch or row.custom_branch == branch)]


def check_cover(doc, kept=None):
    """The form's Others Off the Same Days: where this leave takes its
    department over the limit, and with whom. Returns the clashes."""
    limit = most_off(doc, kept)
    doc.custom_cover = None
    if not limit or not (doc.get("department") and doc.get("from_date") and doc.get("to_date")):
        return []
    first, last = getdate(doc.from_date), getdate(doc.to_date)
    rows = [{"employee": doc.employee, "employee_name": doc.get("employee_name") or doc.employee,
             "department": doc.department, "planned_from": first, "planned_to": last}]
    for row in others_off(doc):
        # only the days they share with this leave
        rows.append({"employee": row.employee, "employee_name": row.employee_name or row.employee,
                     "department": row.department, "planned_from": max(getdate(row.from_date), first),
                     "planned_to": min(getdate(row.to_date), last)})
    found = leave_rules.clashes(rows, limit)
    doc.custom_cover = "\n".join(leave_rules.clash_lines(found, limit)) or None
    return found


def sending_errors(doc):
    """What stops a leave being sent for approval, of its cover: a reliever
    who cannot relieve, and (where Luuka have said so) planned leave that
    leaves the department short. Otherwise the shortage is said, to the
    applicant now and to each approver on the form."""
    kept = settings()
    found = check_cover(doc, kept)
    errors = []
    reliever = doc.get("custom_reliever")
    theirs = frappe.db.get_value("Employee", reliever, ["employee_name", "status"], as_dict=True) if reliever else None
    errors += rules.reliever_errors({
        "employee": doc.employee, "reliever": reliever,
        "reliever_name": theirs.employee_name if theirs else None,
        "reliever_status": theirs.status if theirs else None,
        "reliever_away": bool(reliever) and _on_leave_between(reliever, doc.from_date, doc.to_date, doc.name),
        "days": doc.get("total_leave_days"), "needed_from": kept.reliever_from_days})
    if rules.cover_refused(doc.get("leave_type"), found, kept.cover_blocks):
        errors.append("Too many of the department are off in those days: %s" % doc.custom_cover.replace("\n", " "))
    elif found:
        frappe.msgprint(doc.custom_cover.replace("\n", "<br>"), title=_("Others Off the Same Days"),
                        indicator="orange")
    return errors


def _on_leave_between(employee, start, end, but=None):
    from hrms_addon.hrms_addon import leave_approval as approval

    rows = frappe.get_all(APPLICATION, filters={
        "employee": employee, "docstatus": ["<", 2],
        "custom_leave_status": ["in", list(approval.PENDING_STATES) + [approval.APPROVED]],
        "from_date": ["<=", end], "to_date": [">=", start]}, pluck="name")
    return bool([name for name in rows if name != but])


def tell_reliever(doc):
    """Approved: whoever takes over the work is told, with the handover."""
    reliever = doc.get("custom_reliever")
    user = frappe.db.get_value("Employee", reliever, "user_id") if reliever else None
    if not user:
        return
    message = _("You take over {0}'s work from {1} to {2}.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.format_date(doc.from_date),
        frappe.utils.format_date(doc.to_date))
    people.notify([user], APPLICATION, doc.name, message,
                  message + ("<br><br>" + frappe.utils.escape_html(doc.custom_handover).replace("\n", "<br>")
                             if doc.get("custom_handover") else ""))


# ── 3. After approval ─────────────────────────────────────────────────
# what an ended leave keeps of the one first approved: its place on the
# plan, its advance, who relieves, and Parts 2 and 3 as they were signed
CARRIED = ("custom_plan", "custom_plan_row", "custom_leave_advance", "custom_advance", "custom_advance_amount",
           "custom_accounts_by", "custom_accounts_on", "custom_salary_requested_in_advance",
           "custom_medical_certificate", "custom_reliever", "custom_handover", "custom_off_duty_request",
           "custom_extends")
SIGNED = ("custom_hro_by", "custom_hro_on", "custom_supervisor_remarks", "custom_hod_remarks", "custom_hr_remarks")
# the records that point at a leave, and stay when it is ended early
POINTING = (("Leave Advance", "leave_application"), ("Off Duty Request", "leave_application"),
            (APPLICATION, "custom_extends"))


@frappe.whitelist(methods=["POST"])
def end_early(name, last_day, kind, reason):
    """The employee came back before the leave ran out, or was recalled.
    The leave is cancelled and one for the days taken is approved in its
    place, signed as the first was: Frappe HR's ledger then gives back the
    days not taken, and its attendance frees them for the clock. Nothing
    is approved again by hand. Returns the leave that stands."""
    from frappe.model.workflow import apply_workflow

    from hrms_addon.hrms_addon import leave_approval as approval

    _only_hr()
    doc = frappe.get_doc(APPLICATION, name)
    errors = rules.end_early_errors({"docstatus": doc.docstatus, "status": doc.get("status"),
                                     "from_date": doc.from_date, "to_date": doc.to_date, "last_day": last_day,
                                     "kind": kind, "reason": reason})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(APPLICATION))
    first_back, last_back = rules.given_back(doc.to_date, last_day)
    standing = frappe.copy_doc(doc)
    standing.update({field: doc.get(field) for field in CARRIED})
    standing.update({
        "amended_from": doc.name, "to_date": getdate(last_day), "workflow_state": None, "status": "Open",
        "custom_leave_status": None, "follow_via_email": 0, "custom_change_kind": kind,
        "custom_change_reason": reason, "custom_first_approved_to": doc.get("custom_first_approved_to") or doc.to_date,
        "custom_reported_back": 1, "custom_reported_back_on": first_back, "custom_overstay_days": 0,
        "custom_at_desk_since": None, "custom_chased": None,
        # Part 2 is worked out again on the days now taken
        "custom_balance_before": None, "custom_balance_after": None,
    })
    if standing.get("half_day_date") and getdate(standing.half_day_date) > getdate(last_day):
        standing.update({"half_day": 0, "half_day_date": None})
    doc.flags.ignore_permissions = True
    # its advance, the form that gave it and a leave that extends it stay,
    # and are pointed at the leave that stands
    doc.flags.ignore_links = True
    doc.cancel()
    standing.flags.ignore_permissions = True
    standing.insert()
    standing = apply_workflow(standing, approval.APPROVE_CHANGE)
    _free_for_the_clock(doc.employee, first_back, last_back)
    for doctype, field in POINTING:
        for record in frappe.get_all(doctype, filters={field: doc.name, "docstatus": ["<", 2]}, pluck="name"):
            frappe.db.set_value(doctype, record, field, standing.name, update_modified=False)
    employee = frappe.db.get_value("Employee", doc.employee, ["user_id", "reports_to"], as_dict=True) or frappe._dict()
    users = [employee.user_id, frappe.db.get_value("Employee", employee.reports_to, "user_id")
             if employee.reports_to else None]
    users += list(people.hr_officers(doc.get("custom_branch"), doc.get("department")))
    people.notify(list(dict.fromkeys(user for user in users if user)), APPLICATION, standing.name, _(
        "{0}'s leave now ends on {1} ({2}). {3} to {4} go back to the leave balance.").format(
        doc.get("employee_name") or doc.employee, frappe.utils.format_date(last_day), _(kind).lower(),
        frappe.utils.format_date(first_back), frappe.utils.format_date(last_back)))
    return standing.name


def signed_as(doc):
    """Part 2 and Part 3 of an ended leave, as the leave first approved was
    signed: nobody signs again for days already agreed. Called as the
    leave that stands is approved (leave._check_application_step)."""
    from hrms_addon.hrms_addon import leave_approval as approval

    first = frappe.db.get_value(APPLICATION, doc.amended_from, list(approval.ALL_STAMP_FIELDS) + list(SIGNED),
                                as_dict=True) or {}
    for field in list(approval.ALL_STAMP_FIELDS) + list(SIGNED):
        doc.set(field, first.get(field))


def _free_for_the_clock(employee, first, last):
    """The days given back are no longer leave. A punch made on one of them
    was set aside when it met the leave on the attendance (Frappe HR skips
    it); it is put back, for Frappe HR to mark the day from on its next
    run."""
    for name in frappe.get_all("Employee Checkin", filters={
            "employee": employee, "skip_auto_attendance": 1, "attendance": ["is", "not set"],
            "time": ["between", [first, add_days(last, 1)]]}, pluck="name", limit_page_length=0):
        frappe.db.set_value("Employee Checkin", name, "skip_auto_attendance", 0, update_modified=False)


@frappe.whitelist(methods=["POST"])
def extend(name, new_to, reason):
    """More days on a leave already approved: a leave of its own, from the
    day after it ends, which is sent and signed as any leave is. Returns
    the new application, a draft for the applicant to send."""
    doc = frappe.get_doc(APPLICATION, name)
    doc.check_permission("read")
    errors = rules.extension_errors({"docstatus": doc.docstatus, "status": doc.get("status"), "to_date": doc.to_date,
                                     "new_to": new_to, "reason": reason})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(APPLICATION))
    waiting = frappe.db.get_value(APPLICATION, {"custom_extends": doc.name, "docstatus": 0}, "name")
    if waiting:
        return waiting
    first, last = rules.extension_window(doc.to_date, new_to)
    extension = frappe.get_doc({
        "doctype": APPLICATION, "employee": doc.employee, "leave_type": doc.leave_type, "from_date": first,
        "to_date": last, "posting_date": today(), "description": reason, "company": doc.get("company"),
        "leave_approver": doc.get("leave_approver"), "custom_extends": doc.name,
        "custom_change_kind": rules.EXTENSION, "custom_change_reason": reason,
        "custom_reliever": doc.get("custom_reliever"), "custom_handover": doc.get("custom_handover"),
    })
    extension.insert()
    return extension.name


def watch_returns():
    """Daily, for each approved leave that has run out with nobody marked
    back: the clock is asked. Somebody at work after the last day is back,
    and is marked so, late or not; somebody not seen is asked after by HR,
    and once overdue (Leave Management Settings) HR and the supervisor are
    told, with the count kept on the leave. An extension takes the day due
    back with it. Returns {"back": [...], "overdue": [...]}."""
    kept = settings()
    now = getdate(today())
    out = {"back": [], "overdue": []}
    for row in frappe.get_all(
            APPLICATION, limit=300,
            filters={"docstatus": 1, "status": "Approved", "custom_reported_back": ["!=", 1], "to_date": ["<", now]},
            fields=["name", "employee", "employee_name", "to_date", "custom_branch", "department",
                    "custom_overstay_days", "custom_overstay_told"]):
        # a leave that extends it, approved or still being decided
        further = frappe.get_all(APPLICATION, filters={"custom_extends": row.name, "docstatus": ["<", 2],
                                                       "custom_leave_status": ["not in", ["Rejected", "Cancelled"]]},
                                 fields=["to_date"], order_by="to_date desc", limit=1)
        last = getdate(further[0].to_date) if further else getdate(row.to_date)
        if last >= now:
            continue
        seen = frappe.get_all("Attendance", filters={"employee": row.employee, "docstatus": 1,
                                                     "status": ["in", list(WORKED)], "attendance_date": [">", last]},
                              pluck="attendance_date", order_by="attendance_date asc", limit=1)
        seen += [getdate(time) for time in frappe.get_all(
            "Employee Checkin", filters={"employee": row.employee, "time": [">=", add_days(last, 1)]},
            pluck="time", order_by="time asc", limit=1)]
        back = rules.back_on(last, seen)
        hr = list(people.hr_officers(row.custom_branch, row.department))
        if back:
            frappe.db.set_value(APPLICATION, row.name, {
                "custom_reported_back": 1, "custom_reported_back_on": back,
                "custom_overstay_days": max((back - last).days - 1, 0)}, update_modified=False)
            people.withdraw(APPLICATION, row.name, hr)
            out["back"].append(row.name)
            continue
        people.assign(APPLICATION, row.name, hr, _("{0}'s leave ended on {1}. Mark them as reported back.").format(
            row.employee_name or row.employee, frappe.utils.format_date(last)))
        overdue = rules.overdue_days(row.to_date, now, False, last, kept.overdue_after_days)
        if not overdue:
            continue
        values = {"custom_overstay_days": overdue}
        if not cint(row.custom_overstay_told):
            supervisor = frappe.db.get_value("Employee", row.employee, "reports_to")
            users = hr + [frappe.db.get_value("Employee", supervisor, "user_id") if supervisor else None]
            people.notify(list(dict.fromkeys(user for user in users if user)), APPLICATION, row.name, _(
                "{0} was due back from leave on {1} and has not reported: {2} day(s) overdue.").format(
                row.employee_name or row.employee, frappe.utils.format_date(add_days(last, 1)), overdue))
            values["custom_overstay_told"] = 1
        frappe.db.set_value(APPLICATION, row.name, values, update_modified=False)
        out["overdue"].append(row.name)
    frappe.db.commit()
    return out
