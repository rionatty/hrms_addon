# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent management on the site: the nine-box review, succession, the
graduate trainee scheme, and the development programmes all three feed.

The rules are in talent_rules.py, without a Frappe import
(scripts/verify_talent.py). This reads and writes the site.

  review_*     a round of reviews: who is in it, and the scheduler that
               drafts a placement for everyone eligible when it opens
  placement_*  one employee's cell: the performance read from their
               appraisal, the potential the line manager rates, the
               calibration across plants, and the council's finalisation,
               which draws up the development plan and sends its training
               to L&D
  program_*    the development plan itself — leadership, mentoring and
               coaching, or L&D — and the review of whether it worked; its
               closing decision is acted on: the bench, a promotion drafted,
               or a replacement's requisition
  position_*   a critical role and its bench; confirmed, the development
               needs go to L&D, each successor not ready yet gets a plan
               aimed at the role, and a confirmed gap drafts the requisition
               that becomes the job opening once Luuka's approvals pass it
  separation_* the holder's exit (Exits): the plan learns their last day
  change_*     the promotion into the role approved (Position Change): the
               plan names its new holder
  trainee_*    a graduate trainee from the applicant they were hired as to
               the Employee record confirmation creates
  daily        the cycles that open, the milestones that fall due, the top
               talent somebody should be worried about losing, and the
               holders of critical roles who are on their way out

Nothing here re-enters a number another module already holds: the
performance band comes off the Appraisal, the competency evidence off its
scorecard rows, and the training goes back out as a Training Requisition
rather than as a note in a field. Nor does it decide for HR: what it starts
in another module (a position change, a job requisition, a development
plan) is a draft for HR to complete and send through that module's own
signatures.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, format_date, getdate, today

from hrms_addon.hrms_addon import people, pips, talent_jobs, talent_masters as masters, talent_rules as rules

REVIEW = "Talent Review"
# a development plan's own actions (the appraisal keeps Development Action)
ACTION = "Talent Plan Action"
PLACEMENT = "Talent Placement"
PROGRAM = "Talent Program"
POSITION = "Succession Position"
TRAINEE = "Graduate Trainee Program"
REQUISITION = "Training Requisition"
CHANGE = "Employee Position Change"
JOB_REQUISITION = "Job Requisition"
SEPARATION = "Employee Separation"
CLEARANCE = "Clearance Form"
# a requisition in one of these is no longer the way the role is filled
CLOSED_REQUISITION = ("Cancelled", "Rejected", "Filled")
# what points at a plan, a programme: each is cancelled on its own, so
# neither cancel offers to cancel them nor is refused for them
# the Succession Plan (succession_plans.py) names its roles too: a role cancelled leaves the plan as it was
PLAN = "Succession Plan"
POSITION_RECORDS = (PROGRAM, CHANGE, SEPARATION, TRAINEE, PLAN)
PROGRAM_RECORDS = (POSITION, CHANGE, PLACEMENT, REQUISITION)


# ── 1. The review cycle ───────────────────────────────────────────────
def review_validate(doc, method=None):
    if doc.get("opens_on") and doc.get("closes_on") \
            and getdate(doc.closes_on) < getdate(doc.opens_on):
        frappe.throw(_("A review cannot close before it opens."), title=_(REVIEW))
    if not doc.get("status"):
        doc.status = "Draft"


@frappe.whitelist(methods=["POST"])
def draft_placements(review):
    """Test case 21: when a cycle opens, a draft placement for everyone
    eligible. Eligible means there is a submitted appraisal to read a
    performance band from: without one the placement would have nothing on
    its left-hand axis. A review runs to the whole staff, so the placements
    are drafted in the background (talent_jobs); whoever asked follows it
    on the board and is told when it is done.
    """
    cycle = frappe.get_doc(REVIEW, review)
    cycle.check_permission("write")
    if not _review_source(cycle):
        frappe.throw(_("Name the appraisal plan the review reads, so there are appraisals to place "
                       "people from."), title=_(REVIEW))
    if not frappe.db.exists("Appraisal", dict(_review_source(cycle), docstatus=1)):
        # nobody to place is not everybody placed: say what is missing
        frappe.msgprint(_("Nobody can be placed yet. No appraisal in {0} has been completed.").format(
            cycle.get("appraisal_plan") or cycle.get("appraisal_cycle")))
        return {"queued": 0}
    log = talent_jobs.start("draft", REVIEW, cycle.name, "hrms_addon.hrms_addon.talent.draft_job", review=cycle.name)
    return {"queued": 1, "log": log}


def plants_of(cycle):
    """The plants a review covers: its Plants, else the one plant of a review
    set up before it could cover several, else every plant."""
    plants = [row.branch for row in cycle.get("plants") or [] if row.get("branch")]
    if not plants and cycle.get("branch"):
        plants = [cycle.branch]
    return plants


def to_place(cycle):
    """Everyone the review should place and has not: on the staff (a
    suspension included, suspensions.py), with a completed appraisal in its
    year, in its company, plants and department. One placement a person:
    the year has a completed appraisal for each quarter, each of them the
    same person. Three queries, whatever the size of the staff."""
    source = _review_source(cycle)
    if not source:
        frappe.throw(_("Name the appraisal plan the review reads, so there are appraisals to place "
                       "people from."), title=_(REVIEW))
    employees = sorted(set(frappe.get_all("Appraisal", filters=dict(source, docstatus=1), pluck="employee",
                                          limit_page_length=0)))
    if not employees:
        return []
    have = set(frappe.get_all(PLACEMENT, filters={"talent_review": cycle.name, "docstatus": ["<", 2]},
                              pluck="employee", limit_page_length=0))
    filters = {"name": ["in", employees], "status": ["in", ("Active", "Suspended")]}
    if cycle.get("company"):
        filters["company"] = cycle.company
    if cycle.get("department"):
        filters["department"] = cycle.department
    plants = plants_of(cycle)
    if plants:
        filters["branch"] = ["in", plants]
    return [row for row in frappe.get_all("Employee", filters=filters, fields=["name", "company", "employee_name"],
                                          order_by="name asc", limit_page_length=0)
            if row.name not in have]


def _place(review, row):
    placement = frappe.get_doc({"doctype": PLACEMENT, "talent_review": review, "employee": row.name,
                                "company": row.company})
    placement.flags.ignore_permissions = True
    placement.flags.ignore_mandatory = True
    placement.insert()
    return placement.name


def draft_job(context, review):
    """The background step: a draft placement for each, committed in chunks."""
    cycle = frappe.get_doc(REVIEW, review)
    rows = {row.name: row for row in to_place(cycle)}
    context.doctype = "Employee"
    context.each(list(rows), lambda name: _place(cycle.name, rows[name]),
                 label=lambda name: rows[name].employee_name or name)
    _mark_drafted(cycle, context.done)
    started = frappe.db.get_value(talent_jobs.LOG, context.log, "started_by")
    talent_jobs.tell([started], REVIEW, cycle.name, _("{0}: {1} placements drafted.").format(
        cycle.get("title") or cycle.name, context.done))


def _draft_placements(cycle):
    """The same at once, in the request: what is drafted."""
    made = 0
    for row in to_place(cycle):
        try:
            _place(cycle.name, row)
        except Exception:
            frappe.log_error(title="HRMS Addon: drafting a talent placement")
            continue
        made += 1
    _mark_drafted(cycle, made)
    return made


def _mark_drafted(cycle, made):
    cycle.db_set({"placements_created": cint(cycle.get("placements_created")) + made,
                  "drafted_on": today()}, update_modified=False)
    if made and cycle.get("status") == "Draft":
        cycle.db_set("status", "Open", update_modified=False)


# ── 2. The placement ──────────────────────────────────────────────────
def placement_validate(doc, method=None):
    from hrms_addon.hrms_addon import talent_approval as approval

    from hrms_addon.hrms_addon import retention

    _fill_performance(doc)
    _fill_potential(doc)
    _fill_box(doc)
    _check_placement_step(doc)
    retention.retention_validate(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def placement_on_update(doc, method=None):
    """A flight risk set or changed on the form is kept as an assessment."""
    from hrms_addon.hrms_addon import retention

    retention.placement_changed(doc)


def placement_before_update_after_submit(doc, method=None):
    """A finalised placement's retention actions, checked as they are kept."""
    from hrms_addon.hrms_addon import retention

    retention.retention_validate(doc)


# what a placement reads off each of the year's appraisals
APPRAISAL_FIELDS = ["name", "custom_quarter", "custom_total_score", "final_score", "custom_band",
                    "custom_annual_score", "custom_year_band", "end_date", "custom_outcome",
                    "custom_performance_review"]


def _review_source(review):
    """Where a review's appraisals come from: the appraisal plan of the year
    (Luuka appraise every quarter, and each appraisal carries the year to
    date), or the one cycle a review was set up on before the plans."""
    row = frappe.db.get_value(REVIEW, review, ["appraisal_plan", "appraisal_cycle"], as_dict=True) \
        if isinstance(review, str) else review
    if not row:
        return None
    if row.get("appraisal_plan"):
        return {"custom_plan": row.get("appraisal_plan")}
    if row.get("appraisal_cycle"):
        return {"appraisal_cycle": row.get("appraisal_cycle")}
    return None


def _year_appraisals(employee, review):
    """The employee's completed appraisals of the review's year, first to last."""
    source = _review_source(review)
    if not (employee and source):
        return []
    return frappe.get_all("Appraisal", filters=dict(source, employee=employee, docstatus=1),
                          fields=APPRAISAL_FIELDS, order_by="end_date asc", limit=20)


def _fill_performance(doc):
    """Test case 4: the year's performance as the appraisal module holds it
    — the year to date over the quarters appraised, each quarter beside it —
    and the band it falls in. Nothing is re-entered, so a placement whose
    employee has no completed appraisal in the year carries no performance.
    Read again at every save until the council finalises, so a quarter
    completed meanwhile is counted. The improvement plan the employee is on,
    and what management decided on their appraisal, come across with it."""
    if not (doc.get("employee") and doc.get("talent_review")) or doc.docstatus != 0:
        return
    appraisals = _year_appraisals(doc.employee, doc.talent_review)
    year = rules.year_performance([{
        "name": row.name, "quarter": row.custom_quarter, "total": row.custom_total_score or row.final_score,
        "band": row.custom_band, "year_score": row.custom_annual_score, "year_band": row.custom_year_band,
        "end_date": row.end_date} for row in appraisals])
    doc.improvement_plan = pips.open_plan(doc.employee)
    doc.on_pip = 1 if doc.improvement_plan else 0
    decided = [row for row in appraisals if row.get("custom_outcome")]
    doc.management_decision = decided[-1].custom_outcome if decided else None
    doc.performance_review = decided[-1].custom_performance_review if decided else None
    if not year:
        for field in ("appraisal", "performance_score", "appraisal_band", "performance_band"):
            doc.set(field, None)
        doc.set("quarter_results", [])
        doc.set("competencies", [])
        return
    doc.appraisal = year["appraisal"]
    doc.performance_score = year["score"]
    doc.appraisal_band = year["band"]
    doc.performance_band = rules.performance_band(year["score"], masters.grid())
    doc.set("quarter_results", [{"quarter": row["quarter"], "appraisal": row["appraisal"],
                                 "total": row["total"], "band": row["band"]} for row in year["quarters"]])
    _carry_competencies(doc, [row.name for row in appraisals])


def _carry_competencies(doc, appraisals):
    """Test case 5: the competency levels as the appraisals gave them,
    whichever form the employee is on — a scorecard competency as scored, an
    LPL/HR/18 factor as rated — averaged over the year, as evidence for the
    potential rating. Not typed in, and not a score here; a remark the line
    manager wrote against one stays."""
    remarks = {row.competency: row.remarks for row in doc.get("competencies") or [] if row.get("remarks")}
    order = {name: number for number, name in enumerate(appraisals)}
    scorecard = frappe.get_all("BSC Appraisal Competency",
                               filters={"parent": ["in", appraisals], "parenttype": "Appraisal"},
                               fields=["competency", "score", "parent"], order_by="idx asc", limit=500)
    factors = frappe.get_all("Appraisal Factor Rating",
                             filters={"parent": ["in", appraisals], "parenttype": "Appraisal",
                                      "parentfield": "custom_factors"},
                             fields=["item", "supervisor_rating", "parent"], order_by="idx asc", limit=500)
    by_quarter = lambda row: order.get(row.parent, 0)  # noqa: E731
    evidence = rules.competency_evidence(
        [{"competency": row.competency, "score": row.score, "appraisal": row.parent}
         for row in sorted(scorecard, key=by_quarter)],
        [{"factor": row.item, "rating": row.supervisor_rating, "appraisal": row.parent}
         for row in sorted(factors, key=by_quarter)])
    doc.set("competencies", [{"competency": row["competency"], "level": row["level"], "times": row["times"],
                              "appraisal": row["appraisal"], "remarks": remarks.get(row["competency"])}
                             for row in evidence])


def _fill_potential(doc):
    """The potential from the raters' submitted Potential Assessments
    (potential.py), never typed on the placement; the competency evidence
    averaged beside it."""
    from hrms_addon.hrms_addon import potential

    if doc.docstatus == 0:
        potential.fill_placement(doc)
    doc.competency_average = rules.competency_average(
        [row.as_dict() for row in doc.get("competencies") or []])


def _fill_box(doc):
    """Test case 6: the two bands resolve to one cell, with its name, its
    colour and what it says to do. The potential is the line manager's
    until calibration moves it (talent_board.move)."""
    box = rules.box_for(rules.effective_performance(doc.get("performance_band"), doc.get("calibrated_performance")),
                        rules.effective_potential(doc.get("potential_band"), doc.get("calibrated_potential")),
                        masters.grid())
    if not box:
        for field in ("box", "nine_box", "box_name", "box_colour", "default_action", "suggested_decision"):
            doc.set(field, None)
        doc.top_talent = 0
        return
    doc.box = box["box"]
    doc.nine_box = _nine_box(box["box"])
    doc.box_name = box["name"]
    doc.box_colour = box["colour"]
    doc.default_action = box["action"]
    doc.suggested_decision = box["decision"]
    doc.top_talent = 1 if rules.is_top_talent(box["box"], masters.grid()) else 0


def _check_placement_step(doc):
    from hrms_addon.hrms_addon import talent_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state,
                                      {"return_remarks": doc.get("return_remarks")})
        if new_state == approval.CALIBRATION and old_state in (None, approval.DRAFT):
            errors = rules.placement_errors({
                "employee": doc.get("employee"), "talent_review": doc.get("talent_review"),
                "performance_score": doc.get("performance_score"), "raters": doc.get("raters"),
                "rationale": doc.get("rationale")}) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(PLACEMENT))
        if new_state == approval.DRAFT:
            # back with the line manager: they place the employee afresh,
            # and calibration starts again from what they submit
            from hrms_addon.hrms_addon import calibration

            calibration.revert(doc)
            doc.submitted_box = None
            doc.calibrated_potential = None
            doc.calibrated_performance = None
            doc.calibration_session = None
            _fill_box(doc)
        elif old_state in (None, approval.DRAFT) and new_state == approval.CALIBRATION:
            doc.submitted_box = doc.get("box")
        else:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_placement(doc, new_state)
    if old_state != new_state and new_state == approval.CALIBRATION and doc.get("talent_review"):
        status = frappe.db.get_value(REVIEW, doc.talent_review, "status")
        if status in ("Draft", "Open"):
            frappe.db.set_value(REVIEW, doc.talent_review, "status", "In Calibration", update_modified=False)


