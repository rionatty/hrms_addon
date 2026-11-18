# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Calibration on the site: the sessions, the log and the board's moves.
The rules are in calibration_rules.py (scripts/verify_talent_calibration.py).

  session_*       a Calibration Session: its lines read from their
                  placements, the axis each move changes, the spread over
                  the boxes against the guide; submitted, its agreed moves
                  are applied in the background (talent_jobs) and the
                  review's checkpoint marked
  get_placements  a session's placements: those of its review, plant and
                  department still in calibration
  board_move      a drag on the Talent Board: written into the draft
                  session that covers the placement, else applied at once;
                  logged either way
  log             a Talent Calibration Log entry, insert only
  pending, movers what the board shows: moves waiting in draft sessions, and
                  the latest of each placement's moves
  daily           the mid-year checkpoint, told to HR when it falls due
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, today

from hrms_addon.hrms_addon import calibration_rules as rules, talent_jobs, talent_masters as masters
from hrms_addon.hrms_addon import talent_rules

SESSION, LOG, PLACEMENT, REVIEW = "Calibration Session", "Talent Calibration Log", "Talent Placement", "Talent Review"
CALIBRATING = "In Calibration"
LINE_FIELDS = ["name", "employee", "employee_name", "designation", "department", "branch", "performance_band",
               "potential_band", "calibrated_performance", "calibrated_potential", "box", "workflow_state",
               "docstatus", "talent_review"]


# ── The session ───────────────────────────────────────────────────────
def session_validate(doc):
    year = frappe.db.get_value(REVIEW, doc.talent_review, "review_year") if doc.get("talent_review") else None
    doc.title = " ".join(str(part) for part in (doc.get("checkpoint"), year, doc.get("branch") or _("All plants"),
                                                doc.get("department")) if part)
    _read_lines(doc)
    errors = rules.session_errors({"talent_review": doc.get("talent_review"), "checkpoint": doc.get("checkpoint"),
                                   "lines": [row.as_dict() for row in doc.get("lines") or []]})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SESSION))
    _spread(doc)
    if doc.docstatus == 0:
        doc.status = "Draft"


def _read_lines(doc):
    """Each line as its placement has it; the box proposed is the one the
    placement had when it came into the session."""
    names = [row.placement for row in doc.get("lines") or [] if row.get("placement")]
    found = {row.name: row for row in frappe.get_all(PLACEMENT, filters={"name": ["in", names]}, fields=LINE_FIELDS,
                                                     limit_page_length=0)} if names else {}
    for row in doc.get("lines") or []:
        placement = found.get(row.placement)
        if not placement:
            continue
        for field in ("employee", "employee_name", "designation", "department", "branch", "performance_band",
                      "potential_band"):
            row.set(field, placement.get(field))
        if not row.get("proposed_box"):
            row.proposed_box = placement.box
        if not cint(row.get("calibrated_box")):
            row.calibrated_box = None
        row.axis = rules.axis_of(row.proposed_box, row.calibrated_box)


def _spread(doc):
    lines = [row.as_dict() for row in doc.get("lines") or []]
    grid = masters.grid()
    names = {cell["box"]: cell["name"] for cell in grid["boxes"].values()}
    spread = rules.distribution(rules.counts_of([row.get("proposed_box") for row in lines]),
                                rules.counts_of([rules.line_box(row) for row in lines]), masters.guide())
    doc.set("distribution", [{"box": row["box"], "box_name": names.get(row["box"]), "guide_share": row["guide"],
                              "proposed": row["proposed"], "proposed_share": row["proposed_share"],
                              "calibrated": row["calibrated"], "calibrated_share": row["calibrated_share"],
                              "variance": row["variance"]} for row in spread])
    doc.people = len(lines)
    doc.moves = len([row for row in lines if rules.moves(row)])
    doc.agreed_moves = len(rules.to_apply(lines))
    tolerance = masters.settings().get("guide_tolerance")
    off = rules.off_guide(spread, float(tolerance or 5))
    doc.off_guide = ", ".join("%d %s (%+.1f)" % (box, names.get(box, ""), variance) for box, variance in off) or None


def session_before_submit(doc):
    lines = [row.as_dict() for row in doc.get("lines") or []]
    errors = rules.submit_errors({"talent_review": doc.talent_review, "checkpoint": doc.checkpoint, "lines": lines,
                                  "participants": [row.as_dict() for row in doc.get("participants") or []]})
    names = [row["placement"] for row in lines if rules.moves(row) and cint(row.get("agreed"))]
    if names:
        moved_on = {row.name: row for row in frappe.get_all(PLACEMENT, filters={"name": ["in", names]},
                                                           fields=["name", "employee_name", "workflow_state",
                                                                   "docstatus"], limit_page_length=0)}
        gone = [row.employee_name or row.name for row in moved_on.values()
                if row.docstatus != 0 or row.workflow_state != CALIBRATING]
        if gone:
            errors.append(_("These are no longer in calibration, so their moves cannot be applied: {0}. Untick "
                            "Agreed on their lines or take them out.").format(", ".join(gone)))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SESSION))


