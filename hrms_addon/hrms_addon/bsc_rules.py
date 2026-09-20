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

  Section A   the KPIs, grouped under the four balanced scorecard
              perspectives, worth 80 of the 100. The weight is set once per
              PERSPECTIVE, not per KPI, and the four must total 80. Each
              quarter records the percentage achieved against target; at
              year end a score out of ten is given instead.
  Assignments other tasks given during the period, recorded, not scored
  Section B   five competencies with their behavioural indicators, scored
              out of ten, their weights totalling 20
  Overall     Section A plus Section B, out of 100
  Part D      signed by the Appraiser, the Employee, the Head of
              Department, the HR Manager and the Executive Director
  Part E      the development plan: what to continue, stop and start, and
              the actions agreed with their cost

THE QUARTERLY SCORE

Luuka's workbook computes a quarter as weight x percent / 100 / 10, which
scores a perfect quarter 8 out of 80. The annual column has no such divisor.
Luuka confirmed the quarterly score is a real score, not an indicator, so
the stray tenth is dropped here: a quarter is weight x percent / 100, and a
perfect one scores the full 80, exactly as the year does.
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
TOP_SCORE = 10  # the annual column and every competency are scored out of ten

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
# the workbook records three quarters and then the year itself
QUARTERS = ("Q1", "Q2", "Q3")
ANNUAL = "Annual"
PERIODS = QUARTERS + (ANNUAL,)
# what each period reads off the form: a percentage achieved, or a score
PERCENT_PERIODS, SCORE_PERIODS = QUARTERS, (ANNUAL,)

FORM_SUPERVISORY = "Supervisory Skills (LPL/HR/18)"
FORM_BSC = "Balanced Scorecard"
FORM_TYPES = (FORM_SUPERVISORY, FORM_BSC)


def quarter_score(weight, percent):
    """A perspective's weighted score for a quarter: its weight times the
    percentage achieved. None when nothing is recorded.

    Luuka's workbook divides by a further ten here; they confirmed the
    quarterly score is real, so it is not divided again.
    """
    if percent in (None, "") or weight in (None, ""):
        return None
    return round(float(weight) * float(percent) / 100.0, 2)


def annual_score(weight, score):
    """A perspective's weighted score for the year: its weight times the
    score out of ten."""
    if score in (None, "") or weight in (None, ""):
        return None
    return round(float(weight) * float(score) / TOP_SCORE, 2)


def field_for(period):
    """Which column of a perspective row a period reads."""
    return "annual_score" if period == ANNUAL else "%s_percent" % period.lower()


def section_a(rows, period):
    """Section A's total for a period: the weighted scores of the
    perspectives that have one. None when none of them does.

    rows: [{"weight", "q1_percent", "q2_percent", "q3_percent", "annual_score"}]
    """
    scored = []
    for row in rows or []:
        weight = row.get("weight")
        if period in PERCENT_PERIODS:
            value = quarter_score(weight, row.get(field_for(period)))
        else:
            value = annual_score(weight, row.get("annual_score"))
        if value is not None:
            scored.append(value)
    return round(sum(scored), 2) if scored else None


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
    scored = [competency_score(row.get("weight"), row.get("score")) for row in rows or []]
    scored = [value for value in scored if value is not None]
    return round(sum(scored), 2) if scored else None


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


