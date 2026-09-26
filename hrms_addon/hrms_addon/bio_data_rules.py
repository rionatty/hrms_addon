# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Pre-Interview Bio-Data Form (LPL/HR/19) rules.

No Frappe import, like jd_rules.py, so scripts/verify_bio_data.py can
exercise them without a bench.

Candidates fill the paper form at the interview and the HR Officer enters
it on the Job Applicant's Bio-Data tab. When the candidate is hired, the
Employee created from the Job Offer or Employee Onboarding starts with what
the form captured: employee_values() maps it onto Employee's own fields and
its Personal Bio-Data tab (the Personal Bio-Data Form, LPL/HR/16, which
reuses the parent, next of kin and qualification tables), missing_values()
keeps anything already on the Employee.
"""

import re

# Uganda's districts, from the "Districts of Uganda" list (current as of
# 1 July 2020: 26 Central, 37 Eastern, 39 Northern, 35 Western, Kampala
# included). Candidates pick from this list on the online Job Application
# Form and cannot add to it, so it is seeded in full; HR adds any new one.
UGANDA_DISTRICTS = tuple(sorted((
    # Central
    "Buikwe", "Bukomansimbi", "Butambala", "Buvuma", "Gomba", "Kalangala", "Kalungu", "Kampala", "Kasanda",
    "Kayunga", "Kiboga", "Kyankwanzi", "Kyotera", "Luweero", "Lwengo", "Lyantonde", "Masaka", "Mityana",
    "Mpigi", "Mubende", "Mukono", "Nakaseke", "Nakasongola", "Rakai", "Sembabule", "Wakiso",
    # Eastern
    "Amuria", "Budaka", "Bududa", "Bugiri", "Bugweri", "Bukedea", "Bukwo", "Bulambuli", "Busia", "Butaleja",
    "Butebo", "Buyende", "Iganga", "Jinja", "Kaberamaido", "Kalaki", "Kaliro", "Kamuli", "Kapchorwa",
    "Kapelebyong", "Katakwi", "Kibuku", "Kumi", "Kween", "Luuka", "Manafwa", "Mayuge", "Mbale", "Namayingo",
    "Namisindwa", "Namutumba", "Ngora", "Pallisa", "Serere", "Sironko", "Soroti", "Tororo",
    # Northern
    "Abim", "Adjumani", "Agago", "Alebtong", "Amolatar", "Amudat", "Amuru", "Apac", "Arua", "Dokolo", "Gulu",
    "Kaabong", "Karenga", "Kitgum", "Koboko", "Kole", "Kotido", "Kwania", "Lamwo", "Lira", "Madi-Okollo",
    "Maracha", "Moroto", "Moyo", "Nabilatuk", "Nakapiripirit", "Napak", "Nebbi", "Nwoya", "Obongi", "Omoro",
    "Otuke", "Oyam", "Pader", "Pakwach", "Terego", "Yumbe", "Zombo",
    # Western
    "Buhweju", "Buliisa", "Bundibugyo", "Bunyangabu", "Bushenyi", "Hoima", "Ibanda", "Isingiro", "Kabale",
    "Kabarole", "Kagadi", "Kakumiro", "Kamwenge", "Kanungu", "Kasese", "Kazo", "Kibaale", "Kikuube", "Kiruhura",
    "Kiryandongo", "Kisoro", "Kitagwenda", "Kyegegwa", "Kyenjojo", "Masindi", "Mbarara", "Mitooma", "Ntoroko",
    "Ntungamo", "Rubanda", "Rubirizi", "Rukiga", "Rukungiri", "Rwampara", "Sheema",
)))

# The Bio-Data tab's pick lists, same shape as jd_rules.MASTERS: master
# DocType -> (name field, values seeded once).
BIO_DATA_MASTERS = {
    "District": ("district_name", UGANDA_DISTRICTS),
    "Relationship": ("relationship_name", (
        "Father", "Mother", "Guardian", "Spouse", "Son", "Daughter",
        "Brother", "Sister", "Uncle", "Aunt", "Cousin", "Friend",
    )),
    "Examination Level": ("level_name", ("O-Level (UCE)", "A-Level (UACE)")),
    # Academic, or a certification: the interview shortlist lists
    # certifications in their own column (Qualification Type's
    # "Certification or Licence" check, set on these seeds by pick_lists)
    "Qualification Type": ("type_name", ("Academic", "Professional Certification")),
}
# The seeded Qualification Types that count as certifications
CERTIFICATION_TYPES = ("Professional Certification",)

# (DocType, field) -> the master it links to
BIO_DATA_FIELD_MASTERS = {
    ("Job Applicant", "custom_home_district"): "District",
    ("Job Applicant", "custom_current_district"): "District",
    ("Applicant Parent", "relationship"): "Relationship",
    ("Applicant Parent", "home_district"): "District",
    ("Applicant Parent", "current_district"): "District",
    ("Applicant Next of Kin", "relationship"): "Relationship",
    ("Applicant School Result", "examination_level"): "Examination Level",
    ("Applicant Qualification", "qualification_type"): "Qualification Type",
}

# Job Applicant table field -> child DocType, in the order of the paper form
TABLES = {
    "custom_parents": "Applicant Parent",
    "custom_next_of_kin": "Applicant Next of Kin",
    "custom_qualifications": "Applicant Qualification",
    "custom_school_results": "Applicant School Result",
    "custom_employment_history": "Applicant Employment History",
    "custom_skills": "Applicant Skill",
    "custom_languages": "Applicant Language",
}

# Exactly Employee's own options, so the value carries over on hire
MARITAL_STATUSES = ("Single", "Married", "Divorced", "Widowed")

# Job Applicant field -> Employee field it is copied to on hire. NIN, TIN
# and NSSF No. keep the fieldnames of the Employee master-data template.
EMPLOYEE_FIELDS = {
    "custom_date_of_birth": "date_of_birth",
    "custom_gender": "gender",
    "custom_marital_status": "marital_status",
    "phone_number": "cell_number",
    "custom_nin": "custom_nin",
    "custom_tin": "custom_tin",
    "custom_nssf_no": "custom_nssf_no",
    "custom_health_issues": "health_details",
    # the Employee's Personal Bio-Data tab asks the same
    "custom_home_village": "custom_home_village",
    "custom_home_district": "custom_home_district",
    "custom_current_residence": "custom_current_residence",
    "custom_current_district": "custom_current_district",
}

# Job Applicant table -> the Employee table of the same child DocType, and
# the columns a row carries
EMPLOYEE_TABLES = {"custom_parents": "custom_parents", "custom_next_of_kin": "custom_next_of_kin"}
TABLE_COLUMNS = {
    "Applicant Parent": ("full_name", "relationship", "occupation", "home_village", "home_district",
                         "current_residence", "current_district", "phone"),
    "Applicant Next of Kin": ("full_name", "relationship", "company", "job_title", "phone", "email"),
    "Applicant Qualification": ("qualification_type", "institution", "period", "program", "award"),
}
# Certifications, licences and memberships sit apart from the formal
# education on the Employee, as on the Personal Bio-Data Form
PROFESSIONAL_TABLE = "custom_professional_qualifications"

# Frappe stores Data fields as varchar(140)
DATA_MAX = 140
EARLIEST_YEAR = 1950


def bio_data_errors(applicant, today):
    """Problems with a Job Applicant's Bio-Data tab, as user-facing messages.

    applicant: the Job Applicant as a dict or document, tables included.
    today: the date to judge "in the future" by, as a date or "YYYY-MM-DD".
    Every field is optional: many applicants never reach the interview.
    """
    errors = []
    today = _iso(today)
    this_year = int(today[:4])

    for field, label in (("custom_date_of_birth", "Date of Birth"), ("custom_bio_data_date", "Date Signed")):
        value = _iso(_get(applicant, field))
        if value and value > today:
            errors.append("%s cannot be in the future." % label)

    children = _int(_get(applicant, "custom_no_of_children"))
    if children is not None and children < 0:
        errors.append("No. of Children cannot be negative.")

    for index, row in enumerate(_rows(applicant, "custom_employment_history"), start=1):
        years = {}
        for field, label in (("from_year", "From (Year)"), ("to_year", "To (Year)")):
            value = str(_get(row, field) or "").strip()
            if not value:
                continue
            if not re.fullmatch(r"\d{4}", value) or not EARLIEST_YEAR <= int(value) <= this_year:
                errors.append(
                    "Employment History row %d: %s must be a year from %d to %d, e.g. 2015."
                    % (index, label, EARLIEST_YEAR, this_year)
                )
            else:
                years[field] = int(value)
        if len(years) == 2 and years["to_year"] < years["from_year"]:
            errors.append(
                "Employment History row %d: To (Year) %d is before From (Year) %d."
                % (index, years["to_year"], years["from_year"])
            )

    seen = {}
    for index, row in enumerate(_rows(applicant, "custom_school_results"), start=1):
        subject = " ".join(str(_get(row, "subject") or "").split())
        if not subject:
            continue
        level = _get(row, "examination_level")
        key = (level, subject.lower())
        if key in seen:
            errors.append(
                "A'Level and O'Level Results row %d: %s is already listed for %s in row %d."
                % (index, subject, level, seen[key])
            )
        else:
            seen[key] = index

    errors += _repeats(applicant, "custom_skills", "skill", "Skills Possessed")
    errors += _repeats(applicant, "custom_languages", "language", "Language Proficiency")

    for index, row in enumerate(_rows(applicant, "custom_languages"), start=1):
        if _get(row, "language") and not any(_int(_get(row, f)) for f in ("can_read", "can_write", "can_speak")):
            errors.append(
                "Language Proficiency row %d: tick Read, Write or Speak for %s." % (index, _get(row, "language"))
            )

    return errors


def employee_values(applicant, certification_types=CERTIFICATION_TYPES):
    """Employee fields and tables filled from a Job Applicant's bio-data.

    Returns {Employee field: value, or a list of row dicts for a table}.
    Empty values are left out, so applying the result can only fill in.
    Everything the Employee has no place for (languages, school results by
    subject, reasons for leaving) stays on the Job Applicant, which the
    Employee links to.

    certification_types: the Qualification Types that are certifications or
    licences (the site's own, ticked on the list); those qualifications go to
    the Employee's professional table, the rest to its Education.
    """
    values = {target: _get(applicant, source) for source, target in EMPLOYEE_FIELDS.items()}
    values["current_address"] = _joined(
        _get(applicant, "custom_current_residence"), _get(applicant, "custom_current_district")
    )
    values["permanent_address"] = _joined(
        _get(applicant, "custom_home_village"), _get(applicant, "custom_home_district")
    )

    kin = next((row for row in _rows(applicant, "custom_next_of_kin") if _get(row, "full_name")), None)
    if kin:
        values["person_to_be_contacted"] = _get(kin, "full_name")
        values["relation"] = _get(kin, "relationship")
        values["emergency_phone_number"] = _get(kin, "phone")

    values["family_background"] = family_background(applicant)
    values["education"] = education_rows(applicant, certification_types)
    values[PROFESSIONAL_TABLE] = professional_rows(applicant, certification_types)
    values["external_work_history"] = work_history_rows(applicant)
    for source, target in EMPLOYEE_TABLES.items():
        columns = TABLE_COLUMNS[TABLES[source]]
        values[target] = [_compact({column: _get(row, column) for column in columns})
                          for row in _rows(applicant, source) if _get(row, "full_name")]
    return {field: value for field, value in values.items() if value not in (None, "", [])}


def family_background(applicant):
    """Parents and number of children as lines of text, for Employee's
    Family Background."""
    lines = []
    for row in _rows(applicant, "custom_parents"):
        name = _get(row, "full_name")
        if not name:
            continue
        parts = [name]
        home = _joined(_get(row, "home_village"), _get(row, "home_district"))
        if home:
            parts.append("home: " + home)
        lives = _joined(_get(row, "current_residence"), _get(row, "current_district"))
        if lives:
            parts.append("lives: " + lives)
        if _get(row, "phone"):
            parts.append("tel: " + _get(row, "phone"))
        lines.append("%s: %s" % (_get(row, "relationship") or "Parent", " | ".join(parts)))
    children = _int(_get(applicant, "custom_no_of_children"))
    if children:
        lines.append("Children: %d" % children)
    return "\n".join(lines)


def education_rows(applicant, certification_types=CERTIFICATION_TYPES):
    """Rows for Employee's Education table: one per qualification that is not
    a certification or licence, then one per examination level listing its
    subjects and grades."""
    rows = []
    for row in _rows(applicant, "custom_qualifications"):
        if _get(row, "qualification_type") in certification_types:
            continue
        institution, program, award = _get(row, "institution"), _get(row, "program"), _get(row, "award")
        if not (institution or program or award):
            continue
        rows.append(
            _compact(
                {
                    "school_univ": institution,
                    "qualification": _truncate(program or award),
                    "class_per": _truncate(award) if program else None,
                    "year_of_passing": last_year(_get(row, "period")),
                }
            )
        )

    results = {}
    for row in _rows(applicant, "custom_school_results"):
        level, subject, grade = _get(row, "examination_level"), _get(row, "subject"), _get(row, "grade")
        if level and subject:
            results.setdefault(level, []).append("%s: %s" % (subject, grade) if grade else subject)
    for level, lines in results.items():
        rows.append({"qualification": _truncate(level), "maj_opt_subj": "\n".join(lines)})
    return rows


def professional_rows(applicant, certification_types=CERTIFICATION_TYPES):
    """Rows for the Employee's Professional Certificates and Memberships
    table (Applicant Qualification rows, as they are): the qualifications
    whose type is a certification or licence."""
    columns = TABLE_COLUMNS["Applicant Qualification"]
    return [_compact({column: _get(row, column) for column in columns})
            for row in _rows(applicant, "custom_qualifications")
            if _get(row, "qualification_type") in certification_types and _get(row, "institution")]


def work_history_rows(applicant):
    """Rows for Employee's External Work History table."""
    rows = []
    for row in _rows(applicant, "custom_employment_history"):
        if not _get(row, "workplace"):
            continue
        rows.append(
            _compact(
                {
                    "company_name": _truncate(_get(row, "workplace")),
                    "designation": _truncate(_get(row, "position")),
                    "total_experience": _period(_get(row, "from_year"), _get(row, "to_year")),
                }
            )
        )
    return rows


def missing_values(current, values):
    """The part of `values` that fills blanks in `current` (an Employee): a
    field only when it is empty, a table only when it has no rows. Nothing
    already on the Employee is overwritten."""
    missing = {}
    for field, value in values.items():
        existing = _get(current, field)
        if isinstance(value, list):
            if not existing:
                missing[field] = value
        elif existing in (None, ""):
            missing[field] = value
    return missing


def last_year(period):
    """The last four-digit year in "2014 - 2017", "2019" or "Aug 2016 to Jul 2018"; None if there is none."""
    years = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", str(period or ""))
    return int(years[-1]) if years else None


def _period(start, end):
    start, end = str(start or "").strip(), str(end or "").strip()
    if start and end:
        return "%s - %s" % (start, end)
    return ("from %s" % start) if start else ("to %s" % end) if end else None


def _repeats(applicant, table, field, label):
    errors = []
    seen = {}
    for index, row in enumerate(_rows(applicant, table), start=1):
        value = _get(row, field)
        if not value:
            continue
        key = str(value).strip().lower()
        if key in seen:
            errors.append("%s row %d: %s is already listed in row %d." % (label, index, value, seen[key]))
        else:
            seen[key] = index
    return errors


def _joined(*parts):
    return ", ".join(str(part).strip() for part in parts if part and str(part).strip())


def _truncate(text):
    return text[:DATA_MAX] if isinstance(text, str) else text


def _compact(row):
    return {key: value for key, value in row.items() if value not in (None, "")}


def _rows(doc, field):
    return _get(doc, field) or []


def _iso(value):
    return str(value)[:10] if value else ""


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)
