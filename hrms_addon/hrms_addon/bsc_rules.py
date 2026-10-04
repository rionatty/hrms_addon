# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Balanced Scorecard appraisal (LPL PMS, FY 2026).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_performance.py exercises them without a bench.

TWO APPRAISAL FORMS, SIDE BY SIDE

Luuka runs both (confirmed 23 Sep 2026): the Supervisory Skills Evaluation
Form (LPL/HR/18, appraisal_rules.py) for supervisors, and this balanced
scorecard for graded roles. They share the round — one Appraisal Plan, one
Appraisal Cycle, one Appraisal per employee — and differ in what the form
asks, how it scores, where the bands fall and who signs it. The Appraisal's
Form Type says which one an employee is on.

THE FORM

  Section A   the KPIs under the four balanced scorecard perspectives,
              worth 80 of the 100. Every KPI carries its own weight; a
              perspective weighs what its KPIs weigh, and the four total 80
              (Luuka, 4 Oct 2026: the workbook weighed each perspective
              once). Each quarter the appraiser records the percentage
              achieved against each KPI, and the KPI scores its weight times
              that percentage. The perspectives, below the KPIs, sum them up
              (perspective_summary).
  Assignments other tasks given during the period, recorded, not scored
  Section B   five competencies with their behavioural indicators, scored
              out of ten, their weights totalling 20
  Overall     Section A plus Section B, out of 100
  Part D      signed by the Appraiser, the Employee, the Head of
              Department, the HR Manager and the Executive Director
  Part E      the development plan: what to continue, stop and start, and
              the actions agreed with their cost

THE YEAR

Four quarters, one appraisal each. A quarter's appraisal carries the earlier
quarters as they were recorded, and only its own quarter is filled in. The
year to date is the average of the quarters appraised so far (year_to_date):
Luuka, 4 Oct 2026, in place of the workbook's annual score out of ten.

THE QUARTERLY SCORE

