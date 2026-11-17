# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Matrix (LMS blueprint section 4): how much of what the Training
Rules ask is done, plant by department by job title by employee, a column
for each training category. A cell is the share of the requirements there
that are done and still count, coloured by the Learning Settings' bands;
clicking it opens those requirements. What somebody recommended is not
counted: it is a development need, not a requirement.

It reads through Frappe's permissions, so a plant's HR Officer sees that
plant.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import learning, learning_rules as rules

# the drill-down, top to bottom: plant, department, job title, employee
LEVELS = ("branch", "department", "designation", "employee")
DEPTHS = {"Plant": 1, "Department": 2, "Job Title": 3, "Employee": 4}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    s, day = learning.settings(), getdate(today())
    categories = frappe.get_all("Training Category", fields=["name"], order_by="matrix_order asc, name asc",
                                pluck="name")
    conditions = {"status": ["!=", rules.NOT_APPLICABLE], "requirement_type": ["!=", rules.RECOMMENDED]}
    for field in ("company", "branch", "department", "designation"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    rows = frappe.get_list("Employee Training Requirement", filters=conditions,
                           fields=["employee", "employee_name", "branch", "department", "designation",
                                   "training_category", "status", "requirement_type", "completed_on",
                                   "valid_until"], limit_page_length=0)
    depth = DEPTHS.get(filters.get("down_to") or "Employee", 4)
    data = tree(rows, categories, depth, s, day)
    return columns(categories), data, None, None, summary(rows, day)


def tree(rows, categories, depth, s, day):
    """The rows of the matrix: each plant, then each department under it, and
    so on down to `depth` levels, each with its counts and its cells."""
    groups = {}
    for row in rows:
        path = ()
        for field in LEVELS[:depth]:
            path += (row.get(field) or "",)
            groups.setdefault(path, []).append(row)
    names = {fieldname(category): category for category in categories}
    data = []
    for path in sorted(groups):
        level = len(path) - 1
        field = LEVELS[level]
        members = groups[path]
        label = path[-1] or _("Not set")
        if field == "employee" and members:
            label = "%s: %s" % (path[-1], members[0].get("employee_name") or "")
        done, required = rules.coverage_of(members, day)
        item = {
            "id": "/".join(path), "parent_id": "/".join(path[:-1]) if level else None, "indent": level,
            "name": label, "employees": len({row.employee for row in members}),
            "overall": rules.percent(done, required),
            "overdue": sum(1 for row in members if row.status == rules.OVERDUE),
            "_filters": {LEVELS[index]: value for index, value in enumerate(path) if value},
            "_heat": {}, "_categories": names,
        }
        item["_heat"]["overall"] = rules.heat(item["overall"], s)
        for category in categories:
            cell = rules.percent(*rules.coverage_of(
                [row for row in members if row.training_category == category], day))
            key = fieldname(category)
            item[key] = cell
            item["_heat"][key] = rules.heat(cell, s)
        data.append(item)
    return data


def fieldname(category):
    return "category_" + frappe.scrub(category)


def columns(categories):
    out = [
        {"fieldname": "name", "label": _("Plant / Department / Job Title / Employee"), "fieldtype": "Data",
         "width": 300},
        {"fieldname": "employees", "label": _("Employees"), "fieldtype": "Int", "width": 90},
    ]
    for category in categories:
        out.append({"fieldname": fieldname(category), "label": _(category), "fieldtype": "Percent", "width": 105})
    out += [
        {"fieldname": "overall", "label": _("All Required"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "overdue", "label": _("Overdue"), "fieldtype": "Int", "width": 85},
    ]
    return out


def summary(rows, day):
    done, required = rules.coverage_of(rows, day)
    overall = rules.percent(done, required)
    return [
        {"label": _("Employees"), "value": len({row.employee for row in rows}), "datatype": "Int"},
        {"label": _("Required Done"), "value": overall if overall is not None else 0, "datatype": "Percent",
         "indicator": "Green" if (overall or 0) >= 85 else "Orange" if (overall or 0) >= 65 else "Red"},
        {"label": _("Overdue"), "value": sum(1 for row in rows if row.status == rules.OVERDUE), "datatype": "Int",
         "indicator": "Red"},
    ]
