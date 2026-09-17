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

The JD's other sections are child tables too. Every dropdown in them, and
on the KRA form, picks from a small master HR can add to (MASTERS), seeded
once with the values Luuka's documents use.
"""

# The perspectives a JD starts with, in the order the JD prints them. Only a
# seed for the "KRA Perspective" master: HR can add, rename and reorder
# perspectives, so nothing below treats this list as the complete set.
PERSPECTIVES = (
    "Financial",
    "Customer / Stakeholder",
    "Internal Business Processes",
    "Learning & Growth",
)

# The KRA form's pick lists. Master DocType -> (name field, values seeded
# once). The values are EXACTLY the dropdowns of the "KPI Library" sheet in
# the Part 2 master-data template given to Luuka, so that sheet imports
# cleanly; after seeding, each list is HR's to maintain.
KRA_MASTERS = {
    "KRA Perspective": ("perspective_name", PERSPECTIVES),
    "KRA Level": ("level_name", (
        "Machine Operator", "Shift Supervisor", "Production Officer", "Production Manager",
        "Department Staff", "Supervisory", "Management", "All Staff",
    )),
    "KRA Unit": ("unit_name", ("%", "Metres", "Pieces", "Hours", "Count", "UGX")),
    "KRA Data Source": ("source_name", ("Luuka Prod", "Biometric", "Manual", "ERPNext", "Excel")),
    "KRA Review Frequency": ("frequency_name", ("Monthly", "Quarterly", "Semi-Annual", "Annual", "On Demand", "Once")),
}

# KRA custom field -> the master it links to
KRA_FIELD_MASTERS = {
    "custom_perspective": "KRA Perspective",
    "custom_applies_to": "KRA Level",
    "custom_unit": "KRA Unit",
    "custom_source": "KRA Data Source",
    "custom_frequency": "KRA Review Frequency",
}

HORIZONS = ("Short-Term", "Medium-Term", "Long-Term")

# The standards of LPL's Integrated Management System, in the order the JD
# lists them. IMS Leadership is not a standard, but the JD gives it a line of
# its own, so it is a value like the others.
ISO_STANDARDS = (
    "ISO 9001 (Quality Management)",
    "ISO 22000 (Food Safety)",
    "ISO 45001 (Occupational Health & Safety)",
    "ISO 14001 (Environmental Management)",
    "IMS Leadership",
)
SPECIFICATION_TYPES = ("Academic Qualification", "Professional Training & Certification", "Work Experience")
COMPETENCY_CATEGORIES = ("Technical", "Behavioural")

# The Job Description tables' pick lists, same idea as KRA_MASTERS. The seeds
# are what LPL/JD/SM/001 uses and every value the old dropdowns and text
# sections could hold, so moving an existing JD over never needs a value its
# list lacks.
JD_MASTERS = {
    "JD Relationship Type": ("relationship_type", ("Direct", "Indirect")),
    "JD Stakeholder Type": ("stakeholder_type", ("Internal", "External")),
    "JD Authority Level": ("authority_level", ("Strategic", "Operational", "Managerial")),
    "JD Horizon": ("horizon", HORIZONS),
    "JD ISO Standard": ("standard", ISO_STANDARDS),
    "JD Specification Type": ("specification_type", SPECIFICATION_TYPES),
    "JD Requirement Priority": ("priority", ("Essential", "Preferred", "Desirable")),
    "JD Competency Category": ("category", COMPETENCY_CATEGORIES),
}

# (JD child DocType, field) -> the master it links to
JD_FIELD_MASTERS = {
    ("JD Reporting Line", "relationship"): "JD Relationship Type",
    ("JD Stakeholder", "stakeholder_type"): "JD Stakeholder Type",
    ("JD Decision Authority", "authority_level"): "JD Authority Level",
    ("JD Planning Horizon", "horizon"): "JD Horizon",
    ("JD ISO Responsibility", "standard"): "JD ISO Standard",
    ("JD Job Specification", "specification_type"): "JD Specification Type",
    ("JD Job Specification", "priority"): "JD Requirement Priority",
    ("JD Competency", "category"): "JD Competency Category",
}

# Every pick list, and every (DocType, field) that picks from one
MASTERS = {**KRA_MASTERS, **JD_MASTERS}
FIELD_MASTERS = {
    **{("KRA", field): master for field, master in KRA_FIELD_MASTERS.items()},
    **JD_FIELD_MASTERS,
}

TOTAL_WEIGHTING = 100.0
TOLERANCE = 0.01  # 15.7 + 22.1 + 51.4 + 10.8 is 99.99999999999999 in floating point


def seed_plan(existing, in_use=None, masters=None):
    """Records to create so each master holds its seed values and every
    value already stored in a field that picks from it.

    existing: {master doctype: [names already in the master]}
    in_use:   {master doctype: [values stored in its fields]}; values in use
              are kept valid because those fields used to be Select
              options, and a document holding a value its new master lacks
              could not be saved again.
    masters:  the pick lists to plan, from MASTERS (the default: all).
    Returns {master doctype: [record dicts ready to insert]}.

    Names are compared ignoring case: the database collation treats
    "monthly" and "Monthly" as the same name, so creating both would fail.
    """
    plan = {}
    for doctype, (name_field, seeds) in (MASTERS if masters is None else masters).items():
        taken = {str(name).strip().lower() for name in existing.get(doctype, []) if name}
        records = []
        wanted = list(seeds) + [value for value in (in_use or {}).get(doctype, []) if value]
        for position, value in enumerate(wanted):
            value = str(value).strip()
            if not value or value.lower() in taken:
                continue
            taken.add(value.lower())
            record = {"doctype": doctype, name_field: value}
            if doctype == "KRA Perspective":
                record["sort_order"] = (seeds.index(value) + 1) * 10 if value in seeds else 100 + position
            records.append(record)
        plan[doctype] = records
    return plan


def next_display_order(orders):
    """Display Order for a perspective added without one, e.g. from the KRA
    form's quick entry: the next ten after the highest in use, so it lists
    after the existing perspectives instead of before them (an unset Int is
    0), and HR can still slot one in between later."""
    highest = max([0] + [int(order) for order in orders if order])
    return (highest // 10 + 1) * 10


def perspective_totals(rows, perspectives=None):
    """{perspective: summed weighting}.

    Every perspective in `perspectives` (the master, in display order)
    appears, 0 when unused; any other perspective a row carries follows in
    the order first seen. Defaults to the seed list when none is given.
    """
    totals = {perspective: 0.0 for perspective in (PERSPECTIVES if perspectives is None else perspectives)}
    for row in rows or []:
        perspective = _get(row, "perspective")
        if perspective:
            totals[perspective] = totals.get(perspective, 0.0) + (_number(_get(row, "weighting")) or 0.0)
    return totals


def key_result_area_errors(rows, perspectives=None):
    """Problems with a Key Result Areas table, as user-facing messages.

    rows: iterable of objects or dicts with kra, perspective and weighting.
    `perspective` must already be the KRA's own perspective — the caller
    looks it up rather than trusting what the browser sent.
    perspectives: the KRA Perspective master in display order, used only to
    order the breakdown in the message.
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
            if not perspective:
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
            for perspective, amount in perspective_totals(rows, perspectives).items()
        )
        errors.append(
            "KRA weightings must total 100%% (currently %s%%: %s)." % (_format_number(total), breakdown)
        )
    return errors


