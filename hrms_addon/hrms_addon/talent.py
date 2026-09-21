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
               coaching, or L&D — and the review of whether it worked
  position_*   a critical role and its bench; a confirmed gap raises a job
               opening in resourcing and sends the development needs on
  trainee_*    a graduate trainee from the applicant they were hired as to
               the Employee record confirmation creates
  daily        the cycles that open, the milestones that fall due, and the
               top talent somebody should be worried about losing

Nothing here re-enters a number another module already holds: the
performance band comes off the Appraisal, the competency evidence off its
scorecard rows, and the training goes back out as a Training Requisition
rather than as a note in a field.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import people, talent_rules as rules

REVIEW = "Talent Review"
PLACEMENT = "Talent Placement"
PROGRAM = "Talent Program"
POSITION = "Succession Position"
TRAINEE = "Graduate Trainee Program"
REQUISITION = "Training Requisition"


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
    performance band from — without one the placement would have nothing
    on its left-hand axis.
    """
    cycle = frappe.get_doc(REVIEW, review)
    cycle.check_permission("write")
    made = _draft_placements(cycle)
    frappe.msgprint(_("{0} placements drafted.").format(made) if made
                    else _("Everyone eligible already has a placement in this round."))
    return made


def _draft_placements(cycle):
    filters = {"docstatus": 1, "appraisal_cycle": cycle.appraisal_cycle}
    scope = {"company": cycle.get("company"), "branch": cycle.get("branch"),
             "department": cycle.get("department")}
    appraisals = frappe.get_all(
        "Appraisal", filters=filters,
        fields=["name", "employee", "employee_name", "custom_total_score", "final_score"],
        limit=5000)
    have = set(frappe.get_all(PLACEMENT, filters={"talent_review": cycle.name,
                                                  "docstatus": ["<", 2]},
                              pluck="employee"))
    made = 0
    for row in appraisals:
        if row.employee in have:
            continue
        employee = frappe.db.get_value(
            "Employee", row.employee,
            ["status", "company", "branch", "department", "designation"], as_dict=True)
        if not employee or employee.status != "Active":
            continue
        if any(value and employee.get(field) != value for field, value in scope.items()):
            continue
        try:
            placement = frappe.get_doc({
                "doctype": PLACEMENT, "talent_review": cycle.name, "employee": row.employee,
                "company": employee.company})
            placement.flags.ignore_permissions = True
            placement.flags.ignore_mandatory = True
            placement.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: drafting a talent placement")
            continue
        made += 1
    cycle.db_set({"placements_created": cint(cycle.get("placements_created")) + made,
                  "drafted_on": today()}, update_modified=False)
    if made and cycle.status == "Draft":
        cycle.db_set("status", "Open", update_modified=False)
    return made


# ── 2. The placement ──────────────────────────────────────────────────
def placement_validate(doc, method=None):
    from hrms_addon.hrms_addon import talent_approval as approval

    _fill_performance(doc)
    _fill_potential(doc)
    _fill_box(doc)
    _check_placement_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _fill_performance(doc):
    """Test case 4: the appraisal's own final score, and the band it falls
    in. Nothing is re-entered, so a placement whose employee has no
    appraisal in the cycle carries no performance at all."""
    if not (doc.get("employee") and doc.get("talent_review")):
        return
    cycle = frappe.db.get_value(REVIEW, doc.talent_review, "appraisal_cycle")
    found = frappe.get_all(
        "Appraisal",
        filters={"employee": doc.employee, "appraisal_cycle": cycle, "docstatus": 1},
        fields=["name", "custom_total_score", "final_score", "custom_band"],
        order_by="modified desc", limit=1)
    if not found:
        doc.appraisal = None
        doc.performance_score = None
        doc.appraisal_band = None
        doc.performance_band = None
        return
    row = found[0]
    doc.appraisal = row.name
    doc.performance_score = flt(row.custom_total_score or row.final_score or 0)
    doc.appraisal_band = row.custom_band
    doc.performance_band = rules.performance_band(doc.performance_score)
    _carry_competencies(doc)


def _carry_competencies(doc):
    """Test case 5: the competency levels come across from the scorecard,
    as evidence. They are not typed in and they are not a score here."""
    if doc.get("competencies") or not doc.get("appraisal"):
        return
    rows = frappe.get_all("BSC Appraisal Competency",
                          filters={"parent": doc.appraisal, "parenttype": "Appraisal"},
                          fields=["competency", "score"], order_by="idx asc", limit=50)
    for row in rows:
        doc.append("competencies", {"competency": row.competency, "level": flt(row.score),
                                    "appraisal": doc.appraisal})


def _fill_potential(doc):
    doc.potential_score = rules.potential_score({
        "ability": doc.get("ability"), "aspiration": doc.get("aspiration"),
        "engagement": doc.get("engagement")})
    doc.potential_band = rules.potential_band(doc.potential_score)
    doc.competency_average = rules.competency_average(
        [row.as_dict() for row in doc.get("competencies") or []])


def _fill_box(doc):
    """Test case 6: the two bands resolve to one cell, with its name, its
    colour and what it says to do."""
    box = rules.box_for(doc.get("performance_band"), doc.get("potential_band"))
    if not box:
        for field in ("box", "box_name", "box_colour", "default_action", "suggested_decision"):
            doc.set(field, None)
        doc.top_talent = 0
        return
    doc.box = box["box"]
    doc.box_name = box["name"]
    doc.box_colour = box["colour"]
    doc.default_action = box["action"]
    doc.suggested_decision = box["decision"]
    doc.top_talent = 1 if rules.is_top_talent(box["box"]) else 0
    if not doc.get("themes"):
        doc.append("themes", {"theme": box["action"],
                              "why": _("From the {0} placement.").format(box["name"])})


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
                "performance_score": doc.get("performance_score"),
                "ability": doc.get("ability"), "aspiration": doc.get("aspiration"),
                "engagement": doc.get("engagement"),
                "rationale": doc.get("rationale")}) + errors
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(PLACEMENT))
        if new_state == approval.DRAFT:
            doc.submitted_box = None
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
    _record_calibration(doc, before)


def _record_calibration(doc, before):
    """Test case 7: a box moved during calibration is written into the
    cycle, with who moved it and why, so HR can see the movers."""
    from hrms_addon.hrms_addon import talent_approval as approval

    if doc.get("workflow_state") != approval.CALIBRATION or not before:
        return
    was = before.get("box")
    if not was or was == doc.get("box") or not doc.get("talent_review"):
        return
    errors = rules.calibration_errors({
        "from_box": was, "to_box": doc.get("box"),
        "reason": doc.get("calibration_reason"), "moved_by": frappe.session.user})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Calibration"))
    cycle = frappe.get_doc(REVIEW, doc.talent_review)
    cycle.append("calibration", {
        "placement": doc.name, "employee": doc.employee, "from_box": was, "to_box": doc.box,
        "moved_by": frappe.session.user, "moved_on": today(),
        "reason": doc.calibration_reason})
    cycle.flags.ignore_permissions = True
    cycle.save()
    if cycle.status in ("Draft", "Open"):
        cycle.db_set("status", "In Calibration", update_modified=False)


def _tell_placement(doc, state):
    from hrms_addon.hrms_addon import talent_approval as approval

    users = people.people_for(approval.ROLE_WAITING[state], doc.get("branch"),
                              doc.get("department"))
    if not users:
        return
    message = _("Talent placement for {0} is waiting at {1}.").format(
        doc.get("employee_name") or doc.employee, state)
    people.notify(list(users), doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def placement_on_submit(doc, method=None):
    """Finalised. Test case 9: the placement locks, a development plan is
    drawn up from it, and the training in that plan goes to L&D."""
    _draw_up_development_plan(doc)
    _flag_flight_risk(doc)


def placement_on_cancel(doc, method=None):
    doc.status = "Cancelled"


def _draw_up_development_plan(doc):
    """The box's default action becomes a programme the employee is
    actually on, with the themes as its actions."""
    if doc.get("development_plan"):
        return doc.development_plan
    program_type = _program_type_for(doc.get("box"))
    try:
        program = frappe.get_doc({
            "doctype": PROGRAM, "employee": doc.employee, "company": doc.get("company"),
            "program_type": program_type, "start_date": today(),
            "end_date": add_days(today(), 365), "placement": doc.name,
            "talent_review": doc.get("talent_review"), "box_name": doc.get("box_name"),
            "objectives": doc.get("default_action"),
            "actions": [{"action": row.theme, "by_when": add_days(today(), 180),
                         "by_whom": doc.get("employee_name") or doc.employee}
                        for row in doc.get("themes") or []],
        })
        program.flags.ignore_permissions = True
        program.flags.ignore_mandatory = True
        program.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: development plan from a placement")
        return None
    doc.db_set("development_plan", program.name, update_modified=False)
    _push_to_ld(program, [row.theme for row in doc.get("themes") or []])
    return program.name


def _program_type_for(box):
    """Which programme the box asks for. The three boxes with the
    potential to lead get leadership; the middle of the grid gets a
    mentor; everyone else gets training."""
    if cint(box) in rules.TOP_TALENT:
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
    topic = ", ".join(text for text in topics if text)
    if not topic:
        topic = program.get("objectives") or program.program_type
    try:
        requisition = frappe.get_doc({
            "doctype": REQUISITION, "requested_by": frappe.session.user,
            "department": program.get("department"), "branch": program.get("branch"),
            "request_date": today(), "priority": "Medium", "status": "Draft",
            "training_topic": topic[:140],
            "justification": _("From talent programme {0} ({1}).").format(
                program.name, program.program_type),
            "proposed_method": "Coaching" if program.program_type == "Mentoring and Coaching"
            else "Internal",
            "target_employees": [{"employee": program.employee,
                                  "skill_areas": topic[:500]}],
        })
        requisition.flags.ignore_permissions = True
        requisition.flags.ignore_mandatory = True
        requisition.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: sending a development plan to L&D")
        return None
    program.db_set("training_requisition", requisition.name, update_modified=False)
    return requisition.name


def _flag_flight_risk(doc):
    """Test case 22: top talent somebody might lose is told to HR and the
    council, once."""
    if not (doc.get("top_talent") and doc.get("flight_risk") in ("High", "Medium")):
        return
    if doc.get("risk_notified"):
        return
    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    # people_for, not holders: holders hands back rows, and the council
    # sits over every plant rather than in one of them
    users += list(people.people_for("Talent Council", doc.get("branch"), doc.get("department")))
    if not users:
        return
    people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name,
                  _("{0} is in box {1} ({2}) and flagged {3} flight risk. Retention action is "
                    "the council's to take.").format(
                      doc.get("employee_name") or doc.employee, doc.get("box"),
                      doc.get("box_name"), str(doc.flight_risk).lower()))
    doc.db_set("risk_notified", 1, update_modified=False)


# ── 3. The programme ──────────────────────────────────────────────────
def program_validate(doc, method=None):
    from hrms_addon.hrms_addon import talent_program_approval as approval

    _fill_program_scores(doc)
    _check_program_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


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
    people.notify(users, doc.doctype, doc.name,
                  _("{0} is on the {1} programme.").format(
                      doc.get("employee_name") or doc.employee, doc.program_type))


def program_on_submit(doc, method=None):
    """Closed. Test case 3: the decision taken at the end is acted on —
    a succession pipeline decision puts the employee on the bench for
    their own role's succession position where one exists."""
    if doc.get("decision") != "Succession Pipeline":
        return
    position = _add_to_pool(doc.employee, doc.get("designation"), doc.get("company"),
                            placement=doc.get("placement"))
    if position:
        return
    # nobody is quietly left off a pipeline they were put on: where there
    # is no bench to add them to — their own role has no succession
    # position, or they already hold it — HR is told to find the role the
    # decision meant
    users = people.hr_officers(doc.get("branch"), doc.get("department"))
    if users:
        people.notify(list(users), doc.doctype, doc.name,
                      _("{0} was put in the succession pipeline, but there is no succession "
                        "position to add them to. Name the role they are being grown for.").format(
                          doc.get("employee_name") or doc.employee))


