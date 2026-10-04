# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The balanced scorecard appraisal on the site (LPL PMS FY 2026).

The rules are in bsc_rules.py, without a Frappe import
(scripts/verify_performance.py). This reads and writes the site.

  template_*   the role's scorecard. It lives on Frappe HR's own Appraisal
               Template: Section A's KPIs under their perspectives, every
               KPI with its own weight, the perspectives below summing them
               up to 80, and the competencies out of 20. The same template
               carries the supervisory form (LPL/HR/18) instead when its
               Form Type says so: the ratable factors and the objectives.
               Every Job Title names its template.
  import_*     Luuka's own PMS workbooks read straight in — one sheet per
               role, ten departments, eighty-four roles — so the scorecards
               are not retyped. The workbook weighs a perspective once; its
               weight is shared out between its KPIs. A sheet whose weights
               do not add up is imported and flagged rather than silently
               corrected.
  fill         an appraisal filled from its role's scorecard
  score        each KPI's weighted score for every quarter recorded, the
               perspectives summing them up, Section A for the quarter
               appraised, Section B, and the overall out of 100 on the
               form's own bands

The supervisory form (LPL/HR/18) is in appraisal_rules.py and they run side
by side; the Appraisal's Form Type says which one an employee is on.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms_addon.hrms_addon import bsc_rules as rules

TEMPLATE = "Appraisal Template"  # Frappe HR's own, carrying Luuka's scorecard
PERSPECTIVE_MASTER = "KRA Perspective"
COMPETENCY_MASTER = "BSC Competency"
# the template the supervisory form's Job Titles share (seed_supervisory_template)
SUPERVISORY_TEMPLATE = "Supervisory Skills Evaluation (LPL/HR/18)"


# ── 1. The role's template ────────────────────────────────────────────
def template_validate(doc, method=None):
    doc.custom_form_type = doc.get("custom_form_type") or rules.FORM_BSC
    if doc.custom_form_type == rules.FORM_SUPERVISORY:
        _supervisory_template(doc)
        return
    _arrange_kpis(doc)
    doc.custom_objectives_weight = round(sum(flt(row.weight) for row in doc.get("custom_kpis") or []), 2)
    doc.custom_competencies_weight = sum(flt(row.weight) for row in doc.get("custom_competencies") or [])
    for row in doc.get("custom_competencies") or []:
        if row.competency and not row.indicators:
            row.indicators = frappe.db.get_value(COMPETENCY_MASTER, row.competency, "indicators")
    if not doc.get("custom_kpis") and not doc.get("custom_competencies"):
        # a plain Frappe HR template, with KRAs on it and no scorecard
        doc.custom_import_remarks = None
        return
    _drop_blank_upstream_rows(doc)
    errors = rules.template_errors({
        "designation": doc.get("custom_designation"),
        "kpis": [row.as_dict() for row in doc.get("custom_kpis") or []],
        "competencies": [row.as_dict() for row in doc.get("custom_competencies") or []],
    })
    # a template imported from a sheet whose weights do not add up is kept
    # and flagged, so HR can see what Luuka's own workbook says; it is only
    # refused once someone marks it active
    if errors and doc.get("custom_is_active"):
        frappe.throw("<br>".join(_(message) for message in errors) +
                     ("<br><br>" + _("Untick Active to save it as it stands and put the weights right later.")),
                     title=_("Scorecard Template"))
    doc.custom_import_remarks = "; ".join(errors) if errors else None


def _arrange_kpis(doc):
    """Section A as the form lays it out: each perspective's KPIs together,
    each with its own weight. The perspectives below them weigh what their
    KPIs weigh; they are never typed."""
    rows = doc.get("custom_kpis") or []
    arranged, perspectives = rules.arrange_kpis([
        {"perspective": row.perspective, "kpi": row.kpi, "timing": row.timing, "weight": row.get("weight"),
         "at": index} for index, row in enumerate(rows)])
    ordered = []
    for position, found in enumerate(arranged, 1):
        row = rows[found["at"]]
        row.idx = position
        ordered.append(row)
    doc.set("custom_kpis", ordered)
    have = [(row.perspective, flt(row.weight)) for row in doc.get("custom_perspectives") or []]
    if have != [(row["perspective"], flt(row["weight"])) for row in perspectives]:
        doc.set("custom_perspectives", [{"perspective": row["perspective"], "weight": row["weight"]}
                                        for row in perspectives])


