# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Time to Fill: each Job Requisition, and the days from the request to its
approval, to the advert, to the first offer and to the job being filled,
with the averages on top. Time to Hire starts at the application; this
starts at the requisition, so the wait for approval and advertising shows.
The arithmetic is in interview_analytics_rules.py."""

import frappe
from frappe import _
from frappe.utils import add_months, today

from hrms_addon.hrms_addon import interview_analytics_rules as rules

DAYS = ("days_to_approve", "days_to_advertise", "days_to_offer", "days_to_fill")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = [["posting_date", ">=", filters.get("from_date") or add_months(today(), -12)],
                  ["posting_date", "<=", filters.get("to_date") or today()]]
    for field in ("department", "designation", "status"):
        if filters.get(field):
            conditions.append([field, "=", filters.get(field)])
    if filters.get("branch"):
        conditions.append(["custom_branch", "=", filters.get("branch")])
    requisitions = frappe.get_all(
        "Job Requisition", filters=conditions,
        fields=["name", "designation", "department", "custom_branch", "no_of_positions", "posting_date",
                "custom_ed_date", "status", "completed_on"],
        order_by="posting_date asc")
    names = [row.name for row in requisitions]
    openings = frappe.get_all("Job Opening", filters={"job_requisition": ["in", names or [""]]},
                              fields=["name", "job_requisition", "posted_on", "creation"])
    opening_of = {row.name: row.job_requisition for row in openings}
    advertised = {}
    for row in openings:
        advertised.setdefault(row.job_requisition, []).append(row.posted_on or row.creation)
    applicants = frappe.get_all("Job Applicant", filters={"job_title": ["in", list(opening_of) or [""]]},
                                fields=["name", "job_title"])
    requisition_of = {row.name: opening_of.get(row.job_title) for row in applicants}
    offered, accepted = {}, {}
    for offer in frappe.get_all("Job Offer", filters={"job_applicant": ["in", list(requisition_of) or [""]],
                                                      "docstatus": ["!=", 2]},
                                fields=["job_applicant", "offer_date", "status"]):
        requisition = requisition_of.get(offer.job_applicant)
        offered.setdefault(requisition, []).append(offer.offer_date)
        accepted[requisition] = accepted.get(requisition, 0) + (offer.status == "Accepted")
    rows = []
    for requisition in requisitions:
        advert = rules.earliest(advertised.get(requisition.name))
        first_offer = rules.earliest(offered.get(requisition.name))
        rows.append(dict({
            "job_requisition": requisition.name,
            "designation": requisition.designation,
            "department": requisition.department,
            "branch": requisition.custom_branch,
            "positions": requisition.no_of_positions,
            "requested_on": requisition.posting_date,
            "approved_on": requisition.custom_ed_date,
            "advertised_on": advert,
            "first_offer": first_offer,
            "accepted": accepted.get(requisition.name, 0),
            "filled_on": requisition.completed_on,
            "status": requisition.status,
        }, **rules.fill_timeline(requisition.posting_date, requisition.custom_ed_date, advert, first_offer,
                                 requisition.completed_on)))
    means = rules.averages(rows, DAYS)
    summary = [{"value": means[field], "label": label, "datatype": "Float", "indicator": "Blue"}
               for field, label in zip(DAYS, (_("Average Days to Approve"), _("Average Days to Advertise"),
                                              _("Average Days to First Offer"), _("Average Days to Fill")))]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"fieldname": "job_requisition", "label": _("Job Requisition"), "fieldtype": "Link",
         "options": "Job Requisition", "width": 160},
        {"fieldname": "designation", "label": _("Job Title"), "fieldtype": "Link", "options": "Designation", "width": 160},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 150},
        {"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "positions", "label": _("Positions"), "fieldtype": "Int", "width": 90},
        {"fieldname": "requested_on", "label": _("Requested On"), "fieldtype": "Date", "width": 115},
        {"fieldname": "approved_on", "label": _("Approved On"), "fieldtype": "Date", "width": 115},
        {"fieldname": "advertised_on", "label": _("Advertised On"), "fieldtype": "Date", "width": 115},
        {"fieldname": "first_offer", "label": _("First Offer"), "fieldtype": "Date", "width": 110},
        {"fieldname": "accepted", "label": _("Offers Accepted"), "fieldtype": "Int", "width": 120},
        {"fieldname": "filled_on", "label": _("Filled On"), "fieldtype": "Date", "width": 110},
        {"fieldname": "days_to_approve", "label": _("Days to Approve"), "fieldtype": "Int", "width": 120},
        {"fieldname": "days_to_advertise", "label": _("Days to Advertise"), "fieldtype": "Int", "width": 130},
        {"fieldname": "days_to_offer", "label": _("Days to First Offer"), "fieldtype": "Int", "width": 135},
        {"fieldname": "days_to_fill", "label": _("Days to Fill"), "fieldtype": "Int", "width": 100},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
    ]
