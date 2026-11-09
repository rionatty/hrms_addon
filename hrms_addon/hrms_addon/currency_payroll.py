# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll in another currency than the company's, on the site.

The rules are in currency_payroll_rules.py, without a Frappe import
(scripts/verify_currency_payroll.py). The structure, its formulas and the
two components it adds are site data (the USD Net Pay import files in
Luuka's payroll folder); this sets the rate they are worked out at.

  payroll_entry_before_validate   a Payroll Entry in USD takes the month's
                                  rate from Currency Exchange; a month with
                                  none takes the payroll's own, saved there
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
    period ends in, and its accounting entry posts at it. A month with none
    takes the rate on the payroll, saved in Currency Exchange as the
    month's, so its slips and the month's other payrolls are worked out at
    it too (rules.payroll_rate)."""
    home = company_currency(doc.get("company"))
    if not rules.foreign(doc.get("currency"), home):
        return
    day = getdate(doc.get("end_date") or doc.get("posting_date"))
    rate, step = rules.payroll_rate(doc.get("exchange_rate"), month_rate(doc.get("currency"), home, day))
    if step == rules.REFUSE:
        frappe.throw(_(rules.payroll_rate_message(doc.get("currency"), home, day)), title=_("Exchange Rate"))
    if step == rules.RECORD:
        _save_rate(doc.get("currency"), home, rate, day)
        frappe.msgprint(_(rules.recorded_message(doc.get("currency"), home, rate, day)), title=_("Exchange Rate"),
                        indicator="green")
    elif step == rules.MONTHS:
        frappe.msgprint(_(rules.month_message(doc.get("currency"), home, rate, day)), title=_("Exchange Rate"),
                        indicator="orange")
    doc.exchange_rate = rate


def _save_rate(from_currency, to_currency, rate, day):
    """A payroll's rate entered in Currency Exchange as its month's, dated
    the day its period ends, for buying and selling as a new one starts.
    Saved for whoever runs the payroll, who may not keep Currency Exchange
    themselves."""
    frappe.get_doc({"doctype": EXCHANGE, "date": str(day), "from_currency": from_currency,
                    "to_currency": to_currency, "exchange_rate": rate, "for_buying": 1,
                    "for_selling": 1}).insert(ignore_permissions=True)


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


def month_allowances(employee, start, end, company, rate):
    """The employee's Additional Salary earnings a slip of these days pays (Add Allowance's, and any other), in the
    company's currency: what the USD gross-up takes with the USD pay (rules.ALLOWANCES). As Frappe HR picks them for a
    slip: submitted, not disabled, a one-off dated in the days, a recurring one running on any of them."""
    if not (employee and start and end):
        return 0.0
    fields = ["amount", "currency"]
    common = {"employee": employee, "docstatus": 1, "disabled": 0, "type": "Earning"}
    records = frappe.get_all("Additional Salary", filters=dict(common, is_recurring=0,
                                                               payroll_date=["between", [start, end]]),
                             fields=fields, limit_page_length=0)
    records += frappe.get_all("Additional Salary", filters=dict(common, is_recurring=1, from_date=["<=", end],
                                                                to_date=[">=", start]),
                              fields=fields, limit_page_length=0)
    return rules.allowances_in_company_currency(records, company_currency(company), rate)


class SalarySlipCurrency:
    """An Additional Salary in shillings on a slip in USD, in USD at the slip's rate (rules.additional_amount).
    Frappe HR adds an Additional Salary's amount as it stands (salary_slip.add_additional_salary_components), and
    the app's advance, loan and penalty recoveries are recorded in the company's currency.

    Its formulas are given the month's allowances in shillings (rules.ALLOWANCES), which Frappe HR never shows a
    formula, so the USD gross-up takes them with the USD pay; 0 on a slip in shillings."""

    def get_data_for_eval(self):
        data, default_data = super().get_data_for_eval()
        value = 0.0
        foreign = rules.foreign(self.get("currency"), company_currency(self.get("company")))
        if foreign:
            value = month_allowances(self.get("employee"), self.get("start_date"), self.get("end_date"),
                                     self.get("company"), self.get(rules.RATE_FIELD) or self.get("exchange_rate"))
        data[rules.ALLOWANCES] = value
        default_data[rules.ALLOWANCES] = value
        if foreign:
            self._statistical_earnings(data, default_data)
        return data, default_data

    def _statistical_earnings(self, data, default_data):
        """The structure's statistical earnings (the USD pay, USDP) put in the formulas' data, worked out as Frappe
        HR's earnings pass works them out. Frappe HR v16 builds the data afresh for each table from the slip's rows
        (salary_slip.add_structure_components), and a statistical earning has no row, so a deduction found the USD
        pay 0: PAYE, NSSF and LST came to the allowances' alone (Luuka, 10 Nov 2026)."""
        if not getattr(self, "_evaluated_components", None):
            if not hasattr(self, "_set_evaluated_components"):
                return
            self._set_evaluated_components()
        for row in self._evaluated_components.get("earnings") or ():
            if not (row.get("statistical_component") or row.get("accrual_component")):
                continue
            amount = self.eval_condition_and_formula(row, data)
            default_data[row.abbr] = flt(amount)
            if row.get("depends_on_payment_days"):
                days = flt(self.get("total_working_days"))
                amount = flt(amount) * flt(self.get("payment_days")) / days if days else 0
                data[row.abbr] = flt(amount, row.get("precision"))

    def update_component_row(self, component_data, amount, component_type, additional_salary=None, *args,
                             **kwargs):
        if additional_salary and additional_salary.get("name"):
            home = company_currency(self.get("company"))
            if rules.foreign(self.get("currency"), home):
                recorded = frappe.db.get_value("Additional Salary", additional_salary.name, "currency")
                amount = rules.additional_amount(amount, recorded, self.get("currency"), home,
                                                 self.get(rules.RATE_FIELD) or self.get("exchange_rate"))
        return super().update_component_row(component_data, amount, component_type, additional_salary, *args,
                                            **kwargs)


class SalaryStructureAssignmentCurrency:
    """The assignment's own working out of its formulas (its preview, its Annual Gross Earning, pay.monthly_gross)
    is given the allowances of the pay period Frappe HR works it out for (the one its first day falls in), in
    shillings, under the name the slip gives them; 0 on an assignment in shillings. Without it a USD formula would
    find no such name."""

    def _get_component_eval_context(self):
        data = super()._get_component_eval_context()
        value = 0.0
        if rules.foreign(self.get("currency"), company_currency(self.get("company"))):
            value = month_allowances(self.get("employee"), data.get("start_date") or self.get("from_date"),
                                     data.get("end_date") or self.get("from_date"), self.get("company"),
                                     self.get(rules.RATE_FIELD))
        data[rules.ALLOWANCES] = value
        return data
