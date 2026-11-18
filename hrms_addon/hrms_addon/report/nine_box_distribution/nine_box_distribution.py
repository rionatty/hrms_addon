# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Nine-Box Distribution (test cases 6 and 10; the talent blueprint,
section 10: "Headcount per box by plant and department"): how a review's
people spread over the nine boxes, counted in SQL, each box against the
distribution guide and against the review before, and split by plant or by
department side by side. It names where people sit, so it is for HR and the
Talent Council."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_command, talent_command_rules, talent_masters, talent_reports


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    review = filters.get("talent_review") or talent_reports.latest_review()
    before = filters.get("compared_with") or talent_command.review_before(review)
    by = "department" if filters.get("split_by") == "Department" else "branch"
    parts, values = ["p.docstatus < 2", "p.box between 1 and 9"], {}
    for field in ("branch", "department", "grade", "company"):
        if filters.get(field):
            parts.append("p.%s = %%(%s)s" % (field, field))
            values[field] = filters.get(field)
    plants = talent_command.scope()
    if plants:
        parts.append("p.branch in %(plants)s")
        values["plants"] = plants
    where = " and ".join(parts)

    def grouped(which):
        if not which:
            return []
        return frappe.db.sql("""select p.{by} as grp, p.box, count(*) as n from `tabTalent Placement` p
                                where p.talent_review = %(review)s and {where} group by p.{by}, p.box""".format(
            by=by, where=where), dict(values, review=which), as_dict=True)

    groups = talent_command_rules.side_by_side(grouped(review), grouped(before), talent_masters.guide())
    grid = talent_masters.grid()
    names = {cell["box"]: cell["name"] for cell in grid["boxes"].values()}
    actions = {cell["box"]: cell["action"] for cell in grid["boxes"].values()}
    company = groups[0] if groups else {"boxes": [], "total": 0}
    plants = groups[1:]
    plants_shown = plants[:6]
    rows = []
    for row in reversed(company["boxes"]):
        line = {"box": row["box"], "cell": _(names.get(row["box"], "")), "people": row["n"], "share": row["share"],
                "guide": row["guide"], "variance": row["variance"], "last_share": row["last_share"],
                "action": _(actions.get(row["box"], ""))}
        for number, group in enumerate(plants_shown):
            line["group_%d" % number] = next(item["share"] for item in group["boxes"] if item["box"] == row["box"])
        rows.append(line)
    chart = {"data": {"labels": ["%d %s" % (box, _(names.get(box, ""))) for box in range(1, 10)],
                      "datasets": [{"name": _("This review"), "values": [row["share"] for row in company["boxes"]]},
                                   {"name": _("Guide"), "values": [row["guide"] or 0 for row in company["boxes"]]}]},
             "type": "bar", "colors": ["#14395E", "#E8A317"]}
    top = tuple(grid.get("top_talent") or ())
    summary = [
        {"value": company["total"], "label": _("Placed"), "datatype": "Int", "indicator": "Blue"},
        {"value": sum(row["n"] for row in company["boxes"] if row["box"] in top), "label": _("Top talent"),
         "datatype": "Int", "indicator": "Green"},
        {"value": len([row for row in company["boxes"] if row["variance"] is not None and abs(row["variance"]) > 5]),
         "label": _("Boxes off the guide"), "datatype": "Int", "indicator": "Orange"},
    ]
    return columns(plants_shown), rows, _("Compared with {0}.").format(before) if before else None, chart, summary


def columns(groups=()):
    return [
        {"label": _("Box"), "fieldname": "box", "fieldtype": "Int", "width": 60},
        {"label": _("Cell"), "fieldname": "cell", "fieldtype": "Data", "width": 160},
        {"label": _("People"), "fieldname": "people", "fieldtype": "Int", "width": 80},
        {"label": _("Share"), "fieldname": "share", "fieldtype": "Percent", "width": 85},
        {"label": _("Guide"), "fieldname": "guide", "fieldtype": "Percent", "width": 80},
        {"label": _("Against the Guide"), "fieldname": "variance", "fieldtype": "Float", "width": 110},
        {"label": _("Review Before"), "fieldname": "last_share", "fieldtype": "Percent", "width": 110},
    ] + [{"label": group["group"], "fieldname": "group_%d" % number, "fieldtype": "Percent", "width": 110}
         for number, group in enumerate(groups)] + [
        {"label": _("What to Do"), "fieldname": "action", "fieldtype": "Data", "width": 240},
    ]
