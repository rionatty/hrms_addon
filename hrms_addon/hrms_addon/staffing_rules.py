# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A Job Requisition's headcount against the staffing plan: the gap
analysis of flow chart step 1, before "Manpower required?".

No Frappe import, like the other *_rules.py modules, so
scripts/verify_staffing.py exercises it without a bench. job_requisition.py
reads the plan, the people and the positions already being filled, and
hands them here.

  planned   the Staffing Plan's Number of Positions for the job title: the
            people it had when the plan was made and the vacancies planned
            (Frappe HR's own sum, staffing_plan.set_number_of_positions)
  current   the active employees with the job title
  filling   positions already on their way: the open Job Openings for it,
            and the other requisitions for it that have no opening yet
  gap       planned - current - filling: what the plan still has room for

The figures follow Frappe HR's Staffing Plan, which counts a job title
across the company, so they are the ones Frappe HR checks a Job Opening
against (job_opening.validate_current_vacancies).
"""

NO_PLAN = "No staffing plan"
WITHIN = "Within the plan"
ABOVE = "above the plan"

# a requisition that is still going somewhere: Frappe HR's statuses
LIVE_STATUSES = ("Pending", "Open & Approved")


def headcount(planned, current, filling, requested, has_plan):
    """{"gap", "over_by", "verdict"}: the room the plan has left, how many
    the requisition asks beyond it, and the words for the form. With no plan
    there is nothing to measure against: no gap, and it says so."""
    requested = max(_int(requested), 0)
    if not has_plan:
        return {"gap": None, "over_by": 0, "verdict": NO_PLAN}
    gap = _int(planned) - _int(current) - _int(filling)
    over_by = max(requested - max(gap, 0), 0)
    return {"gap": gap, "over_by": over_by,
            "verdict": "%d %s" % (over_by, ABOVE) if over_by else WITHIN}


def being_filled(openings, requisitions, this_requisition=None):
    """How many positions are already on their way.

    openings: the open Job Openings for the job title ("vacancies",
    "job_requisition"); one with no number of positions counts as one.
    requisitions: the other live requisitions for it ("name",
    "no_of_positions"); one that already has an open opening is counted
    there, not twice. This requisition's own are never counted.
    """
    opened = {row.get("job_requisition") for row in openings or () if row.get("job_requisition")}
    total = 0
    for row in openings or ():
        if this_requisition and row.get("job_requisition") == this_requisition:
            continue
        total += max(_int(row.get("vacancies")), 1)
    for row in requisitions or ():
        name = row.get("name")
        if name == this_requisition or name in opened:
            continue
        total += max(_int(row.get("no_of_positions")), 1)
    return total


def plan_for(plans, day):
    """The plan covering the day, from rows ("name", "from_date", "to_date",
    "number_of_positions"), the latest starting first; None when none does."""
    day = str(day or "")[:10]
    covering = [row for row in plans or ()
                if str(row.get("from_date") or "")[:10] <= day <= str(row.get("to_date") or "")[:10]]
    covering.sort(key=lambda row: str(row.get("from_date") or ""), reverse=True)
    return covering[0] if covering else None


def _int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
