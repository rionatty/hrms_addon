# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Report (Training, case 10): what the HR Officer downloads once a
training's evaluations are keyed in. Four views of the same trainings, the
same figures on top of each; the arithmetic is in training_rules.py (the
report's section), tested by scripts/verify_training_report.py.

The trainings are read with get_list, so an HR Officer kept to a plant sees
that plant's; what hangs off them (the people booked, the evaluations, the
results) is read for those trainings only. A training picked by name is shown
whatever the dates say. Talent Programmes Only keeps the sessions a
development plan's training was booked on, each with the people whose plan
it is (talent.sync_training keeps them on the plan).
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate

from hrms_addon.hrms_addon import training_rules as rules

EVENT_FIELDS = ["name", "training_program", "course", "custom_branch", "custom_department", "start_time", "end_time",
                "trainer_name", "docstatus", "event_status"]
QUESTION_FIELDS = ["custom_%s" % field for field, _question in rules.QUESTIONS]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    view = filters.get("view") if filters.get("view") in rules.VIEWS else rules.TRAININGS
    events = _events(filters)
    names = [event["name"] for event in events]
    participants, evaluations, results = _participants(names), _evaluations(names), _results(names)
    if filters.get("talent_only"):
        events, participants, evaluations, results = _talent_only(events, participants, evaluations, results)
    events, participants, evaluations, results = rules.narrow(
        events, participants, evaluations, results, filters.get("department"))
    trainings = rules.training_rows(events, participants, evaluations, results)
    if view == rules.PARTICIPANTS:
        rows = rules.participant_rows(events, participants, evaluations, results)
    elif view == rules.ITEMS:
        rows = rules.item_rows(evaluations, _items())
    elif view == rules.COMMENTS:
        rows = rules.comment_rows(events, evaluations, _questions(), _items())
    else:
        rows = trainings
    figures = rules.summary(trainings, participants, evaluations, results)
    summary = [{"value": value, "label": _(label), "datatype": datatype, "indicator": colour}
               for label, value, datatype, colour in rules.summary_cards(figures)]
    return columns(view), rows, None, rules.chart(view, trainings, rows), summary


def columns(view):
    return [{"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "options": options, "width": width}
            for fieldname, label, fieldtype, options, width in rules.REPORT_COLUMNS[view]]


def _events(filters):
    conditions = [["docstatus", "<", 2]]
    if filters.get("training_event"):
        conditions.append(["name", "=", filters.get("training_event")])
    else:
        if filters.get("from_date"):
            conditions.append(["start_time", ">=", str(getdate(filters.get("from_date")))])
        if filters.get("to_date"):
            conditions.append(["start_time", "<", str(add_days(getdate(filters.get("to_date")), 1))])
    for field, column in (("company", "company"), ("branch", "custom_branch"), ("training_program", "training_program")):
        if filters.get(field):
            conditions.append([column, "=", filters.get(field)])
    rows = frappe.get_list("Training Event", filters=conditions, fields=EVENT_FIELDS,
                           order_by="start_time asc, name asc", limit_page_length=0)
    return [{"name": row.name, "training_program": row.training_program or row.course, "branch": row.custom_branch,
             "department": row.custom_department, "start": row.start_time, "end": row.end_time,
             "trainer": row.trainer_name, "docstatus": row.docstatus, "event_status": row.event_status}
            for row in rows]


def _participants(names):
    if not names:
        return []
    rows = frappe.get_all("Training Event Employee", filters={"parent": ["in", names], "parenttype": "Training Event"},
                          fields=["parent", "employee", "employee_name", "department", "attendance"],
                          order_by="idx asc", limit_page_length=0)
    return [{"training_event": row.parent, "employee": row.employee, "employee_name": row.employee_name,
             "department": row.department, "attendance": row.attendance} for row in rows]


def _evaluations(names):
    """The submitted evaluation forms, each scored from its ratings as the
    training's own score is (training.consolidated)."""
    if not names:
        return []
    forms = frappe.get_all("Training Feedback", filters={"training_event": ["in", names], "docstatus": 1},
                           fields=["name", "training_event", "employee", "employee_name"] + QUESTION_FIELDS,
                           order_by="creation asc", limit_page_length=0)
    ratings = {}
    if forms:
        for row in frappe.get_all("Training Evaluation Rating",
                                  filters={"parent": ["in", [form.name for form in forms]], "parenttype": "Training Feedback"},
                                  fields=["parent", "item", "rating", "comment"], order_by="idx asc", limit_page_length=0):
            ratings.setdefault(row.parent, []).append(row)
    out = []
    for form in forms:
        rows = [row for row in ratings.get(form.name, []) if row.item]
        out.append({"name": form.name, "training_event": form.training_event, "employee": form.employee,
                    "employee_name": form.employee_name, "score": rules.score([row.rating for row in rows]),
                    "items": {row.item: row.rating for row in rows},
                    "comments": {row.item: row.comment for row in rows if (row.comment or "").strip()},
                    "answers": {field: form.get("custom_%s" % field) for field, _question in rules.QUESTIONS}})
    return out


def _results(names):
    """Each person's marks from the submitted results, the latest where a
    training has more than one."""
    if not names:
        return []
    results = frappe.get_all("Training Result", filters={"training_event": ["in", names], "docstatus": 1},
                             fields=["name", "training_event"], order_by="creation asc", limit_page_length=0)
    if not results:
        return []
    rows = {}
    for row in frappe.get_all("Training Result Employee",
                              filters={"parent": ["in", [result.name for result in results]], "parenttype": "Training Result"},
                              fields=["parent", "employee", "custom_marks", "custom_effective"],
                              order_by="idx asc", limit_page_length=0):
        rows.setdefault(row.parent, []).append(row)
    latest = {}
    for result in results:
        for row in rows.get(result.name, []):
            latest[(result.training_event, row.employee)] = {
                "training_event": result.training_event, "employee": row.employee,
                "marks": row.custom_marks, "effective": row.custom_effective}
    return list(latest.values())


def _talent_only(events, participants, evaluations, results):
    """The sessions a development plan's training was booked on, and on each
    only the people whose plan it is."""
    names = [event["name"] for event in events]
    booked = {}
    for row in frappe.get_all("Development Training", filters={"training_event": ["in", names],
                                                               "parenttype": "Talent Program"},
                              fields=["training_event", "employee"], limit_page_length=0) if names else []:
        booked.setdefault(row.training_event, set()).add(row.employee)

    def theirs(row):
        return row.get("employee") in booked.get(row.get("training_event"), set())

    return ([event for event in events if event["name"] in booked], [row for row in participants if theirs(row)],
            [row for row in evaluations if theirs(row)], [row for row in results if theirs(row)])


def _items():
    """Section A's items in the form's order."""
    return frappe.get_all("Training Evaluation Item", order_by="creation asc", pluck="name")


def _questions():
    """Section B's questions, labelled as the evaluation form labels them."""
    meta = frappe.get_meta("Training Feedback")
    return [(field, meta.get_label("custom_%s" % field)) for field, _question in rules.QUESTIONS]