def _supervisory_template(doc):
    """A template for the Supervisory Skills form (LPL/HR/18): the ratable
    factors, the twelve on the form unless HR chose otherwise, and the
    objectives, up to eight; with none listed the appraisal takes the Job
    Title's Key Result Areas. One such template can serve many Job Titles."""
    if not doc.get("custom_factors"):
        factors = frappe.get_all("Appraisal Factor", pluck="name", order_by="creation asc")
        doc.set("custom_factors", [{"factor": factor} for factor in factors])
    errors = rules.supervisory_template_errors({
        "factors": [row.as_dict() for row in doc.get("custom_factors") or []],
        "objectives": [row.as_dict() for row in doc.get("custom_objectives") or []],
    })
    if errors and doc.get("custom_is_active"):
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Appraisal Template"))
    doc.custom_import_remarks = "; ".join(errors) if errors else None
    _drop_blank_upstream_rows(doc)


def _drop_blank_upstream_rows(doc):
    """Frappe HR's own KRA and rating tables are hidden on a scorecard
    template and Luuka do not fill them, but a blank row left in one
    refuses the save over a table nobody can see. The form drops them too;
    this covers an import or an API call, which never runs a form script.

    A row with anything in it is left alone: a template that really does
    carry KRAs keeps them.
    """
    for table, fields in (("goals", ("key_result_area", "per_weightage")),
                          ("rating_criteria", ("criteria", "per_weightage"))):
        rows = doc.get(table) or []
        kept = [row for row in rows if any(row.get(field) for field in fields)]
        if len(kept) != len(rows):
            doc.set(table, kept)


def template_for(employee=None, designation=None, year=None):
    """The active scorecard for a role, if there is one."""
    designation = designation or (frappe.db.get_value("Employee", employee, "designation") if employee else None)
    if not designation:
        return None
    filters = {"custom_designation": designation, "custom_is_active": 1}
    if year:
        filters["custom_review_year"] = year
    name = frappe.db.get_value(TEMPLATE, filters, "name", order_by="custom_review_year desc")
    if not name and year:
        name = frappe.db.get_value(TEMPLATE, {"custom_designation": designation, "custom_is_active": 1},
                                   "name", order_by="custom_review_year desc")
    return name


# ── 2. The appraisal ──────────────────────────────────────────────────
# what an appraiser or the employee records on a KPI row, kept when the
# template is taken again
RECORDED = ("self_percent",) + tuple(field for quarter in rules.QUARTERS
                                     for field in (rules.percent_field(quarter), rules.comments_field(quarter)))


def fill(doc, template=None):
    """Section A and Section B taken from the role's scorecard: the KPIs as
    the template has them now, each with its weight. What is already
    recorded against a KPI is kept, so re-filling never wipes a rating."""
    name = template or doc.get("appraisal_template")
    if not name or not frappe.db.exists(TEMPLATE, name):
        return 0
    card = frappe.get_doc(TEMPLATE, name)
    doc.appraisal_template = card.name
    recorded = {(row.perspective, _plain(row.kpi)): {field: row.get(field) for field in RECORDED}
                for row in doc.get("custom_bsc_kpis") or []}
    added = len([row for row in card.custom_kpis if (row.perspective, _plain(row.kpi)) not in recorded])
    doc.set("custom_bsc_kpis", [])
    for row in card.custom_kpis:
        doc.append("custom_bsc_kpis", dict(recorded.get((row.perspective, _plain(row.kpi))) or {},
                                           perspective=row.perspective, kpi=row.kpi, timing=row.timing,
                                           weight=flt(row.weight)))
    summarise(doc)
    have = {row.competency for row in doc.get("custom_bsc_competencies") or []}
    for row in card.custom_competencies:
        if row.competency in have:
            for existing in doc.custom_bsc_competencies:
                if existing.competency == row.competency:
                    existing.weight = flt(row.weight)
            continue
        doc.append("custom_bsc_competencies", {"competency": row.competency, "indicators": row.indicators,
                                               "weight": flt(row.weight)})
        added += 1
    return added


