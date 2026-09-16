# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Description rules.

No Frappe import, like requisition_approval.py, so
scripts/verify_job_description.py can exercise them without a bench.

Luuka's JDs (e.g. LPL/JD/SM/001, Head Sales & Marketing) set out Key Result
Areas as a Balanced Scorecard: four perspectives, each with a % weighting
and its key outputs, the weightings totalling 100%. The template is the
same for every role, which is why the JD lives on Designation — the Job
Title master that requisitions and openings already point at.
"""

# Order and wording as printed in the JD. Must match the Select options of
# the JD Key Result Area child table.
PERSPECTIVES = (
    "Financial",
    "Customer / Stakeholder",
    "Internal Business Processes",
    "Learning & Growth",
)

TOTAL_WEIGHTING = 100.0
TOLERANCE = 0.01  # 33.33 + 33.33 + 33.34 must pass


def key_result_area_errors(rows):
    """Problems with a Key Result Areas table, as user-facing messages.

    rows: iterable of objects or dicts with `perspective` and `weighting`.
    An empty table is allowed — not every Job Title has a written JD yet.
    """
    rows = list(rows or [])
    if not rows:
        return []

    errors = []
    seen = set()
    total = 0.0
    for index, row in enumerate(rows, start=1):
        perspective = _get(row, "perspective")
        weighting = _get(row, "weighting")

        if perspective not in PERSPECTIVES:
            errors.append("Row %d: choose a Balanced Scorecard perspective." % index)
        elif perspective in seen:
            errors.append("Row %d: %s appears more than once." % (index, perspective))
        seen.add(perspective)

        try:
            value = float(weighting or 0)
        except (TypeError, ValueError):
            errors.append("Row %d: the weighting must be a number." % index)
            continue
        if value < 0 or value > TOTAL_WEIGHTING:
            errors.append("Row %d: the weighting must be between 0 and 100%%." % index)
        total += value

    if abs(total - TOTAL_WEIGHTING) > TOLERANCE:
        errors.append(
            "Key Result Area weightings must total 100%% (currently %s%%)." % _format_number(total)
        )
    return errors


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _format_number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")
