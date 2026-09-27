# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Applicant Screening: every applicant's screening as it is kept on them
(cv_screening.py), the best first, for one opening or all the open ones.
HR ticks applicants and sets their status in one go (Set Status), or has an
opening's applicants screened again (Screen Again); the report's own export
gives it to Excel. The ordering is cv_screening_rules.sort_key, the same as
the Interview Shortlist's."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import cv_screening_rules as rules

FIELDS = ["name", "applicant_name", "job_title", "status", "creation", "custom_employee", "custom_screened_on",
          *rules.STORED]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    if filters.get("job_opening"):
        conditions.append(["job_title", "=", filters.get("job_opening")])
    else:
        opened = frappe.get_all("Job Opening", filters={"status": "Open"}, pluck="name")
        conditions.append(["job_title", "in", opened or [""]])
    if filters.get("status"):
        conditions.append(["status", "=", filters.get("status")])
    if filters.get("from_date"):
        conditions.append(["creation", ">=", filters.get("from_date")])
    if filters.get("to_date"):
        conditions.append(["creation", "<=", "%s 23:59:59" % filters.get("to_date")])
    data = []
    for row in frappe.get_all("Job Applicant", filters=conditions, fields=FIELDS):
        line = screening_line(row)
        if filters.get("result") and line["screening_result"] != filters.get("result"):
            continue
        if filters.get("min_score") and (line["match_score"] is None
                                         or float(line["match_score"]) < float(filters.get("min_score"))):
            continue
        data.append(line)
    data.sort(key=rules.sort_key)
    counts = {result: sum(1 for line in data if line["screening_result"] == result)
              for result in rules.RESULTS + (rules.NOT_CHECKED,)}
    summary = [{"value": counts[result], "label": _(result), "datatype": "Int", "indicator": colour}
               for result, colour in zip(rules.RESULTS + (rules.NOT_CHECKED,), ("Green", "Orange", "Red", "Grey"))]
    return columns(), data, None, None, summary


def screening_line(row):
    """One applicant as the report lists them. An applicant nothing could be
    checked for has no match: the database keeps a nought for it."""
    result = row.get("custom_screening_result") or rules.NOT_CHECKED
    return {
        "job_applicant": row.get("name"),
        "applicant_name": row.get("applicant_name"),
        "job_opening": row.get("job_title"),
        "status": row.get("status"),
        "match_score": None if result == rules.NOT_CHECKED else row.get("custom_match_score"),
        "screening_result": result,
        "experience_years": row.get("custom_experience_years"),
        "matched": row.get("custom_screening_matched"),
        "missing": row.get("custom_screening_missing"),
        "to_check": row.get("custom_screening_to_check"),
        "flags": row.get("custom_screening_flags"),
        "employee": row.get("custom_employee"),
        "applied_on": str(row.get("creation"))[:10] if row.get("creation") else None,
        "screened_on": row.get("custom_screened_on"),
    }


def columns():
    return [
        {"fieldname": "job_applicant", "label": _("Job Applicant"), "fieldtype": "Link", "options": "Job Applicant",
         "width": 150},
        {"fieldname": "applicant_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "job_opening", "label": _("Job Opening"), "fieldtype": "Link", "options": "Job Opening",
         "width": 170},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "match_score", "label": _("Match"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "screening_result", "label": _("Result"), "fieldtype": "Data", "width": 140},
        {"fieldname": "experience_years", "label": _("Years of Experience"), "fieldtype": "Float", "width": 100},
        {"fieldname": "matched", "label": _("Matched"), "fieldtype": "Small Text", "width": 220},
        {"fieldname": "missing", "label": _("Missing"), "fieldtype": "Small Text", "width": 220},
        {"fieldname": "to_check", "label": _("Check by Hand"), "fieldtype": "Small Text", "width": 180},
        {"fieldname": "flags", "label": _("Flags"), "fieldtype": "Small Text", "width": 220},
        {"fieldname": "employee", "label": _("Current Employee"), "fieldtype": "Link", "options": "Employee",
         "width": 130},
        {"fieldname": "applied_on", "label": _("Applied On"), "fieldtype": "Date", "width": 105},
        {"fieldname": "screened_on", "label": _("Screened On"), "fieldtype": "Datetime", "width": 150},
    ]
