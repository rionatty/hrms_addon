# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Plain descriptions on the records this app created on the site: the
claim types and salary components it seeded, and job openings raised from a
succession gap. A description somebody has changed since is left as it is:
only the exact old wording is replaced."""

import frappe

SECTIONS = ("Per Meter", "Per Piece", "Hourly")

REWORDED = {
    "Expense Claim Type": {
        "A standard claim. Set the amount Luuka pay before it is used.":
            "A standard claim. Set its amount before use.",
        "UGX 350,000 for a female employee, for up to three children born during her employment "
        "(minutes §4.8).": "UGX 350,000 for female employees, up to three times.",
        "70% of the employee's gross, for the loss of a biological mother, father or child "
        "(minutes §4.8).": "70% of gross, for the loss of a mother, father or child.",
    },
    "Salary Component": dict(
        {"%s pay, from the Output Pay Run (minutes §4.6)." % section: "%s pay from the Output Pay Run." % section
         for section in SECTIONS},
        **{
            "Recovery of a penalty for property lost or damaged (LPL/HR/39, minutes §4.11).":
                "Recovery of a penalty for property lost or damaged.",
            "Leave days paid instead of taken (minutes §4.5).": "Leave days paid instead of taken.",
            "Overtime, paid through Frappe HR's Overtime Slip.": "Overtime, paid through the Overtime Slip.",
        }),
}
OLD_OPENING = ": the bench has nobody ready now."
NEW_OPENING = ": no successor is ready."


def execute():
    for doctype, reworded in REWORDED.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        for old, new in reworded.items():
            for name in frappe.get_all(doctype, filters={"description": old}, pluck="name"):
                frappe.db.set_value(doctype, name, "description", new, update_modified=False)
    if frappe.db.exists("DocType", "Job Opening"):
        for row in frappe.get_all("Job Opening", filters={"description": ["like", "%" + OLD_OPENING + "%"]},
                                  fields=["name", "description"]):
            frappe.db.set_value("Job Opening", row.name, "description",
                                row.description.replace(OLD_OPENING, NEW_OPENING), update_modified=False)
