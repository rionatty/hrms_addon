# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview Report

The panel's report on one day's interviews for a Job Opening, laid out like
Luuka's interview report and approved through the Human Resource Manager by the
Executive Director (interview_report_approval.py). Its approval closes the
day's interviews and moves each applicant on. The rules are in
interview_rules.py and the glue in interviews.py.
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import interviews


class InterviewReport(Document):
    def validate(self):
        interviews.validate_report(self)

    def on_submit(self):
        interviews.close_report(self)
