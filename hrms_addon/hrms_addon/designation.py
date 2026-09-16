# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Designation (Job Title) — Job Description template.

The JD fields themselves are fixtures (Job Description tab). This enforces
the Key Result Area rules from jd_rules.py.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import jd_rules

TABLE = "custom_jd_key_result_areas"


def validate(doc, method=None):
    rows = doc.get(TABLE) or []
    _set_perspectives_from_kra(rows)
    errors = jd_rules.key_result_area_errors(rows) + jd_rules.jd_table_errors(
        doc.name or doc.get("designation_name"),
        doc.get("custom_jd_reports_to"),
        doc.get("custom_jd_reporting_lines"),
        doc.get("custom_jd_stakeholders"),
        doc.get("custom_jd_decision_authorities"),
        doc.get("custom_jd_planning_horizons"),
    )
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Key Result Areas"))


def _set_perspectives_from_kra(rows):
    """Each row's perspective, straight from its KRA.

    The form fetches it on pick, but that is the browser's copy: an API
    call or an import can send anything, and Frappe's own server-side
    fetch runs in link validation, not necessarily before this hook. The
    KRA master is the only authority on which perspective a KRA belongs to.
    """
    kras = sorted({row.kra for row in rows if row.get("kra")})
    if not kras:
        return
    perspective_of = dict(
        frappe.get_all("KRA", filters={"name": ["in", kras]}, fields=["name", "custom_perspective"], as_list=True)
    )
    for row in rows:
        if row.get("kra"):
            row.perspective = perspective_of.get(row.kra)
