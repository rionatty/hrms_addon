# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A training no longer holds the onboarding open.

Until Oct 2026 the supervisor's evaluation of a new employee's training was
an onboarding activity, and Frappe HR completes an onboarding only once
every one of its tasks is done, so the onboarding stayed In Process until
the training was over. The evaluation is now a task on the Training Event
(onboarding._ask_evaluation). On each onboarding not yet completed, an
evaluation task still open is cancelled (Frappe HR counts a cancelled task
as done), and the same evaluation is asked on its Training Event. Safe to
run twice.
"""

import frappe

from hrms_addon.hrms_addon import onboarding
from hrms_addon.hrms_addon import onboarding_rules as rules

OPEN = ("Open", "Working", "Pending Review", "Overdue", "Template")


def execute():
    for name in frappe.get_all("Employee Onboarding", filters={"docstatus": 1, "boarding_status": ["!=", "Completed"]},
                               pluck="name"):
        doc = frappe.get_doc("Employee Onboarding", name)
        trainings = {}
        for row in doc.get("custom_trainings") or []:
            if row.get("training_event") and doc.get("boarding_begins_on") and row.get("start"):
                activity = rules.training_evaluation_activity(doc.boarding_begins_on, row.start, row.days,
                                                              row.training_program)
                trainings[activity["activity_name"]] = row
        for activity in doc.get("activities") or []:
            row = trainings.get(activity.get("activity_name"))
            if not row or not activity.get("task"):
                continue
            if frappe.db.get_value("Task", activity.task, "status") not in OPEN:
                continue
            task = frappe.get_doc("Task", activity.task)
            task.status = "Cancelled"
            task.flags.ignore_permissions = True
            task.save()
            onboarding._ask_evaluation(doc, row)