def _tell_placement(doc, state):
    """Who a placement waits for. Calibration is HR's (only HR move it on),
    and HR hear of the placements that came into it once a day, as one
    digest (calibration_digest), not one alert a placement; the council
    hears of the placements sent to it, one message a step."""
    from hrms_addon.hrms_addon import talent_approval as approval

    if state == approval.CALIBRATION:
        return
    users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"), doc.get("department"))
    if users:
        talent_jobs.tell(list(users), doc.doctype, doc.name, _("Talent placement for {0} is waiting at {1}.").format(
            doc.get("employee_name") or doc.employee, state))


def calibration_digest():
    """Daily: the placements that came into calibration since yesterday,
    told to each plant's HR Officers as one message, counted by review."""
    from hrms_addon.hrms_addon import talent_approval as approval
    from hrms_addon.hrms_addon.queries import aggregate

    rows = frappe.get_all(PLACEMENT, filters={"workflow_state": approval.CALIBRATION, "docstatus": 0,
                                              "submitted_on": [">=", add_days(today(), -1)]},
                          fields=["talent_review", "branch", "department", aggregate("COUNT", "*", "n")],
                          group_by="talent_review, branch, department", limit_page_length=0)
    entries = []
    for row in rows:
        title = frappe.db.get_value(REVIEW, row.talent_review, "title") or row.talent_review
        line = _("{0}: {1} placement(s) from {2} ready to calibrate").format(
            title, row.n, row.department or row.branch or _("the review"))
        entries += [(user, line, REVIEW, row.talent_review) for user in people.hr_officers(row.branch, row.department)]
    talent_jobs.send_digest(entries, _("Placements waiting in calibration"), "Talent Review", None)


def placement_on_submit(doc, method=None):
    """Finalised. Test case 9: the placement locks, a development plan is
    drawn up from it, and the training in that plan goes to L&D. The
    employee's earlier plans learn whether this box reaches what they aimed
    at. A finalise over a whole board runs in the background
    (talent_board.advance), and what it tells HR goes as one digest."""
    _draw_up_development_plan(doc)
    _flag_flight_risk(doc)
    _mark_targets(doc)


def _nine_box(box):
    """The Nine Box record of a box number, read once a request."""
    if not box:
        return None
    found = getattr(frappe.local, "ha_nine_box_names", None)
    if found is None:
        found = {cint(row.box): row.name for row in frappe.get_all("Nine Box", fields=["name", "box"])}
        frappe.local.ha_nine_box_names = found
    return found.get(cint(box))


def _mark_targets(doc):
    """Each earlier development plan of the employee with a target box: is
    the box this review gave them at least that, on both axes?"""
    if not (doc.get("employee") and doc.get("box")):
        return
    numbers = {row.name: cint(row.box) for row in frappe.get_all("Nine Box", fields=["name", "box"])}
    for plan in frappe.get_all(PROGRAM, filters={"employee": doc.employee, "docstatus": ["!=", 2],
                                                 "placement": ["!=", doc.name], "target_box": ["is", "set"]},
                               fields=["name", "target_box", "target_reached"]):
        reached = 1 if rules.target_reached(doc.box, numbers.get(plan.target_box)) else 0
        if reached != cint(plan.target_reached):
            frappe.db.set_value(PROGRAM, plan.name, "target_reached", reached, update_modified=False)


def placement_on_cancel(doc, method=None):
    doc.status = "Cancelled"


def _draw_up_development_plan(doc):
    """A programme the employee is actually on, of the kind the box asks
    for: the development themes agreed for them as its objectives and first
    actions, then the development actions the year's appraisals agreed and
    nobody has completed, so the plan carries on from the appraisal rather
    than beside it. The box, and the action the grid suggests for it, are
    the council's alone (case 10): the employee and their mentor read this
    plan, so neither is written into it."""
    if doc.get("development_plan"):
        return doc.development_plan
    program_type = _program_type_for(doc.get("box"))
    agreed = _agreed_actions(doc)
    try:
        program = frappe.get_doc({
            "doctype": PROGRAM, "employee": doc.employee, "company": doc.get("company"),
            "program_type": program_type, "start_date": today(),
            "end_date": add_days(today(), 365), "placement": doc.name,
            "talent_review": doc.get("talent_review"), "box_name": doc.get("box_name"),
            "target_box": _nine_box(rules.target_box(doc.get("box"))),
            "objectives": "\n".join(row.theme for row in doc.get("themes") or []
                                    if (row.theme or "").strip()) or None,
            "actions": [{"action": row.theme, "by_when": add_days(today(), 180), "action_owner": doc.employee,
                         "by_whom": doc.get("employee_name") or doc.employee}
                        for row in doc.get("themes") or []]
            + [{"action": row.action, "duration": row.duration, "by_when": row.by_when,
                "by_whom": row.by_whom, "approved_cost": row.estimated_cost}
               for row in agreed if (row.action or "").strip()],
        })
        program.flags.ignore_permissions = True
        program.flags.ignore_mandatory = True
        program.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: development plan from a placement")
        return None
    doc.db_set("development_plan", program.name, update_modified=False)
    # the themes go to L&D now; a plan with none sends its actions when HR
    # enrols it, rather than the programme's name as a topic
    themes = [row.theme for row in doc.get("themes") or [] if (row.theme or "").strip()]
    if themes:
        _push_to_ld(program, themes)
    return program.name


def _agreed_actions(doc):
    """The development actions the year's appraisals agreed, in the order
    they were agreed, each once, leaving out those already completed."""
    names = [row.name for row in _year_appraisals(doc.get("employee"), doc.get("talent_review"))]
    if not names and doc.get("appraisal"):
        names = [doc.appraisal]
    if not names:
        return []
    rows = frappe.get_all("Development Action",
                          filters={"parent": ["in", names], "parenttype": "Appraisal",
                                   "parentfield": "custom_development_actions"},
                          fields=["parent", "action", "duration", "by_when", "by_whom", "estimated_cost",
                                  "completed_on"], order_by="idx asc", limit=200)
    order = {name: number for number, name in enumerate(names)}
    seen, kept = set(), []
    for row in sorted(rows, key=lambda row: order.get(row.parent, 0)):
        text = " ".join((row.action or "").split()).lower()
        if not text or text in seen or row.get("completed_on"):
            continue
        seen.add(text)
        kept.append(row)
    return kept


def _program_type_for(box):
    """Which programme the box asks for. The three boxes with the
    potential to lead get leadership; the middle of the grid gets a
    mentor; everyone else gets training."""
    if rules.is_top_talent(box, masters.grid()):
        return "Leadership Development"
    if cint(box) in (3, 5, 7):
        return "Mentoring and Coaching"
    return "Learning and Development"


def _push_to_ld(program, topics=None):
    """Test case 9's other half: the training assignments really reach the
    L&D module, as a Training Requisition the HR Officer picks up.

    The topics are passed in as text rather than as rows, because a
    placement's themes and a programme's actions are different documents
    and a field name guessed across the two of them is a field name that
    is wrong on one.
    """
    if program.get("training_requisition"):
        return program.training_requisition
    if topics is None:
        topics = [row.action for row in program.get("actions") or []]
    method = "Coaching" if program.program_type == "Mentoring and Coaching" else "Internal"
    rows = rules.topic_rows(topics, method) \
        or rules.topic_rows([program.get("objectives") or program.program_type], method)
    try:
        requisition = frappe.get_doc({
            "doctype": REQUISITION, "requested_by": frappe.session.user,
            "department": program.get("department"), "branch": program.get("branch"),
            "request_date": today(), "priority": "Medium", "status": "Draft",
            "topics": rows, "talent_program": program.name,
            "justification": _("From talent programme {0} ({1}).").format(
                program.name, program.program_type),
            "target_employees": [{"employee": program.employee,
                                  "skill_areas": ", ".join(row["topic"] for row in rows)[:500]}],
        })
        requisition.flags.ignore_permissions = True
        requisition.flags.ignore_mandatory = True
        requisition.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: sending a development plan to L&D")
        return None
    program.db_set("training_requisition", requisition.name, update_modified=False)
    _ask_hr_to_submit(requisition.name, program.get("branch"), program.get("department"),
                      program.get("employee_name") or program.employee,
                      _("development plan {0}").format(program.name))
    return requisition.name


