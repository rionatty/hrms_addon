# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll in another currency than the company's: which rate it is run at.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_currency_payroll.py checks it without a bench.
currency_payroll.py reads the site.

Luuka, 14 Oct 2026: some staff are paid in USD "strictly with a different
salary structure", the structure's parts being the pay they take home, the
company paying their PAYE, NSSF and Local Service Tax on top, and "during
the salary processing use the set exchange rate from exchange rate table
for that month".

THE RATE

The rate is the one entered in Currency Exchange in the month the payroll
period ends, the latest of them where there are several. A month with none
stops the payroll: the rate is never guessed. A rate entered the other way
round (UGX to USD) is taken as its inverse.

  month_rate     the rate set in a day's month, or None
  latest_rate    the latest rate up to the end of a day's month, or None:
                 for what only needs a near figure (the gross the app's
                 other modules compare), never for a payroll
  rate_message   what the payroll says when the month has no rate
  foreign        whether a currency is not the company's own
"""

import calendar
import datetime

# the earning that adds the tax the company pays to the pay, so the net pay
# is the structure's parts; it is no salary, and the gross the app's other
# modules read leaves it out
TAX_COVER = "Tax Paid by Company"
# the field the USD formulas read the rate from: both the Salary Structure
# Assignment and the Salary Slip have it, the slip's overlaying the
# assignment's when Frappe HR works a slip out
RATE_FIELD = "custom_exchange_rate"


def foreign(currency, company_currency):
    """Whether a payroll's currency is another than the company's."""
    return bool(currency) and bool(company_currency) and currency != company_currency


def month_bounds(day):
    """The first and the last day of the month `day` falls in."""
    day = _day(day)
    return day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _rate_of(row, from_currency, to_currency):
    """The rate a Currency Exchange row gives from one currency to the
    other: its own, or the inverse of one entered the other way round."""
    rate = _num(row.get("exchange_rate"))
    if rate <= 0:
        return None
    if row.get("from_currency") == from_currency and row.get("to_currency") == to_currency:
        return rate
    if row.get("from_currency") == to_currency and row.get("to_currency") == from_currency:
        return round(1.0 / rate, 9)
    return None


def _ordered(rows, from_currency, to_currency):
    """The rows that give the rate, the latest first; of two on one day,
    the one entered in the payroll's own direction."""
    found = []
    for row in rows or []:
        rate = _rate_of(row, from_currency, to_currency)
        day = _day(row.get("date"))
        if rate and day:
            direct = row.get("from_currency") == from_currency
            found.append((day, 1 if direct else 0, rate))
    return sorted(found, reverse=True)


def month_rate(rows, from_currency, to_currency, day):
    """The rate set in Currency Exchange in the month `day` falls in, the
    latest of that month's; None when the month has none."""
    first, last = month_bounds(day)
    for found, _direct, rate in _ordered(rows, from_currency, to_currency):
        if first <= found <= last:
            return rate
    return None


def latest_rate(rows, from_currency, to_currency, day):
    """The latest rate up to the end of the month `day` falls in; None when
    there is none at all."""
    _first, last = month_bounds(day)
    for found, _direct, rate in _ordered(rows, from_currency, to_currency):
        if found <= last:
            return rate
    return None


def rate_message(from_currency, to_currency, day):
    """What a payroll says when its month has no rate."""
    return "Set the %s to %s rate for %s in Currency Exchange." % (
        from_currency, to_currency, _day(day).strftime("%B %Y"))


def in_company_currency(amount, rate):
    """An amount in the payroll's currency, in the company's, at a rate."""
    return round(_num(amount) * _num(rate), 2)


def _day(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
