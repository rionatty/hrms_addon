# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The shortlists already there: each candidate's CV column filled from
their application, so it can be opened from the shortlist
(interviews.shortlist_cv). Safe to run twice."""

import frappe


def execute():
    for row in frappe.get_all("Interview Shortlist Candidate",
                              filters={"parenttype": "Interview Shortlist", "job_applicant": ["is", "set"]},
                              fields=["name", "job_applicant", "cv"]):
        if row.cv:
            continue
        url = frappe.db.get_value("Job Applicant", row.job_applicant, "resume_attachment")
        if url:
            frappe.db.set_value("Interview Shortlist Candidate", row.name, "cv", url, update_modified=False)