def _ask_hr_to_submit(requisition, branch, department, who, why):
    """A requisition talent drafts is the branch HR Officer's to submit, so
    it goes into the Training Needs Assessment: they are told, and it is put
    on their list."""
    users = people.hr_officers(branch, department)
    if not users:
        return
    message = _("Training is requested for {0} ({1}). Submit requisition {2} so it goes into the Training "
                "Needs Assessment.").format(who, why, requisition)
    talent_jobs.tell(list(users), REQUISITION, requisition, message)
    talent_jobs.assign(REQUISITION, requisition, users, message)


def _flag_flight_risk(doc):
    """Test case 22: top talent somebody might lose is told to HR and the
    council, once a level (succession_rules.alert_needed). A finalise over a
    whole board tells them in one digest."""
    from hrms_addon.hrms_addon import succession_rules

    watched = masters.watched_risks()
    if not succession_rules.alert_needed(doc.get("top_talent"), doc.get("flight_risk"), watched,
                                         doc.get("risk_alerted")):
        return
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    # people_for, not holders: holders hands back rows, and the council
    # sits over every plant rather than in one of them
    users += list(people.people_for("Talent Council", doc.get("branch"), doc.get("department")))
    if not users:
        return
    talent_jobs.tell(list(dict.fromkeys(users)), doc.doctype, doc.name,
                     _("{0} is in box {1} ({2}) and flagged {3} flight risk. Retention action is "
                       "the council's to take.").format(
                         doc.get("employee_name") or doc.employee, doc.get("box"),
                         doc.get("box_name"), str(doc.flight_risk).lower()))
    doc.db_set({"risk_notified": 1, "risk_alerted": doc.flight_risk}, update_modified=False)


# ── 3. The programme ──────────────────────────────────────────────────
def program_validate(doc, method=None):
    from hrms_addon.hrms_addon import talent_program_approval as approval

    _fill_program_scores(doc)
    _fill_program_actions(doc)
    _check_program_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _fill_program_actions(doc):
    """Each action's status and progress kept with its completion date, and
    the plan's cost and its 70/20/10 mix read off them."""
    for row in doc.get("actions") or []:
        row.status, row.progress, completed = rules.action_state(row.as_dict(), today())
        if completed and not row.get("completed_on"):
            row.completed_on = completed
    errors = rules.action_errors([row.as_dict() for row in doc.get("actions") or []])
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(PROGRAM))
    found = rules.plan_investment([row.as_dict() for row in doc.get("actions") or []])
    doc.approved_investment = found["approved"]
    doc.actual_investment = found["actual"]
    doc.experience_share = found["mix"][rules.EXPERIENCE]
    doc.exposure_share = found["mix"][rules.EXPOSURE]
    doc.education_share = found["mix"][rules.EDUCATION]


def _fill_program_scores(doc):
    """Test case 2: what the appraisal said before the programme, and what
    it says after it. The effectiveness is the difference, not an
    opinion."""
    if not doc.get("employee"):
        return
    if doc.get("score_before") in (None, "") and doc.get("start_date"):
        doc.score_before = _appraisal_score(doc.employee, before=doc.start_date)
    if doc.get("end_date"):
        after = _appraisal_score(doc.employee, after=doc.end_date)
        if after is not None:
            doc.score_after = after
    doc.movement = rules.movement(doc.get("score_before"), doc.get("score_after"))
    doc.effectiveness = rules.effectiveness(doc.get("score_before"), doc.get("score_after"))


def _appraisal_score(employee, before=None, after=None):
    filters = {"employee": employee, "docstatus": 1}
    if before:
        filters["end_date"] = ["<=", getdate(before)]
    if after:
        filters["end_date"] = [">=", getdate(after)]
    found = frappe.get_all("Appraisal", filters=filters,
                           fields=["custom_total_score", "final_score"],
                           order_by="end_date desc" if before else "end_date asc", limit=1)
    if not found:
        return None
    return flt(found[0].custom_total_score or found[0].final_score or 0)


def _check_program_step(doc):
    from hrms_addon.hrms_addon import talent_program_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state,
                                      {"return_remarks": doc.get("return_remarks")})
        if new_state == approval.ENROLLED and old_state in (None, approval.DRAFT):
            errors = rules.program_errors({
                "employee": doc.get("employee"), "program_type": doc.get("program_type"),
                "mentor": doc.get("mentor"), "start_date": doc.get("start_date"),
                "end_date": doc.get("end_date"),
                "actions": [row.as_dict() for row in doc.get("actions") or []]}) + errors
        if old_state == approval.UNDER_REVIEW and new_state == approval.CLOSED:
            errors += rules.review_errors({
                "score_after": doc.get("score_after"),
                "outcome_notes": doc.get("outcome_notes"), "decision": doc.get("decision")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(PROGRAM))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state == approval.ENROLLED:
        _push_to_ld(doc)
        _tell_program(doc)


def _tell_program(doc):
    users = []
    if doc.get("mentor"):
        user = frappe.db.get_value("Employee", doc.mentor, "user_id")
        if user:
            users.append(user)
    user = frappe.db.get_value("Employee", doc.employee, "user_id")
    if user:
        users.append(user)
    users = [name for name in dict.fromkeys(users) if name]
    if not users:
        return
    talent_jobs.tell(users, doc.doctype, doc.name,
                     _("{0} is on the {1} programme.").format(
                         doc.get("employee_name") or doc.employee, doc.program_type))


def program_on_submit(doc, method=None):
    """Closed. Test case 3: the decision taken at the end is acted on. A
    succession pipeline decision puts the employee on the bench for the
    role the programme was aimed at, else their own role's, where a
    succession position exists; a promotion is drafted as a position
    change, into the role the programme was aimed at when it was; a
    replacement drafts the requisition for whoever replaces them."""
    step = rules.DECISION_STEPS.get(doc.get("decision"))
    if step == "promote":
        _promote_from_program(doc)
        return
    if step == "replace":
        _replace_from_program(doc)
        return
    if step != "pool":
        return
    plan = frappe.db.get_value(POSITION, doc.succession_position, ["designation", "company"], as_dict=True) \
        if doc.get("succession_position") else None
    position = _add_to_pool(doc.employee, (plan or doc).get("designation"), (plan or doc).get("company"),
                            placement=doc.get("placement"))
    if position:
        return
    # nobody is quietly left off a pipeline they were put on: where there
    # is no bench to add them to — their own role has no succession
    # position, or they already hold it — HR is told to find the role the
    # decision meant
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if users:
        talent_jobs.tell(list(users), doc.doctype, doc.name,
                         _("{0} was put in the succession pipeline, but there is no succession "
                           "position to add them to. Name the role they are being grown for.").format(
                             doc.get("employee_name") or doc.employee))


def program_on_cancel(doc, method=None):
    doc.status = "Cancelled"
    doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + PROGRAM_RECORDS


def _promote_from_program(doc):
    """A programme closed with a decision to promote: the promotion drafted
    for HR, into the role the programme was aimed at, from the day its
    holder leaves when that is known. Without a role, HR names it."""
    position = frappe.get_doc(POSITION, doc.succession_position) if doc.get("succession_position") else None
    change = _draft_promotion(doc.employee, position=position, program=doc.name,
                              effective=position.get("retirement_or_exit_due") if position else None)
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if not users:
        return change
    name = doc.get("employee_name") or doc.employee
    if not change:
        message = _("{0}'s programme closed with a decision to promote, and no position change could be "
                    "drafted. Raise it on Employee Position Change.").format(name)
    elif position:
        message = _("{0}'s programme closed with a decision to promote: position change {1} is drafted, "
                    "into {2}. Complete it and send it for signature.").format(name, change, position.designation)
    else:
        message = _("{0}'s programme closed with a decision to promote: position change {1} is drafted. "
                    "Name the new role, complete it and send it for signature.").format(name, change)
    talent_jobs.tell(list(users), doc.doctype, doc.name, message)
    return change


def _replace_from_program(doc):
    """A programme closed with a decision to replace the employee: the
    requisition for whoever replaces them, drafted for HR. The employee's
    own exit, if it comes to that, is HR's to raise."""
    held = frappe.db.get_value("Employee", doc.employee, ["designation", "department", "branch", "company"],
                               as_dict=True) or frappe._dict()
    name = doc.get("employee_name") or doc.employee
    requisition = _draft_requisition(
        held.designation or doc.get("designation"), held.company or doc.get("company"),
        branch=held.branch or doc.get("branch"), department=held.department or doc.get("department"),
        reason_type=rules.REPLACEMENT, program=doc.name,
        why=_("{0} is to be replaced as {1}: the decision at the close of talent programme {2}.").format(
            name, held.designation or doc.get("designation"), doc.name))
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if users:
        talent_jobs.tell(list(users), doc.doctype, doc.name, (
            _("{0}'s programme closed with a decision to replace them: job requisition {1} is drafted. "
              "Complete it and send it for approval.").format(name, requisition) if requisition else
            _("{0}'s programme closed with a decision to replace them, and no job requisition could be "
              "drafted. Raise one.").format(name)))
    return requisition


def _add_to_pool(employee, designation, company, placement=None,
                 readiness=None, box_name=None):
    """Put somebody on the bench for their own role, where that role is
    one the council tracks. A role nobody has opened a succession position
    for is not one to invent here."""
    if not designation:
        return None
    position = frappe.db.get_value(POSITION, {"designation": designation, "company": company,
                                              "docstatus": ["<", 2]}, "name")
    if not position:
        return None
    doc = frappe.get_doc(POSITION, position)
    if any(row.employee == employee for row in doc.get("candidates") or []):
        return position
    if doc.get("incumbent") == employee:
        # they already hold the role, so this is not the bench they belong
        # on: nothing is added, and saying so is what lets the caller tell
        # somebody rather than drop the decision
        return None
    doc.append("candidates", {"employee": employee, "readiness": readiness or rules.EMERGING,
                              "placement": placement, "box_name": box_name,
                              "nominated_by": frappe.session.user})
    doc.flags.ignore_permissions = True
    try:
        doc.save()
    except Exception:
        frappe.log_error(title="HRMS Addon: adding to the succession pool")
        return None
    # a confirmed position is saved after submit, where validate does not
    # run, so the bench is counted again here rather than going stale
    if doc.docstatus == 1:
        _refresh_bench(doc)
    return position


def _refresh_bench(doc):
    candidates = [row.as_dict() for row in doc.get("candidates") or []]
    counts = rules.bench_strength(candidates)
    doc.db_set({
        "ready_now": counts[rules.READY_NOW], "ready_soon": counts[rules.READY_SOON],
        "emerging": counts[rules.EMERGING],
        "bench_depth": len([row for row in candidates if row.get("readiness") != rules.GAP]),
        "coverage": rules.coverage(candidates),
        "gap": 1 if rules.is_gap(candidates) else 0,
    }, update_modified=False)


# ── 4. Succession ─────────────────────────────────────────────────────
def position_validate(doc, method=None):
    from hrms_addon.hrms_addon import succession_approval as approval, succession_risk

    _fill_bench(doc)
    _restart_exit_watch(doc)
    succession_risk.fill(doc)
    _check_position_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _fill_bench(doc):
    """Test case 13: how deep the bench is, and whether the role is
    covered — worked out from the successors, never typed. A successor
    named from a placement and given no readiness is suggested the one the
    Readiness Levels draw from their box."""
    for row in doc.get("candidates") or []:
        if not row.get("readiness") and row.get("placement"):
            row.readiness = masters.suggested_readiness(frappe.db.get_value(PLACEMENT, row.placement, "box"))
    _count_bench(doc)
    if not doc.gap:
        doc.gap_confirmed = 0


def _count_bench(doc):
    """The bench counted. Every figure here may change after the plan is
    confirmed, as successors are added to it."""
    candidates = [row.as_dict() for row in doc.get("candidates") or []]
    counts = rules.bench_strength(candidates)
    doc.ready_now = counts[rules.READY_NOW]
    doc.ready_soon = counts[rules.READY_SOON]
    doc.emerging = counts[rules.EMERGING]
    doc.bench_depth = len([row for row in candidates if row.get("readiness") != rules.GAP])
    doc.coverage = rules.coverage(candidates)
    doc.gap = 1 if rules.is_gap(candidates) else 0


def _restart_exit_watch(doc):
    """A new holder, or a new last day for the holder, is watched from the
    first mark again. A new holder's last day is their own exit's, if they
    have one raised, and so is the holder's on a new plan with none typed."""
    before = doc.get_doc_before_save()
    if before and before.get("incumbent") != doc.get("incumbent"):
        doc.retirement_or_exit_due = _exit_of(doc.get("incumbent")).get("custom_relieving_date")
        doc.exit_alerted = 0
    elif before and str(before.get("retirement_or_exit_due") or "") != str(doc.get("retirement_or_exit_due") or ""):
        doc.exit_alerted = 0
    elif not before and not doc.get("retirement_or_exit_due"):
        doc.retirement_or_exit_due = _exit_of(doc.get("incumbent")).get("custom_relieving_date")


def _check_position_step(doc):
    from hrms_addon.hrms_addon import succession_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"),
            "candidates": [row.as_dict() for row in doc.get("candidates") or []],
            "gap_notes": doc.get("gap_notes")})
        if new_state == approval.NOMINATIONS and old_state in (None, approval.DRAFT):
            errors = rules.position_errors(_position_facts(doc)) + errors
        if old_state == approval.NOMINATIONS and new_state == approval.COUNCIL_REVIEW:
            errors += rules.position_errors(_position_facts(doc))
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(POSITION))
        if new_state != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_position(doc, new_state)


