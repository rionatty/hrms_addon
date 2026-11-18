# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The talent grid as HR keep it (the talent blueprint, section 3: "business
rules must be configurable"). The rules are in talent_rules.py
(scripts/verify_talent.py).

  grid                the bands, boxes, potential weights and trainee pass
                      mark as kept (talent_rules.grid_from), read once a
                      request; what is not kept is the built-in grid
  Performance Band,   the three bands of each axis: their names stay, where
  Potential Band      each starts is HR's, each above the one below
  Nine Box            each cell's name, colour, action, decision and whether
                      it is top talent; its bands follow its number
  Readiness Level     the four readiness levels: their names and order stay,
                      their horizon and the boxes they draw from are HR's
  Talent Settings     the flight risks alerted on, the probability of losing
                      a holder, when raters disagree, how far off the guide
                      is flagged and the trainee milestones raised ahead
  Potential Criterion what potential is rated on (potential_rules.SEED);
  Criticality Factor  what losing a critical role costs; why people leave:
  Retention Driver    lists made once and then HR's
  setup_on_migrate    the masters made once from the built-in grid
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from hrms_addon.hrms_addon import talent_rules as rules

PERFORMANCE, POTENTIAL, BOX, READINESS, SETTINGS = (
    "Performance Band", "Potential Band", "Nine Box", "Readiness Level", "Talent Settings")
BAND_NAMES = {PERFORMANCE: rules.PERFORMANCE_NAMES, POTENTIAL: rules.POTENTIAL_NAMES}
BUILT_IN = {PERFORMANCE: rules.PERFORMANCE_BANDS, POTENTIAL: rules.POTENTIAL_BANDS}
# the blueprint's readiness scale: (readiness, horizon, the boxes it draws from)
# Ready now draws from the Stars and the Future Leaders (boxes 9 and 6), as
# the blueprint's readiness scale says; 1-2 years from the Future Leaders and
# the High Performers
READINESS_SEED = ((rules.READY_NOW, "Within 3 months", (9, 6)),
                  (rules.READY_SOON, "Needs development first", (6, 8)),
                  (rules.EMERGING, "Longer term", (3, 5)),
                  (rules.GAP, "No internal successor", ()))
SETTINGS_SEED = {"watch_high": 1, "watch_medium": 1, "trainee_pass_mark": rules.PASS_MARK, "auto_milestones": 1,
                 "milestone_lead_days": 7, "rater_spread": 1, "probability_high": 60, "probability_medium": 35,
                 "probability_low": 10, "retirement_months": 24, "guide_tolerance": 5}
CRITERION, FACTOR, DRIVER = "Potential Criterion", "Criticality Factor", "Retention Driver"
DRIVER_SEED = ("Pay", "Career growth", "Relationship with the manager", "Workload", "Recognition",
               "Personal or family", "Outside offer", "Relocation", "Working conditions")
_CACHE = "ha_talent_grid"


# ── The grid ──────────────────────────────────────────────────────────
def grid():
    """The grid as kept, read once a request."""
    cached = getattr(frappe.local, _CACHE, None)
    if cached is None:
        cached = rules.grid_from(_kept(PERFORMANCE, ["name", "score_from"]), _kept(POTENTIAL, ["name", "score_from"]),
                                 _kept(BOX, ["box", "box_name", "colour", "default_action", "suggested_decision",
                                             "top_talent", "guide_share"]),
                                 settings(), _kept(CRITERION, ["name", "weight", "active"]))
        setattr(frappe.local, _CACHE, cached)
    return cached


def forget():
    """A master changed: the next read takes it."""
    setattr(frappe.local, _CACHE, None)


def _kept(doctype, fields):
    try:
        return frappe.get_all(doctype, fields=fields, limit_page_length=0)
    except Exception:
        # before the doctype is synced (a patch reading the grid): the built-in grid
        return []


def settings():
    """Talent Settings, the seeded values for whatever is empty."""
    try:
        stored = frappe.get_cached_doc(SETTINGS)
    except Exception:
        return dict(SETTINGS_SEED)
    return {key: (stored.get(key) if stored.get(key) not in (None, "") else default)
            for key, default in SETTINGS_SEED.items()}


def watched_risks():
    """The flight risks HR and the council are alerted on."""
    s = settings()
    return [level for level, key in (("High", "watch_high"), ("Medium", "watch_medium")) if cint(s.get(key))]


def readiness_levels():
    """[(readiness, rank, [the boxes it draws from])]."""
    numbers = {row.name: cint(row.box) for row in _kept(BOX, ["name", "box"])}
    levels = {row.name: (row.name, cint(row.rank), []) for row in _kept(READINESS, ["name", "rank"])}
    if levels:
        for row in frappe.get_all("Readiness Level Box", filters={"parenttype": READINESS},
                                  fields=["parent", "nine_box"], limit_page_length=0):
            if row.parent in levels and row.nine_box in numbers:
                levels[row.parent][2].append(numbers[row.nine_box])
    return list(levels.values())


# ── The masters ───────────────────────────────────────────────────────
def band_validate(doc):
    names = BAND_NAMES[doc.doctype]
    if doc.band_name not in names:
        frappe.throw(_("The bands are {0}. Their names stay; where each starts is HR's.").format(", ".join(names)),
                     title=_(doc.doctype))
    floors = _floors(doc.doctype)
    floors[doc.band_name] = flt(doc.score_from)
    if set(floors) == set(names):
        errors = rules.band_errors([(name, floors[name]) for name in names])
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(doc.doctype))
    doc.score_to = dict((name, end) for name, _start, end in rules.band_ranges(list(floors.items())))[doc.band_name]


