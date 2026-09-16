# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Description rules.

No Frappe import, like requisition_approval.py, so
scripts/verify_job_description.py can exercise them without a bench.

Luuka's JDs (e.g. LPL/JD/SM/001, Head Sales & Marketing) set out Key Result
Areas as a Balanced Scorecard. Each row of a JD's table picks a KRA from
HRMS's standard KRA master — the same master Appraisal Templates use, so a
JD's KRAs and weightings can later become the role's appraisal goals
without re-keying. The KRA carries its Balanced Scorecard perspective
(custom_perspective); several KRAs may share a perspective, so the JD's
"Financial 25%" can be split across three Financial KRAs. The weightings of
all rows together total 100%.
"""

# Order and wording as printed in the JD. Must match the Select options of
# KRA.custom_perspective and JD Key Result Area.perspective.
PERSPECTIVES = (
    "Financial",
    "Customer / Stakeholder",
    "Internal Business Processes",
    "Learning & Growth",
)

TOTAL_WEIGHTING = 100.0
TOLERANCE = 0.01  # 15.7 + 22.1 + 51.4 + 10.8 is 99.99999999999999 in floating point


def perspective_totals(rows):
    """{perspective: summed weighting}, in JD order, for every perspective."""
    totals = {perspective: 0.0 for perspective in PERSPECTIVES}
    for row in rows or []:
        perspective = _get(row, "perspective")
        if perspective in totals:
            totals[perspective] += _number(_get(row, "weighting")) or 0.0
    return totals


def key_result_area_errors(rows):
    """Problems with a Key Result Areas table, as user-facing messages.

    rows: iterable of objects or dicts with kra, perspective and weighting.
    `perspective` must already be the KRA's own perspective — the caller
    looks it up rather than trusting what the browser sent.
    An empty table is allowed: not every Job Title has a written JD yet.
    """
    rows = list(rows or [])
    if not rows:
        return []

    errors = []
    seen = set()
    total = 0.0
    for index, row in enumerate(rows, start=1):
        kra = _get(row, "kra")
        perspective = _get(row, "perspective")
        weighting = _get(row, "weighting")

        if not kra:
            errors.append("Row %d: choose a KRA." % index)
        elif kra in seen:
            errors.append("Row %d: KRA %s is listed more than once." % (index, kra))
        else:
            seen.add(kra)
            if perspective not in PERSPECTIVES:
                errors.append(
                    "Row %d: KRA %s has no Balanced Scorecard perspective. Set it on the KRA first." % (index, kra)
                )

        value = _number(weighting)
        if value is None:
            errors.append("Row %d: the weighting must be a number." % index)
            continue
        if value < 0 or value > TOTAL_WEIGHTING:
            errors.append("Row %d: the weighting must be between 0 and 100%%." % index)
        total += value

    if abs(total - TOTAL_WEIGHTING) > TOLERANCE:
        breakdown = ", ".join(
            "%s %s%%" % (perspective, _format_number(amount))
            for perspective, amount in perspective_totals(rows).items()
        )
        errors.append(
            "KRA weightings must total 100%% (currently %s%%: %s)." % (_format_number(total), breakdown)
        )
    return errors


# ── Reporting, stakeholders, authority and planning horizon tables ───

# Designation table field -> child DocType
TABLES = {
    "custom_jd_reporting_lines": "JD Reporting Line",
    "custom_jd_stakeholders": "JD Stakeholder",
    "custom_jd_decision_authorities": "JD Decision Authority",
    "custom_jd_planning_horizons": "JD Planning Horizon",
}

HORIZONS = ("Short-Term", "Medium-Term", "Long-Term")

# Frappe stores Data fields as varchar(140). A longer value would abort the
# insert, so the migration sends it to the comment instead.
DATA_MAX = 140


def jd_table_errors(designation, reports_to, reporting_lines, stakeholders, authorities, horizons):
    """Problems across the four Job Description tables, as user-facing messages."""
    errors = []

    seen = {}
    for index, row in enumerate(reporting_lines or [], start=1):
        position = _get(row, "designation")
        scope = (_get(row, "scope") or "").strip()
        if not position:
            continue
        if designation and position == designation:
            errors.append("Reporting Relationships row %d: a role cannot report to itself." % index)
        elif reports_to and position == reports_to:
            errors.append(
                "Reporting Relationships row %d: %s is this role's Reports To, so it cannot also report to it."
                % (index, position)
            )
        key = (position, scope.lower())
        if key in seen:
            errors.append(
                "Reporting Relationships row %d: %s%s is already listed in row %d."
                % (index, position, " (%s)" % scope if scope else "", seen[key])
            )
        else:
            seen[key] = index

    seen = {}
    for index, row in enumerate(stakeholders or [], start=1):
        name = (_get(row, "stakeholder") or "").strip()
        kind = _get(row, "stakeholder_type")
        if not name:
            continue
        key = (kind, name.lower())
        if key in seen:
            errors.append("Stakeholder Management row %d: %s is already listed in row %d." % (index, name, seen[key]))
        else:
            seen[key] = index

    seen = {}
    for index, row in enumerate(authorities or [], start=1):
        text = " ".join((_get(row, "decisions") or "").split()).lower()
        if not text:
            continue
        key = (_get(row, "authority_level"), text)
        if key in seen:
            errors.append("Decision-Making Authority row %d repeats row %d." % (index, seen[key]))
        else:
            seen[key] = index

    seen = {}
    for index, row in enumerate(horizons or [], start=1):
        horizon = _get(row, "horizon")
        if horizon in seen:
            errors.append(
                "Work Cycle & Planning Horizon row %d: %s is already in row %d. Use one row per horizon."
                % (index, horizon, seen[horizon])
            )
        elif horizon:
            seen[horizon] = index

    return errors


# ── Moving the old text sections into the tables (one-off migration) ──

# The text fields these tables replace: fieldname -> (table kind, label)
OLD_TEXT_FIELDS = {
    "custom_jd_direct_reports": ("reporting", "Direct"),
    "custom_jd_indirect_reports": ("reporting", "Indirect"),
    "custom_jd_internal_stakeholders": ("stakeholder", "Internal"),
    "custom_jd_external_stakeholders": ("stakeholder", "External"),
    "custom_jd_strategic_authority": ("authority", "Strategic"),
    "custom_jd_operational_authority": ("authority", "Operational"),
    "custom_jd_managerial_authority": ("authority", "Managerial"),
    "custom_jd_short_term": ("horizon", "Short-Term"),
    "custom_jd_medium_term": ("horizon", "Medium-Term"),
    "custom_jd_long_term": ("horizon", "Long-Term"),
}

_BULLETS = "•▪◦‣·*-–—"
_DASHES = (" – ", " — ", " - ")


def split_lines(text):
    """One item per non-empty line, bullets and surrounding space removed."""
    lines = []
    for raw in str(text or "").replace("\r", "\n").split("\n"):
        line = raw.strip().lstrip(_BULLETS).strip()
        if line:
            lines.append(line)
    return lines


def designation_lookup(names):
    """Case-insensitive name -> the Job Title's exact name."""
    return {name.strip().lower(): name for name in names if name}