# ── The other Job Description tables ─────────────────────────────────

# Designation table field -> child DocType
TABLES = {
    "custom_jd_reporting_lines": "JD Reporting Line",
    "custom_jd_stakeholders": "JD Stakeholder",
    "custom_jd_decision_authorities": "JD Decision Authority",
    "custom_jd_planning_horizons": "JD Planning Horizon",
    "custom_jd_iso_responsibilities": "JD ISO Responsibility",
    "custom_jd_specifications": "JD Job Specification",
    "custom_jd_competencies": "JD Competency",
}

# Frappe stores Data fields as varchar(140), document names included. A
# longer value would abort the insert, so the migration sends it to the
# comment instead.
DATA_MAX = 140


def jd_table_errors(
    designation,
    reports_to,
    reporting_lines,
    stakeholders,
    authorities,
    horizons,
    iso_responsibilities=None,
    specifications=None,
    competencies=None,
):
    """Problems across the Job Description tables, as user-facing messages."""
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

    seen = {}
    for index, row in enumerate(iso_responsibilities or [], start=1):
        standard = _get(row, "standard")
        if not standard:
            continue
        if standard.lower() in seen:
            errors.append(
                "ISO Responsibilities row %d: %s is already in row %d. Put all its accountabilities in one row."
                % (index, standard, seen[standard.lower()])
            )
        else:
            seen[standard.lower()] = index

    seen = {}
    for index, row in enumerate(specifications or [], start=1):
        text = " ".join((_get(row, "requirement") or "").split()).lower()
        if not text:
            continue
        key = (_get(row, "specification_type"), text)
        if key in seen:
            errors.append("Ideal Job Specifications row %d repeats row %d." % (index, seen[key]))
        else:
            seen[key] = index

    seen = {}
    for index, row in enumerate(competencies or [], start=1):
        competency = _get(row, "competency")
        if not competency:
            continue
        if competency.lower() in seen:
            errors.append(
                "Competency Framework row %d: %s is already listed in row %d."
                % (index, competency, seen[competency.lower()])
            )
        else:
            seen[competency.lower()] = index

    return errors