Luuka's workbook computes a quarter as weight x percent / 100 / 10, which
scores a perfect quarter 8 out of 80. Luuka confirmed the quarterly score is
a real score, not an indicator, so the stray tenth is dropped here: a KPI
scores weight x percent / 100, and a perfect quarter scores the full 80.
"""
# ── Section A ─────────────────────────────────────────────────────────
PERSPECTIVES = (
    "Financial",
    "Customer / Stakeholder",
    "Internal Business Processes",
    "Learning & Growth",
)
# what the workbook calls them, where it differs from the job descriptions
PERSPECTIVE_ALIASES = {
    "internal process": "Internal Business Processes",
    "internal processes": "Internal Business Processes",
    "internal business process": "Internal Business Processes",
    "customer": "Customer / Stakeholder",
    "customer/stakeholder": "Customer / Stakeholder",
    "learning and growth": "Learning & Growth",
}
CONTINUATION = "↳"  # the workbook marks a KPI under the perspective above with this
# every timing Luuka's own workbooks use (84 role sheets, 23 Sep 2026)
TIMINGS = ("Per shift", "Daily", "Weekly", "Monthly", "Quarterly", "Semi-Annual", "Annual", "Ongoing")

OBJECTIVES_WEIGHT, COMPETENCIES_WEIGHT = 80, 20
TOP_SCORE = 10  # every competency is scored out of ten
# a message names this many KPIs, then says how many more
NAMED_KPIS = 5

# ── Section B ─────────────────────────────────────────────────────────
# The competencies are the role's, not one fixed list: Luuka's workbooks
# use fifteen across the company (Audit Excellence & Rigour, IMS Technical
# Mastery, Planning & Organising and so on). These five are the set most
# roles carry, seeded as the BSC Competency list; the importer adds any
# others it meets.
COMPETENCIES = (
    ("Job Knowledge & Technical Excellence",
     "Deep expertise in function; upholds high output quality; ensures team delivers to standard; "
     "accountable for results.", 4),
    ("Compliance & Governance",
     "Champions LPL policy, ISO/IMS standards, SOPs, and all statutory obligations; zero tolerance for "
     "non-compliance.", 3),
    ("Commitment & Results Delivery",
     "Maintains high personal drive; achieves targets despite challenges; models accountability and ownership.", 4),
    ("Strategic Planning & Decision-Making",
     "Sets clear priorities; makes data-driven decisions; aligns team objectives to the 3-Year Strategic Plan.", 4),
    ("Inclusive Leadership & Team Development",
     "Coaches and develops direct reports; builds succession depth; creates a psychologically safe and "
     "motivated team.", 5),
)
BSC_MASTERS = {"BSC Competency": ("competency_name", tuple(name for name, _indicators, _weight in COMPETENCIES))}

# ── The scale ─────────────────────────────────────────────────────────
# (lowest total %, band), highest first: the form's own scale, which is not
# the Supervisory form's
BANDS = ((90, "Excellent"), (80, "Very Good"), (70, "Good"), (60, "Fair"), (0, "Poor"))
BAND_MEANING = {
    "Excellent": "Consistently exceeds all objectives & expectations",
    "Very Good": "Frequently meets & exceeds targets",
    "Good": "Fully meets most objectives",
    "Fair": "Meets some but not all objectives",
    "Poor": "Consistently fails to meet standards",
}

# ── The year ──────────────────────────────────────────────────────────
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
# what the workbook called its last column, and what an appraisal of it is
# now: the fourth quarter (the patch of October 2026)
ANNUAL = "Annual"

FORM_SUPERVISORY = "Supervisory Skills (LPL/HR/18)"
FORM_BSC = "Balanced Scorecard"
FORM_TYPES = (FORM_SUPERVISORY, FORM_BSC)
# the supervisory form's own limit on objectives (appraisal_rules.MAX_OBJECTIVES)
MAX_OBJECTIVES = 8


def quarter_score(weight, percent):
    """A KPI's weighted score for a quarter: its weight times the percentage
    achieved. None when nothing is recorded.

    Luuka's workbook divides by a further ten here; they confirmed the
    quarterly score is real, so it is not divided again.
    """
    exact = _weighted(weight, percent)
    return None if exact is None else round(exact, 2)


def _weighted(weight, percent):
    """A KPI's weighted score before rounding: totals add these and round
    once, so three KPIs of 8.33, 8.33 and 8.34 half achieved make 12.5, not
    the 12.51 their rounded scores would."""
    if percent in (None, "") or weight in (None, ""):
        return None
    return float(weight) * float(percent) / 100.0


def percent_field(quarter):
    """The column of a KPI row that holds a quarter's percentage achieved."""
    return "%s_percent" % quarter.lower()


def score_field(quarter):
    """The column that holds a quarter's weighted score, on a KPI row and on
    a perspective's."""
    return "%s_score" % quarter.lower()


def comments_field(quarter):
    """The column of a KPI row that holds a quarter's comments."""
    return "%s_comments" % quarter.lower()


