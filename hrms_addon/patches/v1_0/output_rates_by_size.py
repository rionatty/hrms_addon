# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Per Meter by size, not machine (Luuka, 30 Sep 2026).

1. The six sizes on Luuka's PER METER AUGUST 2026 sheet, each with its
   Work Unit from the first day of that month, in the sheet's order
   (output_rules.SHEET_SIZES). A size already there is left as it is.
2. Each piece category the Per Piece machines carried becomes a category
   of its own, with the rates it had and the day each started; where two
   machines priced the same category differently from the same day, the
   first found stands and the Error Log says so.

The machines themselves go: their DocTypes are no longer in the app, and
migrate takes them off the site after the patches (their tables stay,
untouched). Reports and runs made before keep what they recorded.

Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import output_rules as rules

SIZE = "Output Rate"


def execute():
    if not frappe.db.exists("DocType", SIZE):
        return
    for order, (label, unit) in enumerate(rules.SHEET_SIZES, 1):
        _add(label, rules.PER_METER, [{"work_unit": unit, "valid_from": rules.SHEET_FROM}], order)
    categories, clashes = {}, []
    for row in _machine_rates():
        rates = categories.setdefault(row.piece_category.strip(), {})
        start = str(row.valid_from)
        if start in rates and float(rates[start]) != float(row.rate):
            clashes.append("%s from %s: %s and %s" % (row.piece_category, start, rates[start], row.rate))
            continue
        rates.setdefault(start, row.rate)
    for order, (category, rates) in enumerate(sorted(categories.items()), 1):
        _add(category, rules.PER_PIECE, [{"work_unit": rate, "valid_from": start}
                                         for start, rate in sorted(rates.items())], order)
    if clashes:
        frappe.log_error(title="HRMS Addon: piece categories priced twice on the same day",
                         message="The first price found was kept:\n" + "\n".join(clashes))


def _machine_rates():
    """The Per Piece machines' categories, read from their tables while the
    tables are still there."""
    if not (frappe.db.table_exists("Machine Rate") and frappe.db.table_exists("Production Machine")):
        return []
    return frappe.db.sql(
        """select rate.piece_category, rate.rate, rate.valid_from
        from `tabMachine Rate` rate join `tabProduction Machine` machine on machine.name = rate.parent
        where machine.section = 'Per Piece' and ifnull(rate.piece_category, '') != ''
            and rate.valid_from is not null and ifnull(rate.rate, 0) > 0
        order by machine.creation, rate.idx""", as_dict=True)


def _add(size, section, rates, order):
    if frappe.db.exists(SIZE, size):
        return
    doc = frappe.get_doc({"doctype": SIZE, "size": size, "section": section, "sheet_order": order,
                          "enabled": 1, "rates": rates})
    doc.flags.ignore_permissions = True
    doc.insert()
