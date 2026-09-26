# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Time to Hire: each Job Offer made, and the days from the application to
the first interview, to the offer and to joining, with the averages on top.
The arithmetic is in interview_analytics_rules.py."""

import frappe
from frappe import _
from frappe.utils import add_months, today

from hrms_addon.hrms_addon import interview_analytics_rules as rules

DAYS = ("days_to_interview", "days_to_offer", "days_to_join")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = [["offer_date", ">=", filters.get("from_date") or add_months(today(), -6)],
                  ["offer_date", "<=", filters.get("to_date") or today()], ["docstatus", "!=", 2]]
    if filters.get("designation"):
        conditions.append(["designation", "=", filters.get("designation")])
    offers = frappe.get_all("Job Offer", filters=conditions,
                            fields=["name", "job_applicant", "applicant_name", "designation", "offer_date", "status"],
                            order_by="offer_date asc")
    applicants = [offer.job_applicant for offer in offers if offer.job_applicant]
    applied = {row.name: row for row in frappe.get_all("Job Applicant", filters={"name": ["in", applicants or [""]]},
                                                       fields=["name", "job_title", "creation"])}
    first = {}
    for row in frappe.get_all("Interview", filters={"job_applicant": ["in", applicants or [""]], "docstatus": ["!=", 2]},
                              fields=["job_applicant", "scheduled_on"]):
        if row.scheduled_on and (row.job_applicant not in first or str(row.scheduled_on) < str(first[row.job_applicant])):
            first[row.job_applicant] = row.scheduled_on
    joined = dict(frappe.get_all("Employee", filters={"job_applicant": ["in", applicants or [""]]},
                                 fields=["job_applicant", "date_of_joining"], as_list=True))
    rows = []
    for offer in offers:
        applicant = applied.get(offer.job_applicant) or frappe._dict()
        if filters.get("job_opening") and applicant.job_title != filters.get("job_opening"):
            continue
        rows.append(dict({
            "job_offer": offer.name,
            "job_applicant": offer.job_applicant,
            "applicant_name": offer.applicant_name,
            "job_opening": applicant.job_title,
            "designation": offer.designation,
            "applied_on": str(applicant.creation)[:10] if applicant.creation else None,
            "first_interview": first.get(offer.job_applicant),
            "offer_date": offer.offer_date,
            "status": offer.status,
            "joined_on": joined.get(offer.job_applicant),
        }, **rules.hire_timeline(applicant.creation, first.get(offer.job_applicant), offer.offer_date,
                                 joined.get(offer.job_applicant))))
    means = rules.averages(rows, DAYS)
    summary = [{"value": means[field], "label": label, "datatype": "Float", "indicator": "Blue"}
               for field, label in zip(DAYS, (_("Average Days to First Interview"), _("Average Days to Offer"),
                                              _("Average Days to Join")))]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"fieldname": "job_offer", "label": _("Job Offer"), "fieldtype": "Link", "options": "Job Offer", "width": 150},
        {"fieldname": "applicant_name", "label": _("Candidate"), "fieldtype": "Data", "width": 170},
        {"fieldname": "job_opening", "label": _("Job Opening"), "fieldtype": "Link", "options": "Job Opening", "width": 170},
        {"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link", "options": "Designation", "width": 150},
        {"fieldname": "applied_on", "label": _("Applied On"), "fieldtype": "Date", "width": 110},
        {"fieldname": "first_interview", "label": _("First Interview"), "fieldtype": "Date", "width": 120},
        {"fieldname": "offer_date", "label": _("Offer Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "status", "label": _("Offer Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "joined_on", "label": _("Joined On"), "fieldtype": "Date", "width": 110},
        {"fieldname": "days_to_interview", "label": _("Days to Interview"), "fieldtype": "Int", "width": 130},
        {"fieldname": "days_to_offer", "label": _("Days to Offer"), "fieldtype": "Int", "width": 110},
        {"fieldname": "days_to_join", "label": _("Days to Join"), "fieldtype": "Int", "width": 110},
    ]
