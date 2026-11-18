# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Skills Cover (the workbook's critical skills cover): each skill of a plant or
section, how many people are assessed in it and how many are competent, and
what that cover is: none, a single point of failure, thin, or enough for the
people needed on every shift. Cross-train where it is thin.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import competency, competency_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if filters.get("view") == "Plant and Shift":
        return by_shift(filters)
    s = competency.settings()
    skills = competency.skills_in(filters)
    found = rules.current(competency.counting_rows(dict(filters, skill=None)))
    by_skill = {}
    for (employee, skill), row in found.items():
        by_skill.setdefault(skill, []).append(row)
    data = []
    for skill in skills:
        rows = by_skill.get(skill.name, [])
        competent = [row for row in rows if row.status == rules.COMPETENT]
        data.append({"skill": skill.name, "skill_type": skill.custom_skill_type, "branch": skill.custom_branch,
                     "work_section": skill.custom_work_section, "critical": skill.custom_critical,
                     "assessed": len(rows), "competent": len(competent),
                     "cover": rules.cover(len(competent) if rows else None, s),
                     "people": ", ".join(sorted(row.employee_name or row.employee for row in competent))})
    if filters.get("critical_only"):
        data = [row for row in data if row["critical"]]
    order = {name: index for index, name in enumerate(rules.COVERS)}
    data.sort(key=lambda row: (order[row["cover"]], not row["critical"], row["skill"]))
    columns = [
        {"fieldname": "skill", "label": _("Skill"), "fieldtype": "Link", "options": "Skill", "width": 180},
        {"fieldname": "skill_type", "label": _("Type"), "fieldtype": "Data", "width": 120},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 100},
        {"fieldname": "work_section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section",
         "width": 150},
        {"fieldname": "critical", "label": _("Critical"), "fieldtype": "Check", "width": 70},
        {"fieldname": "assessed", "label": _("Assessed"), "fieldtype": "Int", "width": 80},
        {"fieldname": "competent", "label": _("Competent"), "fieldtype": "Int", "width": 90},
        {"fieldname": "cover", "label": _("Cover"), "fieldtype": "Data", "width": 170},
        {"fieldname": "people", "label": _("Competent People"), "fieldtype": "Data", "width": 300},
    ]
    summary = [{"value": sum(1 for row in data if row["cover"] == name), "label": _(name), "datatype": "Int",
                "indicator": {"No Cover": "Red", "Single Point of Failure": "Red", "Thin": "Orange"}.get(name, "Green")}
               for name in (rules.NO_COVER, rules.SINGLE, rules.THIN, rules.OK)]
    return columns, data, None, None, summary


def by_shift(filters):
    """Each skill in each plant: the competent people on each of today's
    shifts against those needed (the skill's own number, else the settings',
    never more than its section's crew)."""
    skills = competency.skills_in(filters)
    if filters.get("critical_only"):
        skills = [skill for skill in skills if skill.custom_critical]
    found = competency.cover_by_shift([skill.name for skill in skills], filters.get("branch"))
    shifts = sorted({shift for row in found for shift in row["by_shift"] if shift})
    data = []
    for row in found:
        line = {"skill": row["skill"], "branch": row["branch"], "critical": row["critical"], "need": row["need"],
                "cover": row["status"], "short": ", ".join(row["short"])}
        for index, shift in enumerate(shifts):
            line["shift_%d" % index] = row["by_shift"].get(shift, 0)
        data.append(line)
    order = {name: index for index, name in enumerate(rules.COVERS)}
    data.sort(key=lambda row: (order[row["cover"]], not row["critical"], row["skill"], row["branch"]))
    columns = [
        {"fieldname": "skill", "label": _("Skill"), "fieldtype": "Link", "options": "Skill", "width": 180},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 100},
        {"fieldname": "critical", "label": _("Critical"), "fieldtype": "Check", "width": 70},
        {"fieldname": "need", "label": _("Needed per Shift"), "fieldtype": "Int", "width": 120},
    ] + [{"fieldname": "shift_%d" % index, "label": shift, "fieldtype": "Int", "width": 100}
         for index, shift in enumerate(shifts)] + [
        {"fieldname": "cover", "label": _("Cover"), "fieldtype": "Data", "width": 170},
        {"fieldname": "short", "label": _("Short On"), "fieldtype": "Data", "width": 160},
    ]
    return columns, data