# ── Uploading a table ─────────────────────────────────────────────────

# Every table on the Job Description tab. Each has Download and Upload
# buttons under it (allow_bulk_edit on its Designation field).
KRA_TABLE = "custom_jd_key_result_areas"
JD_TABLE_FIELDS = (KRA_TABLE, *TABLES)

# The column types uploaded_value repairs as text
TEXT_FIELDTYPES = ("Data", "Small Text", "Text", "Long Text")


def _windows_1252(code):
    try:
        return bytes([code]).decode("cp1252")
    except UnicodeDecodeError:
        return None  # one of the five codes Windows-1252 leaves unused: dropped


# Windows-1252's characters at 0x80-0x9F, keyed by the control character
# Latin-1 reads each of those bytes as (str.translate table)
_WINDOWS_1252 = {code: _windows_1252(code) for code in range(0x80, 0xA0)}


def uploaded_value(fieldtype, value):
    """A table cell as the rules and the database expect it.

    Upload (frappe/public/js/frappe/form/grid.js) copies each CSV cell into
    its row as text, without any form event, so a row can hold exactly what
    Excel wrote:
    - Percent: a percentage cell is written "25%". Without the "%" it is
      25; anything still not a number comes back unchanged for
      key_result_area_errors to report.
    - Text: Excel's plain "CSV" format is Windows-1252, and Frappe reads a
      file that is not UTF-8 as Latin-1 (get_decoded_string in
      frappe/public/js/frappe/utils/utils.js). The two agree except at
      0x80-0x9F, where Word's curly quotes, dashes and bullets land as
      invisible control characters. Nobody types those, so each goes back
      to the character it was.
    Other columns, and values that are not text, come back as they are.
    """
    if not isinstance(value, str):
        return value
    if fieldtype == "Percent":
        text = value.strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        number = _number(text)
        return value if number is None else number
    if fieldtype in TEXT_FIELDTYPES:
        return value.translate(_WINDOWS_1252)
    return value


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


def name_lookup(names):
    """Case-insensitive name -> the record's exact name."""
    return {name.strip().lower(): name for name in names if name}


def designation_lookup(names):
    """Case-insensitive name -> the Job Title's exact name."""
    return name_lookup(names)


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


# The text fields the ISO, specification and competency tables replace:
# fieldname -> the value its rows get in the table's pick list column
ISO_TEXT_FIELDS = dict(
    zip(
        ("custom_jd_iso_9001", "custom_jd_iso_22000", "custom_jd_iso_45001", "custom_jd_iso_14001", "custom_jd_ims_leadership"),
        ISO_STANDARDS,
    )
)
SPECIFICATION_TEXT_FIELDS = dict(
    zip(("custom_jd_academic", "custom_jd_professional", "custom_jd_experience"), SPECIFICATION_TYPES)
)
COMPETENCY_TEXT_FIELDS = dict(
    zip(("custom_jd_technical_competencies", "custom_jd_behavioural_competencies"), COMPETENCY_CATEGORIES)
)
PROFILE_TEXT_FIELDS = {**ISO_TEXT_FIELDS, **SPECIFICATION_TEXT_FIELDS, **COMPETENCY_TEXT_FIELDS}


def skill_name_problem(name):
    """Why `name` cannot be a Skill, or None. Frappe refuses < and > in a
    name, and a name equal to its DocType (frappe/model/naming.py
    validate_name); the name column holds DATA_MAX characters."""
    if len(name) > DATA_MAX:
        return "longer than %d characters" % DATA_MAX
    if "<" in name or ">" in name:
        return "contains < or >"
    if name.lower() == "skill":
        return "a Skill cannot be called Skill"
    return None


