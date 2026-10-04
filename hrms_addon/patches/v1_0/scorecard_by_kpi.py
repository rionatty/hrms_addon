# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The scorecard weighed and scored KPI by KPI, four quarters a year, on a
site that already has templates and appraisals (Luuka, 4 Oct 2026).

1. The fields this writes exist first: fixtures are synced only after every
   patch has run.
2. Each scorecard template weighed a perspective once, on its first KPI: the
   weight is shared out between the perspective's KPIs, evenly to the
   hundredth (bsc_rules.spread_weights), so every perspective still weighs
   what it did. HR sets each KPI's own weight from there.
3. Every appraisal gets its quarter: the plan's, else the scorecard's old
   period (its "Annual" was the year's last column, now the fourth quarter),
   else the quarter its period starts in.
4. Each scorecard appraisal is scored KPI by KPI. A perspective's percentage
   for a quarter becomes each of its KPIs' (an annual score out of ten, ten
   times it, for Q4), so every perspective, section and overall scores what
   it did; each KPI's comments go to its quarter, and the employee's own
   figure to each of its KPIs the same way. The perspectives are then drawn
   from the KPIs. An appraisal already submitted keeps the totals it was
   submitted with.
5. Every appraisal gets its Results This Year and its year to date, and
   says whether the employee is on an improvement plan.
6. The scorecard's own period field is deleted: the quarter replaces it.

Everything is written straight to the database, so nothing is refused by a
check that did not exist when the records were made. Safe to run twice.
"""

import frappe
from frappe.utils import flt, getdate
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import appraisal_approval as approval, appraisals, bsc, bsc_rules, pip_rules, pips

TEMPLATE = "Appraisal Template"
OLD_PERIOD = "Appraisal-custom_period"
# what the scorecard's perspective rows held before October 2026
OLD_PERSPECTIVE = ("perspective", "weight", "self_score", "q1_percent", "q2_percent", "q3_percent", "annual_score")


def execute():
    sync_fixtures("hrms_addon")
    for doctype in ("Appraisal", TEMPLATE, "BSC Appraisal KPI", "BSC Appraisal Perspective",
                    "Appraisal Quarter Result"):
        frappe.clear_cache(doctype=doctype)
    for name in frappe.get_all(TEMPLATE, filters={"custom_form_type": bsc_rules.FORM_BSC}, pluck="name"):
        _template(name)
    names = frappe.get_all("Appraisal", filters={"docstatus": ["!=", 2]}, pluck="name",
                           order_by="employee asc, start_date asc, creation asc")
    for name in names:
        _quarter_and_kpis(name)
    # the quarters are all in place: each appraisal reads its earlier ones
    for name in names:
        _year(name)
    for employee in set(frappe.get_all("Performance Improvement Plan", filters={
            "docstatus": 0, "status": ["in", list(pip_rules.OPEN)]}, pluck="employee")):
        pips.mark_appraisals(employee)
    if frappe.db.exists("Custom Field", OLD_PERIOD):
        frappe.delete_doc("Custom Field", "Appraisal-custom_period", ignore_permissions=True, force=True)
    frappe.clear_cache(doctype="Appraisal")


def _template(name):
    """The template's KPIs weighed one by one, its perspectives drawn from them."""
    doc = frappe.get_doc(TEMPLATE, name)
    rows = doc.get("custom_kpis") or []
    if not rows:
        return
    shared = bsc_rules.spread_weights([{"perspective": row.perspective, "weight": row.get("weight")} for row in rows])
    for row, found in zip(rows, shared):
        row.weight = found["weight"]
    bsc._arrange_kpis(doc)
    doc.custom_objectives_weight = round(sum(flt(row.weight) for row in doc.get("custom_kpis") or []), 2)
    _write(doc, ("custom_kpis", "custom_perspectives"))


def _quarter_and_kpis(name):
    doc = frappe.get_doc("Appraisal", name)
    old_period = _old_period(name)
    if doc.get("custom_quarter") not in bsc_rules.QUARTERS:
        if old_period in bsc_rules.QUARTERS:
            doc.custom_quarter = old_period
        elif old_period == bsc_rules.ANNUAL:
            doc.custom_quarter = bsc_rules.QUARTERS[-1]
        elif doc.get("start_date"):
            doc.custom_quarter = bsc_rules.quarter_of(getdate(doc.start_date).month)
    if doc.get("custom_form_type") == approval.FORM_BSC:
        _kpis(doc, old_period)
    _write(doc, ("custom_bsc_kpis", "custom_bsc_perspectives"))


