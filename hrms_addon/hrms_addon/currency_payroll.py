# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll in another currency than the company's, on the site.

The rules are in currency_payroll_rules.py, without a Frappe import
(scripts/verify_currency_payroll.py). The structure, its formulas and the
two components it adds are site data (the USD Net Pay import files in
Luuka's payroll folder); this sets the rate they are worked out at.

  payroll_entry_before_validate   a Payroll Entry in USD takes the month's
                                  rate from Currency Exchange, or is refused
  salary_slip_before_validate     so does each of its salary slips, and the
                                  slip's formulas are given it
  assignment_validate             a USD assignment's own formulas (its
                                  preview, its Annual Gross Earning) work at
                                  the latest rate there is
  rate_for                        what pay.monthly_gross converts a USD
                                  gross to shillings with

WHY A FIELD OF ITS OWN

Frappe HR works each formula out twice: on the Salary Structure Assignment,
whose context has no exchange rate, and on the slip, whose fields overlay
the assignment's. The USD formulas read custom_exchange_rate, which both
have; the slip's is its own exchange_rate, set here, so the formulas and the
accounting Frappe HR posts from the slip's exchange_rate use the same rate.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import currency_payroll_rules as rules

EXCHANGE = "Currency Exchange"


def company_currency(company):
    """The company's own currency."""
    return frappe.get_cached_value("Company", company, "default_currency") if company else None


def _rows(from_currency, to_currency, until):
    """The Currency Exchange rows between the two currencies, either way
    round, up to a day."""
    rows = []
    for one, other in ((from_currency, to_currency), (to_currency, from_currency)):
        rows += frappe.get_all(EXCHANGE, filters={"from_currency": one, "to_currency": other,
                                                  "date": ["<=", str(until)]},
                               fields=["from_currency", "to_currency", "exchange_rate", "date"],
                               order_by="date desc", limit_page_length=62)
    return rows


def month_rate(from_currency, to_currency, day):
    """The rate set in the month `day` falls in, or None."""
    _first, last = rules.month_bounds(getdate(day))
    return rules.month_rate(_rows(from_currency, to_currency, last), from_currency, to_currency, getdate(day))


def rate_for(from_currency, to_currency, day=None):
    """The rate to put a gross in USD into shillings with, for the app's own
    figures (advance limits, overtime eligibility, a settlement): the
    month's, else the latest before it; None when there is none."""
    day = getdate(day or today())
    _first, last = rules.month_bounds(day)
    return rules.latest_rate(_rows(from_currency, to_currency, last), from_currency, to_currency, day)


def _strict_rate(doc, day):
    """The month's rate for a payroll document in another currency, or the
    document is refused."""
    home = company_currency(doc.get("company"))
    rate = month_rate(doc.get("currency"), home, day)
    if not rate:
        frappe.throw(_(rules.rate_message(doc.get("currency"), home, getdate(day))), title=_("Exchange Rate"))
    return rate


def payroll_entry_before_validate(doc, method=None):
    """A Payroll Entry in USD is run at the rate set for the month its
    period ends in. Its accounting entry posts at it."""
    if not rules.foreign(doc.get("currency"), company_currency(doc.get("company"))):
        return
    doc.exchange_rate = _strict_rate(doc, doc.get("end_date") or doc.get("posting_date"))


def salary_slip_before_validate(doc, method=None):
    """A salary slip in USD is worked out at the rate set for the month its
    period ends in, and its formulas are given it. A slip in shillings has
    the rate 1 for any formula that asks."""
    if not rules.foreign(doc.get("currency"), company_currency(doc.get("company"))):
        doc.set(rules.RATE_FIELD, 1)
        return
    rate = _strict_rate(doc, doc.get("end_date") or doc.get("posting_date"))
    doc.exchange_rate = rate
    doc.set(rules.RATE_FIELD, rate)


def assignment_validate(doc, method=None):
    """A USD assignment's own working out of its formulas (its preview and
    Annual Gross Earning) at the latest rate there is, 1 where there is
    none yet; the slips are worked out at their own month's."""
    home = company_currency(doc.get("company"))
    if not rules.foreign(doc.get("currency"), home):
        doc.set(rules.RATE_FIELD, 1)
        return
    doc.set(rules.RATE_FIELD, flt(rate_for(doc.get("currency"), home, doc.get("from_date"))) or 1)