def program_on_cancel(doc, method=None):
    doc.status = "Cancelled"


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
    from hrms_addon.hrms_addon import succession_approval as approval

    _fill_bench(doc)
    _check_position_step(doc)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _fill_bench(doc):
    """Test case 13: how deep the bench is, and whether the role is
    covered — worked out from the successors, never typed."""
    candidates = [row.as_dict() for row in doc.get("candidates") or []]
    counts = rules.bench_strength(candidates)
    doc.ready_now = counts[rules.READY_NOW]
    doc.ready_soon = counts[rules.READY_SOON]
    doc.emerging = counts[rules.EMERGING]
    doc.bench_depth = len([row for row in candidates if row.get("readiness") != rules.GAP])
    doc.coverage = rules.coverage(candidates)
    doc.gap = 1 if rules.is_gap(candidates) else 0
    if not doc.gap:
        doc.gap_confirmed = 0


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
    people.notify(list(users), doc.doctype, doc.name, message)
    people.assign(doc.doctype, doc.name, users, message)


def position_on_submit(doc, method=None):
    """Confirmed. Test case 14: a confirmed gap raises the job opening in
    resourcing, and the development needs of everyone not ready now go to
    L&D."""
    if doc.get("gap") and doc.get("gap_confirmed"):
        _raise_job_opening(doc)
    _send_needs_to_ld(doc)


