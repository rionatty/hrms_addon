# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview Shortlist

The applicants for one Job Opening invited to interview, laid out like Luuka's
shortlist sheet, screened by HR and then the HOD (interview_shortlist_approval.py).
The rules are in interview_rules.py and the glue in interviews.py.
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import interviews


class InterviewShortlist(Document):
    def validate(self):
        interviews.validate_shortlist(self)

    def on_update(self):
        interviews.shortlist_on_update(self)

    def on_submit(self):
        interviews.mark_shortlisted(self)

    def on_cancel(self):
        interviews.unmark_shortlisted(self)
