# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training and development, the Frappe side of Luuka's To-Be training process.

The rules are in training_rules.py, the two workflows in tna_approval.py and
calendar_approval.py (no Frappe import, tested by scripts/verify_training.py).
Frappe HR's Training Program, Training Event and Training Feedback are used
as they are; this adds what comes before a session and what is made of the
evaluations after it.

  Training Requisition        the HOD's request; the branch HR Officer told
  Training Needs Assessment   the HR Officer's consolidation; HRM then GM approve
  Training Calendar           the planner, approved by the GM (then the Board);
                              a month before each training the HR Officer is
                              reminded to schedule it
  Monthly Training Schedule   the month's sessions; submitting it books a draft
                              Training Event for each, its participants the
                              requisition's target employees, and tells the
                              HODs, trainers and trainees; reminders a week, a
                              day and the morning before
  Training Event              Frappe HR's: a draft while scheduled (the HOD
                              adds participants, HR marks attendance on the
                              day), submitted once conducted
  Training Feedback           Frappe HR's, carrying LPL/TRG/FRM05's ratings and
                              questions; the event keeps the consolidated score

WHY THE EVENT STAYS A DRAFT UNTIL CONDUCTED

Frappe HR lets the participants of a submitted Training Event change but not
their attendance (Training Event Employee.attendance is not allow_on_submit),
and a Training Feedback needs the event submitted. So the session is booked
as a draft, attendance is marked on the draft, and submitting it is what
says the training was held — after which the evaluations are keyed in.

A session booked from a requisition a development plan raised (talent.py)
is reported back to the plan as it is booked, held, cancelled, given its
results or taken away (talent.sync_training), as a new employee's
onboarding is told of its trainings.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import calendar_approval, people, tna_approval, workflows
from hrms_addon.hrms_addon import onboarding_rules
from hrms_addon.hrms_addon import training_rules as rules

HOD_ROLE = onboarding_rules.HOD_ROLE


