# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Skills Matrix (the plant's Skills Matrix sheet): each employee of a plant or
section against each skill assessed there, their level coloured by where they
stand: competent, a gap, a certificate needed, a reassessment due. Someone not
yet assessed in a skill shows nothing in it.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import competency, competency_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    skills = competency.skills_in(filters)
    people_filters = {"status": "Active"}
    for field, key in (("company", "company"), ("branch", "branch"), ("work_section", "custom_work_section")):
        if filters.get(field):
            people_filters[key] = filters.get(field)
    people = frappe.get_list("Employee", filters=people_filters, fields=["name", "employee_name", "designation"],
                             order_by="employee_name asc", limit_page_length=0)
    rows = competency.counting_rows(dict(filters, skill=None))
    found = rules.current(rows)
    data = []
    for person in people:
        line = {"employee": person.name, "employee_name": person.employee_name, "designation": person.designation,
                "_status": {}}
        competent = assessed = 0
        for skill in skills:
            row = found.get((person.name, skill.name))
            if not row:
                continue
            column = fieldname(skill.name)
            line[column] = rules.level_of(row.level)
            line["_status"][column] = row.status
            assessed += 1
            competent += row.status == rules.COMPETENT
        line["competent"] = round(100.0 * competent / assessed, 1) if assessed else None
        data.append(line)
    columns = [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 110},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "designation", "label": _("Job Title"), "fieldtype": "Link", "options": "Designation",
         "width": 140},
    ] + [{"fieldname": fieldname(skill.name), "label": skill.name + (" *" if skill.custom_critical else ""),
          "fieldtype": "Int", "width": 90} for skill in skills] + [
        {"fieldname": "competent", "label": _("Competent %"), "fieldtype": "Percent", "width": 100}]
    return columns, data, _("Levels 1 to 5. A skill marked * is critical.")


def fieldname(skill):
    return "skill_" + frappe.scrub(skill)
