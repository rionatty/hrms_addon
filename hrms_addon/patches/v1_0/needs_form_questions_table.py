# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A Training Needs Form's six answers move into its Questions table
(Training Needs Answer), one row per question in the form's order, each
with the answer its own column held. A form that has rows already is left
as it is. The old columns stay in the database, unread, so nothing is lost.
"""

import frappe

from hrms_addon.hrms_addon import training_rules as rules


def execute():
    columns = set(frappe.db.get_table_columns("Training Needs Form"))
    kept = [key for key, _question, _required in rules.NEEDS_QUESTIONS if key in columns]
    for form in frappe.db.sql("select name, docstatus%s from `tabTraining Needs Form`"
                              % "".join(", `%s`" % column for column in kept), as_dict=True):
        if frappe.db.exists("Training Needs Answer", {"parent": form.name, "parenttype": "Training Needs Form"}):
            continue
        answers = [{"question_key": key, "answer": form.get(key)} for key in kept]
        for index, row in enumerate(rules.needs_rows(answers), 1):
            frappe.get_doc(dict(row, doctype="Training Needs Answer", parent=form.name, parenttype="Training Needs Form",
                                parentfield="questions", idx=index, docstatus=form.docstatus)).db_insert()
