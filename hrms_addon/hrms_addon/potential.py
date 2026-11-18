# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Potential on the site: the criteria, each rater's assessment, the
evidence read from L&D and the appraisal, and the placement's potential as
the raters' weighted mean. The rules are in potential_rules.py
(scripts/verify_talent_potential.py).

  criterion_*      a Potential Criterion: its levels 1 to 5 each once
  assessment_*     a Potential Assessment: the rater is whoever records it,
                   once a placement; each rating told what its score means
                   and whether it is the evidence's or the rater's own;
                   submitted, the placement reads its potential again
  new_assessment   the user's draft assessment of a placement, every active
                   criterion listed and the evidence read
  read_evidence    what L&D's Competency Assessments and the appraisals say
                   for each criterion, and the score it suggests
  fill_placement   the placement's potential from the submitted
                   assessments: the weighted mean, the raters, how far apart
                   they are and each criterion's spread
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, today

from hrms_addon.hrms_addon import potential_rules as rules, talent_masters as masters

CRITERION, ASSESSMENT, PLACEMENT = "Potential Criterion", "Potential Assessment", "Talent Placement"
COMPETENCY = "Competency Assessment"
_CRITERIA = "ha_potential_criteria"


# ── The criteria ──────────────────────────────────────────────────────
def criterion_validate(doc):
    errors = rules.criterion_errors({"weight": doc.get("weight"), "evidence_from": doc.get("evidence_from"),
                                     "levels": [row.as_dict() for row in doc.get("levels") or []]})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(CRITERION))
    doc.set("levels", sorted(doc.get("levels") or [], key=lambda row: cint(row.level)))
    for number, row in enumerate(doc.levels, 1):
        row.idx = number


def criterion_on_update(doc):
    forget()
    masters.forget()


def forget():
    setattr(frappe.local, _CRITERIA, None)


def criteria():
    """The active criteria, read once a request: [{"name", "weight",
    "evidence_from", "levels": {level: descriptor}}]."""
    cached = getattr(frappe.local, _CRITERIA, None)
    if cached is None:
        rows = frappe.get_all(CRITERION, filters={"active": 1}, fields=["name", "weight", "evidence_from"],
                              order_by="name asc", limit_page_length=0)
        levels = {}
        for row in frappe.get_all("Potential Criterion Level", filters={"parenttype": CRITERION},
                                  fields=["parent", "level", "descriptor"], limit_page_length=0):
            levels.setdefault(row.parent, {})[cint(row.level)] = row.descriptor
        cached = [dict(row, weight=flt(row.weight), levels=levels.get(row.name, {})) for row in rows]
        setattr(frappe.local, _CRITERIA, cached)
    return cached


def weights():
    return rules.weights_of([dict(row, active=1) for row in criteria()])


# ── One rater's assessment ────────────────────────────────────────────
def assessment_validate(doc):
    if not doc.get("rater"):
        doc.rater = frappe.session.user
    doc.rater_employee = frappe.db.get_value("Employee", {"user_id": doc.rater}, "name")
    placement = frappe.db.get_value(PLACEMENT, doc.placement, ["employee", "docstatus", "talent_review"],
                                    as_dict=True) if doc.get("placement") else None
    if not placement:
        frappe.throw(_("Say whose placement this assessment is for."), title=_(ASSESSMENT))
    if placement.docstatus != 0 and doc.docstatus == 0 and doc.is_new():
        frappe.throw(_("The placement is finalised, and its potential with it."), title=_(ASSESSMENT))
    taken = frappe.get_all(ASSESSMENT, filters={"placement": doc.placement, "rater": doc.rater, "docstatus": ["<", 2],
                                                "name": ["!=", doc.name or ""]}, pluck="name", limit=1)
    if taken:
        frappe.throw(_("{0} has already assessed this placement: {1}. Amend that one.").format(
            doc.get("rater_name") or doc.rater, taken[0]), title=_(ASSESSMENT))
    known = {row["name"]: row for row in criteria()}
    for row in doc.get("ratings") or []:
        spec = known.get(row.criterion) or {}
        row.weight = spec.get("weight") if spec else row.get("weight")
        level = int(round(flt(row.get("score")))) if flt(row.get("score")) else 0
        row.descriptor = (spec.get("levels") or {}).get(level) if level else None
        row.source = rules.source_after_edit(row.get("score"), row.get("suggested_score"), row.get("source"))
    if doc.docstatus == 1:
        errors = rules.assessment_errors({"placement": doc.placement, "rater": doc.rater,
                                          "rater_role": doc.get("rater_role"),
                                          "ratings": [row.as_dict() for row in doc.get("ratings") or []]}, weights())
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(ASSESSMENT))
    else:
        bad = [row.criterion for row in doc.get("ratings") or []
               if row.get("score") not in (None, "") and flt(row.score) and not rules.LOW <= flt(row.score) <= rules.HIGH]
        if bad:
            frappe.throw(_("{0} is rated 1 to 5.").format(", ".join(bad)), title=_(ASSESSMENT))
    mean = rules.weighted_mean([row.as_dict() for row in doc.get("ratings") or []], weights())
    doc.weighted_score = mean
    doc.potential_score = round(mean * rules.TO_HUNDRED, 2) if mean is not None else None
    doc.status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}[cint(doc.docstatus)]


def assessment_on_submit(doc):
    doc.db_set("status", "Submitted", update_modified=False)
    refresh_placement(doc.placement)


