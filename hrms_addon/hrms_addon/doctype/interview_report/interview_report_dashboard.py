# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Interview Report: the candidates it reports on, their
interviews and the offers that followed, all read from its own rows."""


def get_data():
    return {
        "fieldname": "job_opening",
        "internal_links": {
            "Job Applicant": ["candidates", "job_applicant"],
            "Interview": ["candidates", "interview"],
            "Job Offer": ["candidates", "job_offer"],
            "Job Opening": "job_opening",
        },
        "transactions": [
            {"label": "Candidates", "items": ["Job Applicant", "Interview", "Job Offer"]},
            {"label": "The Post", "items": ["Job Opening"]},
        ],
    }
