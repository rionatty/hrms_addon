# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Who sees which talent records (the talent blueprint, section 8: "Line
Manager: placements and successors for team; Mentor: assigned trainee only;
Employee: own development plan").

No Frappe import (scripts/verify_talent.py). talent_access.py reads the
user's scope and turns this into Frappe's has_permission and
permission_query_conditions.

HR, the Talent Council and those who oversee (the auditor, management)
see every record their roles open. Anyone else sees:

  a line manager (Supervisor, Head of Department)  the records of their
      team: everyone who reports to them, directly or through others, read
      off the Employee tree (lft and rgt), never by loading every reports_to
  a rater                                          the potential assessments
      they made
  a Head of Department                             also the records of the
      departments their User Permissions give them
  a mentor                                         the development plans and
      graduate trainees they mentor; a rotation supervisor, the trainees
      rotating through them
  an employee                                      their own development plan

The box itself stays where it was: at permission level one, for HR and the
council alone. Nobody below them reads a grid position here either.
"""

WHOLE_VIEW = ("System Manager", "HR Manager", "HR User", "Talent Council", "Auditor", "Management Viewer",
              "General Manager", "Executive Director")
MANAGERS = ("Supervisor", "Head of Department")
HEAD = "Head of Department"
MENTOR = "Mentor"

# doctype -> what each record is read by: the employee it is about, the
# mentor, its department, and whether its own employee may read it
DOCTYPES = {
    "Talent Placement": {"employee": "employee", "department": "department", "own": False},
    "Potential Assessment": {"employee": "employee", "department": "department", "own": False, "rater": "rater"},
    "Flight Risk Assessment": {"employee": "employee", "department": "department", "own": False},
    "Talent Program": {"employee": "employee", "mentor": "mentor", "department": "department", "own": True},
    "Succession Position": {"employee": "incumbent", "department": "department", "own": False},
    "Graduate Trainee Program": {"employee": "employee", "mentor": "mentor", "department": "home_department",
                                 "rotations": True, "own": True},
}


def narrowed(roles):
    """Whether the user sees only some records: none of the whole-view roles."""
    return not set(roles or ()) & set(WHOLE_VIEW)


def scope_of(roles, me, team=(), departments=(), tree=None, user=None):
    """What the user may see by: {"me", "user", "team", "tree",
    "departments", "mentor"}. tree: (lft, rgt) of the user's own place in
    the Employee tree; everyone strictly inside it reports to them."""
    roles = set(roles or ())
    manager = bool(roles & set(MANAGERS))
    bounds = tuple(tree) if manager and tree and tree[0] is not None and tree[1] is not None else None
    return {"me": me, "user": user, "team": set(team or ()) if manager else set(), "tree": bounds,
            "departments": set(departments or ()) if HEAD in roles else set(),
            "mentor": MENTOR in roles or bool(me)}


def below(bounds, place):
    """Whether an employee's place (lft, rgt) is inside a manager's."""
    if not bounds or not place or place[0] is None or place[1] is None:
        return False
    return int(place[0]) > int(bounds[0]) and int(place[1]) < int(bounds[1])


def visible(doctype, record, scope):
    """Whether a narrowed user sees this record. record: the doctype's
    fields as DOCTYPES names them, and "rotation_supervisors" for a trainee."""
    spec = DOCTYPES.get(doctype)
    if not spec or not scope:
        return False
    me = scope.get("me")
    employee = record.get(spec["employee"])
    if spec.get("own") and me and employee == me:
        return True
    if employee and employee in scope.get("team", ()):
        return True
    if employee and below(scope.get("tree"), record.get("employee_place")):
        return True
    if spec.get("rater") and scope.get("user") and record.get(spec["rater"]) == scope.get("user"):
        return True
    if record.get(spec["department"]) and record.get(spec["department"]) in scope.get("departments", ()):
        return True
    if me and scope.get("mentor") and spec.get("mentor") and record.get(spec["mentor"]) == me:
        return True
    if me and spec.get("rotations") and me in (record.get("rotation_supervisors") or ()):
        return True
    return False


def conditions(doctype, scope, quote):
    """The same test as a list condition, for lists, reports and link
    searches. quote: how the database writes a value. Nothing visible:
    a condition nothing meets."""
    spec = DOCTYPES.get(doctype)
    if not spec or not scope:
        return "1=0"
    table = "`tab%s`" % doctype
    me = scope.get("me")
    parts = []

    def among(field, values):
        values = sorted(value for value in values if value)
        if values:
            parts.append("%s.`%s` in (%s)" % (table, field, ", ".join(quote(value) for value in values)))

    if spec.get("own") and me:
        parts.append("%s.`%s` = %s" % (table, spec["employee"], quote(me)))
    among(spec["employee"], scope.get("team", ()))
    if scope.get("tree"):
        low, high = (int(value) for value in scope["tree"])
        parts.append("%s.`%s` in (select ha_team.name from `tabEmployee` ha_team where ha_team.lft > %d "
                     "and ha_team.rgt < %d)" % (table, spec["employee"], low, high))
    if spec.get("rater") and scope.get("user"):
        parts.append("%s.`%s` = %s" % (table, spec["rater"], quote(scope["user"])))
    among(spec["department"], scope.get("departments", ()))
    if me and scope.get("mentor") and spec.get("mentor"):
        parts.append("%s.`%s` = %s" % (table, spec["mentor"], quote(me)))
    if me and spec.get("rotations"):
        parts.append("exists (select 1 from `tabTrainee Rotation` ha_rotation where ha_rotation.parent = %s.name "
                     "and ha_rotation.parenttype = '%s' and ha_rotation.supervisor = %s)" % (table, doctype, quote(me)))
    return "(%s)" % " or ".join(parts) if parts else "1=0"


def team_from(me, reports, depth=8):
    """Everyone below `me`, directly or through others. reports:
    {employee: [their direct reports]}."""
    found, frontier = set(), [me]
    for _step in range(depth):
        nxt = [person for boss in frontier for person in reports.get(boss, ()) if person not in found and person != me]
        if not nxt:
            break
        found.update(nxt)
        frontier = nxt
    return found