def quarter_of(month):
    """The quarter a month (1 to 12) falls in."""
    return QUARTERS[(int(month) - 1) // 3]


def recorded(rows, field):
    """Whether a column of figures has been filled in at all. Frappe keeps a
    number left blank as 0, so a column that is blank or 0 on every row was
    never filled in; once any row has a figure, a 0 beside it is a real 0."""
    return any(_number(row.get(field)) for row in rows or [])


def section_a(kpis, quarter):
    """Section A's total for a quarter: the KPIs' weighted scores. None while
    the quarter's column has not been filled in (recorded).

    kpis: [{"weight", "q1_percent", ... "q4_percent"}]
    """
    if quarter not in QUARTERS or not recorded(kpis, percent_field(quarter)):
        return None
    scored = [_weighted(row.get("weight"), row.get(percent_field(quarter))) for row in kpis or []]
    return round(sum(value for value in scored if value is not None), 2)


def perspective_summary(kpis):
    """The perspectives, below the KPIs, summing them up: each one's weight
    (what its KPIs weigh), its weighted score for each quarter (None for a
    quarter whose column has not been filled in) and its year to date, in
    the order the perspectives first appear.

    kpis: [{"perspective", "weight", "q1_percent", ... "q4_percent"}]
    Returns [{"perspective", "weight", "q1_score", ... "q4_score", "year_to_date"}].
    """
    order, groups = [], {}
    for row in kpis or []:
        perspective = row.get("perspective")
        if not perspective:
            continue
        if perspective not in groups:
            order.append(perspective)
            groups[perspective] = []
        groups[perspective].append(row)
    filled = {quarter: recorded(kpis, percent_field(quarter)) for quarter in QUARTERS}
    out = []
    for perspective in order:
        rows = groups[perspective]
        summary = {"perspective": perspective, "weight": round(sum(_number(row.get("weight")) or 0 for row in rows), 2)}
        for quarter in QUARTERS:
            scored = [_weighted(row.get("weight"), row.get(percent_field(quarter))) for row in rows]
            summary[score_field(quarter)] = round(sum(value for value in scored if value is not None), 2) \
                if filled[quarter] else None
        summary["year_to_date"] = year_to_date([summary[score_field(quarter)] for quarter in QUARTERS])
        out.append(summary)
    return out


def year_to_date(totals):
    """The year so far: the average of the quarters appraised, each counted
    once whatever it scored. None until one is."""
    values = [float(value) for value in totals or [] if value not in (None, "")]
    return round(sum(values) / len(values), 2) if values else None


def competency_score(weight, score):
    """One competency's weighted score: its weight times the score out of
    ten."""
    if score in (None, "") or weight in (None, ""):
        return None
    return round(float(weight) * float(score) / TOP_SCORE, 2)


def section_b(rows):
    """Section B's total: the weighted competency scores. None when none is
    scored.

    rows: [{"weight", "score"}]
    """
    if not recorded(rows, "score"):
        return None
    scored = [competency_score(row.get("weight"), row.get("score")) for row in rows or []]
    return round(sum(value for value in scored if value is not None), 2)


def overall(section_a_total, section_b_total):
    """The overall score out of 100. None until something is scored; a
    section left blank counts as nothing rather than dragging the other
    down, which is what the workbook's empty cells do."""
    parts = [value for value in (section_a_total, section_b_total) if value is not None]
    return round(sum(parts), 2) if parts else None


def band(total):
    """The form's own rating of a total (None: not scored yet)."""
    if total is None:
        return None
    return next(name for floor, name in BANDS if total >= floor)


def normalise_perspective(text):
    """A perspective as the masters spell it, whatever the workbook wrote."""
    clean = " ".join(str(text or "").split()).strip()
    if not clean or clean == CONTINUATION:
        return None
    for perspective in PERSPECTIVES:
        if clean.lower() == perspective.lower():
            return perspective
    return PERSPECTIVE_ALIASES.get(clean.lower(), clean)


def arrange_kpis(rows):
    """Section A of a template laid out as the form lays it out: each
    perspective's KPIs together, in the order the perspectives first
    appear, every KPI keeping its own weight.

    rows: [{"perspective", "kpi", "timing", "weight"}]
    Returns (rows, perspectives): the rows in order, and [{"perspective",
    "weight"}], one per perspective, weighing what its KPIs weigh.
    """
    order, groups = [], {}
    for row in rows or []:
        perspective = row.get("perspective")
        if perspective not in groups:
            order.append(perspective)
            groups[perspective] = []
        groups[perspective].append(dict(row))
    arranged = [row for perspective in order for row in groups[perspective]]
    perspectives = [{"perspective": perspective,
                     "weight": round(sum(_number(row.get("weight")) or 0 for row in groups[perspective]), 2)}
                    for perspective in order if perspective]
    return arranged, perspectives


def spread_weights(rows):
    """Luuka's workbooks weigh a perspective once, on one of its KPIs. Where
    that is so, the perspective's weight is shared between all its KPIs,
    evenly to the hundredth, the last taking what the rounding leaves, so
    the perspective still weighs what was written. A perspective whose KPIs
    are weighed one by one, or that has a single KPI, is left as it is.

    rows: [{"perspective", "weight", ...}]; returns copies, in the same order.
    """
    rows = [dict(row) for row in rows or []]
    groups = {}
    for row in rows:
        groups.setdefault(row.get("perspective"), []).append(row)
    for members in groups.values():
        weighed = [row for row in members if _number(row.get("weight"))]
        if len(members) < 2 or len(weighed) != 1:
            continue
        # in hundredths, whole numbers: 0.29 x 100 is not 28.999...
        hundredths = int(round(_number(weighed[0]["weight"]) * 100))
        each = hundredths // len(members)
        for row in members:
            row["weight"] = each / 100.0
        members[-1]["weight"] = (hundredths - each * (len(members) - 1)) / 100.0
    return rows


def supervisory_template_errors(facts):
    """Problems with a template for the Supervisory Skills form (LPL/HR/18)
    as it is made ready to use.

    facts: "factors" ([{"factor"}]), "objectives" ([{"objective"}]).
    """
    errors = []
    factors = [row.get("factor") for row in facts.get("factors") or [] if row.get("factor")]
    if not factors:
        errors.append("List the ratable factors the form carries (Section A).")
    twice = sorted({name for name in factors if factors.count(name) > 1})
    if twice:
        errors.append("These factors are listed twice: %s." % ", ".join(twice))
    objectives = [" ".join(str(row.get("objective") or "").split()) for row in facts.get("objectives") or []]
    objectives = [text for text in objectives if text]
    if len(objectives) > MAX_OBJECTIVES:
        errors.append("The form carries at most %d objectives; this template has %d." % (MAX_OBJECTIVES, len(objectives)))
    twice = sorted({text for text in objectives if objectives.count(text) > 1})
    if twice:
        errors.append("These objectives are listed twice: %s." % ", ".join(twice))
    return errors


def template_errors(facts):
    """Problems with a BSC template as it is made ready to use.

    facts: "designation", "kpis" ([{"perspective", "kpi", "weight"}]),
    "competencies" ([{"competency", "weight"}]). The perspectives weigh what
    their KPIs weigh, so they are not checked apart.
    """
    errors = []
    if not facts.get("designation"):
        errors.append("Name the role the template is for.")
    kpis = facts.get("kpis") or []
    if not kpis:
        errors.append("List the KPIs the role is measured on, each with its weight; they must total %d."
                      % OBJECTIVES_WEIGHT)
    else:
        homeless = [_kpi_name(row) for row in kpis if not row.get("perspective")]
        if homeless:
            errors.append("Put every KPI under one of the perspectives: %s." % _some(homeless))
        unweighed = [_kpi_name(row) for row in kpis if not _number(row.get("weight"))]
        if unweighed:
            errors.append("Give every KPI its weight: %s." % _some(unweighed))
        negative = [_kpi_name(row) for row in kpis if (_number(row.get("weight")) or 0) < 0]
        if negative:
            errors.append("A KPI's weight cannot be negative: %s." % _some(negative))
        total = round(sum(_number(row.get("weight")) or 0 for row in kpis), 2)
        if total != OBJECTIVES_WEIGHT:
            errors.append("The KPIs' weights must total %d, not %g." % (OBJECTIVES_WEIGHT, total))
    competencies = facts.get("competencies") or []
    if not competencies:
        errors.append("List the competencies; their weights must total %d." % COMPETENCIES_WEIGHT)
    else:
        total = sum(float(row.get("weight") or 0) for row in competencies)
        if round(total, 2) != COMPETENCIES_WEIGHT:
            errors.append("The competencies' weights must total %d, not %g." % (COMPETENCIES_WEIGHT, total))
    return errors


def appraisal_errors(facts):
    """Problems with a balanced scorecard appraisal at the step it is at.

    facts: "step" ("self" or "appraiser"), "quarter", "kpis",
    "competencies". The employee's self-appraisal is read from each KPI's
    self_percent, the appraiser's from the quarter's own column, and the
    competencies' from self_score and score.
    """
    errors = []
    step = facts.get("step")
    if step not in ("self", "appraiser"):
        return errors
    quarter = facts.get("quarter")
    kpis = facts.get("kpis") or []
    if not kpis:
        errors.append("The balanced scorecard has no KPIs: pick the role's template first.")
        return errors
    if quarter not in QUARTERS:
        errors.append("Say which quarter the appraisal is for.")
        return errors
    field = "self_percent" if step == "self" else percent_field(quarter)
    whose = "your own " if step == "self" else ""
    # a column never filled in reads 0 throughout once saved (recorded)
    filled = recorded(kpis, field)
    unscored = [_kpi_name(row) for row in kpis if not filled or row.get(field) in (None, "")]
    if unscored:
        errors.append("Record %s%s percentage achieved for every KPI: %s." % (whose, quarter, _some(unscored)))
    out_of_range = [_kpi_name(row) for row in kpis if row.get(field) not in (None, "") and not _within(row[field], 100)]
    if out_of_range:
        errors.append("A percentage achieved is from 0 to 100: %s." % _some(out_of_range))
    competencies = facts.get("competencies") or []
    field = "self_score" if step == "self" else "score"
    filled = recorded(competencies, field)
    unscored = [str(row.get("competency")) for row in competencies if not filled or row.get(field) in (None, "")]
    if unscored:
        errors.append("Score %severy competency out of ten: %s." % ("yourself on " if step == "self" else "",
                                                                    ", ".join(unscored)))
    out_of_range = [str(row.get("competency")) for row in competencies
                    if row.get(field) not in (None, "") and not _within(row[field], TOP_SCORE)]
    if out_of_range:
        errors.append("A competency is scored out of ten: %s." % ", ".join(out_of_range))
    return errors


def self_scores(kpis, competencies, quarter):
    """The employee's own Section A, Section B and overall, worked out the
    way the appraiser's are: {"section_a", "section_b", "overall"}."""
    own_a = [dict(row, **{percent_field(quarter): row.get("self_percent")}) for row in kpis or []] \
        if quarter in QUARTERS else []
    own_b = [{"weight": row.get("weight"), "score": row.get("self_score")} for row in competencies or []]
    section_a_total, section_b_total = section_a(own_a, quarter), section_b(own_b)
    return {"section_a": section_a_total, "section_b": section_b_total,
            "overall": overall(section_a_total, section_b_total)}


def _within(value, top):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return 0 <= number <= top


def _kpi_name(row):
    """A KPI as a message names it: its first line, under its perspective."""
    text = " ".join(str(row.get("kpi") or "").split())
    text = text if len(text) <= 60 else text[:57].rstrip() + "..."
    return "%s (%s)" % (text or "a KPI with no words", row.get("perspective") or "no perspective")


def _some(names):
    """The first few of a list, and how many more."""
    shown = ", ".join(names[:NAMED_KPIS])
    return shown if len(names) <= NAMED_KPIS else "%s and %d more" % (shown, len(names) - NAMED_KPIS)


# ── Reading Luuka's own workbooks ─────────────────────────────────────
# the words the sheet uses to mark where each part starts and ends
SECTION_A_MARK = "SECTION A"
SECTION_B_MARK = "SECTION B"
WEIGHT_CHECK = "WEIGHT CHECK"
COMPETENCY_CHECK = "COMPETENCY WEIGHT CHECK"
ROLE_MARK, DEPARTMENT_MARK, GRADE_MARK, PERIOD_MARK = "Role / Position", "Department", "Grade", "Review Period"


def parse_sheet(rows):
    """One role's sheet of an LPL PMS workbook, read into a template:

      {"role", "department", "grade", "review_period", "form_reference",
       "revision",
       "perspectives": [{"perspective", "weight"}],
       "kpis": [{"perspective", "kpi", "timing", "weight"}],
       "competencies": [{"competency", "indicators", "weight"}]}

    rows: the sheet as lists of cell values, the way openpyxl gives them.
    Blank cells and the workbook's own totals are skipped; a KPI marked with
    the continuation arrow belongs to the perspective above it. Each KPI
    keeps the weight written beside it: Luuka's workbooks write the
    perspective's on its first KPI only, which the importer shares out
    (spread_weights). The footer names the form (PROC/002) and its revision
    (Rev 01).
    """
    found = {"role": None, "department": None, "grade": None, "review_period": None,
             "form_reference": None, "revision": None,
             "perspectives": [], "kpis": [], "competencies": []}
    section = None
    perspective = None
    for row in rows or []:
        cells = [(" ".join(str(cell).split()) if cell is not None else "") for cell in row]
        first = cells[0] if cells else ""
        for index, cell in enumerate(cells):
            for mark, key in ((ROLE_MARK, "role"), (DEPARTMENT_MARK, "department"),
                              (GRADE_MARK, "grade"), (PERIOD_MARK, "review_period")):
                if found[key] is None and cell.rstrip(":").strip() == mark:
                    found[key] = _next_value(cells, index)
        if found["form_reference"] is None and first.count("|") >= 3:
            found["form_reference"], found["revision"] = footer_parts(first)
        if first.startswith(WEIGHT_CHECK) or first.startswith(COMPETENCY_CHECK):
            section = None
            continue
        if first.startswith(SECTION_A_MARK):
            section, perspective = "A", None
            continue
        if first.startswith(SECTION_B_MARK):
            section = "B"
            continue
        if section == "A":
            name, kpi, timing, weight = _at(cells, 1), _at(cells, 2), _at(cells, 3), _at(cells, 4)
            if not kpi or kpi.lower().startswith("kpi"):
                continue
            first_kpi = bool(name and name != CONTINUATION)
            if first_kpi:
                perspective = normalise_perspective(name)
                if weight:
                    found["perspectives"].append({"perspective": perspective, "weight": _number(weight)})
            if perspective:
                found["kpis"].append({"perspective": perspective, "kpi": kpi,
                                      "timing": timing if timing in TIMINGS else (timing or None),
                                      "weight": _number(weight) if weight else None})
        elif section == "B":
            competency, indicators, weight = _at(cells, 0), _at(cells, 3), _at(cells, 9)
            if not competency or competency.lower() == "competency":
                continue
            found["competencies"].append({"competency": competency, "indicators": indicators or None,
                                          "weight": _number(weight)})
    return found


def footer_parts(text):
    """(form reference, revision) from the workbook's footer, "Luuka Plastics
    Limited | PMS BSC Appraisal Form FY 2026 | Procurement | PROC/002 |
    CONFIDENTIAL | Rev 01"; (None, None) when it is not that footer."""
    parts = [" ".join(part.split()) for part in str(text or "").split("|")]
    marks = [index for index, part in enumerate(parts) if part.upper() == "CONFIDENTIAL"]
    if not marks:
        return None, None
    index = marks[0]
    reference = parts[index - 1] if index >= 1 and parts[index - 1] else None
    revision = parts[index + 1] if index + 1 < len(parts) and parts[index + 1] else None
    return reference, revision


def _at(cells, index):
    return cells[index] if index < len(cells) else ""


def _next_value(cells, index):
    """The first filled cell after `index`: the workbook merges its labels
    and values across columns."""
    for cell in cells[index + 1:]:
        if cell:
            return cell
    return None


def _number(value):
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None
