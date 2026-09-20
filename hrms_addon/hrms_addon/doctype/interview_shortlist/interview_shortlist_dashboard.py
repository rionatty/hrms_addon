# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Interview Shortlist: the candidates it shortlisted and
the interviews booked for them, both read from its own rows."""


def get_data():
    return {
        "fieldname": "job_opening",
        "internal_links": {
            "Job Applicant": ["candidates", "job_applicant"],
            "Interview": ["candidates", "interview"],
            "Job Opening": "job_opening",
        },
        "transactions": [
            {"label": "Candidates", "items": ["Job Applicant", "Interview"]},
            {"label": "The Post", "items": ["Job Opening"]},
        ],
    }
