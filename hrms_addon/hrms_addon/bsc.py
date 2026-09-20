# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The balanced scorecard appraisal on the site (LPL PMS FY 2026).

The rules are in bsc_rules.py, without a Frappe import
(scripts/verify_performance.py). This reads and writes the site.

  template_*   the role's scorecard. It lives on Frappe HR's own Appraisal
               Template, extended with the perspectives and their weights
               out of 80, the KPIs under each, and the competencies out of
               20 — the same way both appraisal forms live on Frappe HR's
               Appraisal, rather than in a doctype standing beside it
  import_*     Luuka's own PMS workbooks read straight in — one sheet per
               role, ten departments, eighty-four roles — so the scorecards
               are not retyped. A sheet whose weights do not add up is
               imported and flagged rather than silently corrected.
  fill         an appraisal filled from its role's scorecard
  score        Section A for the period being scored, Section B, and the
               overall out of 100 on the form's own bands

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


# ── 1. The role's scorecard ───────────────────────────────────────────
def template_validate(doc, method=None):
    doc.custom_objectives_weight = sum(flt(row.weight) for row in doc.get("custom_perspectives") or [])
    doc.custom_competencies_weight = sum(flt(row.weight) for row in doc.get("custom_competencies") or [])
    for row in doc.get("custom_competencies") or []:
        if row.competency and not row.indicators:
            row.indicators = frappe.db.get_value(COMPETENCY_MASTER, row.competency, "indicators")
    if not doc.get("custom_perspectives") and not doc.get("custom_competencies"):
        # a plain Frappe HR template, with KRAs on it and no scorecard
        doc.custom_import_remarks = None
        return
    errors = rules.template_errors({
        "designation": doc.get("custom_designation"),
        "perspectives": [row.as_dict() for row in doc.get("custom_perspectives") or []],
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
def fill(doc, template=None):
    """Section A and Section B taken from the role's scorecard. What is
    already scored is left alone, so re-filling never wipes a rating."""
    name = template or doc.get("appraisal_template")
    if not name or not frappe.db.exists(TEMPLATE, name):
        return 0
    card = frappe.get_doc(TEMPLATE, name)
    doc.appraisal_template = card.name
    have = {row.perspective for row in doc.get("custom_bsc_perspectives") or []}
    added = 0
    for row in card.custom_perspectives:
        if row.perspective in have:
            for existing in doc.custom_bsc_perspectives:
                if existing.perspective == row.perspective:
                    existing.weight = flt(row.weight)
            continue
        doc.append("custom_bsc_perspectives", {"perspective": row.perspective, "weight": flt(row.weight)})
        added += 1
    doc.set("custom_bsc_kpis", [])
    for row in card.custom_kpis:
        doc.append("custom_bsc_kpis", {"perspective": row.perspective, "kpi": row.kpi, "timing": row.timing})
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
    """Section C of the scorecard: each quarter's weighted score, the year's,
    Section B, and the overall on the form's own bands."""
    perspectives = doc.get("custom_bsc_perspectives") or []
    for row in perspectives:
        for quarter in rules.QUARTERS:
            row.set("%s_score" % quarter.lower(),
                    rules.quarter_score(row.weight, row.get("%s_percent" % quarter.lower())))
        row.annual_weighted = rules.annual_score(row.weight, row.get("annual_score"))
    competencies = doc.get("custom_bsc_competencies") or []
    for row in competencies:
        row.weighted_score = rules.competency_score(row.weight, row.get("score"))
    period = doc.get("custom_period") or rules.ANNUAL
    section_a = rules.section_a([row.as_dict() for row in perspectives], period)
    section_b = rules.section_b([row.as_dict() for row in competencies])
    overall = rules.overall(section_a, section_b)
    doc.custom_bsc_section_a_score = section_a
    doc.custom_bsc_section_b_score = section_b
    doc.custom_bsc_overall = overall
    doc.custom_bsc_band = rules.band(overall)
    doc.custom_bsc_band_meaning = rules.BAND_MEANING.get(doc.custom_bsc_band)
    return {"section_a": section_a, "section_b": section_b, "overall": overall, "band": doc.custom_bsc_band}


def facts(doc, step=None):
    return {
        "step": step, "period": doc.get("custom_period") or rules.ANNUAL,
        "perspectives": [row.as_dict() for row in doc.get("custom_bsc_perspectives") or []],
        "competencies": [row.as_dict() for row in doc.get("custom_bsc_competencies") or []],
    }


@frappe.whitelist(methods=["POST"])
def get_scorecard(appraisal, template=None):
    """The form's Get Scorecard: fill Section A and B from the role's
    template. Returns how many rows were added."""
    doc = frappe.get_doc("Appraisal", appraisal)
    doc.check_permission("write")
    name = template or doc.get("appraisal_template") or template_for(employee=doc.employee)
    if not name:
        frappe.throw(_("No active scorecard for {0}. Import or draw one up first.").format(
            frappe.db.get_value("Employee", doc.employee, "designation") or doc.employee))
    added = fill(doc, name)
    doc.flags.ignore_permissions = True
    doc.save()
    return added


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
        "custom_designation": designation,
        "custom_review_year": year, "custom_grade": found.get("grade"),
        "custom_review_period": found.get("review_period"), "custom_company": company,
        "custom_department": _department(found.get("department")),
        "custom_source_file": file_url, "custom_source_sheet": sheet,
    })
    doc.set("custom_perspectives", [])
    for row in found["perspectives"]:
        doc.append("custom_perspectives", {"perspective": _perspective(row["perspective"]),
                                           "weight": flt(row["weight"])})
    doc.set("custom_kpis", [])
    for row in found["kpis"]:
        doc.append("custom_kpis", {"perspective": _perspective(row["perspective"]), "kpi": row["kpi"],
                                   "timing": row["timing"] if row["timing"] in rules.TIMINGS else None})
    doc.set("custom_competencies", [])
    for row in found["competencies"]:
        doc.append("custom_competencies", {"competency": _competency(row["competency"], row.get("indicators"),
                                                                     row.get("weight")),
                                           "indicators": row.get("indicators"), "weight": flt(row["weight"])})
    problems = rules.template_errors({
        "designation": designation,
        "perspectives": [row.as_dict() for row in doc.custom_perspectives],
        "kpis": [row.as_dict() for row in doc.custom_kpis],
        "competencies": [row.as_dict() for row in doc.custom_competencies],
    })
    doc.custom_is_active = 1 if (activate and not problems) else 0
    doc.flags.ignore_permissions = True
    doc.save()
    return doc.name, not existing, problems


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
    name = " ".join(str(role or "").split())
    if not frappe.db.exists("Designation", name):
        frappe.get_doc({"doctype": "Designation", "designation_name": name}).insert(ignore_permissions=True)
    return name


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
