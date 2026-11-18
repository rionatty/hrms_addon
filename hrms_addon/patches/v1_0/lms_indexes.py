"""The learning records looked up the way the engine and the reports look for them: a requirement by status and
due date, by plant and department, by rule and by its proof; an assessment by employee and skill; a supervisor's
review by session and employee, and by reviewer and status. An employee holds one requirement per rule: copies a
race between two jobs left behind are taken off first (the oldest kept), then the pair is made unique. Safe to run
again."""

import frappe

REQUIREMENT = "Employee Training Requirement"


def execute():
    from hrms_addon.hrms_addon import learning

    _drop_copies()
    learning.add_indexes()


def _drop_copies():
    if not frappe.db.table_exists(REQUIREMENT):
        return
    seen, copies = set(), []
    for row in frappe.get_all(REQUIREMENT, filters={"training_rule": ["is", "set"]},
                              fields=["name", "employee", "training_rule"], order_by="creation asc",
                              limit_page_length=0):
        key = (row.employee, row.training_rule)
        if key in seen:
            copies.append(row.name)
        else:
            seen.add(key)
    for start in range(0, len(copies), 500):
        frappe.db.delete(REQUIREMENT, {"name": ["in", copies[start:start + 500]]})
    if copies:
        frappe.db.commit()
