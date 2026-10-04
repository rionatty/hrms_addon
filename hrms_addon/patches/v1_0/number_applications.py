# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Every application its own number (Luuka, 5 Oct 2026).

Frappe HR names an applicant after their email, so a shortlist showed
fndolo993@gmail.com-3 where HR wanted an application number. New
applications are numbered as they arrive (careers.number_application);
those already there are numbered here in the order they came in, each by
the year it came in (APP-2026-0001), and the shortlists already made show
the number in their Application ID column. Safe to run twice.
"""

import frappe
from frappe.utils import getdate
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import careers


def execute():
    # the field exists first: fixtures are synced only after every patch
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype="Job Applicant")
    for row in frappe.get_all("Job Applicant", filters={"custom_application_id": ["is", "not set"]},
                              fields=["name", "creation"], order_by="creation asc, name asc"):
        frappe.db.set_value("Job Applicant", row.name, "custom_application_id",
                            careers.application_id(getdate(row.creation).year), update_modified=False)
    numbers = dict(frappe.get_all("Job Applicant", fields=["name", "custom_application_id"], as_list=True))
    for row in frappe.get_all("Interview Shortlist Candidate", filters={"parenttype": "Interview Shortlist"},
                              fields=["name", "job_applicant", "application_id"]):
        number = numbers.get(row.job_applicant)
        if number and row.application_id != number:
            frappe.db.set_value("Interview Shortlist Candidate", row.name, "application_id", number,
                                update_modified=False)
