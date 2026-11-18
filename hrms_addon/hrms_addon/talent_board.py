# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Talent Board (page/talent_board): one review on one grid, and the
talent card of each person on it (Luuka, 5 Oct 2026: the module had every
form and no way to manage talent with them). Built for a review of the
whole staff: the grid is counted in SQL, each cell shows its first people
and pages through the rest, and the steps over everybody run in the
background.

  get_board  the review on the grid (the review picked, or the latest of
             the appraisal plan picked), filtered by plant, department and
             grade: each box counted, its first people, the steps they are
             at, the moves waiting in a calibration session, the movers
             (from the calibration log) and those waiting to be placed
  get_cell, get_waiting
             the next people of a box, and of those waiting to be placed
  start_review  the review of an appraisal plan none reads yet
  get_card   one employee's talent card: the year as their appraisals hold
             it, the potential by criterion and rater, the competency
             evidence, the box over the years, the benches they are on,
             their development plan, flight risk over time and the
             retention actions. Shown on the board, the Employee form and
             the Appraisal form
  move       calibration on the board: a placement moved on either axis,
             with the reason, into the draft session that covers it, else
             at once (calibration.board_move)
  advance    the next step for every placement on the board at the step it
             applies to (send to the council, finalise, return), in the
             background (talent_jobs): each taken as it is on its form, so
             each is checked and signed, one that cannot go left with the
             reason, and one digest a person
  get_succession  every critical role, its holder, the risk of losing them
             and the successors ranked, with their boxes
  get_trainees  every graduate trainee by stage

Only those who may see the boxes may use any of it: permission level 1 of
the Talent Placement, which HR, the Talent Council and the executives have
(case 10).
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import talent, talent_approval as approval, talent_jobs, talent_masters
from hrms_addon.hrms_addon import talent_rules as rules

PLACEMENT, REVIEW, PROGRAM = talent.PLACEMENT, talent.REVIEW, talent.PROGRAM
POSITION, TRAINEE = talent.POSITION, talent.TRAINEE
# the roles nobody can fill first, then the ones that would cost most to lose
COVERAGE_ORDER = {rules.POSITION_GAP: 0, rules.AT_RISK: 1, rules.COVERED: 2}
RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}
PER_CELL = 12
PAGE = 50

BOARD_FIELDS = ["name", "employee", "employee_name", "designation", "department", "branch", "grade",
                "workflow_state", "docstatus", "box", "box_name", "performance_score", "performance_band",
                "potential_score", "potential_band", "calibrated_potential", "calibrated_performance", "top_talent",
                "flight_risk", "on_pip", "submitted_box", "raters", "raters_disagree"]
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


def _where(review, branch=None, department=None, grade=None):
    """The board's filters as SQL on `tabTalent Placement` p."""
    parts, values = ["p.talent_review = %(review)s", "p.docstatus < 2"], {"review": review}
    for field, value in (("branch", branch), ("department", department), ("grade", grade)):
        if value:
            parts.append("p.%s = %%(%s)s" % (field, field))
            values[field] = value
    return " and ".join(parts), values