def assessment_on_cancel(doc):
    doc.db_set("status", "Cancelled", update_modified=False)
    refresh_placement(doc.placement)


@frappe.whitelist(methods=["POST"])
def new_assessment(placement, rater_role=None):
    """The user's draft assessment of a placement: theirs if they have one,
    else a new one with every active criterion and the evidence read."""
    frappe.get_doc(PLACEMENT, placement).check_permission("read")
    mine = frappe.get_all(ASSESSMENT, filters={"placement": placement, "rater": frappe.session.user,
                                               "docstatus": 0}, pluck="name", limit=1)
    if mine:
        return mine[0]
    roles = set(frappe.get_roles())
    role = rater_role or ("HR" if roles & {"HR Manager", "HR User"} else "Head of Department"
                          if "Head of Department" in roles else "Line Manager")
    doc = frappe.get_doc({"doctype": ASSESSMENT, "placement": placement, "rater": frappe.session.user,
                          "rater_role": role, "assessed_on": today(), "ratings": evidence_rows(placement)})
    doc.insert()
    return doc.name


@frappe.whitelist()
def read_evidence(placement):
    """Each criterion with its descriptors and the evidence's suggestion,
    for the form's Read the Evidence."""
    frappe.get_doc(PLACEMENT, placement).check_permission("read")
    return evidence_rows(placement)


def evidence_rows(placement):
    """[{"criterion", "weight", "suggested_score", "score", "source",
    "evidence"}], one an active criterion, the suggestion as its score."""
    doc = frappe.db.get_value(PLACEMENT, placement, ["employee"], as_dict=True) or {}
    employee = doc.get("employee")
    levels, history = _competency(employee)
    appraisal = frappe.get_all("Talent Competency Level", filters={"parent": placement, "parenttype": PLACEMENT},
                               fields=["competency", "level"], order_by="idx asc", limit_page_length=0)
    rows = []
    for spec in criteria():
        score, source, evidence = rules.suggestion(spec.get("evidence_from"), levels=levels, appraisal=appraisal,
                                                   history=history, today=today())
        rows.append({"criterion": spec["name"], "weight": spec["weight"], "suggested_score": score, "score": score,
                     "source": source, "evidence": evidence})
    return rows


def _competency(employee):
    """The employee's counting competency levels in L&D (the newest of each
    skill), and every assessment for the growth over a year."""
    if not employee or not frappe.db.exists("DocType", COMPETENCY):
        return [], []
    rows = frappe.get_all(COMPETENCY, filters={"employee": employee}, fields=["skill", "level", "assessed_on", "status"],
                          order_by="assessed_on asc", limit_page_length=0)
    history = [{"skill": row.skill, "level": _level(row.level), "assessed_on": row.assessed_on} for row in rows]
    counting = {}
    for row in rows:
        if row.status != "Superseded":
            counting[row.skill] = {"skill": row.skill, "level": _level(row.level)}
    return [row for row in counting.values() if row["level"]], history


def _level(value):
    """A competency level's number from its name ("4 Competent Independently")."""
    try:
        return int(str(value or "").split(" ")[0])
    except ValueError:
        return 0


# ── The placement's potential ─────────────────────────────────────────
def submitted(placements):
    """{placement: [{"rater", "ratings": [...]}]} of the submitted assessments."""
    names = [name for name in placements or [] if name]
    if not names:
        return {}
    found = frappe.get_all(ASSESSMENT, filters={"placement": ["in", names], "docstatus": 1},
                           fields=["name", "placement", "rater"], limit_page_length=0)
    ratings = {}
    if found:
        for row in frappe.get_all("Potential Rating", filters={"parent": ["in", [row.name for row in found]],
                                                               "parenttype": ASSESSMENT},
                                  fields=["parent", "criterion", "score"], limit_page_length=0):
            ratings.setdefault(row.parent, []).append({"criterion": row.criterion, "score": row.score})
    out = {}
    for row in found:
        out.setdefault(row.placement, []).append({"rater": row.rater, "ratings": ratings.get(row.name, [])})
    return out


def fill_placement(doc, assessments=None):
    """The placement's potential, from its submitted assessments."""
    if assessments is None:
        assessments = submitted([doc.name]).get(doc.name, []) if doc.get("name") and not doc.is_new() else []
    found = rules.placement_potential(assessments, weights(), masters.settings().get("rater_spread"))
    from hrms_addon.hrms_addon import talent_rules

    doc.raters = found["raters"]
    doc.potential_mean = found["mean"]
    doc.rater_spread = found["spread"]
    doc.raters_disagree = found["disagree"]
    doc.potential_score = found["score"]
    doc.potential_band = talent_rules.potential_band(found["score"], masters.grid())
    doc.set("potential_summary", [{"criterion": row["criterion"], "weight": row["weight"], "average": row["average"],
                                   "lowest": row["lowest"], "highest": row["highest"], "raters": row["raters"]}
                                  for row in found["criteria"]])


def refresh_placement(name):
    """A placement not yet finalised, read again after an assessment came or
    went: written straight in, so its own checks and signatures are not run
    again."""
    if not name:
        return
    doc = frappe.get_doc(PLACEMENT, name)
    if doc.docstatus != 0:
        return
    from hrms_addon.hrms_addon import talent

    fill_placement(doc)
    talent._fill_box(doc)
    doc.db_update()
    doc.update_child_table("potential_summary")
