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
    if not doc.get("years_of_experience"):
        joined = frappe.db.get_value("Employee", doc.employee, "date_of_joining")
        if joined:
            doc.years_of_experience = max((getdate(doc.get("form_date") or today()) - getdate(joined)).days // 365, 0)
    if doc.docstatus == 0:
        doc.status = "Draft"


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
    return [{"employee": row.employee, "needs_form": row.name, "skill_areas": row.skill_areas}
            for row in frappe.get_all("Training Needs Form", filters=filters, fields=["name", "employee", "skill_areas"],
                                      order_by="form_date asc")]


# ── 1. Training Requisition ──────────────────────────────────────────
def requisition_validate(doc):
    if not doc.get("preferred_year") and doc.get("preferred_month"):
        doc.preferred_year = getdate(today()).year
    if doc.docstatus == 0:
        doc.status = "Draft"
    if doc.docstatus == 1:
        errors = rules.requisition_errors({
            "topic": doc.get("training_topic"), "skills": doc.get("required_skills"),
            "employees": len(doc.get("target_employees") or []),
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
    Get Requisitions button, each with its target group written out."""
    frappe.has_permission("Training Needs Assessment", "write", throw=True)
    filters = {"docstatus": 1, "status": "Submitted"}
    if branch:
        filters["branch"] = branch
    if cint(year):
        filters["preferred_year"] = ["in", [cint(year), 0]]
    rows = frappe.get_all(
        "Training Requisition", filters=filters,
        fields=["name", "department", "training_topic", "required_skills", "proposed_method", "proposed_trainer",
                "estimated_budget", "duration", "preferred_month", "requester_name"],
        order_by="request_date asc",
    )
    for row in rows:
        row["requisition"] = row.pop("name")
        row["target_group"] = _target_group(row["requisition"])
    return rows


def _target_group(requisition):
    employees = frappe.get_all("Training Requisition Employee", filters={"parent": requisition, "parenttype": "Training Requisition"},
                               pluck="employee", order_by="idx asc")
    names = [frappe.db.get_value("Employee", employee, "employee_name") or employee for employee in employees if employee]
    return ", ".join(names)[:140]


# ── 2. Training Needs Assessment ─────────────────────────────────────
def assessment_validate(doc):
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
            continue
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
            frappe.delete_doc("Training Event", line.training_event, ignore_permissions=True)
            line.db_set("training_event", None, update_modified=False)
        if line.calendar_entry and frappe.db.exists("Training Calendar Entry", line.calendar_entry):
            frappe.db.set_value("Training Calendar Entry", line.calendar_entry, "scheduled", 0, update_modified=False)


def _book_event(doc, line):
    starts, ends = rules.session_times(line.training_date, line.get("start_time"), line.get("end_time"))
    requisitions = _requisitions_behind(line.calendar_entry)
    participants = _participants(requisitions)
    program = line.get("training_program")
    introduction = "<p>%s</p>" % frappe.utils.escape_html(" ".join(
        part for part in (line.course, "- " + line.target_group if line.get("target_group") else "") if part))
    event = frappe.get_doc({
        "doctype": "Training Event",
        "event_name": rules.event_name(line.course, line.training_date, doc.get("branch")),
        "training_program": program,
        "event_status": rules.EVENT_SCHEDULED,
        "type": "Workshop",
        "company": doc.company,
        "trainer_name": line.trainer,
        "trainer_email": line.get("trainer_email"),
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
    return event


def _requisitions_behind(calendar_entry):
    """The requisitions a calendar row came from: through its need row."""
    if not calendar_entry:
        return []
    need_row = frappe.db.get_value("Training Calendar Entry", calendar_entry, "need_row")
    requisition = frappe.db.get_value("Training Need", need_row, "requisition") if need_row else None
    return [requisition] if requisition else []


def _participants(requisitions):
    seen, out = set(), []
    for requisition in requisitions:
        for employee in frappe.get_all("Training Requisition Employee",
                                       filters={"parent": requisition, "parenttype": "Training Requisition"},
                                       pluck="employee", order_by="idx asc"):
            if employee and employee not in seen and frappe.db.get_value("Employee", employee, "status") == "Active":
                seen.add(employee)
                out.append(employee)
    return out


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
    email = (event.get("trainer_email") or "").strip()
    if not email:
        return
    if frappe.db.exists("User", email):
        people.notify([email], "Training Event", event.name, message)
        return
    try:
        frappe.sendmail(recipients=[email], subject=_("Training: {0}").format(event.course or event.event_name), message=message,
                        reference_doctype="Training Event", reference_name=event.name)
    except Exception:
        frappe.log_error(title="HRMS Addon: trainer email failed")


# ── 5. The session: Frappe HR's Training Event ───────────────────────
def event_on_submit(doc, method=None):
    """Conducted: the requisitions behind it are closed."""
    for requisition in frappe.get_all("Training Requisition", filters={"training_event": doc.name, "docstatus": 1}, pluck="name"):
        frappe.db.set_value("Training Requisition", requisition, "status", "Closed", update_modified=False)


def event_on_cancel(doc, method=None):
    for requisition in frappe.get_all("Training Requisition", filters={"training_event": doc.name, "docstatus": 1}, pluck="name"):
        frappe.db.set_value("Training Requisition", requisition, {"status": "Scheduled", "training_event": None},
                            update_modified=False)


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