def _people(where, values, extra="", order="p.performance_score desc, p.employee_name asc", start=0,
            length=PER_CELL):
    return frappe.db.sql("""select {fields} from `tabTalent Placement` p where {where} {extra}
                            order by {order} limit %(start)s, %(length)s""".format(
        fields=", ".join("p.%s" % field for field in BOARD_FIELDS), where=where, extra=extra, order=order),
        dict(values, start=cint(start), length=cint(length)), as_dict=True)


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
    from hrms_addon.hrms_addon import calibration, calibration_rules

    where, values = _where(review, branch, department, grade)
    watched = talent_masters.watched_risks() or ["-"]
    counts = {cint(row.box): cint(row.n) for row in frappe.db.sql(
        """select p.box, count(*) as n from `tabTalent Placement` p where {0} and p.box between 1 and 9
           group by p.box""".format(where), values, as_dict=True)}
    sums = frappe.db.sql("""
        select count(*) as total,
               sum(case when p.box between 1 and 9 then 0 else 1 end) as waiting,
               sum(case when p.top_talent = 1 and p.flight_risk in %(watched)s then 1 else 0 end) as flight_risk,
               sum(case when p.on_pip = 1 then 1 else 0 end) as on_pip,
               sum(case when p.raters_disagree = 1 then 1 else 0 end) as disagree
        from `tabTalent Placement` p where {0}""".format(where), dict(values, watched=watched), as_dict=True)[0]
    states = {row.state: cint(row.n) for row in frappe.db.sql(
        """select coalesce(p.workflow_state, 'Draft') as state, count(*) as n from `tabTalent Placement` p
           where {0} group by p.workflow_state""".format(where), values, as_dict=True)}
    grid = talent_masters.grid()
    waiting = calibration.pending(review)
    cells = []
    for cell in sorted(grid["boxes"].values(), key=lambda cell: cell["box"]):
        people = _people(where, values, "and p.box = %d" % cell["box"]) if counts.get(cell["box"]) else []
        for row in people:
            _mark(row, waiting)
        cells.append({"box": cell["box"], "name": cell["name"], "colour": cell["colour"], "action": cell["action"],
                      "count": counts.get(cell["box"], 0), "guide": cell.get("guide"), "people": people})
    placed = sum(counts.values())
    top = tuple(grid.get("top_talent") or rules.TOP_TALENT)
    attention = tuple(box for box in rules.ATTENTION if box not in top)
    core = tuple(box for box in range(1, 10) if box not in top and box not in attention)
    strips = {name: sum(counts.get(box, 0) for box in boxes)
              for name, boxes in (("top", top), ("core", core), ("attention", attention))}
    unplaced = _people(where, values, "and (p.box is null or p.box = 0)", order="p.employee_name asc", length=25) \
        if cint(sums.waiting) else []
    shown = {row.name for cell in cells for row in cell["people"]}
    movers = [row for row in calibration.movers(review, limit=500)
              if all(not value or row.get(field) == value for field, value in (("branch", branch),
                                                                               ("department", department)))][:100]
    for row in movers:
        row["shown"] = 1 if row.get("placement") in shown else 0
    spread = calibration_rules.distribution({}, counts, talent_masters.guide())
    roles = frappe.get_roles()
    options = {field: [row[0] for row in frappe.db.sql(
        "select distinct p.{0} from `tabTalent Placement` p where p.talent_review = %(review)s and p.docstatus < 2 "
        "and p.{0} is not null and p.{0} != '' order by p.{0}".format(field), {"review": review})]
        for field in ("branch", "department", "grade")}
    return {
        "reviews": reviews,
        "review": next((row for row in reviews if row.name == review), None)
        or frappe.db.get_value(REVIEW, review, ["name", "title", "review_year", "status", "appraisal_plan"],
                               as_dict=True),
        "board": {"cells": cells, "unplaced": unplaced, "waiting": cint(sums.waiting), "total": placed,
                  "per_cell": PER_CELL},
        "states": states,
        "strips": {name: {"count": count, "share": rules.share(count, placed)} for name, count in strips.items()},
        "guide": [{"box": row["box"], "guide": row["guide"], "share": row["calibrated_share"],
                   "variance": row["variance"]} for row in spread],
        "flight_risk": cint(sums.flight_risk), "on_pip": cint(sums.on_pip), "disagree": cint(sums.disagree),
        "pending": len(waiting),
        "movers": movers,
        "options": options,
        "actions": [action for action, state in BULK.items()
                    if states.get(state) and any(transition[0] == action
                                                 for transition in approval.next_states(state, roles))],
        "can_move": 1 if any(action for action, _next in approval.next_states(approval.CALIBRATION, roles))
        else 0,
        # a review nobody is in yet offers Draft Placements to whoever may write it
        "can_draft": 1 if frappe.has_permission(REVIEW, "write", doc=review) else 0,
    }


def _mark(row, waiting):
    row["state"] = row.get("workflow_state") or approval.DRAFT
    row["moved"] = 1 if row.get("calibrated_potential") or row.get("calibrated_performance") else 0
    row["pending_box"] = waiting.get(row.name)