def _position_facts(doc):
    return {"designation": doc.get("designation"), "company": doc.get("company"),
            "risk_level": doc.get("risk_level"), "incumbent": doc.get("incumbent"),
            "single_person_role": doc.get("single_person_role"),
            "candidates": [row.as_dict() for row in doc.get("candidates") or []]}


def _tell_position(doc, state):
    from hrms_addon.hrms_addon import succession_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"),
                              doc.get("department"))
    if not users:
        return
    message = _("Succession for {0} is waiting at {1}.").format(doc.designation, state)
    talent_jobs.tell(list(users), doc.doctype, doc.name, message)
    talent_jobs.assign(doc.doctype, doc.name, users, message)


def position_on_submit(doc, method=None):
    """Confirmed. Test case 14: a confirmed gap drafts the requisition that
    becomes the job opening in resourcing once Luuka's approvals pass it
    (the opening is not raised round them), and the development needs of
    everyone not ready now go to L&D. Each of them gets a development plan
    aimed at the role, and a holder already on their way out is acted on
    at once."""
    if doc.get("gap") and doc.get("gap_confirmed"):
        if _draft_requisition_for(doc):
            doc.db_set("requisition_drafted_for", doc.get("retirement_or_exit_due"), update_modified=False)
    _send_needs_to_ld(doc)
    _plan_successor_development(doc)
    _act_on_exit(doc)


def position_before_update_after_submit(doc, method=None):
    """A confirmed plan changed: successors added or a new holder named.
    The bench is counted again, and the exit watch restarted for a new
    holder or a new last day."""
    from hrms_addon.hrms_addon import succession_risk

    _count_bench(doc)
    _restart_exit_watch(doc)
    succession_risk.fill(doc)


def position_on_update_after_submit(doc, method=None):
    _plan_successor_development(doc)
    _act_on_exit(doc)


def position_on_cancel(doc, method=None):
    doc.status = "Cancelled"
    doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + POSITION_RECORDS


# ── 4a. Each successor grown for the role ─────────────────────────────
def _plan_successor_development(doc):
    """Every successor not ready yet gets a development plan aimed at the
    role: coached by its holder while there is one, its actions the
    development needs the council named, its training the requisition
    already sent to L&D for them. HR enrols them."""
    if doc.docstatus != 1:
        return []
    mentor = doc.get("incumbent") if doc.get("incumbent") and _active({doc.incumbent}) else None
    rows = rules.successors_to_develop(doc.get("candidates") or [])
    employed = _active({row.employee for row in rows})
    made = []
    for row in rows:
        if row.get("development_plan") or row.employee == doc.get("incumbent") or row.employee not in employed:
            continue
        existing = frappe.db.get_value(PROGRAM, {"employee": row.employee, "succession_position": doc.name,
                                                 "docstatus": ["<", 2]}, "name")
        if existing:
            row.db_set("development_plan", existing, update_modified=False)
            continue
        start = today()
        end = rules.successor_plan_end(row.readiness, start, doc.get("retirement_or_exit_due"))
        name = row.get("employee_name") or frappe.db.get_value("Employee", row.employee, "employee_name") \
            or row.employee
        try:
            program = frappe.get_doc({
                "doctype": PROGRAM, "employee": row.employee, "company": doc.company,
                "program_type": rules.successor_program(bool(mentor)), "mentor": mentor,
                "start_date": start, "end_date": end, "succession_position": doc.name,
                "placement": row.get("placement"), "box_name": row.get("box_name"),
                "talent_review": frappe.db.get_value(PLACEMENT, row.placement, "talent_review")
                if row.get("placement") else None,
                "objectives": _("To be ready to take over as {0} by {1}.").format(doc.designation, format_date(end)),
                "training_requisition": row.get("training_requisition"),
                "actions": [{"action": text, "by_when": end, "by_whom": name}
                            for text in rules.plan_actions(row.get("development_needs"))],
            })
            program.flags.ignore_permissions = True
            program.flags.ignore_mandatory = True
            program.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: a successor's development plan")
            continue
        row.db_set("development_plan", program.name, update_modified=False)
        if row.get("training_requisition"):
            # the needs went to L&D before the plan was drawn up: the
            # requisition names the plan its training comes back to
            frappe.db.set_value(REQUISITION, row.training_requisition, "talent_program", program.name,
                                update_modified=False)
        made.append(program)
    users = people.hr_officers(doc.get("branch"), doc.get("department")) if made else []
    if users:
        talent_jobs.tell(list(users), doc.doctype, doc.name,
                         _("Development plans are drafted for the successors to {0}: {1}. Enrol each to start "
                           "it.").format(doc.designation, ", ".join(
                          "%s (%s)" % (program.get("employee_name") or program.employee, program.name)
                          for program in made)))
    return made


# ── 4b. The holder leaving ────────────────────────────────────────────
def separation_on_update(doc, method=None):
    """An exit raised for the holder of a critical role (Exits, 4.5 and
    4.6): each plan they hold learns their last day and acts on it."""
    if not doc.get("employee") or not doc.get("custom_relieving_date"):
        return
    for name in frappe.get_all(POSITION, filters={"incumbent": doc.employee, "docstatus": ["<", 2]},
                               pluck="name", limit=20):
        position = frappe.get_doc(POSITION, name)
        if str(position.get("retirement_or_exit_due") or "") != str(doc.custom_relieving_date):
            position.db_set({"retirement_or_exit_due": doc.custom_relieving_date, "exit_alerted": 0},
                            update_modified=False)
        if doc.get("custom_succession_position") != name:
            doc.db_set("custom_succession_position", name, update_modified=False)
        _act_on_exit(position)


def separation_on_cancel(doc, method=None):
    """The exit is off, cancelled or deleted: a plan that took its date from
    it no longer expects the holder to go. What it drafted stays, for HR to
    keep or close."""
    if not doc.get("employee") or not doc.get("custom_relieving_date"):
        return
    for name in frappe.get_all(POSITION, filters={"incumbent": doc.employee, "docstatus": ["<", 2],
                                                  "retirement_or_exit_due": doc.custom_relieving_date},
                               pluck="name", limit=20):
        frappe.db.set_value(POSITION, name, {"retirement_or_exit_due": None, "exit_alerted": 0},
                            update_modified=False)
        drafted = drafted_for(name)
        names = [entry.name for entry in (drafted.get("promotion"), drafted.get("requisition")) if entry]
        position = frappe.db.get_value(POSITION, name, ["designation", "branch", "department"], as_dict=True)
        users = people.hr_officers(position.branch, position.department) if names else []
        if users:
            talent_jobs.tell(list(users), POSITION, name,
                          _("{0} is no longer leaving {1}. Close what was drafted for the exit if it is not "
                            "needed: {2}.").format(doc.get("employee_name") or doc.employee,
                                                   position.designation, ", ".join(names)))


def _exit_of(employee):
    """The employee's exit still on foot, if there is one."""
    if not employee:
        return frappe._dict()
    found = frappe.get_all(SEPARATION, filters={"employee": employee, "docstatus": ["<", 2],
                                                "custom_relieving_date": ["is", "set"]},
                           fields=["name", "custom_relieving_date", "custom_reason", "docstatus"],
                           order_by="creation desc", limit=1)
    return found[0] if found else frappe._dict()


def _act_on_exit(doc):
    """What the plan does about its holder leaving (rules.exit_step): a
    promotion drafted for the successor ready now, or the requisition for a
    replacement; and HR and the council told at each mark while nobody is
    ready."""
    if doc.docstatus == 2 or not doc.get("retirement_or_exit_due"):
        return None
    due = str(doc.retirement_or_exit_due)[:10]
    drafted = drafted_for(doc.name)
    promotion, requisition = drafted.get("promotion"), drafted.get("requisition")
    live = requisition and requisition.status not in CLOSED_REQUISITION
    successor = _successor_for(doc)
    step = rules.exit_step({
        "exit_due": due, "confirmed": doc.docstatus == 1, "ready": bool(successor or promotion),
        "promotion": bool(promotion) or str(doc.get("promotion_drafted_for") or "")[:10] == due,
        "requisition": bool(live) or str(doc.get("requisition_drafted_for") or "")[:10] == due,
        "alerted": doc.get("exit_alerted")}, today())
    news = None
    # each is tried once for a given last day: a draft HR delete is not
    # made again the next morning, and a draft that failed is told once
    if step["promote"] and successor:
        name = _draft_promotion(successor.get("employee"), position=doc, effective=due)
        doc.db_set("promotion_drafted_for", due, update_modified=False)
        holder = doc.get("incumbent_name") or doc.get("incumbent")
        named = successor.get("employee_name") or successor.get("employee")
        if name:
            _write_handover(doc)
            news = _("{0} leaves on {1}, and {2} is ready now: their promotion into the role is drafted as "
                     "position change {3}, from that day. Complete it and send it for signature.").format(
                holder, format_date(due), named, name)
        else:
            news = _("{0} leaves on {1}, and {2} is ready now, but their promotion could not be drafted. "
                     "Raise it on Employee Position Change.").format(holder, format_date(due), named)
    if step["recruit"]:
        _draft_requisition_for(doc)
        doc.db_set("requisition_drafted_for", due, update_modified=False)
        drafted = drafted_for(doc.name)
    if step["alert"]:
        doc.db_set("exit_alerted", step["alert"], update_modified=False)
    if step["alert"] or step["recruit"]:
        news = _exit_alert(doc, step["days"], drafted)
    if news:
        _tell_council(doc, news)
    return step


def _successor_for(doc):
    rows = [row.as_dict() for row in doc.get("candidates") or []]
    row = rules.ready_successor(rows, leaver=doc.get("incumbent"),
                                active=_active({row.get("employee") for row in rows}))
    if row and not row.get("employee_name"):
        row["employee_name"] = frappe.db.get_value("Employee", row.get("employee"), "employee_name")
    return row


def _active(employees):
    employees = sorted(name for name in employees if name)
    return set(frappe.get_all("Employee", filters={"name": ["in", employees], "status": "Active"},
                              pluck="name")) if employees else set()


