# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Talent Board (page/talent_board): one review on one grid, and the
talent card of each person on it (Luuka, 5 Oct 2026: the module had every
form and no way to manage talent with them).

  get_board  the review's placements in their boxes, filtered by plant,
             department and grade, with the three strips, the steps they
             are at and the movers (test cases 6 to 8 and 21)
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

Only those who may see the boxes may use any of it: permission level 1 of
the Talent Placement, which HR and the Talent Council have (case 10).
"""

import frappe
from frappe import _
from frappe.utils import cint

from hrms_addon.hrms_addon import talent, talent_approval as approval, talent_rules as rules

PLACEMENT, REVIEW, PROGRAM = talent.PLACEMENT, talent.REVIEW, talent.PROGRAM
POSITION, TRAINEE = talent.POSITION, talent.TRAINEE

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
def get_board(review=None, branch=None, department=None, grade=None):
    _check_access()
    reviews = frappe.get_all(REVIEW, fields=["name", "title", "review_year", "status", "appraisal_plan",
                                             "opens_on", "closes_on"],
                             order_by="review_year desc, opens_on desc", limit=50)
    review = review or (reviews[0].name if reviews else None)
    if not review:
        return {"reviews": [], "review": None}
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
    }


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