@frappe.whitelist()
def get_cell(review, box, start=0, branch=None, department=None, grade=None):
    """The next people of a box, PAGE at a time."""
    _check_access()
    from hrms_addon.hrms_addon import calibration

    where, values = _where(review, branch, department, grade)
    people = _people(where, values, "and p.box = %d" % cint(box), start=cint(start), length=PAGE)
    waiting = calibration.pending(review)
    for row in people:
        _mark(row, waiting)
    return people


@frappe.whitelist()
def get_waiting(review, start=0, branch=None, department=None, grade=None):
    """The next of those waiting to be placed, PAGE at a time."""
    _check_access()
    where, values = _where(review, branch, department, grade)
    return _people(where, values, "and (p.box is null or p.box = 0)", order="p.employee_name asc",
                   start=cint(start), length=PAGE)


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
        "plants": [{"branch": plan.branch}] if plan.get("branch") else [],
        "department": plan.get("department"),
    })
    doc.insert()
    return doc.name


@frappe.whitelist(methods=["POST"])
def move(placement, to_box, reason=None):
    """Test case 7 on the board: the peer group moves a placement on either
    axis and says why. Where a draft calibration session covers it, the
    move is written into the session, applied when it is submitted; else
    it is applied at once. Either way it is in the calibration log. Moving
    it back to its own ratings takes the calibration off."""
    _check_access()
    doc = frappe.get_doc(PLACEMENT, placement)
    doc.check_permission("write")
    errors = rules.move_errors({"state": doc.get("workflow_state"), "calibrating": approval.CALIBRATION,
                                "from_box": doc.get("box"), "to_box": to_box, "reason": reason})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Calibration"))
    from hrms_addon.hrms_addon import calibration

    return calibration.board_move(doc, cint(to_box), reason)


@frappe.whitelist(methods=["POST"])
def advance(review, action, branch=None, department=None, grade=None, remarks=None):
    """The step `action` for every placement on the board at the state it
    applies to, as the workflow allows the user, in the background. Returns
    {"queued": 1, "log"}: the board follows the log."""
    _check_access()
    if action not in BULK:
        frappe.throw(_("{0} is not a step the board takes.").format(action))
    allowed = dict(approval.next_states(BULK[action], frappe.get_roles()))
    if action not in allowed:
        frappe.throw(_("You may not {0} placements.").format(_(action).lower()), frappe.PermissionError)
    if action in (approval.RETURN, approval.RETURN_TO_CALIBRATION) and not (remarks or "").strip():
        frappe.throw(_("Write what the placements must have before they come back."))
    log = talent_jobs.start("advance", REVIEW, review, "hrms_addon.hrms_addon.talent_board.advance_job",
                            review=review, action=action, branch=branch, department=department, grade=grade,
                            remarks=remarks)
    return {"queued": 1, "log": log}


