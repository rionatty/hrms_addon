# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Effectiveness (LMS blueprint, section 4.5): Kirkpatrick's four
levels for each programme's sessions in the period. Reaction is the
evaluation forms' score; learning the share of those assessed who passed;
behaviour the supervisors' application reviews; results the KPIs measured
before and after and how many improved.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from hrms_addon.hrms_addon import learning_delivery_rules as rules, learning_sheets_rules as sheets_rules, training_rules
from hrms_addon.hrms_addon.learning_delivery import IMPACT, REVIEW


def execute(filters=None):
    filters = frappe._dict(filters or {})
    events = sessions(filters)
    names = [event.name for event in events] or [""]
    present = {}
    for row in frappe.get_all("Training Event Employee", filters={"parenttype": "Training Event", "parent": ["in", names],
                                                                 "attendance": "Present"}, fields=["parent"]):
        present[row.parent] = present.get(row.parent, 0) + 1
    results = frappe.get_all("Training Result", filters={"docstatus": 1, "training_event": ["in", names]},
                             fields=["name", "training_event"])
    result_event = {row.name: row.training_event for row in results}
    marks = frappe.get_all("Training Result Employee", filters={"parenttype": "Training Result",
                                                                "parent": ["in", list(result_event) or [""]]},
                           fields=["parent", "custom_effective", "custom_marks", "custom_pre_test"])
    reviews = frappe.get_all(REVIEW, filters={"training_event": ["in", names]},
                             fields=["training_event", "status", "score", "applied"])
    impacts = frappe.get_all(IMPACT, filters={"training_event": ["in", names]}, fields=["training_event", "result",
                                                                                        "benefit", "weight"])
    programme_of = {event.name: event.training_program or _("No Programme") for event in events}
    grouped = {}
    for event in events:
        group = grouped.setdefault(programme_of[event.name], {"events": [], "results": [], "reviews": [],
                                                               "impacts": [], "benefit": 0.0})
        group["events"].append({"present": present.get(event.name, 0),
                                "evaluation_score": event.custom_evaluation_score})
    for row in marks:
        grouped[programme_of[result_event[row.parent]]]["results"].append({"effective": row.custom_effective})
        if row.custom_effective:
            grouped[programme_of[result_event[row.parent]]].setdefault("tests", []).append(
                {"pre": row.custom_pre_test if row.custom_pre_test not in (None, "") and row.custom_pre_test else None,
                 "post": row.custom_marks, "passed": row.custom_effective == training_rules.EFFECTIVE})
    for row in reviews:
        grouped[programme_of[row.training_event]]["reviews"].append(row)
    for row in impacts:
        grouped[programme_of[row.training_event]]["impacts"].append(row)
        grouped[programme_of[row.training_event]]["benefit"] += row.benefit or 0
    data = []
    for programme in sorted(grouped):
        group = grouped[programme]
        found = rules.effectiveness(group["events"], group["results"], group["reviews"], group["impacts"],
                                    training_rules.EFFECTIVE)
        tests = sheets_rules.learning_figures(group.get("tests") or [])
        data.append(dict(found, programme=programme, benefit=group["benefit"], pre_test=tests["pre_test"],
                         post_test=tests["post_test"], gain=tests["gain"],
                         impact_share=rules.impact_share(group["impacts"])))
    return columns(), data


def sessions(filters):
    """The sessions held in the period: submitted, not cancelled, started in it."""
    conditions = {"docstatus": 1, "event_status": ["!=", "Cancelled"],
                  "start_time": ["between", [str(getdate(filters.get("from_date"))) + " 00:00:00",
                                             str(getdate(filters.get("to_date"))) + " 23:59:59"]]}
    if filters.get("company"):
        conditions["company"] = filters.get("company")
    if filters.get("branch"):
        conditions["custom_branch"] = filters.get("branch")
    if filters.get("training_program"):
        conditions["training_program"] = filters.get("training_program")
    return frappe.get_list("Training Event", filters=conditions, limit_page_length=0, order_by="start_time asc",
                           fields=["name", "event_name", "training_program", "start_time", "end_time",
                                   "custom_branch", "custom_evaluation_score"])


def columns():
    return [
        {"fieldname": "programme", "label": _("Training Program"), "fieldtype": "Data", "width": 200},
        {"fieldname": "sessions", "label": _("Sessions"), "fieldtype": "Int", "width": 80},
        {"fieldname": "trainees", "label": _("Trainees"), "fieldtype": "Int", "width": 80},
        {"fieldname": "reaction", "label": _("1 Reaction %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "assessed", "label": _("2 Assessed"), "fieldtype": "Int", "width": 90},
        {"fieldname": "pass_rate", "label": _("2 Pass Rate %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "pre_test", "label": _("2 Pre-Test %"), "fieldtype": "Percent", "width": 105},
        {"fieldname": "post_test", "label": _("2 Post-Test %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "gain", "label": _("2 Knowledge Gain"), "fieldtype": "Float", "precision": 1, "width": 120},
        {"fieldname": "reviews_done", "label": _("3 Reviews Done"), "fieldtype": "Int", "width": 110},
        {"fieldname": "reviews", "label": _("3 Reviews Raised"), "fieldtype": "Int", "width": 110},
        {"fieldname": "application", "label": _("3 Application Score"), "fieldtype": "Percent", "width": 130},
        {"fieldname": "applied_rate", "label": _("3 Applied %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "kpis", "label": _("4 KPIs Measured"), "fieldtype": "Int", "width": 110},
        {"fieldname": "kpis_improved", "label": _("4 KPIs Improved"), "fieldtype": "Int", "width": 110},
        {"fieldname": "impact_share", "label": _("4 Weighted Improvement %"), "fieldtype": "Percent", "width": 150},
        {"fieldname": "benefit", "label": _("4 Benefit"), "fieldtype": "Currency", "width": 140},
    ]
