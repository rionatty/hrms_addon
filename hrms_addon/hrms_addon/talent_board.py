# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Talent Board (page/talent_board): one review on one grid, and the
talent card of each person on it (Luuka, 5 Oct 2026: the module had every
form and no way to manage talent with them).

  get_board  the review's placements in their boxes (the review picked, or
             the latest of the appraisal plan picked), filtered by plant,
             department and grade, with the three strips, the steps they
             are at and the movers (test cases 6 to 8 and 21)
  start_review  the review of an appraisal plan none reads yet, started
             from the board
  get_card   one employee's talent card: the year as their appraisals hold
             it, the potential, the competency evidence, the box over the
             years, the benches they are on, their development plan, flight
             risk and improvement plan. Shown on the board, the Employee
             form and the Appraisal form
  move       calibration on the board: a placement moved up or down its
             column, with the reason, written into the movers (case 7)
  advance    the next step for every placement on the board at the step it
             applies to — send to the council, finalise, return — each
             taken as it is on the form, so each is checked and signed
  get_succession  every critical role, its holder and the risk of losing
             them, and the successors named by readiness (cases 11 to 15)
  get_trainees  every graduate trainee by stage, with the milestone each is
             working towards (cases 16 to 20)

Only those who may see the boxes may use any of it: permission level 1 of
the Talent Placement, which HR and the Talent Council have (case 10).
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import talent, talent_approval as approval, talent_rules as rules

PLACEMENT, REVIEW, PROGRAM = talent.PLACEMENT, talent.REVIEW, talent.PROGRAM
POSITION, TRAINEE = talent.POSITION, talent.TRAINEE
# the roles nobody can fill first, then the ones that would cost most to lose
COVERAGE_ORDER = {rules.POSITION_GAP: 0, rules.AT_RISK: 1, rules.COVERED: 2}
RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}

BOARD_FIELDS = ["name", "employee", "employee_name", "designation", "department", "branch", "grade",
                "workflow_state", "docstatus", "box", "box_name", "performance_score", "performance_band",
                "potential_score", "potential_band", "calibrated_potential", "top_talent", "flight_risk",
                "on_pip", "submitted_box"]
# what each bulk action does: action -> the state it applies to
BULK = {approval.TO_COUNCIL: approval.CALIBRATION, approval.RETURN: approval.CALIBRATION,
        approval.FINALISE: approval.COUNCIL_REVIEW, approval.RETURN_TO_CALIBRATION: approval.COUNCIL_REVIEW}


def can_see_boxes(user=None):
    """Whether the user may see where people sit on the grid: read access at
    permission level 1 of the Talent Placement (test case 10)."""
    return 1 in frappe.get_meta(PLACEMENT).get_permlevel_access("read", user=user)


def _check_access():
    if not can_see_boxes():
        frappe.throw(_("The talent board is for HR and the Talent Council."), frappe.PermissionError)


