"""One competency framework (18 Nov 2026): the brief's categories (Core, Functional, Technical, Safety, Leadership,
Behavioural) seeded, and each skill with a type given the category it falls in. Safe to run again."""

import frappe


def execute():
    from hrms_addon.hrms_addon import competency_rules as rules

    for name in rules.CATEGORIES:
        if not frappe.db.exists("Competency Category", name):
            frappe.get_doc({"doctype": "Competency Category", "category_name": name}).insert(ignore_permissions=True)
    if not frappe.get_meta("Skill").has_field("custom_competency_category"):
        return
    for row in frappe.get_all("Skill", filters={"custom_skill_type": ["is", "set"],
                                                 "custom_competency_category": ["is", "not set"]},
                              fields=["name", "custom_skill_type"]):
        category = rules.TYPE_CATEGORY.get(row.custom_skill_type)
        if category:
            frappe.db.set_value("Skill", row.name, "custom_competency_category", category, update_modified=False)