def score(doc):
    """Section C of the scorecard: each KPI's weighted score for every
    quarter recorded and for the quarter appraised, the perspectives summing
    them up, Section A for the quarter, Section B, and the overall on the
    form's own bands."""
    quarter = doc.get("custom_quarter")
    kpis = doc.get("custom_bsc_kpis") or []
    for row in kpis:
        for each in rules.QUARTERS:
            row.set(rules.score_field(each), rules.quarter_score(row.weight, row.get(rules.percent_field(each))))
        row.score = row.get(rules.score_field(quarter)) if quarter in rules.QUARTERS else None
    summarise(doc)
    competencies = doc.get("custom_bsc_competencies") or []
    for row in competencies:
        row.weighted_score = rules.competency_score(row.weight, row.get("score"))
    rows = [row.as_dict() for row in kpis]
    section_a = rules.section_a(rows, quarter) if quarter in rules.QUARTERS else None
    section_b = rules.section_b([row.as_dict() for row in competencies])
    overall = rules.overall(section_a, section_b)
    doc.custom_bsc_section_a_score = section_a
    doc.custom_bsc_section_b_score = section_b
    doc.custom_bsc_overall = overall
    doc.custom_bsc_band = rules.band(overall)
    doc.custom_bsc_band_meaning = rules.BAND_MEANING.get(doc.custom_bsc_band)
    # the employee's own scores, worked out the same way, where they rate themselves
    own = rules.self_scores(rows, [row.as_dict() for row in competencies], quarter) \
        if doc.get("custom_self_appraisal") else {"overall": None}
    doc.custom_bsc_self_score = own["overall"]
    doc.self_score = flt(own["overall"] or 0)
    return {"section_a": section_a, "section_b": section_b, "overall": overall, "band": doc.custom_bsc_band}


def summarise(doc):
    """The perspectives below the KPIs, worked out from them: never typed,
    so they are drawn afresh every time."""
    doc.set("custom_bsc_perspectives", rules.perspective_summary(
        [row.as_dict() for row in doc.get("custom_bsc_kpis") or []]))


def facts(doc, step=None):
    return {
        "step": step, "quarter": doc.get("custom_quarter"),
        "kpis": [row.as_dict() for row in doc.get("custom_bsc_kpis") or []],
        "competencies": [row.as_dict() for row in doc.get("custom_bsc_competencies") or []],
    }


def _plain(text):
    """A KPI's words as they are matched: spaces and line breaks count as one."""
    return " ".join(str(text or "").split())


@frappe.whitelist(methods=["POST"])
def get_scorecard(appraisal, template=None):
    """The form's Get from Template, by its older name
    (appraisals.apply_template)."""
    from hrms_addon.hrms_addon import appraisals

    return appraisals.apply_template(appraisal, template)


# ── 3. Luuka's own workbooks, read straight in ────────────────────────
@frappe.whitelist(methods=["POST"])
def import_workbook(file_url, review_year, company=None, activate=0):
    """An LPL PMS workbook: one scorecard per role sheet.

    Every sheet is imported. One whose weights do not total 80 and 20 is
    kept but left inactive with the reason on it, because the numbers are
    Luuka's to correct, not ours.
    """
    if not frappe.has_permission(TEMPLATE, "create"):
        frappe.throw(_("You may not create scorecard templates."), frappe.PermissionError)
    from openpyxl import load_workbook

    path = frappe.get_doc("File", {"file_url": file_url}).get_full_path()
    workbook = load_workbook(filename=path, data_only=True, read_only=True)
    made, updated, flagged, skipped = [], [], [], []
    for sheet in workbook.sheetnames:
        rows = [list(row) for row in workbook[sheet].iter_rows(values_only=True)]
        found = rules.parse_sheet(rows)
        if not (found["role"] and found["perspectives"]):
            skipped.append(sheet)
            continue
        name, was_new, problems = _save_template(found, int(review_year), company, file_url, sheet, int(activate or 0))
        (made if was_new else updated).append(name)
        if problems:
            flagged.append({"template": name, "sheet": sheet, "problems": problems})
    workbook.close()
    frappe.db.commit()
    return {"created": made, "updated": updated, "flagged": flagged, "skipped": skipped}


def _save_template(found, year, company, file_url, sheet, activate):
    designation = _designation(found["role"])
    existing = frappe.db.get_value(TEMPLATE, {"custom_designation": designation,
                                              "custom_review_year": year}, "name")
    doc = frappe.get_doc(TEMPLATE, existing) if existing else frappe.new_doc(TEMPLATE)
    if not existing:
        # their template is named after its title, so the role and the year
        # name it; a title already taken keeps the sheet's own name apart
        doc.template_title = _title(designation, year, sheet)
    doc.update({
        "custom_form_type": rules.FORM_BSC, "custom_designation": designation,
        "custom_review_year": year, "custom_grade": found.get("grade"),
        "custom_review_period": found.get("review_period"), "custom_company": company,
        "custom_department": _department(found.get("department")),
        "custom_form_reference": found.get("form_reference"), "custom_revision": found.get("revision"),
        "custom_source_file": file_url, "custom_source_sheet": sheet,
    })
    # Section A as the sheet has it, each perspective's weight shared out
    # between its KPIs where the sheet writes it once
    kpis, perspectives = rules.arrange_kpis(rules.spread_weights(
        [dict(row, perspective=_perspective(row["perspective"])) for row in found["kpis"]]))
    doc.set("custom_kpis", [])
    for row in kpis:
        doc.append("custom_kpis", {"perspective": row["perspective"], "kpi": row["kpi"],
                                   "timing": row["timing"] if row["timing"] in rules.TIMINGS else None,
                                   "weight": row["weight"]})
    doc.set("custom_perspectives", [{"perspective": row["perspective"], "weight": flt(row["weight"])}
                                    for row in perspectives])
    doc.set("custom_competencies", [])
    for row in found["competencies"]:
        doc.append("custom_competencies", {"competency": _competency(row["competency"], row.get("indicators"),
                                                                     row.get("weight")),
                                           "indicators": row.get("indicators"), "weight": flt(row["weight"])})
    problems = rules.template_errors({
        "designation": designation,
        "kpis": [row.as_dict() for row in doc.custom_kpis],
        "competencies": [row.as_dict() for row in doc.custom_competencies],
    })
    doc.custom_is_active = 1 if (activate and not problems) else 0
    doc.flags.ignore_permissions = True
    doc.save()
    _link_designation(designation, doc.name, year)
    return doc.name, not existing, problems