@frappe.whitelist()
def get_board(review=None, branch=None, department=None, grade=None, plan=None):
    """The review on the board: the one picked, else the latest of the
    appraisal plan picked, else the latest of all. A plan no review reads
    yet comes back with the means to start one (start_review)."""
    _check_access()
    reviews = frappe.get_all(REVIEW, filters={"appraisal_plan": plan} if plan else {},
                             fields=["name", "title", "review_year", "status", "appraisal_plan",
                                     "opens_on", "closes_on"],
                             order_by="review_year desc, opens_on desc", limit=50)
    if review and plan and frappe.db.get_value(REVIEW, review, "appraisal_plan") != plan:
        review = None  # a review of another plan: the plan picked decides
    review = review or (reviews[0].name if reviews else None)
    if not review:
        return {"reviews": [], "review": None,
                "plan": frappe.db.get_value("Appraisal Plan", plan, ["name", "title", "year", "branch",
                                                                    "department", "docstatus"], as_dict=True)
                if plan else None,
                "can_start": 1 if plan and frappe.has_permission(REVIEW, "create") else 0}
    everyone = frappe.get_all(PLACEMENT, filters={"talent_review": review, "docstatus": ["<", 2]},
                              fields=BOARD_FIELDS, limit=5000)
    scope = {"branch": branch, "department": department, "grade": grade}
    shown = [row for row in everyone if all(not value or row.get(field) == value for field, value in scope.items())]
    movers = frappe.get_all("Talent Calibration Entry",
                            filters={"parent": review, "parenttype": REVIEW},
                            fields=["placement", "employee", "employee_name", "from_box", "to_box", "moved_by",
                                    "moved_on", "reason"], order_by="idx asc", limit=500)
    moved = {row.placement for row in movers}
    for row in shown:
        row["moved"] = 1 if row.name in moved else 0
        row["state"] = row.get("workflow_state") or approval.DRAFT
    composed = rules.board(shown)
    states = {}
    for row in shown:
        states[row["state"]] = states.get(row["state"], 0) + 1
    roles = frappe.get_roles()
    return {
        "reviews": reviews,
        "review": next((row for row in reviews if row.name == review), None)
        or frappe.db.get_value(REVIEW, review, ["name", "title", "review_year", "status", "appraisal_plan"],
                               as_dict=True),
        "board": composed,
        "states": states,
        "strips": {name: {"count": count, "share": rules.share(count, composed["total"])}
                   for name, count in composed["strips"].items()},
        "flight_risk": len([row for row in shown if cint(row.get("top_talent"))
                            and row.get("flight_risk") in ("High", "Medium")]),
        "on_pip": len([row for row in shown if cint(row.get("on_pip"))]),
        "movers": [row for row in movers if row.placement in {each.name for each in shown}],
        "options": {field: sorted({row.get(field) for row in everyone if row.get(field)})
                    for field in ("branch", "department", "grade")},
        "actions": [action for action, state in BULK.items()
                    if states.get(state) and any(transition[0] == action
                                                 for transition in approval.next_states(state, roles))],
        "can_move": 1 if any(action for action, _next in approval.next_states(approval.CALIBRATION, roles))
        else 0,
        # a review nobody is in yet offers Draft Placements to whoever may write it
        "can_draft": 1 if frappe.has_permission(REVIEW, "write", doc=review) else 0,
    }


@frappe.whitelist(methods=["POST"])
def start_review(appraisal_plan):
    """The talent review of an appraisal plan, started from the board: the
    plan's year, plant and department, read from the latest quarter it has
    opened. One already reading the plan is given back instead."""
    _check_access()
    frappe.has_permission(REVIEW, "create", throw=True)
    existing = frappe.db.get_value(REVIEW, {"appraisal_plan": appraisal_plan, "status": ["!=", "Cancelled"]},
                                   "name")
    if existing:
        return existing
    plan = frappe.get_doc("Appraisal Plan", appraisal_plan)
    plan.check_permission("read")
    if plan.docstatus != 1:
        frappe.throw(_("Submit appraisal plan {0} first: its quarters open once it is.").format(plan.name),
                     title=_(REVIEW))
    opened = frappe.get_all("Appraisal Plan Quarter",
                            filters={"parent": plan.name, "parenttype": "Appraisal Plan",
                                     "appraisal_cycle": ["is", "set"]},
                            fields=["appraisal_cycle"], order_by="to_date desc", limit=1)
    if not opened:
        frappe.throw(_("No quarter of {0} has been opened yet, so nobody has been appraised to place.").format(
            plan.name), title=_(REVIEW))
    doc = frappe.new_doc(REVIEW)
    doc.update({
        "title": rules.review_title(plan.year, plan.get("branch"), plan.get("department"), plan.name,
                                    frappe.get_all(REVIEW, pluck="name")),
        "review_year": plan.year, "appraisal_plan": plan.name, "appraisal_cycle": opened[0].appraisal_cycle,
        "opens_on": today(), "company": plan.company, "branch": plan.get("branch"),
        "department": plan.get("department"),
    })
    doc.insert()
    return doc.name


