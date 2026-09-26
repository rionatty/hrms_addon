# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Who may do what with interviews, beyond the role permissions.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_interview_access.py exercises it without a bench.
interview_access.py wires it into Frappe's has_permission and
permission_query_conditions hooks.

Frappe HR gives its Interviewer role create, write, submit, cancel and
delete on every Interview and every Interview Feedback, and write on every
Interview Type. A panel member is narrowed here to:

  Interview            the interviews they sit on, to read
  Interview Feedback   their own score sheets; a colleague's only once they
                       have submitted their own for that interview, and then
                       only to read, so nobody scores with the others' marks
                       in front of them
  Interview Type       to read
  Interview Shortlist  the ones for an opening they sit on a panel for, to read
  Interview Report     the ones that list them on the panel, to read

Whoever also holds a role with the whole view is not narrowed: HR, the
read-only oversight roles, and for the shortlist and the report the people
who act on them. A controller check only ever takes rights away; what is
left is still what the roles give.
"""

PANEL_ROLE = "Interviewer"
HR_ROLES = ("HR User", "HR Manager", "System Manager")
OVERSIGHT_ROLES = ("Auditor", "Management Viewer")

# the roles that see every document of the kind, as the role permissions say
WHOLE_VIEW = {
    "Interview": HR_ROLES + OVERSIGHT_ROLES,
    "Interview Feedback": HR_ROLES + OVERSIGHT_ROLES,
    "Interview Type": HR_ROLES,
    "Interview Shortlist": HR_ROLES + OVERSIGHT_ROLES + ("Head of Department",),
    "Interview Report": HR_ROLES + OVERSIGHT_ROLES + ("Executive Director",),
}
DOCTYPES = tuple(WHOLE_VIEW)

# what a panel member may do with a document that is not theirs
LOOK_ONLY = ("read", "select", "print")


def narrowed(doctype, roles):
    """True when these roles make a panel member whose view of `doctype` is narrowed."""
    roles = set(roles or ())
    return PANEL_ROLE in roles and not roles & set(WHOLE_VIEW.get(doctype, ()))


def allowed(doctype, ptype, facts):
    """May a narrowed panel member `ptype` this document?

    facts, as each doctype needs them:
      Interview            on_panel: they are one of its interviewers
      Interview Feedback   own: the sheet is theirs; submitted_own: they have
                           submitted their own sheet for its interview
      Interview Shortlist  sits_for_opening: they sit on a panel for its opening
      Interview Report     listed: its panel lists them
    """
    facts = facts or {}
    if doctype == "Interview Feedback":
        if facts.get("own"):
            return True
        return ptype in LOOK_ONLY and bool(facts.get("submitted_own"))
    if doctype not in WHOLE_VIEW:
        return True
    if ptype not in LOOK_ONLY:
        return False
    if doctype == "Interview":
        return bool(facts.get("on_panel"))
    if doctype == "Interview Shortlist":
        return bool(facts.get("sits_for_opening"))
    if doctype == "Interview Report":
        return bool(facts.get("listed"))
    return True


def sheet_owner_error(interviewer, user):
    """Why `user` may not write this score sheet, or None: a sheet is filed
    and changed by its own interviewer."""
    if not interviewer or user in (interviewer, "Administrator"):
        return None
    return "A score sheet is filled in by its own interviewer: this one is %s's." % interviewer


def revealed_average(panel, sheets):
    """The Interview's average rating while its panel is still scoring.

    panel: the users on the interview. sheets: the submitted score sheets,
    each with its interviewer and 0-1 average_rating. The panel's average
    shows once everyone on it has submitted; until then it stays 0, so the
    last to score do not see the others' marks on the Interview. An
    interview with no panel listed shows whatever is in.
    """
    panel = {user for user in panel or () if user}
    sheets = [sheet for sheet in sheets or () if _get(sheet, "interviewer")]
    if not sheets:
        return 0.0
    if panel and not panel <= {_get(sheet, "interviewer") for sheet in sheets}:
        return 0.0
    ratings = [float(_get(sheet, "average_rating") or 0) for sheet in sheets]
    return round(sum(ratings) / len(ratings), 4)


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)
