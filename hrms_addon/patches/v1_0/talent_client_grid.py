# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The nine boxes in Luuka's own words (the talent blueprint v2.0, section
4), Ready Now drawn from boxes 9 and 6, and the distribution guide.

A Nine Box record still holding what the first build seeded (its name, its
action, its colour) takes the blueprint's; one HR changed keeps what they
gave it. The same old name on a placement, a development plan or a
successor row is a label, and is renamed with it. Ready Now, still drawing
from box 9 alone as first seeded, draws from box 6 too. A box with no share
of the guide takes the built-in one. Safe to run twice.
"""

import frappe
from frappe.utils import cint, flt

from hrms_addon.hrms_addon import talent_masters, talent_rules as rules


def execute():
    if not frappe.db.table_exists("Nine Box"):
        return
    renamed = {}
    for row in frappe.get_all("Nine Box", fields=["name", "box", "box_name", "default_action", "colour", "guide_share"]):
        box = cint(row.box)
        old = rules.OLD_SEED.get(box)
        new = rules.box_of(box)
        if not old or not new:
            continue
        values = {}
        if (row.box_name or "").strip() == old[0] and old[0] != new["name"]:
            values["box_name"] = new["name"]
            renamed[box] = (old[0], new["name"])
        if (row.default_action or "").strip() == old[1]:
            values["default_action"] = new["action"]
        if row.colour == old[2] and old[2] != new["colour"]:
            values["colour"] = new["colour"]
        if not flt(row.guide_share):
            values["guide_share"] = rules.GUIDE[box]
        if values:
            frappe.db.set_value("Nine Box", row.name, values, update_modified=False)
    for box, (old, new) in renamed.items():
        frappe.db.sql("""update `tabTalent Placement` set box_name = %(new)s
                         where box = %(box)s and box_name = %(old)s""", {"new": new, "box": box, "old": old})
        if frappe.db.has_column("Talent Placement", "default_action"):
            frappe.db.sql("""update `tabTalent Placement` set default_action = %(action)s
                             where box = %(box)s and default_action = %(old)s""",
                          {"action": rules.box_of(box)["action"], "box": box, "old": rules.OLD_SEED[box][1]})
        for doctype in ("Talent Program", "Succession Candidate"):
            if frappe.db.has_column(doctype, "box_name"):
                frappe.db.sql("update `tab%s` set box_name = %%(new)s where box_name = %%(old)s" % doctype,
                              {"new": new, "old": old})
    _ready_now_from_six()
    talent_masters.forget()


def _ready_now_from_six():
    """Ready Now, as first seeded (box 9 only), draws from box 6 as well."""
    if not frappe.db.exists("Readiness Level", rules.READY_NOW):
        return
    six = frappe.db.get_value("Nine Box", {"box": 6}, "name")
    nine = frappe.db.get_value("Nine Box", {"box": 9}, "name")
    boxes = frappe.get_all("Readiness Level Box", filters={"parent": rules.READY_NOW, "parenttype": "Readiness Level"},
                           pluck="nine_box")
    if not six or set(boxes) != {nine}:
        return
    doc = frappe.get_doc("Readiness Level", rules.READY_NOW)
    doc.append("boxes", {"nine_box": six})
    doc.flags.ignore_permissions = True
    doc.save()
