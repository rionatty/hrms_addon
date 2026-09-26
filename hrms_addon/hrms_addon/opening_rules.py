# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Opening: what it takes from its Job Requisition and its JD, and the
route of its careers page. No Frappe here, so scripts/verify_openings.py
runs without a bench; job_openings.py applies it.
"""

import re

# the opening's field -> the requisition's field it is taken from, when the
# opening leaves it blank (the description, "Responsibilities" on the
# requisition, among them)
FROM_REQUISITION = {
    "job_title": "designation",
    "designation": "designation",
    "department": "department",
    "vacancies": "no_of_positions",
    "description": "description",
    "custom_reason_type": "custom_reason_type",
    "custom_reporting_line": "custom_reporting_line",
    "custom_subordinates": "custom_subordinates",
}
# the modes of recruitment, taken together: the requisition's when the
# opening ticks none
MODES = ("custom_external_advert", "custom_internal_advert", "custom_head_hunt", "custom_reference_to_database")
# a screening question's columns, the same on the JD and on the opening
QUESTION_FIELDS = ("question", "answer_type", "wanted", "minimum", "maximum", "priority")


def blanks_from(opening, requisition, has_content=None):
    """{field: value}: what the opening leaves blank and its requisition
    says. has_content says whether a text says anything; an editor's empty
    paragraph does not."""
    has_content = has_content or _has_text
    out = {}
    for field, source in FROM_REQUISITION.items():
        if _blank(opening.get(field), has_content) and not _blank(requisition.get(source), has_content):
            out[field] = requisition.get(source)
    if not any(_ticked(opening.get(field)) for field in MODES):
        out.update({field: 1 for field in MODES if _ticked(requisition.get(field))})
    return out


def route_for(company, job_title):
    """HRMS's route for an opening's page: jobs/<company>/<job-title>."""
    return "jobs/%s/%s" % (_scrub(company), _scrub(job_title).replace("_", "-"))


def unique_route(route, taken):
    """The route itself when no other opening has it, else the first free
    one of route-2, route-3 and so on: two openings for the same job keep
    pages of their own."""
    taken = set(taken or ())
    if route not in taken:
        return route
    number = 2
    while "%s-%d" % (route, number) in taken:
        number += 1
    return "%s-%d" % (route, number)


def question_rows(rows):
    """The JD's screening questions as rows for an opening."""
    return [{field: row.get(field) for field in QUESTION_FIELDS} for row in rows or () if row.get("question")]


def _scrub(text):
    """frappe.scrub: spaces and hyphens become underscores, all lower case."""
    return str(text or "").replace(" ", "_").replace("-", "_").lower()


def _has_text(value):
    return bool(re.sub(r"<[^>]+>", "", str(value or "")).strip())


def _blank(value, has_content):
    if value is None or isinstance(value, (bool, int, float)):
        return not value
    return not has_content(value)


def _ticked(value):
    try:
        return bool(int(value or 0))
    except (TypeError, ValueError):
        return False
