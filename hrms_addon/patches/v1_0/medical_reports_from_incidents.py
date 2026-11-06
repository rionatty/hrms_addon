"""The doctor's report and the sick leave an incident held as single fields,
before it could hold more than one (review item 14, Luuka 5 Nov 2026: "the
doctor's report is more than one. Need a provision for multiple reports and
rest days"), become its first doctor's report. A day off is a rest, with the
sick leave it gave; a report with no day off found the employee fit to work.
Safe to run twice: an incident with a report already is left alone."""

import frappe
from frappe.utils import add_days, cint, getdate

FIELDS = ["name", "incident_on", "hospital", "doctor_report", "day_off_required", "sick_from", "sick_days", "sick_leave"]


def execute():
    for row in frappe.get_all("Safety Incident", filters={"docstatus": ["<", 2]}, fields=FIELDS,
                              limit_page_length=0):
        if not (row.doctor_report or row.day_off_required):
            continue
        if frappe.db.exists("Safety Medical Report", {"parent": row.name, "parenttype": "Safety Incident"}):
            continue
        rest = bool(row.day_off_required)
        start = getdate(row.sick_from or row.incident_on)
        days = (cint(row.sick_days) or 1) if rest else 0
        frappe.get_doc({
            "doctype": "Safety Medical Report", "parent": row.name, "parenttype": "Safety Incident",
            "parentfield": "medical_reports", "idx": 1, "report_date": start, "hospital": row.hospital,
            "report": row.doctor_report, "recommendation": "Rest" if rest else "Fit to Work",
            "rest_from": start if rest else None, "rest_days": days, "rest_to": add_days(start, days - 1) if rest else None,
            "leave_application": row.sick_leave if rest else None,
        }).db_insert()
