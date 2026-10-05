# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What the talent reports share (report/nine_box_distribution and the six
beside it), and the month the Monthly Talent Report reads — the testing
sheet's recommendation, "Provide end-of-month reports in the system".

  latest_review   the review a report reads when none is named
  check_boxes     a report that names boxes is for HR and the Talent Council
  plan_progress   each development plan's actions done, and past their date
  month           what happened in talent in a month, and where it stands
"""

import frappe
from frappe import _
from frappe.utils import cint, today

from hrms_addon.hrms_addon import talent, talent_board, talent_rules as rules

PLACEMENT, PROGRAM, POSITION, TRAINEE = talent.PLACEMENT, talent.PROGRAM, talent.POSITION, talent.TRAINEE


def latest_review():
    found = frappe.get_all(talent.REVIEW, order_by="review_year desc, opens_on desc", limit=1, pluck="name")
    return found[0] if found else None


def check_boxes():
    """Test case 10 for the reports: one that names where people sit is for
    those who may read the boxes."""
    if not talent_board.can_see_boxes():
        frappe.throw(_("This report names where people sit on the nine-box: it is for HR and the Talent Council."),
                     frappe.PermissionError)


def plan_progress(plans, day=None):
    """{plan: {"actions", "done", "late", "share"}} for the plans named."""
    names = list(plans or [])
    rows = frappe.get_all("Development Action", filters={"parent": ["in", names], "parenttype": PROGRAM},
                          fields=["parent", "completed_on", "by_when"], limit=0) if names else []
    by_plan = {}
    for row in rows:
        by_plan.setdefault(row.parent, []).append(row)
    return {name: rules.plan_progress(by_plan.get(name, []), day or today()) for name in names}


def month(day=None):
    """What happened in talent in the month `day` falls in (today's when
    none), and where things stand at its end: {"start", "end", "events",
    "summary"}. Each event is a row of the report: when, the part of
    talent, who, what happened, and the document it happened on."""
    start, end = rules.month_bounds(day or today())
    within = ["between", [start, end]]
    events = []

    def event(date, area, employee_name, what, doctype, name):
        events.append({"date": date, "area": area, "employee_name": employee_name, "what": what,
                       "reference_doctype": doctype, "reference_name": name})

    finalised = frappe.get_all(PLACEMENT, filters={"docstatus": 1, "finalised_on": within}, fields=[
        "name", "employee_name", "box", "box_name", "top_talent", "flight_risk", "finalised_on"], limit=0)
    for row in finalised:
        risk = _(", flight risk {0}").format(_(row.flight_risk).lower()) \
            if cint(row.top_talent) and row.flight_risk in ("High", "Medium") else ""
        event(row.finalised_on, _("Nine-box"), row.employee_name,
              _("Finalised in box {0}, {1}{2}").format(row.box, _(row.box_name or ""), risk), PLACEMENT, row.name)
    moves = frappe.get_all("Talent Calibration Entry", filters={"parenttype": talent.REVIEW, "moved_on": within},
                           fields=["parent", "placement", "employee_name", "from_box", "to_box", "reason", "moved_on"],
                           limit=0)
    for row in moves:
        event(row.moved_on, _("Calibration"), row.employee_name,
              _("Moved from box {0} to box {1}: {2}").format(row.from_box, row.to_box, row.reason or ""),
              PLACEMENT, row.placement)
    confirmed = frappe.get_all(POSITION, filters={"docstatus": 1, "confirmed_on": within}, fields=[
        "name", "designation", "incumbent_name", "coverage", "gap_confirmed", "job_opening", "confirmed_on"], limit=0)
    for row in confirmed:
        what = _("Bench confirmed for {0}: {1}").format(row.designation, _(row.coverage or ""))
        if cint(row.gap_confirmed) and row.job_opening:
            what += _("; the gap is being recruited for ({0})").format(row.job_opening)
        event(row.confirmed_on, _("Succession"), row.incumbent_name, what, POSITION, row.name)
    done = frappe.get_all("Development Action", filters={"parenttype": PROGRAM, "completed_on": within},
                          fields=["parent", "action", "completed_on"], limit=0)
    owners = {row.name: row.employee_name for row in frappe.get_all(
        PROGRAM, filters={"name": ["in", sorted({row.parent for row in done})]},
        fields=["name", "employee_name"], limit=0)} if done else {}
    for row in done:
        event(row.completed_on, _("Development"), owners.get(row.parent), _("Done: {0}").format(row.action),
              PROGRAM, row.parent)
    closed = frappe.get_all(PROGRAM, filters={"docstatus": 1, "reviewed_on": within}, fields=[
        "name", "employee_name", "program_type", "effectiveness", "decision", "reviewed_on"], limit=0)
    for row in closed:
        event(row.reviewed_on, _("Development"), row.employee_name,
              _("{0} closed: {1}, decided {2}").format(_(row.program_type or ""), _(row.effectiveness or "not read"),
                                                        _(row.decision or "nothing")), PROGRAM, row.name)
    trainees = frappe.get_all(TRAINEE, filters={"docstatus": 1, "confirmed_on": within}, fields=[
        "name", "trainee_name", "workflow_state", "confirmed_employment_type", "exit_reason", "confirmed_on"],
        limit=0)
    for row in trainees:
        what = _("Confirmed as {0}").format(row.confirmed_employment_type or _("an employee")) \
            if row.workflow_state != "Exited" else _("Left the programme: {0}").format(row.exit_reason or "")
        event(row.confirmed_on, _("Graduate trainees"), row.trainee_name, what, TRAINEE, row.name)
    events.sort(key=lambda row: (str(row["date"] or ""), row["area"]))
    late = frappe.get_all("Development Action", filters={"parenttype": PROGRAM, "completed_on": ["is", "not set"],
                                                         "by_when": ["<=", end]}, pluck="name", limit=0)
    summary = {
        "finalised": len(finalised),
        "top_talent": len([row for row in finalised if cint(row.top_talent)]),
        "at_risk": len([row for row in finalised if cint(row.top_talent) and row.flight_risk in ("High", "Medium")]),
        "moves": len(moves),
        "roles_confirmed": len(confirmed),
        "gaps": len([row for row in confirmed if cint(row.gap_confirmed)]),
        "actions_done": len(done),
        "actions_late": len(late),
        "programmes_closed": len(closed),
        "trainees_confirmed": len([row for row in trainees if row.workflow_state != "Exited"]),
        "trainees_left": len([row for row in trainees if row.workflow_state == "Exited"]),
    }
    return {"start": start, "end": end, "events": events, "summary": summary}