def band_on_update(doc):
    """Each band runs up to where the next starts."""
    for name, _start, end in rules.band_ranges(list(_floors(doc.doctype).items())):
        frappe.db.set_value(doc.doctype, name, "score_to", end, update_modified=False)
    forget()


def _floors(doctype):
    return {row.name: flt(row.score_from) for row in frappe.get_all(doctype, fields=["name", "score_from"])}


def box_validate(doc):
    box = cint(doc.box)
    if box not in rules.BOX_AXES:
        frappe.throw(_("A box is numbered 1 to 9."), title=_(BOX))
    doc.performance_band, doc.potential_band = rules.BOX_AXES[box]
    doc.box_name = (doc.box_name or "").strip()


def readiness_validate(doc):
    if doc.readiness not in rules.READINESS:
        frappe.throw(_("The readiness levels are {0}. Their names and order stay; the horizon and the boxes "
                       "they draw from are HR's.").format(", ".join(rules.READINESS)), title=_(READINESS))
    doc.rank = rules.READINESS_RANK[doc.readiness]


def settings_validate(doc):
    if not 0 < flt(doc.get("trainee_pass_mark")) <= 100:
        frappe.throw(_("The milestone pass mark is above 0 and at most 100."), title=_(SETTINGS))
    for key in ("probability_high", "probability_medium", "probability_low"):
        if not 0 <= flt(doc.get(key)) <= 100:
            frappe.throw(_("A probability of loss is 0 to 100."), title=_(SETTINGS))
    if flt(doc.get("rater_spread")) < 0:
        frappe.throw(_("The spread between raters is 0 or more."), title=_(SETTINGS))


def guide():
    """{box: share} of the distribution guide, as kept on the Nine Box records."""
    return {cell["box"]: cell.get("guide") for cell in grid()["boxes"].values()}


def master_on_update(doc):
    forget()


def _seed_lists():
    """The potential criteria, the criticality factors and the retention
    drivers the module starts with, made once and then HR's; the guide's
    shares where a box has none."""
    from hrms_addon.hrms_addon import potential_rules, succession_rules

    for spec in potential_rules.SEED:
        if not frappe.db.exists(CRITERION, spec["criterion"]):
            frappe.get_doc({"doctype": CRITERION, "criterion_name": spec["criterion"], "weight": spec["weight"],
                            "active": 1, "evidence_from": spec["evidence_from"],
                            "levels": [{"level": number, "descriptor": text}
                                       for number, text in enumerate(spec["levels"], 1)]}).insert(
                ignore_permissions=True)
    for name, weight, description in succession_rules.FACTOR_SEED:
        if not frappe.db.exists(FACTOR, name):
            frappe.get_doc({"doctype": FACTOR, "factor_name": name, "weight": weight,
                            "description": description}).insert(ignore_permissions=True)
    for name in DRIVER_SEED:
        if not frappe.db.exists(DRIVER, name):
            frappe.get_doc({"doctype": DRIVER, "driver_name": name}).insert(ignore_permissions=True)
    for row in frappe.get_all(BOX, fields=["name", "box", "guide_share"]):
        if not flt(row.guide_share) and cint(row.box) in rules.GUIDE:
            frappe.db.set_value(BOX, row.name, "guide_share", rules.GUIDE[cint(row.box)], update_modified=False)


def suggested_readiness(box):
    """The readiness a successor from this box is suggested."""
    return rules.readiness_for(box, readiness_levels()) if box not in (None, "") else None


# ── Made once ─────────────────────────────────────────────────────────
def setup_on_migrate():
    """The masters from the built-in grid, made once and then HR's."""
    try:
        for doctype in (PERFORMANCE, POTENTIAL):
            for floor, name in sorted(BUILT_IN[doctype]):
                if not frappe.db.exists(doctype, name):
                    frappe.get_doc({"doctype": doctype, "band_name": name, "score_from": floor}).insert(
                        ignore_permissions=True)
            for name, _start, end in rules.band_ranges(list(_floors(doctype).items())):
                frappe.db.set_value(doctype, name, "score_to", end, update_modified=False)
        for spec in sorted(rules.BOXES.values(), key=lambda spec: spec["box"]):
            if not frappe.db.exists(BOX, {"box": spec["box"]}):
                frappe.get_doc({"doctype": BOX, "box": spec["box"], "box_name": spec["name"],
                                "colour": spec["colour"], "default_action": spec["action"],
                                "suggested_decision": spec["decision"], "guide_share": rules.GUIDE[spec["box"]],
                                "top_talent": 1 if spec["box"] in rules.TOP_TALENT else 0}).insert(ignore_permissions=True)
        for readiness, horizon, boxes in READINESS_SEED:
            if not frappe.db.exists(READINESS, readiness):
                frappe.get_doc({"doctype": READINESS, "readiness": readiness, "horizon": horizon,
                                "boxes": [{"nine_box": frappe.db.get_value(BOX, {"box": box}, "name")}
                                          for box in boxes]}).insert(ignore_permissions=True)
        _seed_lists()
        doc = frappe.get_single(SETTINGS)
        missing = {key: value for key, value in SETTINGS_SEED.items() if doc.get(key) in (None, "")}
        if doc.get("trainee_pass_mark") in (None, "", 0):
            missing = dict(SETTINGS_SEED)
        if not doc.get("rotation_criteria"):
            from hrms_addon.hrms_addon import graduate_rules

            missing["rotation_criteria"] = [{"criterion": name} for name in graduate_rules.CRITERIA]
        if missing:
            doc.update(missing)
            doc.flags.ignore_permissions = True
            doc.save()
        forget()
    except Exception:
        frappe.log_error(title="HRMS Addon: setting up the talent grid")
