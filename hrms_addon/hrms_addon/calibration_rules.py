# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Calibration: the peer group sitting down over one plant's or one
department's placements in a review (the talent blueprint, section 5.1,
stage 4: "Adjust for consistency across plants; HR records movers"), at
the mid-year checkpoint and at the year end.

No Frappe import (scripts/verify_talent_calibration.py); calibration.py
reads and writes the site.

  Calibration Session   one sitting: who took part, a Calibration Line per
                        placement (the box proposed, the box agreed, which
                        axis moved, why, and whether it was agreed), and the
                        spread over the nine boxes against the distribution
                        guide. Submitted, its agreed moves are applied to the
                        placements in the background
  Talent Calibration    every move, insert only: proposed on the board or in
  Log                   a session, applied when the session is submitted,
                        moved straight on a placement outside any session,
                        or taken off when a placement goes back to its line
                        manager. Nothing in it is ever written over
"""

MID_YEAR, YEAR_END = "Mid-Year", "Year End"
CHECKPOINTS = (MID_YEAR, YEAR_END)
POTENTIAL, PERFORMANCE, BOTH = "Potential", "Performance", "Both"
AXES = (POTENTIAL, PERFORMANCE, BOTH)
# what a log entry records
PROPOSED, APPLIED, MOVED, REVERTED, NOT_AGREED = "Proposed", "Applied", "Moved", "Reverted", "Not Agreed"
EVENTS = (PROPOSED, APPLIED, MOVED, REVERTED, NOT_AGREED)
BOARD, SESSION, FORM, MIGRATED = "Board", "Session", "Form", "Migrated"
SOURCES = (BOARD, SESSION, FORM, MIGRATED)
PARTICIPANT_ROLES = ("Facilitator", "Line Manager", "Head of Department", "HR", "Talent Council")
BOX_NUMBERS = tuple(range(1, 10))


def place(box):
    """(performance column 0-2, potential row 0-2) of a box 1 to 9."""
    box = _int(box)
    if box not in BOX_NUMBERS:
        return None
    return (box - 1) // 3, (box - 1) % 3


def axis_of(from_box, to_box):
    """Which axis a move changes: Potential up or down its column,
    Performance along its row, Both, or None for no move."""
    was, now = place(from_box), place(to_box)
    if not was or not now or was == now:
        return None
    if was[0] == now[0]:
        return POTENTIAL
    if was[1] == now[1]:
        return PERFORMANCE
    return BOTH


# ── A session ─────────────────────────────────────────────────────────
def session_errors(facts):
    """facts: "talent_review", "checkpoint", "lines": [{"placement",
    "proposed_box", "calibrated_box", "reason", "agreed"}],
    "participants": [{"user" or "employee"}]."""
    errors = []
    if not facts.get("talent_review"):
        errors.append("A session belongs to a talent review.")
    if facts.get("checkpoint") not in CHECKPOINTS:
        errors.append("Say whether this is the mid-year or the year-end calibration.")
    seen = set()
    for number, row in enumerate(facts.get("lines") or [], 1):
        name = row.get("placement")
        if not name:
            errors.append("Line %d names no placement." % number)
            continue
        if name in seen:
            errors.append("%s is in the session twice." % (row.get("employee_name") or name))
        seen.add(name)
        errors += line_errors(row)
    return errors


def line_errors(row):
    """A line that moves a box says why; the box is one of the nine."""
    errors = []
    who = row.get("employee_name") or row.get("placement") or "A line"
    calibrated = row.get("calibrated_box")
    if calibrated not in (None, "", 0) and _int(calibrated) not in BOX_NUMBERS:
        errors.append("%s: a box is 1 to 9." % who)
    if moves(row) and not _text(row.get("reason")):
        errors.append("%s moves from box %s to %s. Say why." % (who, row.get("proposed_box"), calibrated))
    return errors


def moves(row):
    """Whether a line moves the placement: a calibrated box set and not the
    one proposed."""
    calibrated = _int(row.get("calibrated_box"))
    return calibrated in BOX_NUMBERS and calibrated != _int(row.get("proposed_box"))


def submit_errors(facts):
    """What a session needs before it is submitted: lines, somebody who
    took part, and every move agreed or left out."""
    errors = session_errors(facts)
    if not facts.get("lines"):
        errors.append("There is nobody in the session. Get the placements first.")
    if not facts.get("participants"):
        errors.append("Say who took part in the session.")
    return errors


def to_apply(lines):
    """The agreed moves: [(placement, box)]. A move not agreed is logged
    and left."""
    return [(row.get("placement"), _int(row.get("calibrated_box"))) for row in lines or []
            if moves(row) and int(_number(row.get("agreed")))]


def line_box(row):
    """Where a line has the person now: the agreed box, else the proposed."""
    return _int(row.get("calibrated_box")) if moves(row) else _int(row.get("proposed_box"))


# ── The spread, against the guide ─────────────────────────────────────
def guide_of(shares):
    """{box: share of 100} as kept on the Nine Box records, normalised so the
    shares add up to a hundred whatever HR typed; None without a guide."""
    kept = {_int(box): max(0.0, _number(value)) for box, value in (shares or {}).items() if _int(box) in BOX_NUMBERS}
    total = sum(kept.values())
    if not total:
        return None
    return {box: round(100.0 * kept.get(box, 0.0) / total, 1) for box in BOX_NUMBERS}


def distribution(proposed, calibrated, guide=None, before=None):
    """The nine boxes: [{"box", "guide", "proposed", "proposed_share",
    "calibrated", "calibrated_share", "variance", "last", "last_share"}].

    proposed, calibrated, before: {box: count}; guide: {box: share}. The
    variance is the calibrated share less the guide's, in points."""
    totals = {name: sum((counts or {}).values()) for name, counts in
              (("proposed", proposed), ("calibrated", calibrated), ("before", before))}
    guide = guide_of(guide) if guide else None
    out = []
    for box in BOX_NUMBERS:
        row = {"box": box, "guide": guide.get(box) if guide else None,
               "proposed": int((proposed or {}).get(box, 0)),
               "calibrated": int((calibrated or {}).get(box, 0)),
               "last": int((before or {}).get(box, 0))}
        row["proposed_share"] = _share(row["proposed"], totals["proposed"])
        row["calibrated_share"] = _share(row["calibrated"], totals["calibrated"])
        row["last_share"] = _share(row["last"], totals["before"]) if before else None
        row["variance"] = round(row["calibrated_share"] - row["guide"], 1) if guide else None
        out.append(row)
    return out