def _exit_alert(doc, days, drafted):
    """What HR and the council are told as the holder's last day nears."""
    holder = doc.get("incumbent_name") or doc.get("incumbent") or _("The holder")
    when = format_date(doc.retirement_or_exit_due)
    if doc.docstatus != 1:
        head = _("{0} leaves {1} on {2}, in {3} days, and its succession plan is not confirmed.").format(
            holder, doc.designation, when, days)
    else:
        head = _("{0} leaves {1} on {2}, in {3} days, and nobody is ready to take over.").format(
            holder, doc.designation, when, days)
    requisition, opening = drafted.get("requisition"), drafted.get("opening")
    if opening:
        tail = _("The replacement is being recruited on job opening {0}.").format(opening.name)
    elif requisition and requisition.status in CLOSED_REQUISITION:
        tail = _("Job requisition {0} for a replacement is {1}.").format(requisition.name,
                                                                        _(requisition.status).lower())
    elif requisition:
        tail = _("Job requisition {0} for a replacement is at {1}.").format(
            requisition.name, _(requisition.get("workflow_state") or requisition.status))
    elif doc.docstatus == 1:
        tail = _("There is no job requisition for a replacement. Raise one.")
    else:
        tail = _("Confirm it, so a promotion or a replacement can be drafted.")
    return "%s %s" % (head, tail)


def _tell_council(doc, message):
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    users += list(people.people_for("Talent Council", doc.get("branch"), doc.get("department")))
    users = list(dict.fromkeys(users))
    if users:
        talent_jobs.tell(users, POSITION, doc.name, message)


def drafted_for(position):
    return drafted_for_many([position]).get(position, {})


def drafted_for_many(positions):
    """What each plan has led to: {plan: {"promotion", "requisition",
    "opening", "exit"}}, the latest of each. The promotion is the position
    change drafted for its successor (cancelled ones left out); the
    requisition is for a replacement, whatever became of it; the opening is
    the one that requisition became; the exit is its holder's."""
    names = sorted({name for name in positions if name})
    if not names:
        return {}
    out = {name: {} for name in names}
    for row in frappe.get_all(CHANGE, filters={"succession_position": ["in", names], "docstatus": ["<", 2]},
                              fields=["name", "succession_position", "employee", "employee_name", "status",
                                      "docstatus", "effective_date"], order_by="creation asc", limit=0):
        out[row.succession_position]["promotion"] = row
    requisitions = frappe.get_all(JOB_REQUISITION, filters={"custom_succession_position": ["in", names]},
                                  fields=["name", "custom_succession_position", "status", "workflow_state",
                                          "expected_by"], order_by="creation asc", limit=0)
    for row in requisitions:
        if row.status != "Cancelled" or "requisition" not in out[row.custom_succession_position]:
            out[row.custom_succession_position]["requisition"] = row
    by_requisition = {entry["requisition"].name: name for name, entry in out.items() if entry.get("requisition")}
    if by_requisition:
        for row in frappe.get_all("Job Opening", filters={"job_requisition": ["in", sorted(by_requisition)]},
                                  fields=["name", "job_requisition", "status"], order_by="creation asc", limit=0):
            out[by_requisition[row.job_requisition]]["opening"] = row
    for row in frappe.get_all(SEPARATION, filters={"custom_succession_position": ["in", names],
                                                   "docstatus": ["<", 2]},
                              fields=["name", "custom_succession_position", "employee", "custom_reason",
                                      "custom_relieving_date", "docstatus"], order_by="creation asc", limit=0):
        out[row.custom_succession_position]["exit"] = row
    return out


def _draft_promotion(employee, position=None, program=None, effective=None):
    """A promotion drafted as an Employee Position Change for HR to send
    through its signatures: into the plan's role when there is a plan,
    from the day its holder leaves, reporting where the holder reported.
    One already drafted for the plan, or for the programme, is returned
    instead."""
    if not employee:
        return None
    filters = {"docstatus": ["<", 2]}
    if position:
        filters["succession_position"] = position.name
    elif program:
        filters["talent_program"] = program
    existing = frappe.db.get_value(CHANGE, filters, "name") if (position or program) else None
    if existing:
        return existing
    values = {"doctype": CHANGE, "change_type": "Promotion", "employee": employee,
              "succession_position": position.name if position else None, "talent_program": program,
              "effective_date": effective, "appraisal_score": _score_of(employee) or None}
    if position:
        held = frappe.db.get_value("Employee", employee, ["branch", "department"], as_dict=True) or frappe._dict()
        above = frappe.db.get_value("Employee", position.incumbent, "reports_to") if position.get("incumbent") else None
        values.update({
            "new_designation": position.designation, "desired_position": position.designation,
            "new_branch": position.branch if position.get("branch") and position.branch != held.branch else None,
            "new_department": position.department
            if position.get("department") and position.department != held.department else None,
            "new_supervisor": above if above and above != employee else None})
    try:
        change = frappe.get_doc(values)
        change.flags.ignore_permissions = True
        change.flags.ignore_mandatory = True
        change.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: a promotion drafted from talent")
        return None
    return change.name


def _score_of(employee):
    """The year to date the promotion's preamble quotes: the employee's
    latest finalised placement's, else their latest completed appraisal's."""
    found = frappe.get_all(PLACEMENT, filters={"employee": employee, "docstatus": 1},
                           fields=["performance_score"], order_by="creation desc", limit=1)
    if found and flt(found[0].performance_score):
        return flt(found[0].performance_score)
    found = frappe.get_all("Appraisal", filters={"employee": employee, "docstatus": 1},
                           fields=["custom_annual_score", "custom_total_score", "final_score"],
                           order_by="end_date desc", limit=1)
    if not found:
        return None
    return flt(found[0].custom_annual_score or found[0].custom_total_score or found[0].final_score) or None


def _draft_requisition_for(doc):
    """The requisition for whoever fills the plan's role when nobody on its
    bench can: a replacement for a holder leaving or a role nobody holds,
    else an addition who grows into it."""
    holder = doc.get("incumbent_name") or doc.get("incumbent")
    due = doc.get("retirement_or_exit_due")
    if due and holder:
        why = _("{0} leaves on {1} and nobody on the succession plan ({2}) is ready to take over.").format(
            holder, format_date(due), doc.name)
    elif not holder:
        why = _("Nobody holds the role and nobody on the succession plan ({0}) is ready for it.").format(doc.name)
    else:
        why = _("Nobody on the succession plan ({0}) is ready to take over from {1}.").format(doc.name, holder)
    branch = doc.get("branch") or (frappe.db.get_value("Employee", doc.incumbent, "branch")
                                   if doc.get("incumbent") else None)
    return _draft_requisition(doc.designation, doc.company, branch=branch, department=doc.get("department"),
                              reason_type=rules.requisition_reason(due, doc.get("incumbent")),
                              expected_by=due, why=why, position=doc.name)


def _draft_requisition(designation, company, branch=None, department=None, reason_type=None,
                       expected_by=None, why=None, position=None, program=None):
    """A Job Requisition drafted for HR to complete (how to recruit, the
    salary) and send through Luuka's approvals, after which it becomes the
    job opening. One already open for the plan or the programme is
    returned, and one already open for the same role at the same plant is
    taken over rather than doubled."""
    if not designation or not company:
        return None
    open_ = ["not in", CLOSED_REQUISITION]
    for field, value in (("custom_succession_position", position), ("custom_talent_program", program)):
        if value:
            found = frappe.db.get_value(JOB_REQUISITION, {field: value, "status": open_}, "name")
            if found:
                return found
    same = frappe.db.get_value(JOB_REQUISITION, {
        "designation": designation, "company": company, "custom_branch": branch, "status": open_,
        "custom_succession_position": ["is", "not set"], "custom_talent_program": ["is", "not set"]}, "name")
    if same:
        frappe.db.set_value(JOB_REQUISITION, same, {"custom_succession_position": position,
                                                    "custom_talent_program": program}, update_modified=False)
        return same
    try:
        requisition = frappe.get_doc({
            "doctype": JOB_REQUISITION, "designation": designation, "company": company,
            "department": department, "custom_branch": branch, "no_of_positions": 1, "posting_date": today(),
            "expected_by": expected_by, "custom_reason_type": reason_type or rules.REPLACEMENT,
            "reason_for_requesting": why, "custom_succession_position": position,
            "custom_talent_program": program})
        requisition.flags.ignore_permissions = True
        requisition.flags.ignore_mandatory = True
        # how to recruit is HR's to choose: the requisition asks for it when
        # they send it on (job_requisition.validate)
        requisition.flags.drafted_by_talent = True
        requisition.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: a job requisition drafted from talent")
        return None
    return requisition.name


def _write_handover(doc):
    """A clearance already drawn up for the holder gets the handover line,
    where nobody has written one (exits.draw_up_clearance writes it on a
    clearance drawn up later)."""
    if not doc.get("incumbent"):
        return
    clearance = frappe.db.get_value(CLEARANCE, {"employee": doc.incumbent, "docstatus": 0}, "name")
    if not clearance:
        return
    row = frappe.db.get_value("Clearance Item", {"parent": clearance, "parenttype": CLEARANCE, "section": "A",
                                                 "item": rules.HANDOVER_ITEM}, ["name", "remarks"], as_dict=True)
    note = handover_for(doc.incumbent)
    if row and note and not (row.remarks or "").strip():
        # written for the employee, so it does not account for the report
        frappe.db.set_value("Clearance Item", row.name, {"remarks": note, "drawn_remarks": note},
                            update_modified=False)


def handover_for(employee):
    """The clearance's handover line for a holder of critical roles (box A,
    "Handover report"): who takes each over. None for anybody else."""
    notes = []
    for position in frappe.get_all(POSITION, filters={"incumbent": employee, "docstatus": ["<", 2]},
                                   fields=["name", "designation"], limit=5):
        promotion = drafted_for(position.name).get("promotion")
        if promotion:
            successor = promotion.employee_name or promotion.employee
        else:
            row = _successor_for(frappe.get_doc(POSITION, position.name))
            successor = (row.get("employee_name") or row.get("employee")) if row else None
        notes.append(rules.handover_note(position.designation, successor))
    return "; ".join(notes)[:140] or None


# ── 4c. The promotion into the role approved ──────────────────────────
def change_on_submit(doc, method=None):
    """Employee Position Change approved. A promotion into a planned role
    hands the role over: the plan names its new holder and the one before,
    and takes them off its own bench."""
    if doc.get("change_type") != "Promotion" or not doc.get("succession_position"):
        return
    position = frappe.get_doc(POSITION, doc.succession_position)
    if position.docstatus != 1 or position.get("incumbent") == doc.employee \
            or (doc.get("new_designation") and doc.new_designation != position.designation):
        return
    before = position.get("incumbent")
    position.previous_incumbent = before
    position.previous_incumbent_name = position.get("incumbent_name")
    position.handed_over_on = doc.get("effective_date") or today()
    position.incumbent = doc.employee
    position.set("candidates", [row for row in position.candidates if row.employee != doc.employee])
    for number, row in enumerate(position.candidates, 1):
        row.idx = number
    position.flags.ignore_permissions = True
    position.save()
    # the rest of the bench is coached by the role's holder: now the new one
    if before:
        for name in frappe.get_all(PROGRAM, filters={"succession_position": position.name, "docstatus": 0,
                                                     "mentor": before}, pluck="name"):
            frappe.db.set_value(PROGRAM, name, "mentor", doc.employee, update_modified=False)


def change_on_cancel(doc, method=None):
    """The promotion undone: the plan names its previous holder again, and
    the successor is back on its bench, ready now."""
    if doc.get("change_type") != "Promotion" or not doc.get("succession_position"):
        return
    position = frappe.get_doc(POSITION, doc.succession_position)
    if position.docstatus != 1 or position.get("incumbent") != doc.employee \
            or not position.get("previous_incumbent"):
        return
    position.incumbent = position.previous_incumbent
    for field in ("previous_incumbent", "previous_incumbent_name", "handed_over_on"):
        position.set(field, None)
    position.append("candidates", {"employee": doc.employee, "readiness": rules.READY_NOW,
                                   "nominated_by": frappe.session.user, "idx": len(position.candidates) + 1})
    position.flags.ignore_permissions = True
    position.save()


