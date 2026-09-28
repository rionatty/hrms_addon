# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A Training Requisition's one topic becomes the first row of its Training
Topics table (Training Requisition Topic): the topic, skills, method,
trainer, budget and duration the requisition held. The old columns stay in
the database, unread, so nothing is lost.
"""

import frappe
from frappe.utils import flt

OLD = ("required_skills", "proposed_method", "proposed_trainer", "estimated_budget", "duration")


def execute():
    columns = set(frappe.db.get_table_columns("Training Requisition"))
    kept = [column for column in OLD if column in columns]
    for row in frappe.db.sql("""select name, docstatus, training_topic%s from `tabTraining Requisition`
            where ifnull(training_topic, '') != ''""" % "".join(", " + column for column in kept), as_dict=True):
        if frappe.db.exists("Training Requisition Topic", {"parent": row.name, "parenttype": "Training Requisition"}):
            continue
        frappe.get_doc({
            "doctype": "Training Requisition Topic", "parent": row.name, "parenttype": "Training Requisition",
            "parentfield": "topics", "idx": 1, "docstatus": row.docstatus, "topic": row.training_topic[:140],
            "required_skills": row.get("required_skills"), "method": row.get("proposed_method"),
            "trainer": row.get("proposed_trainer"), "budget": flt(row.get("estimated_budget")),
            "duration": row.get("duration"),
        }).db_insert()
