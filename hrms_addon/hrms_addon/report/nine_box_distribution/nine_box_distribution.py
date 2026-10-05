# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Nine-Box Distribution (test cases 6 and 10): how a review's people
spread over the nine cells, by plant, department and grade — the top talent,
the core and those needing attention — with who is in each. It names where
people sit, so it is for HR and the Talent Council."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_reports, talent_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    review = filters.get("talent_review") or talent_reports.latest_review()
    conditions = {"talent_review": review, "docstatus": ["<", 2]}
    for field in ("branch", "department", "grade"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    placed = frappe.get_list("Talent Placement", filters=conditions, fields=["employee_name", "box"],
                             limit_page_length=0) if review else []
    board = rules.board(placed)
    rows = [{"box": cell["box"], "cell": _(cell["name"]), "people": len(cell["people"]),
             "share": rules.share(len(cell["people"]), board["total"]), "action": _(cell["action"]),
             "names": ", ".join(sorted(row.get("employee_name") or "" for row in cell["people"]))}
            for cell in reversed(board["cells"])]
    chart = {"data": {"labels": ["%d %s" % (cell["box"], _(cell["name"])) for cell in board["cells"]],
                      "datasets": [{"name": _("People"), "values": [len(cell["people"]) for cell in board["cells"]]}]},
             "type": "bar", "colors": ["#14395E"]}
    summary = [
        {"value": board["strips"]["top"], "label": _("Top talent"), "datatype": "Int", "indicator": "Green"},
        {"value": board["strips"]["core"], "label": _("Core"), "datatype": "Int", "indicator": "Blue"},
        {"value": board["strips"]["attention"], "label": _("Needs attention"), "datatype": "Int",
         "indicator": "Red"},
        {"value": len(board["unplaced"]), "label": _("Not placed yet"), "datatype": "Int", "indicator": "Grey"},
    ]
    return columns(), rows, None, chart, summary


def columns():
    return [
        {"label": _("Box"), "fieldname": "box", "fieldtype": "Int", "width": 60},
        {"label": _("Cell"), "fieldname": "cell", "fieldtype": "Data", "width": 160},
        {"label": _("People"), "fieldname": "people", "fieldtype": "Int", "width": 80},
        {"label": _("Share"), "fieldname": "share", "fieldtype": "Percent", "width": 90},
        {"label": _("What to Do"), "fieldname": "action", "fieldtype": "Data", "width": 240},
        {"label": _("Who"), "fieldname": "names", "fieldtype": "Data", "width": 420},
    ]