@frappe.whitelist()
def get_follow_through(position):
    """The plan's form: what its holder's exit and its bench have led to."""
    doc = frappe.get_doc(POSITION, position)
    doc.check_permission("read")
    drafted = drafted_for(doc.name)
    plans = [row.development_plan for row in doc.get("candidates") or [] if row.get("development_plan")]
    from hrms_addon.hrms_addon import talent_reports

    progress = talent_reports.plan_progress(plans) if plans else {}
    successor = _successor_for(doc)
    return {
        "exit": drafted.get("exit"), "promotion": drafted.get("promotion"),
        "requisition": drafted.get("requisition"), "opening": drafted.get("opening"),
        "days": rules.days_until(doc.get("retirement_or_exit_due"), today()),
        "window": rules.EXIT_WINDOW,
        "successor": {"employee": successor.get("employee"), "employee_name": successor.get("employee_name")}
        if successor else None,
        "plans": {name: progress.get(name) for name in plans},
    }


def _send_needs_to_ld(doc):
    """What the bench needs before it is a bench, as one requisition per
    successor, so L&D can schedule against a named person."""
    needs = rules.development_needs([row.as_dict() for row in doc.get("candidates") or []])
    if not needs:
        return 0
    sent = 0
    for row in doc.get("candidates") or []:
        if row.get("training_requisition") or row.readiness == rules.READY_NOW:
            continue
        gaps = (row.get("development_needs") or "").strip()
        if not gaps:
            continue
        try:
            requisition = frappe.get_doc({
                "doctype": REQUISITION, "requested_by": frappe.session.user,
                "department": doc.get("department"), "branch": doc.get("branch"),
                "request_date": today(), "priority": "High" if doc.get("gap") else "Medium",
                "status": "Draft",
                # one topic a need, as the successor's plan has one action a need
                "topics": rules.topic_rows(rules.plan_actions(gaps), "On the Job"),
                "justification": _("Succession for {0}: {1} is {2}.").format(
                    doc.designation, row.get("employee_name") or row.employee, row.readiness),
                "target_employees": [{"employee": row.employee, "skill_areas": gaps[:500]}],
            })
            requisition.flags.ignore_permissions = True
            requisition.flags.ignore_mandatory = True
            requisition.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: succession development needs to L&D")
            continue
        row.db_set("training_requisition", requisition.name, update_modified=False)
        _ask_hr_to_submit(requisition.name, doc.get("branch"), doc.get("department"),
                          row.get("employee_name") or row.employee,
                          _("successor for {0}").format(doc.designation))
        sent += 1
    if sent:
        doc.db_set("needs_sent_on", today(), update_modified=False)
    return sent


# ── 5. The graduate trainee ───────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def trainee_from_applicant(job_applicant, cohort=None, start_date=None):
    """Test case 16: the applicant in resourcing becomes a trainee on
    hire, state Recruited."""
    from hrms_addon.hrms_addon import graduates

    existing = frappe.db.get_value(TRAINEE, {"job_applicant": job_applicant,
                                             "docstatus": ["<", 2]}, "name")
    if existing:
        return existing
    applicant = frappe.db.get_value(
        "Job Applicant", job_applicant,
        ["applicant_name", "designation", "job_title", "custom_branch"], as_dict=True)
    if not applicant:
        frappe.throw(_("There is no such applicant."))
    # the applicant record itself carries neither company nor department:
    # both belong to the opening they applied against
    opening = frappe.db.get_value("Job Opening", applicant.job_title,
                                  ["company", "department", "designation"],
                                  as_dict=True) if applicant.job_title else None
    opening = opening or frappe._dict()
    doc = frappe.get_doc({
        "doctype": TRAINEE, "job_applicant": job_applicant,
        "trainee_name": applicant.applicant_name,
        "cohort": graduates.cohort_of_text(cohort or _("Graduate Intake {0}").format(getdate(today()).year),
                                           opening.company),
        "company": opening.company or frappe.defaults.get_user_default("Company"),
        "home_department": opening.department, "home_branch": applicant.custom_branch,
        "designation": applicant.designation or opening.designation,
        "start_date": start_date or today()})
    doc.insert()
    return doc.name


def trainee_validate(doc, method=None):
    from hrms_addon.hrms_addon import graduates, trainee_approval as approval

    graduates.trainee_milestones(doc)
    _fill_trainee(doc)
    _check_trainee_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.RECRUITED


def _fill_trainee(doc):
    milestones = [row.as_dict() for row in doc.get("milestones") or []]
    scored = [flt(row.get("score")) for row in milestones if row.get("score") not in (None, "")]
    doc.milestones_passed = len([row for row in milestones
                                 if row.get("result") in ("Pass", "Final Pass")])
    doc.average_score = round(sum(scored) / len(scored), 2) if scored else None
    doc.last_result = milestones[-1].get("result") if milestones else None
    for row in doc.get("milestones") or []:
        if row.score not in (None, "") and not row.result:
            row.result = rules.milestone_outcome(row.score, final=_is_final(doc, row))


def _is_final(doc, row):
    return rules.final_milestone(row.get("due_on"), row is doc.milestones[-1], doc.get("end_date"))


def _check_trainee_step(doc):
    from hrms_addon.hrms_addon import trainee_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"), "exit_reason": doc.get("exit_reason")})
        if new_state == approval.IN_INDUCTION and old_state in (None, approval.RECRUITED):
            errors = rules.trainee_errors({
                "job_applicant": doc.get("job_applicant"),
                "trainee_name": doc.get("trainee_name"), "cohort": doc.get("cohort"),
                "start_date": doc.get("start_date")}) + errors
        if old_state == approval.IN_INDUCTION and new_state == approval.IN_ROTATION:
            errors += rules.induction_errors({
                "mentor": doc.get("mentor"),
                "checklist": [row.as_dict() for row in doc.get("checklist") or []]})
            errors += rules.rotation_errors([row.as_dict() for row in doc.get("rotations") or []])
        if old_state == approval.IN_ROTATION and new_state == approval.UNDER_ASSESSMENT:
            errors += _milestone_errors(doc)
        if new_state == approval.CONFIRMED:
            errors += rules.confirmation_errors({"employment_type": doc.get("confirmed_employment_type")})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(TRAINEE))
        if new_state != approval.RECRUITED:
            doc.return_remarks = None
        # employed from induction; a trainee inducted before trainees were
        # employed is taken on at the next step, so their milestones can
        # still be appraised
        if new_state in (approval.IN_INDUCTION, approval.IN_ROTATION, approval.UNDER_ASSESSMENT) \
                and not doc.get("employee"):
            _employ_trainee(doc)
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, today(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state and new_state == approval.UNDER_ASSESSMENT:
        _raise_milestone_appraisal(doc)
    if old_state != new_state and new_state in approval.PENDING_STATES:
        _tell_trainee(doc, new_state)


def _milestone_errors(doc):
    rows = [row.as_dict() for row in doc.get("milestones") or []]
    if not rows:
        return ["There is no milestone to assess. Add the milestone first."]
    errors = []
    for row in rows:
        errors += rules.milestone_errors(row)
    return errors


def _raise_milestone_appraisal(doc):
    """Test case 19: the milestone is assessed on a real Appraisal in the
    performance module, on the form the trainee's Job Title's template
    gives, and goes round the appraisal's own signatures. When it is
    completed, its score and its competency check come back onto the
    milestone (appraisal_on_submit): nobody types them twice."""
    pending = [row for row in doc.get("milestones") or [] if not row.appraisal]
    if not pending or not doc.get("employee"):
        return None
    row = pending[0]
    try:
        appraisal = frappe.get_doc({
            "doctype": "Appraisal", "employee": doc.employee, "company": doc.company,
            "start_date": doc.get("start_date"), "end_date": row.due_on,
        })
        appraisal.flags.ignore_permissions = True
        appraisal.flags.ignore_mandatory = True
        appraisal.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: milestone appraisal for a trainee")
        return None
    row.appraisal = appraisal.name
    if not row.is_new():
        row.db_set("appraisal", appraisal.name, update_modified=False)
    return appraisal.name


def _tell_trainee(doc, state):
    from hrms_addon.hrms_addon import trainee_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("home_branch"),
                              doc.get("home_department"))
    if doc.get("mentor"):
        user = frappe.db.get_value("Employee", doc.mentor, "user_id")
        if user:
            users = list(users) + [user]
    if not users:
        return
    message = _("Graduate trainee {0} is at {1}.").format(doc.trainee_name, state)
    talent_jobs.tell(list(dict.fromkeys(users)), doc.doctype, doc.name, message)


def trainee_on_submit(doc, method=None):
    """Confirmed or exited. Test case 20: a confirmation creates the
    Employee record and enters the trainee into the grid as emerging
    talent and into the succession pool."""
    from hrms_addon.hrms_addon import trainee_approval as approval

    if doc.get("workflow_state") == approval.EXITED or doc.get("status") == approval.EXITED:
        _raise_trainee_exit(doc)
        return
    employee = _create_employee(doc)
    if not employee:
        return
    if doc.get("confirmed_employment_type"):
        frappe.db.set_value("Employee", employee, "employment_type", doc.confirmed_employment_type)
    _enter_the_grid(doc, employee)


def trainee_on_cancel(doc, method=None):
    doc.status = "Cancelled"


def _employ_trainee(doc):
    """A trainee is employed from induction, as a graduate trainee: the
    milestone appraisals (test case 19) are an employee's to have, and so is
    the pay and attendance of the programme. Confirmation (test case 20)
    puts them on the employment type HR names. A trainee who cannot be
    employed does not go on to induction: HR is told why."""
    if doc.get("employee"):
        return doc.employee
    kind = rules.TRAINEE_EMPLOYMENT if frappe.db.exists("Employment Type", rules.TRAINEE_EMPLOYMENT) else None
    try:
        doc.employee = _new_employee(doc, kind)
    except Exception as error:
        frappe.throw(_("{0} could not be taken on as an employee: {1}").format(doc.trainee_name, error),
                     title=_(TRAINEE))
    return doc.employee


def _raise_trainee_exit(doc):
    """A trainee who leaves the programme was employed from induction, so
    they leave through the exit process like anybody else: an involuntary
    separation at the end of their contract, with the reason given, which
    the exit interview, clearance and final dues follow from (exits.py).
    One already open for them is used."""
    if not doc.get("employee") or doc.get("separation"):
        return doc.get("separation")
    existing = frappe.db.get_value("Employee Separation", {"employee": doc.employee, "docstatus": ["<", 2]},
                                   "name")
    if not existing:
        try:
            separation = frappe.get_doc({
                "doctype": "Employee Separation", "employee": doc.employee, "company": doc.company,
                "department": doc.get("home_department"), "designation": doc.get("designation"),
                "boarding_status": "Pending", "custom_exit_type": "Involuntary",
                "custom_reason": "End of Contract", "custom_relieving_date": today(),
                "custom_termination_date": today(),
                "custom_termination_reason": _("Graduate trainee programme {0}: {1}").format(
                    doc.name, doc.get("exit_reason") or ""),
            })
            separation.flags.ignore_permissions = True
            separation.flags.ignore_mandatory = True
            separation.insert()
            existing = separation.name
        except Exception:
            frappe.log_error(title="HRMS Addon: separation for an exited trainee")
            return None
    doc.db_set("separation", existing, update_modified=False)
    users = people.hr_officers(doc.get("home_branch"), doc.get("home_department"))
    if users:
        talent_jobs.tell(list(users), "Employee Separation", existing,
                      _("{0} has left the graduate trainee programme. Their exit is open.").format(
                          doc.trainee_name))
    return existing


