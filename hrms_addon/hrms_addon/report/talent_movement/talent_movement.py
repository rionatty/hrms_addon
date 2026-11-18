# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent Movement (the talent blueprint, section 10: "box changes cycle on
cycle"): where each person sat in one talent review and where they sit in
the next, and which way they moved. Up where neither performance nor
potential fell and one rose, Down where neither rose and one fell, Across
where one rose and the other fell; New with no earlier box, Not Placed with
no later one. It names where people sit, so it is for HR and the Talent
Council."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_masters, talent_reports, talent_rules as rules

FIELDS = ["employee", "employee_name", "branch", "department", "designation", "box", "performance_band",
          "potential_band"]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    later = filters.get("talent_review") or talent_reports.latest_review()
    earlier = filters.get("compared_with") or review_before(later)
    names = {cell["box"]: cell["name"] for cell in talent_masters.grid()["boxes"].values()}
    now, was = _placed(later, filters), _placed(earlier, filters)
    data = []
    for employee in sorted(set(now) | set(was), key=lambda key: (now.get(key) or was.get(key)).employee_name or ""):
        after, before = now.get(employee), was.get(employee)
        moved = rules.box_movement(before.box if before else None, after.box if after else None)
        if not moved or (filters.get("movement") and moved != filters.get("movement")):
            continue
        if filters.get("from_box") not in (None, "") and int(filters.get("from_box") or 0) != int(
                (before.box if before else 0) or 0):
            continue
        if filters.get("to_box") not in (None, "") and int(filters.get("to_box") or 0) != int(
                (after.box if after else 0) or 0):
            continue
        row = after or before
        data.append({
            "employee": employee, "employee_name": row.employee_name, "branch": row.branch,
            "department": row.department, "designation": row.designation,
            "was": _box(before, names), "now": _box(after, names), "movement": moved,
            "performance": _change(before, after, "performance_band"),
            "potential": _change(before, after, "potential_band"),
        })
    counts = {kind: sum(1 for row in data if row["movement"] == kind)
              for kind in (rules.UP, rules.DOWN, rules.ACROSS, rules.SAME, rules.NEW, rules.OUT)}
    chart = {"data": {"labels": [_(kind) for kind in counts], "datasets": [{"name": _("People"),
                                                                            "values": list(counts.values())}]},
             "type": "bar", "colors": ["#14395E"]}
    summary = [{"value": value, "label": _(kind), "datatype": "Int",
                "indicator": {rules.UP: "Green", rules.DOWN: "Red", rules.ACROSS: "Orange"}.get(kind, "Grey")}
               for kind, value in counts.items()]
    message = _("{0} compared with {1}.").format(later or _("No review"), earlier or _("no earlier review"))
    return columns(), data, message, chart, summary


def review_before(review):
    """The review before this one: the latest of an earlier year."""
    if not review:
        return None
    year = frappe.db.get_value("Talent Review", review, "review_year")
    found = frappe.get_all("Talent Review", filters={"name": ["!=", review], "review_year": ["<", year or 0]},
                           order_by="review_year desc, opens_on desc", limit=1, pluck="name")
    return found[0] if found else None


def _placed(review, filters):
    if not review:
        return {}
    conditions = {"talent_review": review, "docstatus": ["<", 2]}
    for field in ("branch", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    return {row.employee: row for row in frappe.get_list("Talent Placement", filters=conditions, fields=FIELDS,
                                                         limit_page_length=0)}


def _box(row, names):
    if not row or not row.box:
        return None
    return "%s %s" % (row.box, _(names.get(int(row.box), "")))


def _change(before, after, field):
    was, now = (before or {}).get(field), (after or {}).get(field)
    if was == now:
        return _(now) if now else None
    return "%s → %s" % (_(was) if was else "–", _(now) if now else "–")


def columns():
    return [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"fieldname": "designation", "label": _("Job Title"), "fieldtype": "Link", "options": "Designation",
         "width": 140},
        {"fieldname": "was", "label": _("Was"), "fieldtype": "Data", "width": 150},
        {"fieldname": "now", "label": _("Now"), "fieldtype": "Data", "width": 150},
        {"fieldname": "movement", "label": _("Movement"), "fieldtype": "Data", "width": 100},
        {"fieldname": "performance", "label": _("Performance"), "fieldtype": "Data", "width": 150},
        {"fieldname": "potential", "label": _("Potential"), "fieldtype": "Data", "width": 150},
    ]
