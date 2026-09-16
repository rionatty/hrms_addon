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


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return None


def _format_number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")