@frappe.whitelist(methods=["POST"])
def move(placement, to_box, reason=None):
    """Test case 7 on the board: the peer group moves a placement up or down
    its column — potential is theirs to weigh across the plants, performance
    is the appraisal's — and says why; the move is written into the movers
    (talent._record_calibration). Moving it back to the line manager's own
    rating takes the calibration off."""
    _check_access()
    doc = frappe.get_doc(PLACEMENT, placement)
    doc.check_permission("write")
    errors = rules.move_errors({"state": doc.get("workflow_state"), "calibrating": approval.CALIBRATION,
                                "from_box": doc.get("box"), "to_box": to_box, "reason": reason})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Calibration"))
    potential = rules.box_axes(to_box)[1]
    doc.calibrated_potential = None if potential == doc.get("potential_band") else potential
    doc.calibration_reason = reason
    # the calibrated potential is at permission level 1, which is checked
    # here (_check_access) rather than left for the save to quietly undo
    doc.flags.ignore_permissions = True
    doc.save()
    return {"box": doc.box, "box_name": doc.box_name}


@frappe.whitelist(methods=["POST"])
def advance(review, action, branch=None, department=None, grade=None, remarks=None):
    """The step `action` for every placement on the board at the state it
    applies to, as the workflow allows the user. Each is saved as it is
    from the form, so each is checked, signed and told; one that cannot go
    is left, with the reason. Returns {"done": n, "left": [[name, why]]}."""
    _check_access()
    if action not in BULK:
        frappe.throw(_("{0} is not a step the board takes.").format(action))
    state = BULK[action]
    allowed = dict(approval.next_states(state, frappe.get_roles()))
    if action not in allowed:
        frappe.throw(_("You may not {0} placements.").format(_(action).lower()), frappe.PermissionError)
    returning = action in (approval.RETURN, approval.RETURN_TO_CALIBRATION)
    if returning and not (remarks or "").strip():
        frappe.throw(_("Write what the placements must have before they come back."))
    filters = {"talent_review": review, "workflow_state": state, "docstatus": 0}
    for field, value in (("branch", branch), ("department", department), ("grade", grade)):
        if value:
            filters[field] = value
    done, left = 0, []
    for number, name in enumerate(frappe.get_all(PLACEMENT, filters=filters, pluck="name", limit=5000)):
        doc = frappe.get_doc(PLACEMENT, name)
        doc.workflow_state = allowed[action]
        if returning:
            doc.return_remarks = remarks
        # each placement in a savepoint of its own: one that is refused
        # takes back only what it wrote
        savepoint = "ha_talent_advance_%d" % number
        frappe.db.savepoint(savepoint)
        try:
            if allowed[action] == approval.FINALISED:
                doc.submit()
            else:
                doc.save()
            done += 1
        except Exception as error:  # noqa: BLE001 - each placement stands alone
            frappe.db.rollback(save_point=savepoint)
            left.append([doc.get("employee_name") or doc.employee, _plain(error)])
    return {"done": done, "left": left}