def split_parenthetical(text):
    """'CFO (credit, collections)' -> ('CFO', 'credit, collections').
    Text without a trailing (...) -> (text, None)."""
    text = str(text or "").strip()
    if text.endswith(")") and "(" in text:
        head, _, tail = text.rpartition("(")
        if head.strip():
            return head.strip(), tail[:-1].strip()
    return text, None


def parse_reporting_line(line, lookup):
    """(Job Title, scope) when the line names an existing Job Title, else None.

    Handles the JD's two styles, "Sales Manager – PE/Kawempe" and
    "Senior Sales/CCE (all plants)". A Job Title that does not exist is not
    guessed at: the row would carry a broken link and block the next save.
    """
    text = str(line or "").strip()
    if text.lower() in lookup:
        return lookup[text.lower()], ""
    for dash in _DASHES:
        if dash in text:
            head, tail = text.split(dash, 1)
            if head.strip().lower() in lookup:
                return lookup[head.strip().lower()], tail.strip()
    head, scope = split_parenthetical(text)
    if scope is not None and head.lower() in lookup:
        return lookup[head.lower()], scope
    return None


def text_sections_to_rows(values, lookup):
    """Rows for the four tables from one Designation's old text fields.

    Returns ({table field: [row dict, ...]}, [lines that could not be moved]).
    Nothing is dropped silently: every line either becomes a row or is
    returned for the caller to record.
    """
    tables = {field: [] for field in TABLES}
    unconverted = []

    def fits(*parts):
        return all(len(part or "") <= DATA_MAX for part in parts)

    for field, (kind, label) in OLD_TEXT_FIELDS.items():
        text = values.get(field)
        if not text or not str(text).strip():
            continue

        if kind == "reporting":
            for line in split_lines(text):
                parsed = parse_reporting_line(line, lookup)
                if parsed and fits(parsed[1]):
                    tables["custom_jd_reporting_lines"].append(
                        {"relationship": label, "designation": parsed[0], "scope": parsed[1]}
                    )
                else:
                    unconverted.append("%s report: %s" % (label, line))

        elif kind == "stakeholder":
            for line in split_lines(text):
                name, detail = split_parenthetical(line)
                if fits(name, detail):
                    tables["custom_jd_stakeholders"].append(
                        {"stakeholder_type": label, "stakeholder": name, "interaction": detail or ""}
                    )
                else:
                    unconverted.append("%s stakeholder: %s" % (label, line))

        elif kind == "authority":
            tables["custom_jd_decision_authorities"].append(
                {"authority_level": label, "decisions": str(text).strip()}
            )

        else:
            work_cycle = " ".join(str(text).split())
            if fits(work_cycle):
                tables["custom_jd_planning_horizons"].append({"horizon": label, "work_cycle": work_cycle})
            else:
                unconverted.append("%s: %s" % (label, work_cycle))

    return tables, unconverted


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return None


def _format_number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")