def advance_job(context, review, action, branch=None, department=None, grade=None, remarks=None):
    """The background step, as the user who asked: each placement at the
    state saved or submitted as from its form, in a savepoint of its own."""
    state = BULK[action]
    allowed = dict(approval.next_states(state, frappe.get_roles()))
    if action not in allowed:
        frappe.throw(_("You may not {0} placements.").format(_(action).lower()), frappe.PermissionError)
    returning = action in (approval.RETURN, approval.RETURN_TO_CALIBRATION)
    filters = {"talent_review": review, "workflow_state": state, "docstatus": 0}
    for field, value in (("branch", branch), ("department", department), ("grade", grade)):
        if value:
            filters[field] = value
    rows = {row.name: row for row in frappe.get_all(PLACEMENT, filters=filters, fields=["name", "employee_name"],
                                                    order_by="name asc", limit_page_length=0)}
    context.doctype = PLACEMENT

    def work(name):
        doc = frappe.get_doc(PLACEMENT, name)
        doc.workflow_state = allowed[action]
        if returning:
            doc.return_remarks = remarks
        if allowed[action] == approval.FINALISED:
            doc.submit()
        else:
            doc.save()

    context.each(list(rows), work, label=lambda name: rows[name].employee_name or name)
    title = frappe.db.get_value(REVIEW, review, "title") or review
    users = list(talent.people.hr_officers(branch, department))
    if allowed[action] == approval.COUNCIL_REVIEW:
        users += list(talent.people.people_for("Talent Council", branch, department))
    talent_jobs.tell(users, REVIEW, review, _("{0}: {1} placement(s) now at {2}, {3} left with a reason.").format(
        title, context.done, _(allowed[action]), len(context.left)))


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
            "calibrated_performance": doc.get("calibrated_performance"),
            "appraisal_band": doc.get("appraisal_band"), "appraisal": doc.get("appraisal"),
            "potential": doc.get("potential_score"), "potential_band": doc.get("potential_band"),
            "calibrated_potential": doc.get("calibrated_potential"),
            "raters": cint(doc.get("raters")), "rater_spread": doc.get("rater_spread"),
            "raters_disagree": cint(doc.get("raters_disagree")),
            "criteria": [{"criterion": row.criterion, "average": row.average, "lowest": row.lowest,
                          "highest": row.highest} for row in doc.get("potential_summary") or []],
            "competencies": sorted([{"competency": row.competency, "level": row.level} for row in doc.competencies],
                                   key=lambda row: -(row["level"] or 0))[:6],
            "quarters": [{"quarter": row.quarter, "total": row.total, "band": row.band, "appraisal": row.appraisal}
                         for row in doc.get("quarter_results") or []],
            "flight_risk": doc.get("flight_risk"), "impact_of_loss": doc.get("impact_of_loss"),
            "risk_assessed_on": doc.get("risk_assessed_on"),
            "retention": [{"action": row.action, "status": row.status, "due": row.due}
                          for row in doc.get("retention_actions") or [] if row.status not in ("Done", "Dropped")],
            "rationale": doc.get("rationale"), "top_talent": cint(doc.get("top_talent")),
            "on_pip": cint(doc.get("on_pip")), "improvement_plan": doc.get("improvement_plan"),
            "management_decision": doc.get("management_decision"),
            "development_plan": doc.get("development_plan"),
        }
    card["history"] = [{"year": row.review_year, "box": row.box, "box_name": row.box_name}
                       for row in frappe.db.sql("""
                           select review.review_year, p.box, p.box_name from `tabTalent Placement` p
                           left join `tabTalent Review` review on review.name = p.talent_review
                           where p.employee = %(employee)s and p.docstatus = 1
                           order by review.review_year asc, p.creation asc""", {"employee": employee}, as_dict=True)]
    card["risk_history"] = frappe.get_all("Flight Risk Assessment", filters={"employee": employee},
                                          fields=["assessed_on", "risk"], order_by="assessed_on desc", limit=5)
    card["successor_for"] = frappe.db.sql("""
        select candidate.parent as position, position.designation as role, candidate.readiness, candidate.rank
        from `tabSuccession Candidate` candidate
        join `tabSuccession Position` position on position.name = candidate.parent
        where candidate.parenttype = 'Succession Position' and candidate.employee = %(employee)s
          and position.docstatus < 2""", {"employee": employee}, as_dict=True)
    card["holds"] = frappe.get_all(POSITION, filters={"incumbent": employee, "docstatus": ["<", 2]},
                                   fields=["name", "designation", "coverage", "risk_level", "role_risk"], limit=5)
    card["pools"] = frappe.db.sql("""
        select pool.name, pool.pool_name, member.status from `tabTalent Pool Member` member
        join `tabTalent Pool` pool on pool.name = member.parent
        where member.parenttype = 'Talent Pool' and member.employee = %(employee)s and member.status != 'Exited'
        """, {"employee": employee}, as_dict=True)
    plan = frappe.get_all(PROGRAM, filters={"employee": employee, "docstatus": ["<", 2]},
                          fields=["name", "program_type", "workflow_state", "start_date", "end_date",
                                  "approved_investment"],
                          order_by="creation desc", limit=1)
    if plan:
        actions = frappe.get_all(talent.ACTION, filters={"parent": plan[0].name, "parenttype": PROGRAM},
                                 fields=["completed_on"], limit=200)
        card["plan"] = dict(plan[0], actions=len(actions),
                            completed=len([row for row in actions if row.completed_on]))
    trainee = frappe.get_all(TRAINEE, filters={"employee": employee, "docstatus": ["<", 2]},
                             fields=["name", "cohort", "workflow_state", "milestones_passed"], limit=1)
    card["trainee"] = trainee[0] if trainee else None
    # somebody not yet placed may still be on an improvement plan
    card["improvement_plan"] = card["placement"]["improvement_plan"] if card["placement"] \
        else talent.pips.open_plan(employee)
    return card


