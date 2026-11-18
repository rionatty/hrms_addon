# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A review covers several plants (its Plants table): a review set up for
one plant has it in the table. Each placement's box is linked to its Nine
Box record. The graduate trainees' cohorts become Graduate Cohort records,
each with the 30, 60 and 90 day milestones. Safe to run twice.
"""

import frappe
from frappe.utils import getdate

from hrms_addon.hrms_addon import graduate_rules


def execute():
    if frappe.db.table_exists("Talent Review Plant"):
        have = set(frappe.db.sql_list("""select distinct parent from `tabTalent Review Plant`
                                         where parenttype = 'Talent Review'"""))
        for row in frappe.get_all("Talent Review", filters={"branch": ["is", "set"]}, fields=["name", "branch"]):
            if row.name in have:
                continue
            frappe.get_doc({"doctype": "Talent Review Plant", "parent": row.name, "parenttype": "Talent Review",
                            "parentfield": "plants", "idx": 1, "branch": row.branch}).db_insert()
    if frappe.db.has_column("Talent Placement", "nine_box"):
        frappe.db.sql("""update `tabTalent Placement` placement
                         join `tabNine Box` box on box.box = placement.box
                         set placement.nine_box = box.name
                         where placement.box between 1 and 9 and ifnull(placement.nine_box, '') = ''""")
    if frappe.db.table_exists("Graduate Cohort"):
        for row in frappe.db.sql("""select cohort, min(start_date) as start, max(company) as company
                                    from `tabGraduate Trainee Program` where ifnull(cohort, '') != ''
                                    group by cohort""", as_dict=True):
            if frappe.db.exists("Graduate Cohort", row.cohort):
                continue
            doc = frappe.get_doc({
                "doctype": "Graduate Cohort", "cohort_name": row.cohort, "company": row.company,
                "intake_year": getdate(row.start).year if row.start else None, "start_date": row.start,
                "status": "Running",
                "milestones": [{"milestone": name, "days_after_start": days, "final": final}
                               for name, days, final in graduate_rules.TEMPLATE]})
            doc.flags.ignore_permissions = True
            doc.flags.ignore_links = True
            doc.insert()