def _link_designation(designation, template, year):
    """The Job Title names the template it is appraised on: this one, where
    it names none yet or names a scorecard of an earlier year."""
    current = frappe.db.get_value("Designation", designation, "appraisal_template")
    if current and current != template:
        current_year = frappe.db.get_value(TEMPLATE, current, "custom_review_year") \
            if frappe.db.exists(TEMPLATE, current) else None
        if current_year and int(current_year) >= int(year):
            return
    if current != template:
        frappe.db.set_value("Designation", designation, "appraisal_template", template, update_modified=False)


def _title(designation, year, sheet):
    title = " ".join(("%s %s" % (designation, year)).split())
    if not frappe.db.exists(TEMPLATE, title):
        return title
    apart = " ".join(("%s %s (%s)" % (designation, year, sheet)).split())
    if not frappe.db.exists(TEMPLATE, apart):
        return apart
    nth = 2
    while frappe.db.exists(TEMPLATE, "%s (%d)" % (apart, nth)):
        nth += 1
    return "%s (%d)" % (apart, nth)


def _designation(role):
    """The Job Title a sheet is for, made where there is none. Every Job Title
    must name its Appraisal Template, and this one's is being made now, so
    it is named as soon as the template is saved (_link_designation)."""
    name = " ".join(str(role or "").split())
    if not frappe.db.exists("Designation", name):
        designation = frappe.get_doc({"doctype": "Designation", "designation_name": name})
        designation.flags.ignore_mandatory = True
        designation.insert(ignore_permissions=True)
    return name


def seed_supervisory_template():
    """The template for the Supervisory Skills Evaluation Form (LPL/HR/18),
    made once with the form's twelve factors, so a supervisor's Job Title
    has a template to name."""
    found = frappe.db.get_value(TEMPLATE, {"template_title": SUPERVISORY_TEMPLATE}, "name")
    if found:
        return found
    doc = frappe.new_doc(TEMPLATE)
    doc.template_title = SUPERVISORY_TEMPLATE
    doc.custom_form_type = rules.FORM_SUPERVISORY
    doc.custom_is_active = 1
    doc.custom_form_reference = "LPL/HR/18"
    doc.custom_revision = "Rev 01"
    factors = frappe.get_all("Appraisal Factor", pluck="name", order_by="creation asc")
    doc.set("custom_factors", [{"factor": factor} for factor in factors])
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.insert()
    return doc.name


def _department(text):
    """The workbook writes 'Procurement — Head Office'; a Department is only
    linked where one of that name really exists."""
    if not text:
        return None
    name = " ".join(str(text).split())
    for candidate in (name, name.split("—")[0].strip(), name.split("-")[0].strip()):
        if candidate and frappe.db.exists("Department", candidate):
            return candidate
    like = frappe.get_all("Department", filters={"department_name": ["like", "%s%%" % name.split("—")[0].strip()]},
                          pluck="name", limit=1)
    return like[0] if like else None


def _perspective(name):
    if name and not frappe.db.exists(PERSPECTIVE_MASTER, name):
        frappe.get_doc({"doctype": PERSPECTIVE_MASTER, "perspective_name": name}).insert(ignore_permissions=True)
    return name


def _competency(name, indicators=None, weight=None):
    clean = " ".join(str(name or "").split())
    if clean and not frappe.db.exists(COMPETENCY_MASTER, clean):
        frappe.get_doc({"doctype": COMPETENCY_MASTER, "competency_name": clean, "indicators": indicators,
                        "default_weight": flt(weight)}).insert(ignore_permissions=True)
    return clean
