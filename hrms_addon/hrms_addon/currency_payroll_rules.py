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
period ends, the latest of them where there are several. A rate entered the
other way round (UGX to USD) is taken as its inverse. A month with none
takes the rate set on its payroll, saved in Currency Exchange as the
month's (Luuka, 8 Nov 2026), so every payroll and slip of the month is
worked out at one rate. A payroll with no rate either is refused, and a
slip never sets one: the rate is never guessed.

  month_rate     the rate set in a day's month, or None
  latest_rate    the latest rate up to the end of a day's month, or None:
                 for what only needs a near figure (the gross the app's
                 other modules compare), never for a payroll
  payroll_rate   the rate a payroll is run at, and whether it is saved as
                 its month's
  rate_message   what a slip says when its month has no rate
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


# what a payroll does with the rate it shows (payroll_rate)
RECORD, MONTHS, REFUSE = "record", "month", "refuse"


def payroll_rate(shown, month):
    """The rate a payroll in another currency is run at, and what that
    takes: (rate, step).

    shown: the rate on the payroll; month: its month's in Currency
    Exchange, or None. A month with a rate runs every payroll of the month
    at it, the step MONTHS when the payroll showed another (Frappe HR fills
    the field with today's rate when the currency is picked): a month's
    rate is changed in Currency Exchange. A month with none takes the
    payroll's own, the step RECORD, which saves it as the month's. With a
    rate on neither, the step REFUSE."""
    shown, month = _num(shown), _num(month)
    if month > 0:
        return month, (None if round(shown, 9) == round(month, 9) else MONTHS)
    if shown > 0:
        return shown, RECORD
    return None, REFUSE


def show_rate(rate):
    """A rate as it is read: 4,061.72, 3,700, 0.00027."""
    return "{:,.6f}".format(_num(rate)).rstrip("0").rstrip(".")


def recorded_message(from_currency, to_currency, rate, day):
    """What a payroll says when its rate is saved as its month's."""
    return "1 %s = %s %s saved for %s in Currency Exchange." % (
        from_currency, show_rate(rate), to_currency, _day(day).strftime("%B %Y"))


def month_message(from_currency, to_currency, rate, day):
    """What a payroll says when it is run at its month's rate rather than
    the one it showed."""
    return "Run at the rate set for %s in Currency Exchange: 1 %s = %s %s. Change it there if it is wrong." % (
        _day(day).strftime("%B %Y"), from_currency, show_rate(rate), to_currency)


def payroll_rate_message(from_currency, to_currency, day):
    """What a payroll says when neither it nor its month has a rate."""
    return "Enter the exchange rate for %s: 1 %s in %s." % (_day(day).strftime("%B %Y"), from_currency, to_currency)


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