def profile_sections_to_rows(values, skills):
    """Rows for the ISO Responsibilities, Ideal Job Specifications and
    Competency Framework tables from one Designation's old text fields.

    skills: {lower-cased name: exact name} of the Skills that already exist.
    Returns ({table field: [row dict, ...]}, [Skills to create first],
    [lines that could not be moved]).

    An ISO field becomes one row, whole: the table takes one row per
    standard. Each line of a specification or competency field becomes a
    row; a line repeated in the same list is kept once. A competency the
    Skill list lacks becomes a new Skill, unless it cannot be a Skill name.
    Nothing else is dropped: a line that cannot become a row is returned.
    """
    tables = {"custom_jd_iso_responsibilities": [], "custom_jd_specifications": [], "custom_jd_competencies": []}
    new_skills = []
    unconverted = []

    for field, standard in ISO_TEXT_FIELDS.items():
        text = str(values.get(field) or "").strip()
        if text:
            tables["custom_jd_iso_responsibilities"].append({"standard": standard, "accountabilities": text})

    seen = set()
    for field, kind in SPECIFICATION_TEXT_FIELDS.items():
        for line in split_lines(values.get(field)):
            key = (kind, " ".join(line.split()).lower())
            if key not in seen:
                seen.add(key)
                tables["custom_jd_specifications"].append({"specification_type": kind, "requirement": line})

    known = dict(skills)
    listed = {}  # lower-cased competency -> the category it was listed under
    for field, category in COMPETENCY_TEXT_FIELDS.items():
        for line in split_lines(values.get(field)):
            name = " ".join(line.split())
            key = name.lower()
            if key in listed:
                if listed[key] != category:
                    unconverted.append("%s competency: %s (already listed as %s)" % (category, line, listed[key]))
                continue
            if key not in known:
                problem = skill_name_problem(name)
                if problem:
                    unconverted.append("%s competency: %s (%s)" % (category, line, problem))
                    continue
                known[key] = name
                new_skills.append(name)
            listed[key] = category
            tables["custom_jd_competencies"].append({"category": category, "competency": known[key]})

    return tables, new_skills, unconverted


# ── The careers page ──────────────────────────────────────────────────

# What a Job Opening page may show from a Job Description. Everything else
# (KRA weightings and perspectives, reporting lines, stakeholders, decision
# authority, planning horizons, ISO responsibilities, sign-off) is internal.
POSTING_PARTS = ("purpose", "responsibilities", "requirements", "competencies")


def posting_details(
    purpose=None,
    key_result_areas=None,
    specifications=None,
    competencies=None,
    specification_order=(),
    category_order=(),
):
    """The candidate-facing parts of a Job Description, for the careers page.

    purpose           : the Job Purpose Statement
    key_result_areas  : JD Key Result Area rows; each line of their Key
                        Outputs becomes one responsibility, repeats dropped
    specifications    : JD Job Specification rows, grouped by type
    competencies      : JD Competency rows, grouped by category
    *_order           : the masters' order, so groups read as HR set them;
                        a group missing from it follows, in order of first use

    Returns {"purpose": str, "responsibilities": [str],
    "requirements": [{"title", "items": [{"text", "priority"}]}],
    "competencies": [{"title", "items": [str]}]}, or {} when there is
    nothing to show.
    """
    responsibilities, seen = [], set()
    for row in key_result_areas or []:
        for line in split_lines(_get(row, "key_outputs")):
            key = " ".join(line.split()).lower()
            if key not in seen:
                seen.add(key)
                responsibilities.append(line)

    def requirement(row):
        text = " ".join(str(_get(row, "requirement") or "").split())
        return {"text": text, "priority": _get(row, "priority") or ""} if text else None

    details = {
        "purpose": str(purpose or "").strip(),
        "responsibilities": responsibilities,
        "requirements": _grouped(specifications, "specification_type", specification_order, requirement),
        "competencies": _grouped(competencies, "category", category_order, lambda row: _get(row, "competency") or None),
    }
    return details if any(details.values()) else {}


def _grouped(rows, key, order, value):
    groups = {}
    for row in rows or []:
        item = value(row)
        if item:
            groups.setdefault(_get(row, key) or "", []).append(item)
    titles = [title for title in order if title in groups]
    titles += [title for title in groups if title not in titles]
    return [{"title": title, "items": groups[title]} for title in titles]


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _number(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return None
    # float() also reads "nan" and "inf", which an uploaded cell can hold.
    # Neither is a weighting, and NaN would slip past the range and total
    # checks (every comparison with it is false) to fail the database write.
    return number if number == number and abs(number) != float("inf") else None


def _format_number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")