def template_errors(facts):
    """Problems with a BSC template as it is made ready to use.

    facts: "designation", "perspectives" ([{"perspective", "weight"}]),
    "kpis" ([{"perspective", "kpi"}]), "competencies" ([{"competency", "weight"}]).
    """
    errors = []
    if not facts.get("designation"):
        errors.append("Name the role the template is for.")
    perspectives = facts.get("perspectives") or []
    if not perspectives:
        errors.append("Give each balanced scorecard perspective its weight; they must total %d."
                      % OBJECTIVES_WEIGHT)
    else:
        total = sum(float(row.get("weight") or 0) for row in perspectives)
        if round(total, 2) != OBJECTIVES_WEIGHT:
            errors.append("The perspectives' weights must total %d, not %g." % (OBJECTIVES_WEIGHT, total))
        seen = set()
        for row in perspectives:
            name = row.get("perspective")
            if name in seen:
                errors.append("%s is weighted twice." % name)
                break
            seen.add(name)
    kpis = facts.get("kpis") or []
    if not kpis:
        errors.append("List the KPIs the role is measured on.")
    weighted = {row.get("perspective") for row in perspectives}
    stray = sorted({str(row.get("perspective")) for row in kpis if row.get("perspective") not in weighted})
    if stray:
        errors.append("These KPIs sit under a perspective that carries no weight: %s." % ", ".join(stray))
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

    facts: "step" ("appraiser"), "period", "perspectives", "competencies".
    """
    errors = []
    if facts.get("step") != "appraiser":
        return errors
    period = facts.get("period") or ANNUAL
    perspectives = facts.get("perspectives") or []
    if not perspectives:
        errors.append("The balanced scorecard has no perspectives: pick the role's template first.")
        return errors
    field = field_for(period)
    unscored = [str(row.get("perspective")) for row in perspectives if row.get(field) in (None, "")]
    if unscored:
        errors.append("Record the %s for every perspective: %s."
                      % ("annual score out of ten" if period == ANNUAL else "%s percentage achieved" % period,
                         ", ".join(unscored)))
    out_of_range = [str(row.get("perspective")) for row in perspectives
                    if row.get(field) not in (None, "") and not _within(row[field], period)]
    if out_of_range:
        errors.append("%s is out of range for %s: %s."
                      % ("The score" if period == ANNUAL else "The percentage", period, ", ".join(out_of_range)))
    competencies = facts.get("competencies") or []
    unscored = [str(row.get("competency")) for row in competencies if row.get("score") in (None, "")]
    if unscored:
        errors.append("Score every competency out of ten: %s." % ", ".join(unscored))
    return errors


def _within(value, period):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return 0 <= number <= (TOP_SCORE if period == ANNUAL else 100)


# ── Reading Luuka's own workbooks ─────────────────────────────────────
# the words the sheet uses to mark where each part starts and ends
SECTION_A_MARK = "SECTION A"
SECTION_B_MARK = "SECTION B"
WEIGHT_CHECK = "WEIGHT CHECK"
COMPETENCY_CHECK = "COMPETENCY WEIGHT CHECK"
ROLE_MARK, DEPARTMENT_MARK, GRADE_MARK, PERIOD_MARK = "Role / Position", "Department", "Grade", "Review Period"


def parse_sheet(rows):
    """One role's sheet of an LPL PMS workbook, read into a template:

      {"role", "department", "grade", "review_period",
       "perspectives": [{"perspective", "weight"}],
       "kpis": [{"perspective", "kpi", "timing"}],
       "competencies": [{"competency", "indicators", "weight"}]}

    rows: the sheet as lists of cell values, the way openpyxl gives them.
    Blank cells and the workbook's own totals are skipped; a KPI marked with
    the continuation arrow belongs to the perspective above it.
    """
    found = {"role": None, "department": None, "grade": None, "review_period": None,
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
            if name and name != CONTINUATION:
                perspective = normalise_perspective(name)
                if weight:
                    found["perspectives"].append({"perspective": perspective, "weight": _number(weight)})
            if perspective:
                found["kpis"].append({"perspective": perspective, "kpi": kpi,
                                      "timing": timing if timing in TIMINGS else (timing or None)})
        elif section == "B":
            competency, indicators, weight = _at(cells, 0), _at(cells, 3), _at(cells, 9)
            if not competency or competency.lower() == "competency":
                continue
            found["competencies"].append({"competency": competency, "indicators": indicators or None,
                                          "weight": _number(weight)})
    return found


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