@frappe.whitelist()
def get_card(employee, review=None):
    """One employee's talent card, or {"allowed": 0} for somebody who may
    not see where people sit (the Employee and Appraisal forms ask quietly)."""
    if not can_see_boxes():
        return {"allowed": 0}
    person = frappe.db.get_value("Employee", employee, ["name", "employee_name", "designation", "department",
                                                        "branch", "grade", "image", "date_of_joining",
                                                        "employment_type", "status"], as_dict=True)
    if not person:
        return {"allowed": 1, "employee": None}
    filters = {"employee": employee, "docstatus": ["<", 2]}
    if review:
        filters["talent_review"] = review
    placement = frappe.get_all(PLACEMENT, filters=filters, fields=["name"], order_by="creation desc", limit=1)
    card = {"allowed": 1, "employee": person, "placement": None}
    if placement:
        doc = frappe.get_doc(PLACEMENT, placement[0].name)
        card["placement"] = {
            "name": doc.name, "review": doc.talent_review, "state": doc.get("workflow_state") or approval.DRAFT,
            "box": doc.get("box"), "box_name": doc.get("box_name"), "colour": doc.get("box_colour"),
            "action": doc.get("default_action"), "decision": doc.get("suggested_decision"),
            "performance": doc.get("performance_score"), "performance_band": doc.get("performance_band"),
            "appraisal_band": doc.get("appraisal_band"), "appraisal": doc.get("appraisal"),
            "potential": doc.get("potential_score"), "potential_band": doc.get("potential_band"),
            "calibrated_potential": doc.get("calibrated_potential"),
            "dimensions": {name: doc.get(name) for name in rules.POTENTIAL_DIMENSIONS},
            "competencies": sorted([{"competency": row.competency, "level": row.level} for row in doc.competencies],
                                   key=lambda row: -(row["level"] or 0))[:6],
            "quarters": [{"quarter": row.quarter, "total": row.total, "band": row.band, "appraisal": row.appraisal}
                         for row in doc.get("quarter_results") or []],
            "flight_risk": doc.get("flight_risk"), "impact_of_loss": doc.get("impact_of_loss"),
            "rationale": doc.get("rationale"), "top_talent": cint(doc.get("top_talent")),
            "on_pip": cint(doc.get("on_pip")), "improvement_plan": doc.get("improvement_plan"),
            "management_decision": doc.get("management_decision"),
            "development_plan": doc.get("development_plan"),
        }
    card["history"] = [{"year": _year_of(row.talent_review), "box": row.box, "box_name": row.box_name}
                       for row in frappe.get_all(PLACEMENT, filters={"employee": employee, "docstatus": 1},
                                                 fields=["talent_review", "box", "box_name"],
                                                 order_by="creation asc", limit=10)]
    card["successor_for"] = [
        {"position": row.parent, "role": frappe.db.get_value(POSITION, row.parent, "designation"),
         "readiness": row.readiness}
        for row in frappe.get_all("Succession Candidate", filters={"employee": employee, "parenttype": POSITION},
                                  fields=["parent", "readiness"], limit=10)
        if frappe.db.get_value(POSITION, row.parent, "docstatus") != 2]
    card["holds"] = frappe.get_all(POSITION, filters={"incumbent": employee, "docstatus": ["<", 2]},
                                   fields=["name", "designation", "coverage", "risk_level"], limit=5)
    plan = frappe.get_all(PROGRAM, filters={"employee": employee, "docstatus": ["<", 2]},
                          fields=["name", "program_type", "workflow_state", "start_date", "end_date"],
                          order_by="creation desc", limit=1)
    if plan:
        actions = frappe.get_all("Development Action", filters={"parent": plan[0].name, "parenttype": PROGRAM},
                                 fields=["completed_on"], limit=100)
        card["plan"] = dict(plan[0], actions=len(actions),
                            completed=len([row for row in actions if row.completed_on]))
    trainee = frappe.get_all(TRAINEE, filters={"employee": employee, "docstatus": ["<", 2]},
                             fields=["name", "cohort", "workflow_state", "milestones_passed"], limit=1)
    card["trainee"] = trainee[0] if trainee else None
    # somebody not yet placed may still be on an improvement plan
    card["improvement_plan"] = card["placement"]["improvement_plan"] if card["placement"] \
        else talent.pips.open_plan(employee)
    return card


def _year_of(review):
    return frappe.db.get_value(REVIEW, review, "review_year") if review else None


def _plain(error):
    """A refusal as the user reads it: the message, without the markup."""
    text = str(error.args[0]) if getattr(error, "args", None) else str(error)
    return frappe.utils.strip_html(text).strip() or type(error).__name__


