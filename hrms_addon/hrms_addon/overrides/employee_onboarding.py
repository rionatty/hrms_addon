# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Onboarding, Frappe HR's controller with one change: when the
Employee cannot be created or saved yet, say which tasks are still open.

Frappe HR checks it in two places, both through this class (hooks.py
override_doctype_class): Create > Employee on the onboarding
(employee_onboarding.make_employee), and every save of an Employee whose
candidate has a running onboarding (overrides/employee_master.py
validate_onboarding_process). Its own message names nothing.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_fullname
from hrms.hr.doctype.employee_onboarding.employee_onboarding import EmployeeOnboarding as HRMSEmployeeOnboarding
from hrms.hr.doctype.employee_onboarding.employee_onboarding import IncompleteTaskError

from hrms_addon.hrms_addon import onboarding_rules as rules


class EmployeeOnboarding(HRMSEmployeeOnboarding):
    def validate_employee_creation(self):
        if self.docstatus != 1:
            frappe.throw(
                _("Start the onboarding {0} (Start Onboarding) before creating the Employee.").format(frappe.bold(self.name)),
                title=_("Employee Onboarding"),
            )
        activities = []
        for activity in self.activities:
            if not activity.required_for_employee_creation:
                continue
            status, assigned = (
                frappe.db.get_value("Task", activity.task, ["status", "_assign"]) if activity.task else None
            ) or (None, None)
            activities.append({
                "activity_name": activity.activity_name,
                "required_for_employee_creation": 1,
                "task": activity.task if status else None,  # a deleted task is not linked
                "task_status": status,
                "assignees": [get_fullname(user) for user in json.loads(assigned or "[]")] or (
                    [get_fullname(activity.user)] if activity.user else []
                ),
            })
        pending = rules.pending_required(activities)
        if pending:
            frappe.throw(
                rules.pending_message(self.name, pending),
                IncompleteTaskError,
                title=_("Onboarding tasks to complete"),
            )
