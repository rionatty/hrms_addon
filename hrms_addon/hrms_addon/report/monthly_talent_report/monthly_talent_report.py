# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Monthly Talent Report — the testing sheet's recommendation, "Provide
end-of-month reports in the system": what happened in talent in a month —
placements finalised and their boxes, moves in calibration, critical roles
confirmed and gaps recruited for, development actions done and programmes
closed, trainees confirmed or gone — each a row with its document, and the
month's figures at the top, actions still past their date at its end among
them. HR and the Talent Council are told when a month closes
(talent.monthly). It names boxes, so it is for them."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_reports


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    month = talent_reports.month(filters.get("month"))
    figures = month["summary"]
    summary = [
        {"value": figures["finalised"], "label": _("Placements finalised"), "datatype": "Int", "indicator": "Blue"},
        {"value": figures["top_talent"], "label": _("Of them top talent"), "datatype": "Int", "indicator": "Green"},
        {"value": figures["at_risk"], "label": _("Top talent at risk"), "datatype": "Int", "indicator": "Red"},
        {"value": figures["moves"], "label": _("Moved in calibration"), "datatype": "Int", "indicator": "Blue"},
        {"value": figures["roles_confirmed"], "label": _("Critical roles confirmed"), "datatype": "Int",
         "indicator": "Blue"},
        {"value": figures["gaps"], "label": _("Gaps recruited for"), "datatype": "Int", "indicator": "Orange"},
        {"value": figures["actions_done"], "label": _("Development actions done"), "datatype": "Int",
         "indicator": "Green"},
        {"value": figures["actions_late"], "label": _("Actions past their date"), "datatype": "Int",
         "indicator": "Red"},
        {"value": figures["programmes_closed"], "label": _("Programmes closed"), "datatype": "Int",
         "indicator": "Blue"},
        {"value": figures["trainees_confirmed"], "label": _("Trainees confirmed"), "datatype": "Int",
         "indicator": "Green"},
        {"value": figures["trainees_left"], "label": _("Trainees who left"), "datatype": "Int", "indicator": "Grey"},
    ]
    return columns(), month["events"], None, None, summary


def columns():
    return [
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
        {"label": _("Area"), "fieldname": "area", "fieldtype": "Data", "width": 130},
        {"label": _("Who"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("What Happened"), "fieldname": "what", "fieldtype": "Data", "width": 420},
        {"label": _("Document Type"), "fieldname": "reference_doctype", "fieldtype": "Link", "options": "DocType",
         "width": 150, "hidden": 1},
        {"label": _("Document"), "fieldname": "reference_name", "fieldtype": "Dynamic Link",
         "options": "reference_doctype", "width": 160},
    ]