def session_on_submit(doc):
    """The agreed moves applied to the placements in the background."""
    doc.db_set("status", "Applying", update_modified=False)
    log_name = talent_jobs.start("calibration", SESSION, doc.name, "hrms_addon.hrms_addon.calibration.apply_job",
                                 session=doc.name)
    doc.db_set("job_log", log_name, update_modified=False)


def session_on_cancel(doc):
    """Cancelled: the moves already applied stay, each in the log; HR move a
    placement back on the board if it must go back."""
    doc.db_set("status", "Cancelled", update_modified=False)


def apply_job(context, session):
    doc = frappe.get_doc(SESSION, session)
    context.doctype = PLACEMENT
    lines = {row.placement: row for row in doc.lines}
    moves = dict(rules.to_apply([row.as_dict() for row in doc.lines]))

    def work(name):
        row = lines[name]
        apply_move(frappe.get_doc(PLACEMENT, name), moves[name], row.reason, session=doc.name,
                   event=rules.APPLIED, source=rules.SESSION)

    context.each(list(moves), work, label=lambda name: lines[name].employee_name or name)
    for row in doc.lines:
        if rules.moves(row.as_dict()) and not cint(row.agreed):
            log(row.placement, rules.NOT_AGREED, rules.SESSION, row.proposed_box, row.calibrated_box, row.reason,
                session=doc.name, review=doc.talent_review, placement_row=row)
    flag = "mid_year_done" if doc.checkpoint == rules.MID_YEAR else "year_end_done"
    review = frappe.db.get_value(REVIEW, doc.talent_review, ["status"], as_dict=True) or {}
    values = {flag: 1}
    if review.get("status") in ("Draft", "Open"):
        values["status"] = "In Calibration"
    frappe.db.set_value(REVIEW, doc.talent_review, values, update_modified=False)
    doc.db_set({"status": "Applied", "applied_on": now_datetime()}, update_modified=False)
    _tell_session(doc, context)


def _tell_session(doc, context):
    from hrms_addon.hrms_addon import people

    users = list(people.hr_officers(doc.get("branch"), doc.get("department")))
    users += [row.user for row in doc.participants if row.get("user")]
    talent_jobs.tell(users, SESSION, doc.name, _("{0}: {1} agreed moves applied, {2} left.").format(
        doc.title or doc.name, context.done, len(context.left)))


@frappe.whitelist(methods=["POST"])
def get_placements(session):
    """The review's placements in the session's plant and department that are
    in calibration and not in the session yet. Returns how many came in."""
    doc = frappe.get_doc(SESSION, session)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("The session is submitted."), title=_(SESSION))
    filters = {"talent_review": doc.talent_review, "docstatus": 0, "workflow_state": CALIBRATING}
    for field in ("branch", "department"):
        if doc.get(field):
            filters[field] = doc.get(field)
    have = {row.placement for row in doc.lines}
    added = 0
    for row in frappe.get_all(PLACEMENT, filters=filters, fields=LINE_FIELDS, order_by="department asc, employee_name asc",
                              limit_page_length=0):
        if row.name in have:
            continue
        doc.append("lines", {"placement": row.name, "proposed_box": row.box, "agreed": 1})
        added += 1
    doc.save()
    return added


# ── A move ────────────────────────────────────────────────────────────
def apply_move(placement, to_box, reason, session=None, event=rules.MOVED, source=rules.BOARD):
    """A placement put in a box by calibration: the bands it calibrates, the
    reason, the session, and the log entry."""
    was = placement.get("box")
    performance, potential = talent_rules.calibrated_bands(placement.get("performance_band"),
                                                           placement.get("potential_band"), to_box)
    placement.calibrated_performance = performance
    placement.calibrated_potential = potential
    placement.calibration_reason = reason
    if session:
        placement.calibration_session = session
    placement.flags.ignore_permissions = True
    placement.flags.calibrated = True
    placement.save()
    log(placement.name, event, source, was, placement.get("box"), reason, session=session,
        review=placement.get("talent_review"), placement_row=placement)
    return placement


def board_move(placement, to_box, reason):
    """The board's drag (talent_board.move), checked already: into the draft
    session covering the placement, else applied now."""
    session = _session_for(placement)
    if not session:
        apply_move(placement, to_box, reason)
        return {"box": placement.box, "box_name": placement.box_name, "pending": 0}
    doc = frappe.get_doc(SESSION, session)
    row = next((line for line in doc.lines if line.placement == placement.name), None)
    if not row:
        row = doc.append("lines", {"placement": placement.name, "proposed_box": placement.box})
    was = rules.line_box(row.as_dict())
    row.calibrated_box = cint(to_box)
    row.reason = reason
    row.agreed = 1
    doc.flags.ignore_permissions = True
    doc.save()
    log(placement.name, rules.PROPOSED, rules.BOARD, was, to_box, reason, session=session,
        review=placement.get("talent_review"), placement_row=placement)
    cell = talent_rules.box_of(to_box, masters.grid()) or {}
    return {"box": cint(to_box), "box_name": cell.get("name"), "pending": 1, "session": session}