def position_on_cancel(doc, method=None):
    doc.status = "Cancelled"


def _raise_job_opening(doc):
    if doc.get("job_opening"):
        return doc.job_opening
    existing = frappe.db.get_value("Job Opening", {"designation": doc.designation,
                                                   "company": doc.company, "status": "Open"},
                                   "name")
    if existing:
        doc.db_set("job_opening", existing, update_modified=False)
        return existing
    try:
        opening = frappe.get_doc({
            "doctype": "Job Opening", "job_title": doc.designation, "designation": doc.designation,
            "company": doc.company, "department": doc.get("department"),
            "status": "Open", "posted_on": today(),
            "description": _("Raised from succession position {0}: the bench has nobody ready "
                             "now.").format(doc.name),
        })
        opening.flags.ignore_permissions = True
        opening.flags.ignore_mandatory = True
        opening.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: job opening from a succession gap")
        return None
    doc.db_set("job_opening", opening.name, update_modified=False)
    return opening.name


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
                "status": "Draft", "training_topic": gaps[:140],
                "justification": _("Succession for {0}: {1} is {2}.").format(
                    doc.designation, row.get("employee_name") or row.employee, row.readiness),
                "proposed_method": "On the Job",
                "target_employees": [{"employee": row.employee, "skill_areas": gaps[:500]}],
            })
            requisition.flags.ignore_permissions = True
            requisition.flags.ignore_mandatory = True
            requisition.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: succession development needs to L&D")
            continue
        row.db_set("training_requisition", requisition.name, update_modified=False)
        sent += 1
    if sent:
        doc.db_set("needs_sent_on", today(), update_modified=False)
    return sent