@frappe.whitelist()
def get_succession(branch=None, department=None):
    """Test cases 11 to 15 on the board: every critical role, who holds it
    and what losing them would cost, the successors named for it by
    readiness with where each sits on the grid, and how covered the roles
    are, the gaps first. A holder on their way out shows what is filling
    the role: the promotion drafted for a successor, or the requisition for
    a replacement and the opening it became."""
    _check_access()
    filters = {"docstatus": ["<", 2]}
    for field, value in (("branch", branch), ("department", department)):
        if value:
            filters[field] = value
    positions = frappe.get_all(POSITION, filters=filters, fields=[
        "name", "designation", "department", "branch", "incumbent", "incumbent_name", "single_person_role",
        "risk_level", "coverage", "bench_depth", "gap", "gap_confirmed", "job_opening", "workflow_state",
        "retirement_or_exit_due"], limit=500)
    names = [row.name for row in positions]
    candidates = frappe.get_all("Succession Candidate", filters={"parent": ["in", names], "parenttype": POSITION},
                                fields=["parent", "employee", "employee_name", "candidate_designation", "readiness"],
                                order_by="idx asc", limit=5000) if names else []
    boxes = _latest_boxes([row.employee for row in candidates] + [row.incumbent for row in positions])
    slates = {}
    for row in candidates:
        found = boxes.get(row.employee) or {}
        slates.setdefault(row.parent, []).append(dict(row, box=found.get("box"), box_name=found.get("box_name"),
                                                      colour=found.get("box_colour")))
    drafted = talent.drafted_for_many(names)
    for position in positions:
        position["slate"] = rules.readiness_order(slates.get(position.name, []))
        held = boxes.get(position.incumbent) or {}
        position["incumbent_box"] = held.get("box")
        position["incumbent_risk"] = held.get("flight_risk")
        found = drafted.get(position.name) or {}
        position["exit_days"] = rules.days_until(position.retirement_or_exit_due, today())
        position["exit_reason"] = (found.get("exit") or {}).get("custom_reason")
        position["promotion"] = found.get("promotion")
        position["requisition"] = found.get("requisition")
        position["opening"] = found.get("opening")
    positions.sort(key=lambda row: (COVERAGE_ORDER.get(row.coverage, 3), RISK_ORDER.get(row.risk_level, 3),
                                    str(row.designation or "")))
    summary = {"roles": len(positions)}
    for name in (rules.COVERED, rules.AT_RISK, rules.POSITION_GAP):
        summary[name] = len([row for row in positions if row.coverage == name])
    summary["covered_share"] = rules.share(summary[rules.COVERED], len(positions))
    summary["single_person"] = len([row for row in positions if cint(row.single_person_role)])
    summary["high_risk"] = len([row for row in positions if row.risk_level == "High"])
    return {"positions": positions, "summary": summary}


def _latest_boxes(employees):
    """Each employee's box on their latest finalised placement, and the
    flight risk it carries."""
    employees = sorted({name for name in employees if name})
    if not employees:
        return {}
    found = {}
    for row in frappe.get_all(PLACEMENT, filters={"employee": ["in", employees], "docstatus": 1},
                              fields=["employee", "box", "box_name", "box_colour", "flight_risk", "creation"],
                              order_by="creation asc", limit=5000):
        found[row.employee] = row
    return found


@frappe.whitelist()
def get_trainees(branch=None):
    """Test cases 16 to 20 on the board: every graduate trainee by the stage
    they are at, with their mentor, how far they are and the milestone
    they are working towards."""
    _check_access()
    filters = {"docstatus": ["<", 2]}
    if branch:
        filters["home_branch"] = branch
    rows = frappe.get_all(TRAINEE, filters=filters, fields=[
        "name", "trainee_name", "cohort", "workflow_state", "mentor_name", "home_branch", "designation",
        "start_date", "end_date", "milestones_passed", "average_score", "last_result", "employee"],
        order_by="start_date desc", limit=1000)
    names = [row.name for row in rows]
    due = {}
    for row in frappe.get_all("Trainee Milestone", filters={"parent": ["in", names], "parenttype": TRAINEE,
                                                             "result": ["in", ("", None)]},
                              fields=["parent", "milestone", "due_on"], order_by="due_on asc", limit=5000) \
            if names else []:
        due.setdefault(row.parent, row)
    today_ = getdate(today())
    for row in rows:
        upcoming = due.get(row.name)
        row["next_milestone"] = upcoming.milestone if upcoming else None
        row["next_due"] = upcoming.due_on if upcoming else None
        row["overdue"] = 1 if upcoming and upcoming.due_on and getdate(upcoming.due_on) < today_ else 0
    stages = [{"stage": stage, "trainees": [row for row in rows if (row.workflow_state or rules.RECRUITED) == stage]}
              for stage in rules.TRAINEE_STATES]
    return {"stages": stages, "summary": {
        "in_programme": len([row for row in rows if row.workflow_state not in (rules.CONFIRMED, rules.EXITED)]),
        "confirmed": len([row for row in rows if row.workflow_state == rules.CONFIRMED]),
        "exited": len([row for row in rows if row.workflow_state == rules.EXITED]),
        "overdue": len([row for row in rows if row.get("overdue")]),
    }}
