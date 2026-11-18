# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The nine-box out of what the line manager, the employee and the mentor
read (Luuka, 6 Oct 2026).

A placement's box used to put the action the grid suggests for it into its
development themes, with the box's name ("Exit, or move to work that fits",
"From the Risk placement."). The plan drawn up from the placement carried
that action as its objective and as its first action. The box is for HR
and the Talent Council (case 10), and the plan is the employee's own.

Those words come out where the system wrote them: the theme rows exactly
as written, the plan's objective where it is still the action alone, and
the plan's action of the same words where nobody has done it yet. Anything
someone has since changed stays. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import talent_rules as rules


def execute():
    # the words the first grid seeded (the boxes have Luuka's own since)
    actions = sorted({action for _name, action, _colour in rules.OLD_SEED.values()})
    reasons = sorted({"From the %s placement." % name for name, _action, _colour in rules.OLD_SEED.values()})
    themes = frappe.get_all("Development Theme", filters={"parenttype": "Talent Placement",
                                                          "theme": ["in", actions], "why": ["in", reasons]},
                            fields=["name", "parent"])
    for row in themes:
        frappe.db.delete("Development Theme", {"name": row.name})
    _renumber("Development Theme", "Talent Placement", {row.parent for row in themes})
    for name in frappe.get_all("Talent Program", filters={"docstatus": ["<", 2], "objectives": ["in", actions]},
                               pluck="name"):
        frappe.db.set_value("Talent Program", name, "objectives", None, update_modified=False)
    # a plan's actions, in the appraisal's table as they were, or in the plan's own (talent_plan_actions)
    for doctype in ("Development Action", "Talent Plan Action"):
        if not frappe.db.table_exists(doctype):
            continue
        steps = frappe.get_all(doctype, filters={"parenttype": "Talent Program", "action": ["in", actions],
                                                 "completed_on": ["is", "not set"]},
                               fields=["name", "parent"])
        for row in steps:
            frappe.db.delete(doctype, {"name": row.name})
        _renumber(doctype, "Talent Program", {row.parent for row in steps})


def _renumber(doctype, parenttype, parents):
    """The rows left numbered 1 to n again, in their order."""
    for parent in sorted(parents):
        rows = frappe.get_all(doctype, filters={"parent": parent, "parenttype": parenttype},
                              order_by="idx asc", pluck="name")
        for number, name in enumerate(rows, 1):
            frappe.db.set_value(doctype, name, "idx", number, update_modified=False)