# ── 5. The graduate trainee ───────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def trainee_from_applicant(job_applicant, cohort=None, start_date=None):
    """Test case 16: the applicant in resourcing becomes a trainee on
    hire, state Recruited."""
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
        "cohort": cohort or _("Graduate Intake {0}").format(getdate(today()).year),
        "company": opening.company or frappe.defaults.get_user_default("Company"),
        "home_department": opening.department, "home_branch": applicant.custom_branch,
        "designation": applicant.designation or opening.designation,
        "start_date": start_date or today()})
    doc.insert()
    return doc.name


def trainee_validate(doc, method=None):
    from hrms_addon.hrms_addon import trainee_approval as approval

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
            row.result = rules.milestone_outcome(row.score, final=row is doc.milestones[-1])


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
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(TRAINEE))
        if new_state != approval.RECRUITED:
            doc.return_remarks = None
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
    performance module, with the competency check beside it."""
    pending = [row for row in doc.get("milestones") or [] if not row.appraisal]
    if not pending or not doc.get("employee"):
        return None
    row = pending[0]
    try:
        appraisal = frappe.get_doc({
            "doctype": "Appraisal", "employee": doc.employee, "company": doc.company,
            "custom_form_type": "Supervisory Skills (LPL/HR/18)",
            "start_date": doc.get("start_date"), "end_date": row.due_on,
            "custom_roles": _("Graduate trainee milestone: {0}").format(row.milestone),
        })
        appraisal.flags.ignore_permissions = True
        appraisal.flags.ignore_mandatory = True
        appraisal.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: milestone appraisal for a trainee")
        return None
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
    people.notify(list(dict.fromkeys(users)), doc.doctype, doc.name, message)


def trainee_on_submit(doc, method=None):
    """Confirmed or exited. Test case 20: a confirmation creates the
    Employee record and enters the trainee into the grid as emerging
    talent and into the succession pool."""
    from hrms_addon.hrms_addon import trainee_approval as approval

    if doc.get("workflow_state") == approval.EXITED or doc.get("status") == approval.EXITED:
        return
    employee = _create_employee(doc)
    if not employee:
        return
    _enter_the_grid(doc, employee)


def trainee_on_cancel(doc, method=None):
    doc.status = "Cancelled"


def _create_employee(doc):
    if doc.get("employee"):
        return doc.employee
    names = (doc.trainee_name or "").split()
    try:
        employee = frappe.get_doc({
            "doctype": "Employee", "employee_name": doc.trainee_name,
            "first_name": names[0] if names else doc.trainee_name,
            "last_name": " ".join(names[1:]) or None,
            "company": doc.company, "status": "Active",
            "date_of_joining": doc.get("start_date") or today(),
            "department": doc.get("home_department"), "branch": doc.get("home_branch"),
            "designation": doc.get("designation"),
        })
        employee.flags.ignore_permissions = True
        employee.flags.ignore_mandatory = True
        employee.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: employee record for a confirmed trainee")
        return None
    doc.db_set("employee", employee.name, update_modified=False)
    return employee.name


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


# ── 6. What the clock does ────────────────────────────────────────────
def daily():
    _open_review_cycles()
    _chase_milestones()
    _watch_top_talent()


def _open_review_cycles():
    """Test case 21: on the day a cycle opens, everyone eligible gets a
    draft placement without anybody asking for it."""
    for name in frappe.get_all(REVIEW, filters={"status": "Draft",
                                                "opens_on": ["<=", today()]}, pluck="name"):
        try:
            _draft_placements(frappe.get_doc(REVIEW, name))
        except Exception:
            frappe.log_error(title="HRMS Addon: opening a talent review")
    frappe.db.commit()


def _chase_milestones():
    """A milestone that has fallen due and has no result yet is somebody's
    to do something about."""
    rows = frappe.get_all(
        "Trainee Milestone",
        filters={"parenttype": TRAINEE, "due_on": ["<=", today()], "result": ["in", ("", None)]},
        fields=["name", "parent", "milestone", "due_on"], limit=200)
    for row in rows:
        trainee = frappe.db.get_value(TRAINEE, row.parent,
                                      ["trainee_name", "status", "home_branch",
                                       "home_department", "docstatus"], as_dict=True)
        if not trainee or trainee.docstatus != 0:
            continue
        users = people.hr_officers(trainee.home_branch, trainee.home_department)
        if not users:
            continue
        people.notify(list(users), TRAINEE, row.parent,
                      _("Milestone {0} for {1} was due on {2} and has no result.").format(
                          row.milestone, trainee.trainee_name,
                          frappe.utils.format_date(row.due_on)))
    frappe.db.commit()


def _watch_top_talent():
    """Test case 22, for a risk flagged after the placement was
    finalised."""
    for name in frappe.get_all(PLACEMENT, filters={"docstatus": 1, "top_talent": 1,
                                                   "risk_notified": ["!=", 1],
                                                   "flight_risk": ["in", ("High", "Medium")]},
                               pluck="name", limit=200):
        try:
            _flag_flight_risk(frappe.get_doc(PLACEMENT, name))
        except Exception:
            frappe.log_error(title="HRMS Addon: flight-risk alert")
    frappe.db.commit()


# ── 7. Wiring ─────────────────────────────────────────────────────────
def setup_workflows_on_migrate():
    from hrms_addon.hrms_addon import (succession_approval, talent_approval,
                                       talent_program_approval, trainee_approval, workflows)

    for module, label in ((talent_approval, "talent placement"),
                          (talent_program_approval, "talent programme"),
                          (succession_approval, "succession position"),
                          (trainee_approval, "graduate trainee")):
        workflows.setup_on_migrate(module, label)
