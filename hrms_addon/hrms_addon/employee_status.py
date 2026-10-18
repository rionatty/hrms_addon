# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Each employee's Status as Luuka names it, and Frappe's own kept to it.

The rules, and why Frappe's four stay underneath, are in
employee_status_rules.py (scripts/verify_employee_status.py). The statuses
are Employee Status records, HR's to add to: each says which of Frappe's four
it counts as.

  employee_before_validate  Employee, before Frappe's own validation: the
                            System Status from the Status picked, or the
                            Status from a System Status moved by itself
  move                      a System Status set without a save (a
                            suspension), and the Status with it
  exit_status               the status an exit for this reason leaves
  reconcile                 daily and after migrate: every employee's Status
                            in step with their System Status
  install                   after migrate: Frappe's four as statuses, and
                            every employee given theirs
  install_luuka             once (patch employee_statuses): Luuka's own
  statuses                  for the boot: each status, what it counts as,
                            its colour in the Employee list
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import employee_status_rules as rules

DOCTYPE = "Employee Status"
FIELD = "custom_employee_status"


def _ready():
    return frappe.db.exists("DocType", DOCTYPE) and frappe.get_meta("Employee").has_field(FIELD)


def _statuses():
    """[(status, what it counts as, disabled)], read once a request."""
    found = getattr(frappe.local, "ha_employee_statuses", None)
    if found is None:
        found = []
        if frappe.db.exists("DocType", DOCTYPE):
            found = [(row.name, row.counts_as, row.disabled) for row in frappe.get_all(
                DOCTYPE, fields=["name", "counts_as", "disabled"], limit_page_length=0)]
        frappe.local.ha_employee_statuses = found
    return found


def counts():
    """{status: what it counts as}, those no longer used as well: employees
    may still have them."""
    return {name: counts_as for name, counts_as, _off in _statuses()}


def disabled():
    """The statuses no longer used: nobody is given one again."""
    return {name for name, _counts_as, off in _statuses() if off}


def forget():
    frappe.local.ha_employee_statuses = None


def employee_before_validate(doc, method=None):
    """Before Frappe's own validation, so its rules for Left (a relieving
    date, nobody still reporting to them) hold for every status that counts
    as Left."""
    if not frappe.get_meta(doc.doctype).has_field(FIELD):
        return
    known = counts()
    if not known:
        return
    before = doc.get_doc_before_save()
    was = (before.get("status"), before.get(FIELD)) if before else None
    picked = doc.get(FIELD)
    status, chosen = rules.settle(doc.get("status"), picked, was, known)
    if picked and chosen == picked and picked != (was[1] if was else None) and picked in disabled():
        frappe.throw(_("The status {0} is no longer used: choose another.").format(picked), title=_("Status"))
    doc.status = status
    doc.set(FIELD, chosen)


def move(employee, status):
    """A System Status set without a save (suspensions.py): the Status with
    it, kept while it still counts as the new one."""
    values = {"status": status}
    if _ready() and counts():
        values[FIELD] = rules.moved(frappe.db.get_value("Employee", employee, FIELD), status, counts())
    frappe.db.set_value("Employee", employee, values, update_modified=False)


def exit_status(reason):
    """The status an exit for this reason leaves the employee in (exits.py):
    None on a site without the statuses."""
    if not (_ready() and counts()):
        return None
    return rules.exit_status(reason, counts(), disabled())


def reconcile():
    """Daily and after migrate: an employee whose Status is empty (one from
    before the Status, or imported without it) or no longer counts as their
    System Status (one set without a save, by Frappe HR's transfer to another
    company say) is given the Status of their System Status."""
    if not _ready():
        return 0
    rows = frappe.get_all("Employee", fields=["name", "status", FIELD], limit_page_length=0)
    fixed = rules.drift(rows, counts())
    for name, chosen in fixed:
        frappe.db.set_value("Employee", name, FIELD, chosen, update_modified=False)
    return len(fixed)


def _make(name, counts_as, standard):
    if frappe.db.exists(DOCTYPE, name):
        return
    frappe.get_doc({"doctype": DOCTYPE, "status_name": name, "counts_as": counts_as,
                    "is_standard": 1 if standard else 0}).insert(ignore_permissions=True)


def install():
    """after_migrate: Frappe's four, each a status counting as itself, and
    every employee given their Status."""
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    for name in rules.BASE:
        _make(name, name, True)
    forget()
    reconcile()


def install_luuka():
    """Once (patch employee_statuses): the statuses Luuka's records use.
    After that the list is HR's: one taken off is not put back."""
    install()
    for name, counts_as in rules.LUUKA:
        _make(name, counts_as, False)
    forget()


def statuses():
    """{status: {"counts_as", "colour"}} for the boot (the Employee list's
    colours). Nothing on a site without the statuses."""
    try:
        if not frappe.db.exists("DocType", DOCTYPE):
            return {}
        rows = frappe.get_all(DOCTYPE, fields=["name", "counts_as", "colour"], limit_page_length=0)
        known = {row.name: row.counts_as for row in rows}
        colours = {row.name: row.colour for row in rows}
        return {name: {"counts_as": known[name], "colour": rules.colour_of(name, known, colours)} for name in known}
    except Exception:
        return {}