# ── 0. Training Needs Form (LPL/TRG/FRM06): the employee's own answers ─
def needs_form_validate(doc):
    if doc.get("employee") and doc.get("year") and frappe.db.exists("Training Needs Form", {
            "employee": doc.employee, "year": doc.year, "docstatus": ["!=", 2], "name": ["!=", doc.name]}):
        frappe.throw(_("{0} already has a Training Needs Form for {1}.").format(
            doc.get("employee_name") or doc.employee, doc.year), title=_("Training Needs Form"))
    if not doc.get("years_of_experience"):
        joined = frappe.db.get_value("Employee", doc.employee, "date_of_joining")
        if joined:
            doc.years_of_experience = max((getdate(doc.get("form_date") or today()) - getdate(joined)).days // 365, 0)
    # the questions as a table: each once, in the form's order, the first two answered
    rows = rules.needs_rows([row.as_dict() for row in doc.get("questions") or []])
    _set_question_rows(doc, rows)
    errors = rules.needs_errors(rows)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Training Needs Form"))
    if doc.docstatus == 0:
        doc.status = "Draft"


def _set_question_rows(doc, rows):
    """The form's question rows as `rows`, keeping each row it already has
    (so a save does not churn them), numbered 1..n."""
    have = {row.get("question_key"): row for row in doc.get("questions") or [] if row.get("question_key")}
    kept = []
    for values in rows:
        row = have.pop(values["question_key"], None) or doc.append("questions", {})
        row.update(values)
        kept.append(row)
    doc.set("questions", kept)
    for index, row in enumerate(doc.get("questions"), 1):
        row.idx = index


@frappe.whitelist()
def get_needs_questions():
    """The question rows a new Training Needs Form starts with."""
    frappe.has_permission("Training Needs Form", "create", throw=True)
    return rules.needs_rows([])


def needs_form_on_submit(doc):
    doc.db_set("status", "Submitted", update_modified=False)


def needs_form_on_cancel(doc):
    doc.db_set("status", "Cancelled", update_modified=False)


@frappe.whitelist()
def get_needs_forms(department=None, year=None):
    """The employees' submitted forms not yet taken into a requisition, as
    target employee rows, for the Get Needs Forms button."""
    frappe.has_permission("Training Requisition", "write", throw=True)
    filters = {"docstatus": 1, "status": "Submitted"}
    if department:
        filters["department"] = department
    if cint(year):
        filters["year"] = cint(year)
    forms = frappe.get_all("Training Needs Form", filters=filters, fields=["name", "employee"], order_by="form_date asc")
    skills = dict(frappe.get_all("Training Needs Answer", filters={
        "parenttype": "Training Needs Form", "parent": ["in", [row.name for row in forms] or [""]],
        "question_key": rules.SKILLS_QUESTION}, fields=["parent", "answer"], as_list=True))
    return [{"employee": row.employee, "needs_form": row.name, "skill_areas": skills.get(row.name) or ""}
            for row in forms]


# ── 1. Training Requisition ──────────────────────────────────────────
def requisition_validate(doc):
    if not doc.get("preferred_year") and doc.get("preferred_month"):
        doc.preferred_year = getdate(today()).year
    if doc.docstatus == 0:
        doc.status = "Draft"
    topics = [row.as_dict() for row in doc.get("topics") or []]
    if topics:
        doc.training_topic = rules.topics_summary(topics)
    _twice_or_throw(doc.get("target_employees"), _("Target Employees"))
    if doc.docstatus == 1:
        errors = rules.requisition_errors({
            "topics": topics, "employees": len(doc.get("target_employees") or []),
        })
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Training Requisition"))


def requisition_on_submit(doc):
    """The branch HR Officer is told, and given the requisition to assess."""
    doc.db_set("status", "Submitted", update_modified=False)
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    message = _("Training requested for {0}: {1} ({2} employees). Take it into a Training Needs Assessment.").format(
        doc.department, doc.training_topic, len(doc.get("target_employees") or []))
    people.notify(users, "Training Requisition", doc.name, message)
    people.assign("Training Requisition", doc.name, users, message)
    if users:
        doc.db_set("hr_officer", users[0], update_modified=False)
    _mark_needs_forms(doc, "In Requisition", doc.name)


def requisition_on_cancel(doc):
    doc.db_set("status", "Cancelled", update_modified=False)
    _mark_needs_forms(doc, "Submitted", None)


def _mark_needs_forms(doc, status, requisition):
    for row in doc.get("target_employees") or []:
        if row.get("needs_form") and frappe.db.exists("Training Needs Form", row.needs_form):
            frappe.db.set_value("Training Needs Form", row.needs_form, {"status": status, "requisition": requisition},
                                update_modified=False)


@frappe.whitelist()
def get_requisitions(branch=None, year=None):
    """The submitted requisitions not yet taken into an assessment, for the
    Get Requisitions button: each with its department and who asked, and its
    topics as Training Needs rows naming it."""
    frappe.has_permission("Training Needs Assessment", "write", throw=True)
    filters = {"docstatus": 1, "status": "Submitted"}
    if branch:
        filters["branch"] = branch
    if cint(year):
        filters["preferred_year"] = ["in", [cint(year), 0]]
    out = []
    for row in frappe.get_all("Training Requisition", filters=filters,
                              fields=["name", "department", "requester_name", "preferred_month", "training_topic"],
                              order_by="request_date asc"):
        topics = frappe.get_all("Training Requisition Topic", filters={"parent": row.name, "parenttype": "Training Requisition"},
                                fields=["topic", "required_skills", "method", "trainer", "budget", "duration"],
                                order_by="idx asc") or ([{"topic": row.training_topic}] if row.training_topic else [])
        requisition = {"requisition": row.name, "department": row.department, "requester_name": row.requester_name,
                       "preferred_month": row.preferred_month, "target_group": _target_group(row.name)}
        requisition["needs"] = rules.need_rows(requisition, topics)
        out.append(requisition)
    return out


def _target_group(requisition):
    employees = frappe.get_all("Training Requisition Employee", filters={"parent": requisition, "parenttype": "Training Requisition"},
                               pluck="employee", order_by="idx asc")
    names = [frappe.db.get_value("Employee", employee, "employee_name") or employee for employee in employees if employee]
    return ", ".join(names)[:140]


# ── 2. Training Needs Assessment ─────────────────────────────────────
def assessment_validate(doc):
    _twice_or_throw(doc.get("requisitions"), _("Requisitions Taken Up"), "requisition")
    if doc.docstatus == 0:
        _mark_requisitions(doc, "In Assessment", doc.name)
    old_state, new_state = _check_step(doc, tna_approval, _assessment_facts(doc), _("Training Needs Assessment"))
    doc.status = new_state or doc.get("status") or tna_approval.DRAFT


def _assessment_facts(doc):
    return {
        "assessment_errors": rules.assessment_errors({
            "needs": [{"topic": row.topic, "method": row.method, "objectives": row.objectives} for row in doc.get("needs") or []],
            "objectives": doc.get("objectives"),
        }),
        "return_remarks": doc.get("return_remarks"),
    }


def assessment_on_submit(doc):
    """Approved by the General Manager: the HR Officer who prepared it is told
    to consolidate it into the calendar."""
    doc.db_set("status", tna_approval.APPROVED, update_modified=False)
    message = _("Training Needs Assessment {0} is approved: consolidate its needs into the Training Calendar.").format(doc.title)
    people.notify([doc.get("prepared_by")], "Training Needs Assessment", doc.name, message)
    people.assign("Training Needs Assessment", doc.name, [doc.get("prepared_by")], message)


def assessment_on_cancel(doc):
    doc.db_set("status", tna_approval.CANCELLED, update_modified=False)
    _mark_requisitions(doc, "Submitted", None)


def _mark_requisitions(doc, status, assessment):
    for row in doc.get("requisitions") or []:
        if row.requisition and frappe.db.exists("Training Requisition", row.requisition):
            frappe.db.set_value("Training Requisition", row.requisition, {"status": status, "assessment": assessment},
                                update_modified=False)


# ── 3. Training Calendar ─────────────────────────────────────────────
@frappe.whitelist()
def get_approved_needs(year=None, branch=None):
    """The needs of the approved assessments of the year not yet on a calendar,
    as calendar rows, for the Get Approved Needs button."""
    frappe.has_permission("Training Calendar", "write", throw=True)
    filters = {"docstatus": 1, "status": tna_approval.APPROVED}
    if cint(year):
        filters["year"] = cint(year)
    if branch:
        filters["branch"] = ["in", [branch, ""]]
    assessments = frappe.get_all("Training Needs Assessment", filters=filters, pluck="name")
    if not assessments:
        return []
    placed = set(frappe.get_all("Training Calendar Entry", filters={"need_row": ["is", "set"]}, pluck="need_row"))
    needs = frappe.get_all(
        "Training Need", filters={"parent": ["in", assessments], "parenttype": "Training Needs Assessment"},
        fields=["name", "parent", "topic", "section", "target_group", "method", "month", "budget", "trainer", "duration"],
        order_by="parent asc, idx asc",
    )
    return rules.calendar_rows([{
        "topic": need.topic, "section": need.section, "trainer": need.trainer, "method": need.method,
        "budget": need.budget, "duration": need.duration, "month": need.month, "target_group": need.target_group,
        "assessment": need.parent, "need_row": need.name,
    } for need in needs if need.name not in placed], cint(year) or getdate(today()).year)


def calendar_validate(doc):
    for row in doc.get("entries") or []:
        if not row.planned_year:
            row.planned_year = doc.calendar_year
    doc.total_budget = sum(flt(row.budget) for row in doc.get("entries") or [])
    old_state, new_state = _check_step(doc, calendar_approval, {
        "entries": len(doc.get("entries") or []), "return_remarks": doc.get("return_remarks"),
    }, _("Training Calendar"))
    doc.status = new_state or doc.get("status") or calendar_approval.DRAFT


def calendar_on_submit(doc):
    doc.db_set("status", calendar_approval.APPROVED, update_modified=False)
    for assessment in {row.assessment for row in doc.get("entries") or [] if row.assessment}:
        if frappe.db.exists("Training Needs Assessment", assessment):
            frappe.db.set_value("Training Needs Assessment", assessment, "calendar", doc.name, update_modified=False)


def calendar_on_cancel(doc):
    doc.db_set("status", calendar_approval.CANCELLED, update_modified=False)
    for assessment in {row.assessment for row in doc.get("entries") or [] if row.assessment}:
        if frappe.db.get_value("Training Needs Assessment", assessment, "calendar") == doc.name:
            frappe.db.set_value("Training Needs Assessment", assessment, "calendar", None, update_modified=False)


# ── 4. Monthly Training Schedule ─────────────────────────────────────
@frappe.whitelist()
def get_calendar_trainings(month, year, branch=None, training_calendar=None):
    """The approved calendar's rows for the month not yet scheduled, as
    schedule lines, for the Get Calendar Trainings button."""
    frappe.has_permission("Monthly Training Schedule", "write", throw=True)
    filters = {"docstatus": 1, "status": calendar_approval.APPROVED}
    if training_calendar:
        filters["name"] = training_calendar
    if branch:
        filters["branch"] = ["in", [branch, ""]]
    calendars = frappe.get_all("Training Calendar", filters=filters, pluck="name")
    if not calendars:
        return []
    entries = frappe.get_all(
        "Training Calendar Entry",
        filters={"parent": ["in", calendars], "parenttype": "Training Calendar", "planned_month": month,
                 "planned_year": cint(year), "scheduled": 0},
        fields=["name", "course", "section", "trainer", "target_group", "training_program"],
        order_by="parent asc, idx asc",
    )
    return [{
        "course": entry.course, "trainer": entry.trainer, "target_group": entry.target_group,
        "training_program": entry.training_program, "calendar_entry": entry.name,
        "department": entry.section if frappe.db.exists("Department", entry.section or "") else None,
    } for entry in entries]


def schedule_validate(doc):
    doc.title = " - ".join(part for part in ("%s %s" % (doc.month, doc.year), doc.get("branch")) if part)
    if doc.docstatus == 1:
        errors = rules.schedule_errors({
            "lines": [{"course": line.course, "date": line.training_date, "venue": line.venue, "trainer": line.trainer}
                      for line in doc.get("lines") or []],
            "month": doc.month, "year": doc.year,
        })
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Monthly Training Schedule"))


def schedule_on_submit(doc):
    """Each line becomes a draft Training Event, its participants the target
    employees of the requisition behind it; the HODs, trainers and trainees
    are told; the calendar rows are marked scheduled."""
    for line in doc.get("lines") or []:
        if line.training_event:
            # booked as it was put on the HR calendar: told of now, with the rest
            if frappe.db.get_value("Training Event", line.training_event, "docstatus") != 0:
                continue
            event = frappe.get_doc("Training Event", line.training_event)
        else:
            event = _book_event(doc, line)
            line.db_set("training_event", event.name, update_modified=False)
        if line.calendar_entry and frappe.db.exists("Training Calendar Entry", line.calendar_entry):
            frappe.db.set_value("Training Calendar Entry", line.calendar_entry, "scheduled", 1, update_modified=False)
        _tell_about(event, doc)


def schedule_on_cancel(doc):
    """A session not yet held (still a draft) goes with the schedule; one
    already held stays. The calendar rows are open to be scheduled again."""
    for line in doc.get("lines") or []:
        if line.training_event and frappe.db.get_value("Training Event", line.training_event, "docstatus") == 0:
            event = line.training_event
            line.db_set("training_event", None, update_modified=False)
            drop_event(event)
        if line.calendar_entry and frappe.db.exists("Training Calendar Entry", line.calendar_entry):
            frappe.db.set_value("Training Calendar Entry", line.calendar_entry, "scheduled", 0, update_modified=False)


def _book_event(doc, line, employees=None):
    starts, ends = rules.session_times(line.training_date, line.get("start_time"), line.get("end_time"))
    requisitions = _requisitions_behind(line.calendar_entry)
    participants = _participants(requisitions, employees)
    program = line.get("training_program") or program_for(line.course, doc.company)
    introduction = "<p>%s</p>" % frappe.utils.escape_html(" ".join(
        part for part in (line.course, "- " + line.target_group if line.get("target_group") else "") if part))
    event = frappe.get_doc({
        "doctype": "Training Event",
        "event_name": rules.event_name(line.course, line.training_date, doc.get("branch")),
        "training_program": program,
        "event_status": rules.EVENT_SCHEDULED,
        "type": "Workshop",
        "company": doc.company,
        "custom_trainers": [{"trainer_name": line.trainer.strip(), "trainer_email": line.get("trainer_email")}]
        if (line.get("trainer") or "").strip() else [],
        "course": line.course,
        "location": line.venue,
        "start_time": starts,
        "end_time": ends,
        "introduction": introduction,
        "employees": [{"employee": employee} for employee in participants],
        "custom_branch": doc.get("branch"),
        "custom_department": line.get("department"),
        "custom_schedule": doc.name,
        "custom_calendar_entry": line.calendar_entry,
    })
    event.flags.ignore_permissions = True
    event.insert()
    for requisition in requisitions:
        frappe.db.set_value("Training Requisition", requisition, {"status": "Scheduled", "training_event": event.name},
                            update_modified=False)
    _to_talent(event.name)
    return event


def _requisitions_behind(calendar_entry):
    """The requisitions a calendar row came from: through its need row."""
    if not calendar_entry:
        return []
    need_row = frappe.db.get_value("Training Calendar Entry", calendar_entry, "need_row")
    requisition = frappe.db.get_value("Training Need", need_row, "requisition") if need_row else None
    return [requisition] if requisition else []


def _participants(requisitions, employees=None):
    """The requisitions' target employees, then anyone named besides; each
    once, the active ones only."""
    named = []
    for requisition in requisitions:
        named += frappe.get_all("Training Requisition Employee",
                                filters={"parent": requisition, "parenttype": "Training Requisition"},
                                pluck="employee", order_by="idx asc")
    seen, out = set(), []
    for employee in named + list(employees or []):
        if employee and employee not in seen and frappe.db.get_value("Employee", employee, "status") == "Active":
            seen.add(employee)
            out.append(employee)
    return out


def drop_event(name):
    """A session not yet held taken away: what pointed at it is let go, and
    the draft event is deleted."""
    _release(name)
    frappe.delete_doc("Training Event", name, ignore_permissions=True)


def _release(training_event):
    """What points at a session about to go: the requisitions it was booked
    for are open to be scheduled again, and a line of a schedule still drawn
    up forgets it (Frappe keeps a linked event from being deleted). The
    development plans it was booked for let go of it."""
    from hrms_addon.hrms_addon import talent

    talent.forget_training(training_event)
    for requisition in frappe.get_all("Training Requisition", filters={"training_event": training_event},
                                      fields=["name", "assessment"]):
        frappe.db.set_value("Training Requisition", requisition.name,
                            {"training_event": None, "status": "In Assessment" if requisition.assessment else "Submitted"},
                            update_modified=False)
    for line in frappe.get_all("Training Schedule Line", filters={"training_event": training_event,
                                                                  "parenttype": "Monthly Training Schedule"},
                               fields=["name", "parent"]):
        if frappe.db.get_value("Monthly Training Schedule", line.parent, "docstatus") == 0:
            frappe.db.set_value("Training Schedule Line", line.name, "training_event", None, update_modified=False)


def schedule_on_trash(doc):
    """A schedule deleted while being drawn up takes the trainings booked on it
    (from the HR calendar) with it."""
    for line in doc.get("lines") or []:
        if line.get("training_event") and frappe.db.get_value("Training Event", line.training_event, "docstatus") == 0:
            event = line.training_event
            line.db_set("training_event", None, update_modified=False)
            drop_event(event)


def _tell_about(event, schedule):
    """The HOD is asked to confirm the participants; the trainer and the
    trainees are told the date, time and venue."""
    when = "%s, %s at %s" % (event.course, frappe.utils.format_date(event.start_time),
                             frappe.utils.format_time(event.start_time))
    hods = people.people_for(HOD_ROLE, schedule.get("branch"), event.get("custom_department"))
    message = _("Training scheduled: {0} at {1}. Confirm the participants on the Training Event.").format(when, event.location)
    people.notify(hods, "Training Event", event.name, message)
    people.assign("Training Event", event.name, hods, message, date=getdate(event.start_time))
    trainees = [user for user in frappe.get_all("Employee", filters={"name": ["in", [row.employee for row in event.employees]]},
                                                pluck="user_id") if user] if event.employees else []
    people.notify(trainees, "Training Event", event.name,
                  _("You are booked for training: {0} at {1}.").format(when, event.location))
    _tell_trainer(event, _("You are the trainer for {0} at {1}.").format(when, event.location))


def _tell_trainer(event, message):
    """Every trainer of the session: in the desk if they have a user, else by email."""
    for email in _trainer_emails(event):
        if frappe.db.exists("User", email):
            people.notify([email], "Training Event", event.name, message)
            continue
        try:
            frappe.sendmail(recipients=[email], subject=_("Training: {0}").format(event.course or event.event_name),
                            message=message, reference_doctype="Training Event", reference_name=event.name)
        except Exception:
            frappe.log_error(title="HRMS Addon: trainer email failed")


def _trainer_emails(event):
    rows = event.get("custom_trainers")
    if rows is None:  # a row from get_all: the table is read here
        rows = frappe.get_all("Training Event Trainer", filters={"parent": event.name, "parenttype": "Training Event"},
                              fields=["trainer_email", "employee"], order_by="idx asc")
    emails = []
    for row in rows:
        email = (row.get("trainer_email") or "").strip() or (
            frappe.db.get_value("Employee", row.employee, "user_id") if row.get("employee") else None)
        if email:
            emails.append(email)
    if not rows and (event.get("trainer_email") or "").strip():
        emails.append(event.trainer_email.strip())
    return list(dict.fromkeys(emails))


# ── 5. The session: Frappe HR's Training Event ───────────────────────
def event_validate(doc, method=None):
    """Its trainers are a table, Frappe HR's own Trainer Name and Email kept
    from it; the programme is filled from the course; nobody is booked twice."""
    _sync_trainers(doc)
    if not doc.get("training_program") and (doc.get("course") or "").strip():
        doc.training_program = program_for(doc.course, doc.get("company"))
    if doc.get("training_program") and not (doc.get("course") or "").strip():
        doc.course = doc.training_program
    _twice_or_throw(doc.get("employees"), _("Employees"))


def _sync_trainers(doc):
    rows = [row for row in doc.get("custom_trainers") or [] if (row.get("trainer_name") or "").strip()]
    if rows:
        doc.trainer_name = rules.trainers_line([row.trainer_name for row in rows])
        doc.trainer_email = next((row.trainer_email for row in rows if row.get("trainer_email")), None)
        return
    before = doc.get_doc_before_save()
    if before and before.get("custom_trainers"):  # every trainer taken off
        doc.trainer_name = doc.trainer_email = None
    elif (doc.get("trainer_name") or "").strip():  # set by Frappe HR, or from before the table
        doc.append("custom_trainers", {"trainer_name": doc.trainer_name.strip(), "trainer_email": doc.get("trainer_email"),
                                       "contact_number": doc.get("contact_number")})


def event_on_trash(doc, method=None):
    """A draft session deleted from its form: let go of what points at it."""
    _release(doc.name)


def event_on_submit(doc, method=None):
    """Conducted: the requisitions behind it are closed, and a new employee's
    onboarding and the development plans it was booked for learn who
    attended."""
    for requisition in frappe.get_all("Training Requisition", filters={"training_event": doc.name, "docstatus": 1}, pluck="name"):
        frappe.db.set_value("Training Requisition", requisition, "status", "Closed", update_modified=False)
    _to_onboardings(doc.name, {row.employee: {"attendance": row.attendance} for row in doc.employees})
    _to_talent(doc.name)


def event_on_cancel(doc, method=None):
    # the plans let go of the session while its requisitions still name it;
    # a closed plan's Training row still pointing at it does not stop it
    doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + ("Talent Program",)
    _to_talent(doc.name)
    for requisition in frappe.get_all("Training Requisition", filters={"training_event": doc.name, "docstatus": 1}, pluck="name"):
        frappe.db.set_value("Training Requisition", requisition, {"status": "Scheduled", "training_event": None},
                            update_modified=False)
    _to_onboardings(doc.name, {row.employee: {"attendance": None} for row in doc.employees})


def _to_talent(training_event):
    """The development plans whose training this session is (talent.py)."""
    from hrms_addon.hrms_addon import talent

    talent.sync_training(training_event)


def _to_onboardings(training_event, values):
    """The onboarding trainings booked as this event: {employee: values}."""
    for row in frappe.get_all("Onboarding Training", filters={"training_event": training_event, "parenttype": "Employee Onboarding"},
                              fields=["name", "parent"]):
        employee = frappe.db.get_value("Employee Onboarding", row.parent, "employee")
        if employee in values:
            frappe.db.set_value("Onboarding Training", row.name, values[employee], update_modified=False)


@frappe.whitelist()
def result_employees(training_event: str):
    """Frappe HR's Training Result fills itself with every participant: those
    marked Present only."""
    frappe.has_permission("Training Event", "read", training_event, throw=True)
    return [row for row in frappe.get_doc("Training Event", training_event).employees if row.attendance == rules.PRESENT]


# ── 5b. The result: Frappe HR's Training Result ───────────────────────
def result_validate(doc, method=None):
    """Only those who attended are given a result, each once; their marks say
    whether the training was effective."""
    _twice_or_throw(doc.get("employees"), _("Employees"))
    participants = dict(frappe.get_all("Training Event Employee", filters={"parent": doc.training_event, "parenttype": "Training Event"},
                                       fields=["employee", "attendance"], as_list=True)) if doc.get("training_event") else {}
    refused = rules.result_errors([row.employee for row in doc.get("employees") or []], participants)
    if refused:
        names = {row.employee: row.get("employee_name") or row.employee for row in doc.employees}
        frappe.throw("<br>".join(
            (_("{0} was not booked for this training.") if why == "not booked" else _("{0} did not attend this training.")).format(
                names.get(employee, employee)) for employee, why in refused), title=_("Training Result"))
    result_marks(doc)


def result_marks(doc, method=None):
    pass_mark = _pass_mark(doc.get("training_event"))
    for row in doc.get("employees") or []:
        row.custom_effective = rules.effectiveness(row.get("custom_marks"), pass_mark)


def result_on_submit(doc, method=None):
    """The marks, and whether the training worked, on a new employee's
    onboarding and on the development plans the session was booked for."""
    _to_onboardings(doc.training_event, {row.employee: {"marks": row.get("custom_marks"), "effectiveness": row.get("custom_effective")}
                                         for row in doc.employees})
    _to_talent(doc.training_event)


def result_on_cancel(doc, method=None):
    _to_onboardings(doc.training_event, {row.employee: {"marks": None, "effectiveness": None} for row in doc.employees})
    _to_talent(doc.training_event)


def _pass_mark(training_event):
    program = frappe.db.get_value("Training Event", training_event, "training_program") if training_event else None
    return flt(frappe.db.get_value("Training Program", program, "custom_pass_mark")) if program else 0


@frappe.whitelist(methods=["POST"])
def create_evaluations(training_event):
    """An evaluation form (a draft Training Feedback carrying Section A's
    items) for each participant marked Present who has none yet, so HR keys
    in the paper forms one after another. Returns how many were made."""
    event = frappe.get_doc("Training Event", training_event)
    event.check_permission("write")
    if event.docstatus != 1:
        frappe.throw(_("Mark the attendance and submit the Training Event first: the training must have been held."))
    made = 0
    for row in event.employees:
        if row.attendance != rules.PRESENT:
            continue
        if frappe.db.exists("Training Feedback", {"training_event": event.name, "employee": row.employee, "docstatus": ["!=", 2]}):
            continue
        feedback = frappe.new_doc("Training Feedback")
        feedback.update({"employee": row.employee, "training_event": event.name, "feedback": ""})
        _fill_items(feedback)
        feedback.flags.ignore_mandatory = True
        feedback.insert(ignore_permissions=True)
        made += 1
    return made


# ── 6. The evaluation: Frappe HR's Training Feedback ─────────────────
def feedback_validate(doc, method=None):
    if doc.get("training_event") and doc.get("employee") and frappe.db.exists("Training Feedback", {
            "training_event": doc.training_event, "employee": doc.employee, "docstatus": ["!=", 2], "name": ["!=", doc.name]}):
        frappe.throw(_("{0} already has an evaluation of this training.").format(doc.get("employee_name") or doc.employee),
                     title=_("Training Feedback"))
    if not doc.get("custom_ratings"):
        _fill_items(doc)
    doc.custom_score = rules.score([row.rating for row in doc.get("custom_ratings") or []])
    doc.custom_band = rules.band(doc.custom_score)
    # Frappe HR's own free-text field: filled from the form's answers when the
    # evaluation is submitted with nothing typed there, never on the draft
    if doc.docstatus == 1 and not (doc.get("feedback") or "").strip():
        doc.feedback = doc.get("custom_learnt") or doc.get("custom_expectations") or _("See the evaluation form.")


def feedback_on_submit(doc, method=None):
    _score_event(doc.training_event)


def feedback_on_cancel(doc, method=None):
    _score_event(doc.training_event)


def _fill_items(doc):
    for item in frappe.get_all("Training Evaluation Item", order_by="creation asc", pluck="name"):
        doc.append("custom_ratings", {"item": item})


def _score_event(training_event):
    """The event's consolidated score: over its submitted evaluations."""
    summary = consolidated(training_event)
    frappe.db.set_value("Training Event", training_event,
                        {"custom_evaluation_score": summary["score"], "custom_evaluation_band": summary["band"],
                         "custom_evaluations": summary["count"]}, update_modified=False)


def consolidated(training_event):
    """The consolidated evaluation report of a training (jinja method for the
    Training Evaluation Summary print): each item's average, the overall
    score, and every answer to the six questions."""
    feedbacks = frappe.get_all("Training Feedback", filters={"training_event": training_event, "docstatus": 1},
                               fields=["name", "employee", "employee_name", "custom_score"] +
                                      ["custom_%s" % field for field, _q in rules.QUESTIONS])
    evaluations, answers = [], {field: [] for field, _q in rules.QUESTIONS}
    for feedback in feedbacks:
        ratings = frappe.get_all("Training Evaluation Rating", filters={"parent": feedback.name, "parenttype": "Training Feedback"},
                                 fields=["item", "rating"])
        # scored from its ratings: Frappe keeps a blank score as 0, which
        # would count a form with nothing rated as 0%
        feedback.custom_score = rules.score([r.rating for r in ratings])
        evaluations.append({"items": {r.item: r.rating for r in ratings}, "score": feedback.custom_score})
        for field, _question in rules.QUESTIONS:
            text = (feedback.get("custom_%s" % field) or "").strip()
            if text:
                answers[field].append({"employee": feedback.employee_name or feedback.employee, "text": text})
    summary = rules.consolidate(evaluations)
    summary["answers"] = answers
    summary["questions"] = list(rules.QUESTIONS)
    summary["participants"] = [{"employee": f.employee, "name": f.employee_name, "score": f.custom_score} for f in feedbacks]
    return summary


# ── 7. The scheduler ─────────────────────────────────────────────────
def daily():
    """A month before a calendar training, the HR Officer is reminded to
    schedule it; a week, a day and the morning before a session, everyone
    booked for it is reminded."""
    day = today()
    _remind_to_schedule(day)
    _remind_of_sessions(day)


def _remind_to_schedule(day):
    rows = frappe.get_all(
        "Training Calendar Entry",
        filters={"parenttype": "Training Calendar", "scheduled": 0, "reminded_on": ["is", "not set"]},
        fields=["name", "parent", "course", "planned_month", "planned_year", "target_group"],
    )
    calendars = {name: (branch, status) for name, branch, status in frappe.get_all(
        "Training Calendar", filters={"name": ["in", list({r.parent for r in rows})]},
        fields=["name", "branch", "status"], as_list=True)} if rows else {}
    live = [row for row in rows if calendars.get(row.parent, (None, None))[1] == calendar_approval.APPROVED]
    for row in rules.due_for_schedule([dict(r, scheduled=0, reminded_on=None) for r in live], day):
        branch = calendars[row["parent"]][0]
        users = people.hr_officers(branch)
        message = _("{0} is on the Training Calendar for {1} {2}: draw up the Monthly Training Schedule.").format(
            row["course"], row["planned_month"], row["planned_year"])
        people.notify(users, "Training Calendar", row["parent"], message)
        people.assign("Training Calendar", row["parent"], users, message)
        frappe.db.set_value("Training Calendar Entry", row["name"], "reminded_on", day, update_modified=False)


def _remind_of_sessions(day):
    events = frappe.get_all(
        "Training Event", filters={"docstatus": 0, "event_status": rules.EVENT_SCHEDULED, "start_time": [">=", day]},
        fields=["name", "course", "event_name", "start_time", "location", "custom_branch", "custom_department",
                "custom_reminders_sent", "trainer_email"],
    )
    for event in events:
        due = rules.reminders_due(event.start_time, day, event.custom_reminders_sent)
        if not due:
            continue
        when = "%s, %s at %s" % (event.course or event.event_name, frappe.utils.format_date(event.start_time),
                                 frappe.utils.format_time(event.start_time))
        message = {7: _("Training in a week: {0} at {1}."), 1: _("Training tomorrow: {0} at {1}."),
                   0: _("Training today: {0} at {1}.")}[due[0]].format(when, event.location)
        employees = frappe.get_all("Training Event Employee", filters={"parent": event.name, "parenttype": "Training Event"},
                                   pluck="employee")
        users = [u for u in frappe.get_all("Employee", filters={"name": ["in", employees]}, pluck="user_id") if u] if employees else []
        users += people.people_for(HOD_ROLE, event.custom_branch, event.custom_department)
        people.notify(list(dict.fromkeys(users)), "Training Event", event.name, message)
        _tell_trainer(frappe._dict(event), message)
        frappe.db.set_value("Training Event", event.name, "custom_reminders_sent",
                            rules.record_reminders(event.custom_reminders_sent, due), update_modified=False)


# ── the workflows, the masters ───────────────────────────────────────
def program_for(course, company=None):
    """The Training Program of a course: the one of that name, else a new one."""
    name = (course or "").strip()[:140]
    if not name:
        return None
    found = frappe.db.get_value("Training Program", name, "name")
    if found:
        return found
    company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
        "Global Defaults", "default_company") or (frappe.get_all("Company", pluck="name", limit=1) or [None])[0]
    program = frappe.get_doc({"doctype": "Training Program", "training_program": name, "company": company,
                              "description": "<p>%s</p>" % frappe.utils.escape_html(name)})
    program.flags.ignore_permissions = True
    program.insert()
    return program.name


def _twice_or_throw(rows, table, field="employee"):
    """Nobody (or nothing) listed twice in a table."""
    rows = rows or []
    twice = rules.duplicates([row.get(field) for row in rows])
    if not twice:
        return
    names = {row.get(field): (row.get("employee_name") if field == "employee" else None) or row.get(field) for row in rows}
    frappe.throw(_("{0} is listed more than once in {1}.").format(", ".join(names[value] for value in twice), table),
                 title=table)


def _check_step(doc, approval, facts, title):
    before = doc.get_doc_before_save()
    old_state = before.get(approval.STATE_FIELD) if before else None
    new_state = doc.get(approval.STATE_FIELD)
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, facts)
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=title)
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current).items():
        doc.set(field, value)
    return old_state, new_state


def setup_workflows_on_migrate():
    """after_migrate: the assessment's and the calendar's workflows, and the
    HR Officer's and the HOD's rights on Frappe HR's training documents
    (workflows.py)."""
    workflows.setup_on_migrate(tna_approval, "Training Needs Assessment workflow")
    workflows.setup_on_migrate(calendar_approval, "Training Calendar workflow")
    workflows.grant_on_migrate(rules, "training permissions")