def _session_for(placement):
    """The draft session of the placement's review that covers it, the one
    narrowest in scope first."""
    found = frappe.get_all(SESSION, filters={"talent_review": placement.talent_review, "docstatus": 0},
                           fields=["name", "branch", "department", "session_date"],
                           order_by="session_date desc", limit_page_length=0)
    covering = [row for row in found if rules.in_scope(row, placement.as_dict())]
    covering.sort(key=lambda row: (0 if row.department else 1, 0 if row.branch else 1))
    return covering[0].name if covering else None


def revert(placement):
    """A placement back with its line manager: its calibration comes off,
    and the log says so."""
    if not (placement.get("calibrated_potential") or placement.get("calibrated_performance")):
        return
    log(placement.name, rules.REVERTED, rules.FORM, placement.get("box"), None,
        placement.get("return_remarks") or _("Returned to the line manager"),
        review=placement.get("talent_review"), placement_row=placement)


# ── The log ───────────────────────────────────────────────────────────
def log(placement, event, source, from_box, to_box, reason, session=None, review=None, placement_row=None):
    """One entry, written once."""
    row = placement_row or frappe.db.get_value(PLACEMENT, placement, ["employee", "employee_name", "branch",
                                                                      "department", "talent_review"], as_dict=True) or {}
    entry = frappe.get_doc({
        "doctype": LOG, "talent_review": review or row.get("talent_review"), "calibration_session": session,
        "placement": placement, "employee": row.get("employee"), "employee_name": row.get("employee_name"),
        "branch": row.get("branch"), "department": row.get("department"), "event": event, "source": source,
        "from_box": cint(from_box) or None, "to_box": cint(to_box) or None,
        "axis": rules.axis_of(from_box, to_box), "reason": reason, "moved_by": frappe.session.user,
        "moved_on": now_datetime()})
    entry.flags.ignore_permissions = True
    entry.insert()
    return entry.name


def log_validate(doc):
    if not doc.is_new():
        frappe.throw(_("A calibration entry is kept as it was written. Record a new move instead."), title=_(LOG))
    if doc.get("event") not in rules.EVENTS:
        frappe.throw(_("A calibration entry is one of: {0}.").format(", ".join(rules.EVENTS)), title=_(LOG))
    doc.moved_by = doc.get("moved_by") or frappe.session.user
    doc.moved_on = doc.get("moved_on") or now_datetime()
    doc.axis = rules.axis_of(doc.get("from_box"), doc.get("to_box"))


def log_on_trash(doc):
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("A calibration entry is kept."), frappe.PermissionError)


# ── What the board shows ──────────────────────────────────────────────
def pending(review):
    """{placement: box} the draft sessions of the review have moved."""
    if not review:
        return {}
    rows = frappe.db.sql("""
        select line.placement, line.proposed_box, line.calibrated_box
        from `tabCalibration Line` line
        join `tabCalibration Session` session on session.name = line.parent
        where line.parenttype = 'Calibration Session' and session.talent_review = %(review)s
          and session.docstatus = 0 and line.calibrated_box between 1 and 9""", {"review": review}, as_dict=True)
    return rules.pending(rows)


def movers(review, placements=None, limit=200):
    """The latest move of each placement of the review, newest first, from
    the log."""
    if not review:
        return []
    rows = frappe.db.sql("""
        select name, placement, employee, employee_name, branch, department, event, from_box, to_box, axis,
               moved_by, moved_on, reason, calibration_session
        from `tabTalent Calibration Log`
        where talent_review = %(review)s and event in ('Moved', 'Applied', 'Reverted', 'Proposed')
        order by moved_on asc, name asc""", {"review": review}, as_dict=True)
    proposed = {}
    for row in rows:
        if row.event == rules.PROPOSED:
            proposed[row.placement] = row
    found = rules.latest_moves(rows)
    waiting = pending(review)
    for placement, row in proposed.items():
        if placement in waiting and placement not in {entry.get("placement") for entry in found}:
            found.append(row)
    if placements is not None:
        found = [row for row in found if row.get("placement") in placements]
    return sorted(found, key=lambda row: str(row.get("moved_on") or ""), reverse=True)[:limit]


# ── The clock ─────────────────────────────────────────────────────────
def daily():
    """A review whose mid-year checkpoint has come with no mid-year session
    applied: HR are told on the day and a week on."""
    from hrms_addon.hrms_addon import people

    day = today()
    for row in frappe.get_all(REVIEW, filters={"mid_year_on": ["<=", day], "mid_year_done": 0,
                                               "status": ["not in", ("Finalised", "Cancelled")]},
                              fields=["name", "title", "mid_year_on", "branch"], limit_page_length=0):
        due = str(row.mid_year_on)[:10]
        if day not in (due, str(add_days(getdate(due), 7))):
            continue
        users = list(people.hr_officers(row.branch)) + list(people.people_for("HR Manager", row.branch))
        talent_jobs.tell(users, REVIEW, row.name, _("The mid-year calibration of {0} is due. Hold a Calibration "
                                                    "Session for each plant.").format(row.title or row.name))
    frappe.db.commit()