def _new_employee(doc, employment_type=None):
    names = (doc.trainee_name or "").split()
    employee = frappe.get_doc({
        "doctype": "Employee", "employee_name": doc.trainee_name,
        "first_name": names[0] if names else doc.trainee_name,
        "last_name": " ".join(names[1:]) or None,
        "company": doc.company, "status": "Active",
        "date_of_joining": doc.get("start_date") or today(),
        "department": doc.get("home_department"), "branch": doc.get("home_branch"),
        "designation": doc.get("designation"), "employment_type": employment_type,
    })
    employee.flags.ignore_permissions = True
    employee.flags.ignore_mandatory = True
    employee.insert()
    return employee.name


def _create_employee(doc):
    """The Employee record at confirmation, for a trainee taken on before
    trainees were employed from induction."""
    if doc.get("employee"):
        return doc.employee
    try:
        name = _new_employee(doc)
    except Exception:
        frappe.log_error(title="HRMS Addon: employee record for a confirmed trainee")
        return None
    doc.db_set("employee", name, update_modified=False)
    return name


def _enter_the_grid(doc, employee):
    """A confirmed trainee has potential seen and performance not yet
    earned over a full year, so they enter as emerging: a draft placement
    for the line manager to complete, and a place on the bench."""
    entry = rules.trainee_placement()
    cycle = frappe.db.get_value(REVIEW, {"status": ["in", ("Draft", "Open")]}, "name",
                                order_by="opens_on desc")
    if cycle and not doc.get("placement"):
        try:
            placement = frappe.get_doc({
                "doctype": PLACEMENT, "talent_review": cycle, "employee": employee,
                "company": doc.company,
                "rationale": _("Confirmed graduate trainee, entering as emerging talent.")})
            placement.flags.ignore_permissions = True
            placement.flags.ignore_mandatory = True
            placement.insert()
            doc.db_set("placement", placement.name, update_modified=False)
        except Exception:
            frappe.log_error(title="HRMS Addon: placement for a confirmed trainee")
    designation = frappe.db.get_value("Employee", employee, "designation")
    position = _add_to_pool(employee, designation, doc.company,
                            placement=doc.get("placement"), readiness=entry["readiness"],
                            box_name=entry["box_name"])
    if position:
        doc.db_set("succession_position", position, update_modified=False)


# ── 6. An appraisal completed ─────────────────────────────────────────
def appraisal_on_submit(doc, method=None):
    """Appraisal on_submit (hooks.py): a completed appraisal reaches talent
    at once. The trainee milestone it was raised for takes its score and
    its competency check (test case 19), and the employee's placements not
    yet finalised read their year again."""
    _record_milestone(doc)
    _refresh_open_placements(doc.get("employee"))


def _record_milestone(appraisal):
    rows = frappe.get_all("Trainee Milestone", filters={"appraisal": appraisal.name, "parenttype": TRAINEE},
                          fields=["name", "parent"], limit=5)
    for row in rows:
        trainee = frappe.get_doc(TRAINEE, row.parent)
        if trainee.docstatus != 0:
            continue
        milestone = next((line for line in trainee.milestones if line.name == row.name), None)
        if milestone is None:
            continue
        milestone.score = flt(appraisal.get("custom_total_score") or appraisal.get("final_score"))
        milestone.competency_check = _competency_level(appraisal)
        milestone.result = rules.milestone_outcome(milestone.score, final=_is_final(trainee, milestone),
                                                   pass_mark=masters.grid()["pass_mark"])
        milestone.assessed_by = frappe.session.user
        trainee.flags.ignore_permissions = True
        trainee.save()
        users = people.hr_officers(trainee.get("home_branch"), trainee.get("home_department"))
        if users:
            talent_jobs.tell(list(users), TRAINEE, trainee.name,
                             _("Milestone {0} for {1} is assessed: {2} out of 100, {3}.").format(
                                 milestone.milestone, trainee.trainee_name, milestone.score, milestone.result))


def _competency_level(appraisal):
    """The appraisal's competency check out of ten: its scorecard
    competencies as scored, or its LPL/HR/18 factors as rated."""
    evidence = rules.competency_evidence(
        [{"competency": row.competency, "score": row.score}
         for row in appraisal.get("custom_bsc_competencies") or []],
        [{"factor": row.item, "rating": row.supervisor_rating} for row in appraisal.get("custom_factors") or []])
    return rules.competency_average([{"level": row["level"]} for row in evidence])


def _refresh_open_placements(employee):
    """The employee's placements not yet finalised, read again from the
    appraisals: written straight in, so their own checks and signatures
    are not run again."""
    if not employee:
        return
    for name in frappe.get_all(PLACEMENT, filters={"employee": employee, "docstatus": 0}, pluck="name"):
        doc = frappe.get_doc(PLACEMENT, name)
        _fill_performance(doc)
        _fill_potential(doc)
        _fill_box(doc)
        doc.db_update()
        for table in ("quarter_results", "competencies", "themes"):
            doc.update_child_table(table)


def seed_masters():
    """The employment type a graduate trainee is on, made once (after_install
    and the patch seed_talent_masters): HR may rename it or take it away,
    and it is not put back."""
    if frappe.db.exists("DocType", "Employment Type") \
            and not frappe.db.exists("Employment Type", rules.TRAINEE_EMPLOYMENT):
        frappe.get_doc({"doctype": "Employment Type",
                        "employee_type_name": rules.TRAINEE_EMPLOYMENT}).insert(ignore_permissions=True)


# ── 7. What the clock does ────────────────────────────────────────────
def monthly():
    """Scheduler, on the first of each month (hooks.py): the month just
    ended in talent, told to the HR Managers and the Talent Council with
    the Monthly Talent Report for it — the testing sheet's recommendation,
    "Provide end-of-month reports in the system"."""
    from hrms_addon.hrms_addon import talent_reports

    month = talent_reports.month(add_days(today(), -1))
    users = list(dict.fromkeys(row["user"] for role in ("HR Manager", "Talent Council")
                               for row in people.holders(role)))
    if not users:
        return
    label = getdate(month["start"]).strftime("%B %Y")
    figures = month["summary"]
    lines = [
        _("{0} placements finalised, {1} of them top talent, {2} of those at risk of leaving").format(
            figures["finalised"], figures["top_talent"], figures["at_risk"]),
        _("{0} moved in calibration").format(figures["moves"]),
        _("{0} critical roles confirmed, {1} gaps being recruited for, {2} handed over to a successor").format(
            figures["roles_confirmed"], figures["gaps"], figures["handovers"]),
        _("{0} development actions done, {1} past their date").format(
            figures["actions_done"], figures["actions_late"]),
        _("{0} programmes closed").format(figures["programmes_closed"]),
        _("{0} graduate trainees confirmed, {1} left the programme").format(
            figures["trainees_confirmed"], figures["trainees_left"]),
    ]
    link = "/app/query-report/Monthly Talent Report?month=%s" % month["end"]
    people.notify(users, "Report", "Monthly Talent Report",
                  _("The talent report for {0} is ready.").format(label),
                  "<p>%s</p><ul>%s</ul><p><a href=\"%s\">%s</a></p>" % (
                      _("Talent in {0}:").format(label), "".join("<li>%s</li>" % line for line in lines),
                      frappe.utils.get_url(link), _("Open the Monthly Talent Report")))


def daily():
    from hrms_addon.hrms_addon import calibration, succession_risk

    _open_review_cycles()
    _raise_due_milestones()
    _chase_milestones()
    _watch_top_talent()
    _watch_exits()
    _link_openings()
    calibration_digest()
    calibration.daily()
    succession_risk.daily()


def _open_review_cycles():
    """Test case 21: on the day a cycle opens, everyone eligible gets a
    draft placement without anybody asking for it."""
    for name in frappe.get_all(REVIEW, filters={"status": "Draft",
                                                "opens_on": ["<=", today()]}, pluck="name"):
        try:
            # the whole staff is drafted in the background, a review at a time
            talent_jobs.start("draft", REVIEW, name, "hrms_addon.hrms_addon.talent.draft_job", review=name)
        except Exception:
            frappe.clear_last_message()
            frappe.log_error(title="HRMS Addon: opening a talent review")
    frappe.db.commit()


def _raise_due_milestones():
    """Blueprint section 9, "Trainee milestone due": a trainee in rotation
    whose next milestone falls due within the days Talent Settings give is
    moved to Under Assessment, which raises the milestone's appraisal, and
    their rotation supervisor, mentor and HR are told, each once a day."""
    s = masters.settings()
    if not cint(s.get("auto_milestones")):
        return
    by_day = add_days(today(), cint(s.get("milestone_lead_days")))
    frappe.flags[talent_jobs._DIGEST] = []
    try:
        _raise_milestones_by(by_day)
        entries = frappe.flags.get(talent_jobs._DIGEST) or []
    finally:
        frappe.flags[talent_jobs._DIGEST] = None
    talent_jobs.send_digest(entries, _("Trainee milestones due"), TRAINEE, None)


def _raise_milestones_by(by_day):
    from hrms_addon.hrms_addon import trainee_approval as approval

    due = frappe.get_all("Trainee Milestone",
                         filters={"parenttype": TRAINEE, "due_on": ["<=", by_day], "appraisal": ["is", "not set"],
                                  "result": ["in", ("", None)]},
                         fields=["parent", "milestone", "due_on"], order_by="due_on asc", limit=200)
    for parent in dict.fromkeys(row.parent for row in due):
        trainee = frappe.get_doc(TRAINEE, parent)
        if trainee.docstatus != 0 or trainee.get("workflow_state") != approval.IN_ROTATION:
            continue
        from frappe.model.workflow import apply_workflow

        try:
            trainee = apply_workflow(trainee, approval.ASSESS)
        except Exception:
            frappe.log_error(title="HRMS Addon: raising a trainee's milestone appraisal")
            frappe.clear_last_message()
            continue
        milestone = next((row for row in trainee.milestones if row.appraisal and not row.result), None)
        if milestone:
            _tell_milestone_due(trainee, milestone)
    frappe.db.commit()


def _tell_milestone_due(trainee, milestone):
    users = list(people.hr_officers(trainee.get("home_branch"), trainee.get("home_department")))
    for employee in (_rotation_supervisor(trainee), trainee.get("mentor")):
        user = frappe.db.get_value("Employee", employee, "user_id") if employee else None
        if user:
            users.append(user)
    if users:
        talent_jobs.tell(list(dict.fromkeys(users)), "Appraisal", milestone.appraisal,
                      _("{0}'s milestone {1} falls due on {2}: its appraisal is ready to be filled in.").format(
                          trainee.trainee_name, milestone.milestone, format_date(milestone.due_on)))


def _rotation_supervisor(trainee):
    """The supervisor of the rotation the trainee is on today, else of the last one begun."""
    day = getdate(today())
    begun = [row for row in trainee.get("rotations") or [] if row.from_date and getdate(row.from_date) <= day]
    current = [row for row in begun if not row.to_date or getdate(row.to_date) >= day]
    rows = current or begun
    return rows[-1].supervisor if rows else None


def _chase_milestones():
    """A milestone that has fallen due and has no result yet is somebody's
    to do something about: each plant's HR told once a day, in one digest."""
    rows = frappe.get_all(
        "Trainee Milestone",
        filters={"parenttype": TRAINEE, "due_on": ["<=", today()], "result": ["in", ("", None)]},
        fields=["name", "parent", "milestone", "due_on"], limit=0)
    trainees = {row.name: row for row in frappe.get_all(
        TRAINEE, filters={"name": ["in", sorted({row.parent for row in rows})], "docstatus": 0},
        fields=["name", "trainee_name", "home_branch", "home_department"], limit=0)} if rows else {}
    entries = []
    for row in rows:
        trainee = trainees.get(row.parent)
        if not trainee:
            continue
        line = _("Milestone {0} for {1} was due on {2} and has no result.").format(
            row.milestone, trainee.trainee_name, frappe.utils.format_date(row.due_on))
        entries += [(user, line, TRAINEE, row.parent)
                    for user in people.hr_officers(trainee.home_branch, trainee.home_department)]
    talent_jobs.send_digest(entries, _("Trainee milestones with no result"), TRAINEE, None)
    frappe.db.commit()


