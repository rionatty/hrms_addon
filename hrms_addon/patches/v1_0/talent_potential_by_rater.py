# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Potential rated by rater and criterion (potential.py): each placement's
ability, aspiration and engagement, typed out of ten on the placement,
become one submitted Potential Assessment by the line manager who placed
them, each rated 1 to 5 (half the score out of ten). The potential they make
out of a hundred is the same as before. A finalised placement keeps its
numbers and is given the raters and the criteria beside them.

The old columns stay in the table (Frappe does not drop them); nothing reads
them any more. Safe to run twice: a placement with an assessment already
is left alone.
"""

import frappe

from hrms_addon.hrms_addon import potential, potential_rules, talent_masters


def execute():
    if not (frappe.db.table_exists("Potential Assessment") and frappe.db.has_column("Talent Placement", "ability")):
        return
    talent_masters._seed_lists()
    potential.forget()
    rows = frappe.db.sql("""
        select name, employee, docstatus, ability, aspiration, engagement, submitted_by, owner, submitted_on,
               creation
        from `tabTalent Placement`
        where docstatus < 2 and (ifnull(ability, 0) > 0 or ifnull(aspiration, 0) > 0 or ifnull(engagement, 0) > 0)
        """, as_dict=True)
    done = set(frappe.get_all("Potential Assessment", filters={"docstatus": ["<", 2]}, pluck="placement",
                              limit_page_length=0))
    for number, row in enumerate(rows, 1):
        if row.name in done:
            continue
        ratings = potential_rules.from_old(row)
        if not ratings:
            continue
        rater = row.submitted_by or row.owner
        if not frappe.db.exists("User", rater):
            rater = "Administrator"
        doc = frappe.get_doc({"doctype": "Potential Assessment", "placement": row.name, "rater": rater,
                              "rater_role": "Line Manager", "assessed_on": row.submitted_on or str(row.creation)[:10],
                              "ratings": ratings, "comments": "Moved from the placement's own ratings."})
        doc.flags.ignore_permissions = True
        doc.flags.migrating = True
        doc.insert()
        doc.submit()
        if row.docstatus == 1:
            placement = frappe.get_doc("Talent Placement", row.name)
            score = placement.potential_score
            band = placement.potential_band
            potential.fill_placement(placement)
            # a finalised placement keeps the potential it was finalised on
            placement.potential_score, placement.potential_band = score, band
            placement.db_update()
            placement.update_child_table("potential_summary")
        if number % 200 == 0:
            frappe.db.commit()