def _kpis(doc, old_period):
    """The appraisal's KPIs carrying their weights and what its perspectives
    recorded."""
    perspectives = _old_perspectives(doc.name)
    if not doc.get("custom_bsc_kpis") and doc.get("appraisal_template"):
        bsc.fill(doc, doc.appraisal_template)
    kpis = doc.get("custom_bsc_kpis") or []
    if not kpis:
        return
    weights = _template_weights(doc.get("appraisal_template"))
    shared = bsc_rules.spread_weights([
        {"perspective": row.perspective,
         "weight": flt((perspectives.get(row.perspective) or {}).get("weight")) if index == _first(kpis, row) else None}
        for index, row in enumerate(kpis)])
    comments = _old_comments(doc.name)
    annual = old_period == bsc_rules.ANNUAL
    for row, fallback in zip(kpis, shared):
        if not row.get("weight"):
            row.weight = weights.get((row.perspective, bsc._plain(row.kpi)), fallback["weight"])
        recorded = perspectives.get(row.perspective) or {}
        for quarter in bsc_rules.QUARTERS[:3]:
            if row.get(bsc_rules.percent_field(quarter)) in (None, "") and recorded.get(quarter.lower() + "_percent") \
                    not in (None, ""):
                row.set(bsc_rules.percent_field(quarter), flt(recorded[quarter.lower() + "_percent"]))
        q4 = bsc_rules.percent_field(bsc_rules.QUARTERS[-1])
        if row.get(q4) in (None, "") and recorded.get("annual_score") not in (None, ""):
            row.set(q4, round(flt(recorded["annual_score"]) * 10, 2))
        if row.get("self_percent") in (None, "") and recorded.get("self_score") not in (None, ""):
            row.self_percent = round(flt(recorded["self_score"]) * (10 if annual else 1), 2)
        said = comments.get((row.perspective, bsc._plain(row.kpi)))
        field = bsc_rules.comments_field(doc.custom_quarter) if doc.get("custom_quarter") in bsc_rules.QUARTERS \
            else None
        if said and field and not row.get(field):
            row.set(field, said)
    if doc.docstatus == 0:
        bsc.score(doc)
        appraisals._carry_scores(doc, doc.get("custom_bsc_overall"), doc.get("custom_bsc_band"))
    else:
        # submitted: the KPIs and perspectives drawn, the totals as submitted
        for row in kpis:
            for quarter in bsc_rules.QUARTERS:
                row.set(bsc_rules.score_field(quarter),
                        bsc_rules.quarter_score(row.weight, row.get(bsc_rules.percent_field(quarter))))
            row.score = row.get(bsc_rules.score_field(doc.custom_quarter)) \
                if doc.get("custom_quarter") in bsc_rules.QUARTERS else None
        bsc.summarise(doc)


def _year(name):
    doc = frappe.get_doc("Appraisal", name)
    if doc.docstatus == 0 and doc.get("custom_form_type") == approval.FORM_BSC:
        appraisals._carry_earlier_quarters(doc)
        bsc.score(doc)
        appraisals._carry_scores(doc, doc.get("custom_bsc_overall"), doc.get("custom_bsc_band"))
    appraisals._year_so_far(doc)
    appraisals._mark_pip(doc)
    _write(doc, ("custom_bsc_kpis", "custom_bsc_perspectives", "custom_quarter_results"))


def _write(doc, tables):
    """The record and these tables as they stand, without its checks."""
    for table in tables:
        for row in doc.get(table) or []:
            row.docstatus = doc.docstatus
    doc.db_update()
    for table in tables:
        if doc.meta.get_field(table):
            doc.update_child_table(table)


def _first(rows, row):
    """The index of the first KPI of `row`'s perspective."""
    return next(index for index, other in enumerate(rows) if other.perspective == row.perspective)


def _template_weights(template):
    if not template or not frappe.db.exists(TEMPLATE, template):
        return {}
    return {(row.perspective, bsc._plain(row.kpi)): flt(row.weight)
            for row in frappe.get_all("BSC Template KPI", filters={"parent": template, "parenttype": TEMPLATE},
                                      fields=["perspective", "kpi", "weight"])}


def _old_period(name):
    if not frappe.db.has_column("Appraisal", "custom_period"):
        return None
    return frappe.db.get_value("Appraisal", name, "custom_period")


def _old_perspectives(name):
    """{perspective: what its row held} before October 2026; nothing where
    the old columns are gone (a site made after it)."""
    columns = [column for column in OLD_PERSPECTIVE if frappe.db.has_column("BSC Appraisal Perspective", column)]
    if "perspective" not in columns or len(columns) == 2:
        return {}
    rows = frappe.db.sql("select {0} from `tabBSC Appraisal Perspective` where parent=%s and parenttype='Appraisal'"
                         .format(", ".join("`%s`" % column for column in columns)), name, as_dict=True)
    return {row.perspective: row for row in rows}


def _old_comments(name):
    if not frappe.db.has_column("BSC Appraisal KPI", "comments"):
        return {}
    return {(row.perspective, bsc._plain(row.kpi)): row.comments for row in frappe.db.sql(
        "select perspective, kpi, comments from `tabBSC Appraisal KPI` where parent=%s and parenttype='Appraisal' "
        "and ifnull(comments, '') != ''", name, as_dict=True)}
