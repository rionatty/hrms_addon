# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A development plan's actions in their own table, Talent Plan Action
(owner, type, skill, status, progress, the course and the session, the cost
approved and spent, the evidence), apart from the appraisal's Development
Action, which the appraisal keeps.

Each plan's rows move across in their order: the estimated cost becomes the
cost approved, a completion date makes the action Done, the session that
marked it done is kept. The old rows are taken out, and each plan's cost and
mix read again. Safe to run twice: a plan with actions of its own already is
left alone.
"""

import frappe

from hrms_addon.hrms_addon import talent_rules as rules


def execute():
    if not frappe.db.table_exists("Talent Plan Action"):
        return
    rows = frappe.db.sql("""select * from `tabDevelopment Action` where parenttype = 'Talent Program'
                            order by parent asc, idx asc""", as_dict=True)
    moved = set(frappe.db.sql_list("""select distinct parent from `tabTalent Plan Action`
                                      where parenttype = 'Talent Program'"""))
    events = set(frappe.get_all("Training Event", pluck="name", limit_page_length=0)) \
        if frappe.db.table_exists("Training Event") else set()
    plans = set()
    for row in rows:
        if row.parent in moved:
            continue
        done = bool(row.get("completed_on"))
        session = row.get("training_event")
        values = {"doctype": "Talent Plan Action", "parent": row.parent, "parenttype": "Talent Program",
                  "parentfield": "actions", "idx": row.idx, "action": row.action, "duration": row.get("duration"),
                  "by_when": row.get("by_when"), "by_whom": row.get("by_whom"),
                  "approved_cost": row.get("estimated_cost") or 0, "completed_on": row.get("completed_on"),
                  "status": rules.DONE if done else "Not Started", "progress": 100 if done else 0,
                  "done_at_session": session, "training_event": session if session in events else None}
        frappe.get_doc(values).db_insert()
        frappe.db.delete("Development Action", {"name": row.name})
        plans.add(row.parent)
    for plan in sorted(plans):
        actions = frappe.get_all("Talent Plan Action", filters={"parent": plan, "parenttype": "Talent Program"},
                                 fields=["action_type", "status", "approved_cost", "actual_cost"], limit_page_length=0)
        found = rules.plan_investment(actions)
        frappe.db.set_value("Talent Program", plan, {
            "approved_investment": found["approved"], "actual_investment": found["actual"],
            "experience_share": found["mix"][rules.EXPERIENCE], "exposure_share": found["mix"][rules.EXPOSURE],
            "education_share": found["mix"][rules.EDUCATION]}, update_modified=False)
