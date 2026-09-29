# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Frappe HR's Salary Structure and Salary Structure Assignment on the site,
once other documents point at them (salary_structure_rules.py).

  keep_records        Salary Structure Assignment and Salary Structure
                      on_cancel: the onboarding and the position change that
                      keep them as a record do not stop the cancel, and are
                      not cancelled with it (the forms leave them off the
                      Cancel All list too)
  follow_replacement  Salary Structure Assignment on_submit: the assignment
                      that replaces a cancelled one takes its place on them
  rows_after_submit   Salary Structure before_update_after_submit: a
                      component added to a submitted structure is checked
                      and filled in as before submit, and the totals follow;
                      none is taken off
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import salary_structure_rules as rules

ASSIGNMENT = "Salary Structure Assignment"


def keep_records(doc, method=None):
    """Cancelling an assignment (or a structure) to correct it: the records
    that keep it are not linked documents to cancel first."""
    doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + rules.RECORDS


def follow_replacement(doc, method=None):
    """A submitted assignment takes the place of the cancelled one it
    replaces on the onboarding and the position change that kept it; one
    cancelled itself stays as it was."""
    candidates = frappe.get_all(ASSIGNMENT, filters={"employee": doc.employee, "docstatus": 2},
                                fields=["name", "employee", "from_date", "amended_from"])
    mine = {"name": doc.name, "employee": doc.employee, "from_date": doc.get("from_date"),
            "amended_from": doc.get("amended_from")}
    replaced = [row.name for row in candidates if rules.replaced(row, mine)]
    if not replaced:
        return
    for doctype, field in rules.ASSIGNMENT_LINKS:
        if not frappe.get_meta(doctype).has_field(field):
            continue
        for name in frappe.get_all(doctype, filters={field: ["in", replaced], "docstatus": ["!=", 2]}, pluck="name"):
            frappe.db.set_value(doctype, name, field, doc.name, update_modified=False)


def rows_after_submit(doc, method=None):
    """A submitted structure takes a new component, checked and filled in
    as Frappe HR does before submit; none is taken off. The totals follow
    the rows, as the form works them out."""
    before = doc.get_doc_before_save()
    if not before:
        return
    had, now = _rows(before), _rows(doc)
    gone = rules.removed_rows(had, now)
    if gone:
        frappe.throw(_("A component cannot be taken off a submitted salary structure: {0}. To stop one, give it "
                       "the condition 0.").format(", ".join(row[2] or "" for row in gone)),
                     title=_("Salary Structure"))
    added = rules.added_rows(had, now)
    if not added:
        return
    new = []
    for table, rows in added.items():
        for found in rows:
            row = _row(doc, table, found)
            component = frappe.db.get_value("Salary Component", row.salary_component, list(rules.COMPONENT_FIELDS),
                                            as_dict=True) if row.salary_component else None
            filled = rules.defaults_for(row.as_dict(), component)
            for field, value in filled.items():
                row.set(field, value)
            if "formula" in filled:
                # Frappe HR's structure read the formulas before this hook and
                # puts back what it read once saved (reset_condition_and_formula_fields)
                row._formula = row.formula
            new.append((table, row, component))
    abbrs = [row.get("abbr") for table in rules.TABLES for row in doc.get(table) or []
             if row.get("depends_on_payment_days")]
    others = {table: [row.salary_component for row in before.get(table) or []] for table in rules.TABLES}
    errors = []
    for table, row, component in new:
        errors += rules.row_errors(table, row.as_dict(), component, others[table], abbrs)
        others[table].append(row.salary_component)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Salary Structure"))
    doc.update(rules.totals([row.get("amount") for row in doc.get("earnings") or []],
                            [row.get("amount") for row in doc.get("deductions") or []],
                            doc.get("salary_slip_based_on_timesheet")))


def _rows(doc):
    return {table: [{"name": row.name, "idx": row.idx, "salary_component": row.salary_component}
                    for row in doc.get(table) or [] if not row.is_new()] +
            [{"name": None, "idx": row.idx, "salary_component": row.salary_component, "_row": row}
             for row in doc.get(table) or [] if row.is_new()]
            for table in rules.TABLES}


def _row(doc, table, found):
    if found.get("_row") is not None:
        return found["_row"]
    return next(row for row in doc.get(table) or [] if row.name == found.get("name"))
