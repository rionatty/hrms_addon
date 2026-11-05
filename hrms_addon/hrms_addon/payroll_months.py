# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The months of a payroll year, each open or closed: the rules are in
payroll_month_rules.py (scripts/verify_payroll_months.py).

  year_validate     Payroll Period validate: its months made from its dates
  open_months       the list a monthly payroll's Period is picked from
  payroll_validate  Payroll Entry validate: a monthly payroll runs for an open
                    month of its company
  refuse_closed     a salary slip saved, and a payroll or slip cancelled or
                    deleted, in a closed month; and Recreate Salary Slips
  fill_on_migrate   after_migrate: a year saved before there were months gets them

A slip is refused only for a closed month, not for one that is missing: a slip of
a month no year covers has been made by now or it would not be there.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime

from hrms_addon.hrms_addon import payroll_month_rules as rules
from hrms_addon.hrms_addon import payslip_rules

YEAR = "Payroll Period"
MONTH = "Payroll Month"
TABLE = "custom_months"
MONTHLY = "Monthly"


def year_validate(doc, method=None):
    """Whatever was sent, the rows are the year's months. Only their status comes from the form."""
    before = doc.get_doc_before_save()
    stored = (before.get(TABLE) if before else None) or []
    months = payslip_rules.months_of(doc.get("start_date"), doc.get("end_date"))
    lost = rules.dropped_closed(months, stored)
    if lost:
        frappe.throw(_("{0} would be lost with these dates, and closed. Open it first.").format(", ".join(lost)), title=_(YEAR))
    rows = rules.rows_for_year(months, doc.get(TABLE), stored, frappe.session.user, now_datetime())
    doc.set(TABLE, [])
    for row in rows:
        doc.append(TABLE, row)


@frappe.whitelist()
def open_months(company=None):
    """The company's open months, the first still to run first."""
    return rules.listed((_months(company) or {}).values())


def _months(company):
    """{(first day, last day): the month} for a company, read once in a job or request: a payroll's slips all ask. None on a
    site that has the code and has not been migrated yet, where there is nothing to go by."""
    known = getattr(frappe.local, "ha_payroll_months", None)
    if known is None:
        known = frappe.local.ha_payroll_months = {}
    if company not in known:
        if not frappe.db.table_exists(MONTH):
            return None
        years = frappe.get_all(YEAR, filters={"company": company}, pluck="name", limit_page_length=0)
        rows = frappe.get_all(MONTH, filters={"parenttype": YEAR, "parent": ["in", years]}, limit_page_length=0,
                              fields=["parent", "period_name", "start_date", "end_date", "status"]) if years else []
        known[company] = {(getdate(row.start_date), getdate(row.end_date)): row for row in rows}
    return known[company]


def _month_of(doc):
    """(the name of the month, the month if there is one) of a payroll or slip; None for one that runs on no month."""
    if (doc.get("payroll_frequency") or MONTHLY) != MONTHLY or cint(doc.get("salary_slip_based_on_timesheet")):
        return None
    start, end = doc.get("start_date"), doc.get("end_date")
    name = payslip_rules.period_name(start, end)
    months = _months(doc.get("company")) if name else None
    if months is None:
        return None
    return name, months.get((getdate(start), getdate(end)))


def payroll_validate(doc, method=None):
    found = _month_of(doc)
    problem = rules.why_not_open(found[0], found[1], doc.get("company")) if found else None
    if problem:
        frappe.throw(_(problem), title=_(YEAR))


def refuse_closed(doc, method=None):
    found = _month_of(doc)
    problem = rules.why_closed(found[0], found[1]) if found else None
    if problem:
        frappe.throw(_(problem), title=_(YEAR))


def fill_on_migrate():
    if not frappe.db.table_exists(MONTH):
        return
    for name in frappe.get_all(YEAR, pluck="name", limit_page_length=0):
        if frappe.db.exists(MONTH, {"parenttype": YEAR, "parent": name}):
            continue
        try:
            frappe.get_doc(YEAR, name).save(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="Payroll Period %s: its months" % name)
