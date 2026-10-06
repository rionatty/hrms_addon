# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Next Steps on every form whose process goes on into other documents:
the documents this one raised, or that followed it, each opened from a
button (public/js/hrms_addon_next_steps.js). Which documents follow which
is in next_steps_rules.py, without a Frappe import
(scripts/verify_next_steps.py).

  get_next_steps  the steps of one document that lead somewhere: for each,
                  the documents found that are not cancelled and that the
                  user may read, and the filter that lists them all
"""

import frappe

from hrms_addon.hrms_addon import next_steps_rules as rules


@frappe.whitelist()
def get_next_steps(doctype, name):
    """[{"label", "doctype", "names", "count", "filters"}] in the process's
    order, for a document the user may read."""
    steps = rules.STEPS.get(doctype)
    if not steps:
        return []
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    out = []
    for step in steps:
        target = step[0]
        if not frappe.has_permission(target, "read"):
            continue
        names, filters = _follow(doc, target, step[1])
        names = _readable(target, names)
        if not names:
            continue
        out.append({"label": rules.label_of(step), "doctype": target, "names": names[:rules.LIMIT],
                    "count": len(names), "filters": filters or {"name": ["in", names[:rules.LIMIT]]}})
    return out


def _follow(doc, target, relation):
    """(the names a step leads to, the list filter that shows them)."""
    kind, parts = rules.parse(relation)
    if kind == "field":
        return rules.unique([doc.get(parts[0])]), None
    if kind == "rows":
        table, field = parts
        return rules.unique(row.get(field) for row in doc.get(table) or []), None
    if kind == "back":
        field = parts[0]
        return frappe.get_all(target, filters={field: doc.name}, pluck="name", order_by="creation asc"), \
            {field: doc.name}
    if kind == "back_rows":
        table, field = parts
        child = frappe.get_meta(target).get_field(table).options
        return rules.unique(frappe.get_all(child, filters={field: doc.name, "parenttype": target,
                                                           "parentfield": table},
                                           pluck="parent", order_by="creation asc")), None
    own, theirs = parts
    if not doc.get(own):
        return [], None
    return frappe.get_all(target, filters={theirs: doc.get(own)}, pluck="name", order_by="creation asc"), \
        {theirs: doc.get(own)}


def _readable(target, names):
    """The names, in their order, that are not cancelled and that the user
    may read (frappe.get_list, which applies their permissions)."""
    if not names:
        return []
    allowed = set(frappe.get_list(target, filters={"name": ["in", names], "docstatus": ["!=", 2]},
                                  pluck="name", limit_page_length=0))
    return [name for name in names if name in allowed]