@frappe.whitelist()
def get_succession(branch=None, department=None):
    """Test cases 11 to 15 on the board: every critical role, who holds it
    and what losing them would cost, the successors named for it in the
    council's order with where each sits on the grid, and how covered the
    roles are, the gaps first. A holder on their way out shows what is
    filling the role."""
    _check_access()
    from hrms_addon.hrms_addon import succession_risk, succession_rules

    filters = {"docstatus": ["<", 2]}
    for field, value in (("branch", branch), ("department", department)):
        if value:
            filters[field] = value
    positions = frappe.get_all(POSITION, filters=filters, fields=[
        "name", "designation", "department", "branch", "incumbent", "incumbent_name", "single_person_role",
        "risk_level", "coverage", "bench_depth", "gap", "gap_confirmed", "job_opening", "workflow_state",
        "retirement_or_exit_due", "role_risk", "impact_score", "loss_probability", "successors"],
        limit_page_length=0)
    names = [row.name for row in positions]
    candidates = frappe.get_all("Succession Candidate", filters={"parent": ["in", names], "parenttype": POSITION},
                                fields=["parent", "employee", "employee_name", "candidate_designation", "readiness",
                                        "rank", "emergency_cover", "other_roles"],
                                order_by="idx asc", limit_page_length=0) if names else []
    boxes = succession_risk.latest_boxes([row.employee for row in candidates] + [row.incumbent for row in positions])
    slates = {}
    for row in candidates:
        found = boxes.get(row.employee) or {}
        slates.setdefault(row.parent, []).append(dict(row, box=found.get("box"), box_name=found.get("box_name"),
                                                      colour=found.get("box_colour"),
                                                      flight_risk=found.get("flight_risk")))
    drafted = talent.drafted_for_many(names)
    for position in positions:
        position["slate"] = succession_rules.ranked(slates.get(position.name, []))
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
                                    -(row.role_risk or 0), str(row.designation or "")))
    summary = {"roles": len(positions)}
    for name in (rules.COVERED, rules.AT_RISK, rules.POSITION_GAP):
        summary[name] = len([row for row in positions if row.coverage == name])
    summary["covered_share"] = rules.share(summary[rules.COVERED], len(positions))
    summary["single_person"] = len([row for row in positions if cint(row.single_person_role)])
    summary["high_risk"] = len([row for row in positions if row.risk_level == "High"])
    summary["bench"] = succession_rules.bench_index([{"ready_now": len([row for row in position["slate"]
                                                                        if row.get("readiness") == rules.READY_NOW]),
                                                      "successors": position.successors or len(position["slate"])}
                                                     for position in positions])
    return {"positions": positions, "summary": summary}


def _latest_boxes(employees):
    """Each employee's box on their latest finalised placement, newest first
    and without a cut-off (succession_risk.latest_boxes)."""
    from hrms_addon.hrms_addon import succession_risk

    return succession_risk.latest_boxes(employees)


@frappe.whitelist()
def get_trainees(branch=None, cohort=None):
    """Test cases 16 to 20 on the board: every graduate trainee by the stage
    they are at, with their mentor, how far they are and the milestone
    they are working towards."""
    _check_access()
    filters = {"docstatus": ["<", 2]}
    if branch:
        filters["home_branch"] = branch
    if cohort:
        filters["cohort"] = cohort
    rows = frappe.get_all(TRAINEE, filters=filters, fields=[
        "name", "trainee_name", "cohort", "discipline", "workflow_state", "mentor_name", "home_branch", "designation",
        "start_date", "end_date", "milestones_passed", "average_score", "last_result", "employee",
        "rotation_assessments", "mentoring_sessions"], order_by="start_date desc", limit_page_length=0)
    names = [row.name for row in rows]
    due = {}
    for row in frappe.get_all("Trainee Milestone", filters={"parent": ["in", names], "parenttype": TRAINEE,
                                                             "result": ["in", ("", None)]},
                              fields=["parent", "milestone", "due_on"], order_by="due_on asc",
                              limit_page_length=0) if names else []:
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