def counts_of(boxes):
    """{box: how many} from a list of boxes."""
    out = {}
    for box in boxes or []:
        box = _int(box)
        if box in BOX_NUMBERS:
            out[box] = out.get(box, 0) + 1
    return out


def off_guide(rows, tolerance=5.0):
    """The boxes the calibrated spread is more than `tolerance` points away
    from the guide: [(box, variance)], the widest first."""
    found = [(row["box"], row["variance"]) for row in rows or []
             if row.get("variance") is not None and abs(row["variance"]) > tolerance]
    return sorted(found, key=lambda item: -abs(item[1]))


# ── Box to box, cycle on cycle ────────────────────────────────────────
def matrix(pairs):
    """A 9 x 9 grid of how many went from each box (rows, 1 to 9) to each box
    (columns), with a row for those new to the grid (box 0 in) and a column
    for those no longer in it (box 0 out). pairs: [(from box or None, to box
    or None)]."""
    grid = {was: {now: 0 for now in (0,) + BOX_NUMBERS} for was in (0,) + BOX_NUMBERS}
    for was, now in pairs or []:
        was = _int(was) if _int(was) in BOX_NUMBERS else 0
        now = _int(now) if _int(now) in BOX_NUMBERS else 0
        if was or now:
            grid[was][now] += 1
    return grid


def matrix_summary(grid):
    """Of those in both cycles: how many stayed, moved up, moved down or
    across, by where they sit on the two axes."""
    out = {"same": 0, "up": 0, "down": 0, "across": 0, "new": 0, "gone": 0}
    for was, row in (grid or {}).items():
        for now, count in row.items():
            if not count:
                continue
            if not was:
                out["new"] += count
            elif not now:
                out["gone"] += count
            elif was == now:
                out["same"] += count
            else:
                before, after = place(was), place(now)
                if after[0] >= before[0] and after[1] >= before[1]:
                    out["up"] += count
                elif after[0] <= before[0] and after[1] <= before[1]:
                    out["down"] += count
                else:
                    out["across"] += count
    return out


# ── The log ───────────────────────────────────────────────────────────
def latest_moves(entries):
    """The latest Moved or Applied entry of each placement, newest first:
    who moved where, as the movers list shows it. A placement reverted
    after its move drops out."""
    out = {}
    for row in sorted(entries or [], key=lambda row: (str(row.get("moved_on") or ""), str(row.get("name") or ""))):
        if row.get("event") in (MOVED, APPLIED):
            out[row.get("placement")] = row
        elif row.get("event") == REVERTED:
            out.pop(row.get("placement"), None)
    return sorted(out.values(), key=lambda row: str(row.get("moved_on") or ""), reverse=True)


def pending(lines):
    """{placement: box} of a draft session's moves: shown on the board until
    the session is submitted."""
    return {row.get("placement"): _int(row.get("calibrated_box")) for row in lines or [] if moves(row)}


def in_scope(session, placement):
    """Whether a placement falls in a session's plant and department."""
    for field in ("branch", "department"):
        if session.get(field) and session.get(field) != placement.get(field):
            return False
    return True


def checkpoint_due(mid_year_on, today, done):
    """Whether the mid-year checkpoint has come and has no session yet."""
    return bool(mid_year_on) and not done and str(mid_year_on)[:10] <= str(today)[:10]


# ── Small helpers ─────────────────────────────────────────────────────
def _share(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value):
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))