def _watch_top_talent():
    """Test case 22, for a risk flagged after the placement was
    finalised."""
    watched = masters.watched_risks()
    if not watched:
        return
    frappe.flags[talent_jobs._DIGEST] = []
    try:
        for name in frappe.get_all(PLACEMENT, filters={"docstatus": 1, "top_talent": 1,
                                                       "risk_alerted": ["in", ("", None)],
                                                       "flight_risk": ["in", watched]},
                                   pluck="name", limit=0):
            try:
                _flag_flight_risk(frappe.get_doc(PLACEMENT, name))
            except Exception:
                frappe.log_error(title="HRMS Addon: flight-risk alert")
        entries = frappe.flags.get(talent_jobs._DIGEST) or []
    finally:
        frappe.flags[talent_jobs._DIGEST] = None
    talent_jobs.send_digest(entries, _("Top talent at flight risk"), "Report", "Top Talent and Flight Risk")
    frappe.db.commit()


def _watch_exits():
    """Every plan whose holder leaves within the window, acted on each day
    (rules.exit_step): the marks it reaches told, a promotion or a
    replacement's requisition drafted once."""
    window = [today(), add_days(today(), rules.EXIT_WINDOW)]
    for name in frappe.get_all(POSITION, filters={"docstatus": ["<", 2],
                                                  "retirement_or_exit_due": ["between", window]},
                               pluck="name", limit=500):
        try:
            _act_on_exit(frappe.get_doc(POSITION, name))
        except Exception:
            frappe.log_error(title="HRMS Addon: a succession plan's exit watch")
    frappe.db.commit()


def _link_openings():
    """A plan's requisition that has become a job opening: the plan shows
    the opening, as one raised directly used to."""
    plans = frappe.get_all(POSITION, filters={"docstatus": 1, "job_opening": ["is", "not set"]},
                           pluck="name", limit=500)
    for name, drafted in drafted_for_many(plans).items():
        if drafted.get("opening"):
            frappe.db.set_value(POSITION, name, "job_opening", drafted["opening"].name, update_modified=False)
    frappe.db.commit()


# ── 8. The print outs ─────────────────────────────────────────────────
# Jinja methods (hooks.py): what the talent print formats print beyond the
# document itself. Any template may call them, so each answers only a
# reader who may open the document it is asked about.
def talent_grid():
    """The Talent Card's nine boxes, a row per potential band (high to
    low), performance low to high across: each cell's number and name."""
    boxes = masters.grid()["boxes"]
    return [[{"box": boxes[(performance, potential)]["box"],
              "name": boxes[(performance, potential)]["name"]}
             for performance in (rules.LOW, rules.MEETING, rules.EXCEEDING)]
            for potential in (rules.POTENTIAL_HIGH, rules.POTENTIAL_MODERATE, rules.POTENTIAL_LOW)]


def talent_follow_through(position):
    """The Succession Slate's "Filling the Role": the holder's exit, the
    promotion or the replacement's requisition and its opening, and how far
    each successor's development plan has got."""
    if not position or not frappe.has_permission(POSITION, "read", doc=position):
        return {}
    from hrms_addon.hrms_addon import talent_reports

    plans = frappe.get_all("Succession Candidate", filters={"parent": position, "parenttype": POSITION,
                                                             "development_plan": ["is", "set"]},
                           pluck="development_plan")
    return dict(drafted_for(position), plans=talent_reports.plan_progress(plans) if plans else {})


def talent_plan_progress(plan):
    """The Talent Card's development plan: its actions, done and late."""
    if not plan or not frappe.has_permission(PROGRAM, "read", doc=plan):
        return None
    from hrms_addon.hrms_addon import talent_reports

    return talent_reports.plan_progress([plan]).get(plan)


# ── 8a. Training, back from L&D ───────────────────────────────────────
# L&D (training.py) calls these as a session booked from a plan's
# requisition is booked, held, cancelled, given its results, or taken away.
# The plan keeps its own record of each session (Development Training), as
# an onboarding does of its trainings, and an action of the session's topic
# is done the day an attendee was there.
TRAINING = "Development Training"


def sync_training(training_event):
    """The plans a session's training is for, brought up to date with it: a
    row of the plan's Training for its employee while booked on it; once
    held, whether they attended, and the plan's actions of the session's
    topic done that day for one who did; once marked, their marks and
    whether it worked. A session cancelled, or one the employee is no
    longer booked on, leaves the plan as if it had never been."""
    event = frappe.db.get_value("Training Event", training_event,
                                ["name", "docstatus", "start_time", "end_time", "course", "custom_calendar_entry"],
                                as_dict=True)
    if not event:
        return 0
    topic, requisitions = _training_behind(event)
    plans = _plans_for(requisitions)
    if not plans:
        return 0
    booked = {row.employee: row.attendance for row in frappe.get_all(
        "Training Event Employee", filters={"parent": event.name, "parenttype": "Training Event"},
        fields=["employee", "attendance"], limit=0)}
    held = event.docstatus == 1
    results = _training_results(event.name) if held else {}
    when = event.get("end_time") or event.get("start_time")
    day = getdate(when) if when else None
    for plan in plans:
        row = frappe.db.get_value(TRAINING, {"parent": plan.name, "parenttype": PROGRAM,
                                             "training_event": event.name}, "name")
        if event.docstatus == 2 or plan.employee not in booked:
            if row:
                _drop_training_row(plan.name, row)
            _unmark_actions(plan.name, event.name)
            continue
        marks, effective = results.get(plan.employee, (None, None))
        values = {"topic": topic, "training_date": day, "training_requisition": plan.requisition,
                  "employee": plan.employee, "attendance": booked.get(plan.employee) if held else None,
                  "marks": flt(marks), "effectiveness": effective}
        if row:
            frappe.db.set_value(TRAINING, row, values, update_modified=False)
        else:
            _add_training_row(plan.name, dict(values, training_event=event.name))
        if held and booked.get(plan.employee) == rules.ATTENDED:
            _mark_actions(plan.name, topic, day, event.name)
        else:
            _unmark_actions(plan.name, event.name)
    return len(plans)


def forget_training(training_event):
    """A session taken away before it was held: the plans let go of it."""
    for row in frappe.get_all(TRAINING, filters={"training_event": training_event, "parenttype": PROGRAM},
                              fields=["name", "parent"], limit=0):
        _drop_training_row(row.parent, row.name)
        _unmark_actions(row.parent, training_event)


def _training_behind(event):
    """The topic a session teaches and the requisitions it was booked for:
    through the calendar row it was scheduled from, and the requisitions
    that name it."""
    need = None
    if event.get("custom_calendar_entry"):
        need_row = frappe.db.get_value("Training Calendar Entry", event.custom_calendar_entry, "need_row")
        need = frappe.db.get_value("Training Need", need_row, ["topic", "requisition"], as_dict=True) \
            if need_row else None
    requisitions = set(frappe.get_all(REQUISITION, filters={"training_event": event.name}, pluck="name"))
    if need and need.get("requisition"):
        requisitions.add(need.requisition)
    return (need.get("topic") if need else None) or event.get("course"), sorted(requisitions)


def _plans_for(requisitions):
    """The development plans those requisitions were raised for: each with
    its employee, and the requisition it came from."""
    if not requisitions:
        return []
    found = {}
    for row in frappe.get_all(REQUISITION, filters={"name": ["in", requisitions], "talent_program": ["is", "set"]},
                              fields=["name", "talent_program"], limit=0):
        found[row.talent_program] = row.name
    for row in frappe.get_all(PROGRAM, filters={"training_requisition": ["in", requisitions]},
                              fields=["name", "training_requisition"], limit=0):
        found.setdefault(row.name, row.training_requisition)
    if not found:
        return []
    return [frappe._dict(plan, requisition=found[plan.name])
            for plan in frappe.get_all(PROGRAM, filters={"name": ["in", sorted(found)], "docstatus": ["<", 2]},
                                       fields=["name", "employee"], limit=0)]


def _training_results(training_event):
    """Each person's marks from the session's submitted results, the latest
    where it has more than one."""
    out = {}
    for result in frappe.get_all("Training Result", filters={"training_event": training_event, "docstatus": 1},
                                 pluck="name", order_by="creation asc", limit=0):
        for row in frappe.get_all("Training Result Employee", filters={"parent": result, "parenttype": "Training Result"},
                                  fields=["employee", "custom_marks", "custom_effective"], limit=0):
            out[row.employee] = (row.custom_marks, row.custom_effective)
    return out


def _add_training_row(plan, values):
    """A row of the plan's Training, written straight in: the plan's form
    may be open with somebody, and its own fields are left alone."""
    number = frappe.db.count(TRAINING, {"parent": plan, "parenttype": PROGRAM}) + 1
    frappe.get_doc(dict(values, doctype=TRAINING, parent=plan, parenttype=PROGRAM, parentfield="trainings",
                        idx=number)).db_insert()


def _drop_training_row(plan, row):
    frappe.db.delete(TRAINING, {"name": row})
    for number, name in enumerate(frappe.get_all(TRAINING, filters={"parent": plan, "parenttype": PROGRAM},
                                                 order_by="idx asc", pluck="name", limit=0), 1):
        frappe.db.set_value(TRAINING, name, "idx", number, update_modified=False)


def _mark_actions(plan, topic, day, training_event):
    """The plan's actions of the session's topic, done the day it was held,
    unless someone has already said when they were."""
    actions = frappe.get_all(ACTION, filters={"parent": plan, "parenttype": PROGRAM},
                             fields=["name", "action", "completed_on", "training_event"], limit=0)
    for row in rules.actions_for_topic(actions, topic):
        if not row.get("completed_on"):
            frappe.db.set_value(ACTION, row.name, {"completed_on": day, "done_at_session": training_event,
                                                   "training_event": row.get("training_event") or training_event,
                                                   "status": rules.DONE, "progress": 100},
                                update_modified=False)


def _unmark_actions(plan, training_event):
    """Only what this session marked: a date someone typed stays."""
    for name in frappe.get_all(ACTION, filters={"parent": plan, "parenttype": PROGRAM,
                                                "done_at_session": training_event},
                               pluck="name", limit=0):
        frappe.db.set_value(ACTION, name, {"completed_on": None, "done_at_session": None, "status": "In Progress"},
                            update_modified=False)


# ── 9. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    from hrms_addon.hrms_addon import (succession_approval, succession_plan_approval, talent_approval,
                                       talent_program_approval, trainee_approval, workflows)

    for module, label in ((talent_approval, "talent placement"),
                          (talent_program_approval, "talent programme"),
                          (succession_approval, "succession position"),
                          (succession_plan_approval, "succession plan"),
                          (trainee_approval, "graduate trainee")):
        workflows.setup_on_migrate(module, label)


# the indexes a review of the whole staff is read by: (doctype, [fields])
INDEXES = (
    (PLACEMENT, ["talent_review", "workflow_state"]),
    (PLACEMENT, ["employee", "docstatus"]),
    (PLACEMENT, ["talent_review", "box"]),
    ("Succession Candidate", ["employee"]),
    ("Trainee Milestone", ["appraisal"]),
    ("Talent Calibration Log", ["talent_review", "moved_on"]),
    ("Potential Assessment", ["placement", "docstatus"]),
)


def add_indexes():
    """on_doctype_update of the Talent Placement, and the patch talent_indexes:
    each index once. A speed-up only, so one a table will not take holds
    nothing else up."""
    for doctype, fields in INDEXES:
        if not frappe.db.table_exists(doctype):
            continue
        try:
            frappe.db.add_index(doctype, fields, index_name="ha_%s" % "_".join(fields))
        except Exception:
            frappe.log_error(title="HRMS Addon: index on %s %s" % (doctype, ", ".join(fields)), defer_insert=True)
