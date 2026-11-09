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

THE TAX THE COMPANY PAYS

Luuka, 8 Nov 2026, with their own expatriate payroll for September 2026
beside ours: the tax an employer pays for an employee is the employee's
income too (Income Tax Act s.19(1)(c), s.58), so it is taxed as well, and
an allowance is employment income (s.19(1)(a)). The pay is grossed up until
what PAYE and NSSF 5% leave of it is the net agreed: the USD pay at the
month's rate, and the allowance paid in shillings outside the payroll (the
assignment's UGX Allowance). LST is on top, NSSF 5% and 10% on the gross
and LST. The slip's lines are those amounts in USD to the cent, and Tax
Paid by Company is their sum, so the employee is left the USD pay. Luuka's
September figures come out of these formulas to the shilling.

  usd_gross_up_formulas   the USD structure's tax lines, by abbreviation
                          (patches/v1_0/usd_gross_up.py writes them on)
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


# The USD structure's lines, by the abbreviations its import gave them (usd_net_pay.py)
PAY_ABBR, COVER_ABBR = "USDP", "TPBC"        # the USD pay (statistical), the tax the company pays
LST_ABBR, PAYE_ABBR, NSSF_ABBR, NSSF_EMPLOYER_ABBR = "LST", "payee", "NSSFE", "NSSFEC"
# The allowances of a USD salary are added with the assignment's Add Allowance, in shillings, as any employee's
# are (standing_allowances.py; Luuka, 10 Nov 2026: "you have removed the button add allowances?"). The slip pays each
# in USD at the month's rate (SalarySlipCurrency), and the formulas are given their month's total in shillings under
# this name, so the gross-up takes them with the USD pay. Frappe HR never shows a formula an Additional Salary.
ALLOWANCES = "allowances_ugx"
# the assignment field that held the allowance before (28a839f to be1a403), moved onto Add Allowance and removed by
# patch usd_allowances_on_panel; and the structure line be1a403 made of it
OLD_ALLOWANCE_FIELD = "custom_ugx_allowance"
# the component Add Allowance offers first on a USD salary: not cut by the days paid, as the gross-up takes the
# month's allowance whole
ALLOWANCE_COMPONENT, ALLOWANCE_ABBR = "UGX Allowance", "UGXA"
ALLOWANCE_FLAGS = {"type": "Earning", "depends_on_payment_days": 0, "is_tax_applicable": 1,
                   "statistical_component": 0, "do_not_include_in_total": 0}
# the component whose accounts the allowance's are copied from, the first the site has
ALLOWANCE_ACCOUNTS_FROM = ("House Rent Allowance", "Transport Allowance")
# PAYE on a month's chargeable income, the Income Tax (Amendment) Act 2026 bands, each as (up to, rate, less):
# rate x income - less. Up to 335,000 nil; 20% to 410,000; 15,000 + 25% to 485,000; 33,750 + 30% to
# 10,000,000; above it a further 10%.
PAYE_BANDS = ((335000, 0, 0), (410000, 0.2, 67000), (485000, 0.25, 87500), (10000000, 0.3, 111750),
              (None, 0.4, 1111750))
# Local Service Tax a month, July to October, by the month's pay (as the shilling structures have it)
LST_BANDS = ((100000, 0), (200000, 1250), (300000, 2500), (400000, 5000), (500000, 7500), (600000, 10000),
             (700000, 15000), (800000, 17500), (900000, 20000), (1000000, 22500))
LST_MOST, LST_MONTHS = 25000, (7, 8, 9, 10)
NSSF_EMPLOYEE, NSSF_EMPLOYER = 0.05, 0.1
# no NSSF from Payroll Settings' NSSF Age Limit on, unless NSSF Voluntary is ticked (nssf_age_rules: the
# formula is given nssf_age_limit and employee_age, and every employee field)
NSSF_EXEMPT = "nssf_age_limit and employee_age >= nssf_age_limit and not custom_nssf_voluntary"


def _figure(value):
    return "%g" % value


def gross_up_formula(net, nssf):
    """The gross whose PAYE and NSSF (nssf: a rate) leave net, as a formula. Band by band, PAYE is rate x gross
    - less, so net = (1 - rate - nssf) x gross + less, and gross = (net - less) / (1 - rate - nssf) while net is
    within what the band's top leaves."""
    parts = []
    for upto, rate, less in PAYE_BANDS:
        keep = "(%s - %s)" % (_figure(1 - rate), nssf)
        value = "(%s - %d) / %s" % (net, less, keep) if less else "%s / %s" % (net, keep)
        parts.append(value if upto is None else "%s if %s <= %s * %d + %d" % (value, net, keep, upto, less))
    return "(" + " else ".join(parts) + ")"


def paye_formula(chargeable):
    """PAYE on a month's chargeable income on the 2026 bands, as a formula: what the checks hold the grossed-up
    PAYE to."""
    parts = []
    for upto, rate, less in PAYE_BANDS:
        value = "%s * %s - %d" % (_figure(rate), chargeable, less) if rate else "0"
        parts.append(value if upto is None else "%s if %s <= %d" % (value, chargeable, upto))
    return "(" + " else ".join(parts) + ")"


def lst_formula(pay):
    """Local Service Tax a month on a pay, July to October, as a formula."""
    bands = " else ".join("%d if %s <= %d" % (amount, pay, upto) for upto, amount in LST_BANDS)
    return "((%s else %d) if getdate(end_date).month in %s else 0)" % (bands, LST_MOST, str(LST_MONTHS))


def gross_up_amounts(rate="custom_exchange_rate"):
    """The grossed-up amounts in shillings at the month's rate, as formulas: the net is the USD pay and the month's
    allowances; the gross what PAYE and NSSF 5% leave that net of; PAYE the gross less the net and that NSSF (the
    2026 bands on the gross, by the gross-up's own sum); LST on the net, on top; NSSF 5% and 10% on the gross and
    LST, each to the shilling. cover is the NSSF 5% on the gross alone, which the company pays: the 5% on LST is
    the employee's, as Luuka's own expatriate payroll leaves it (1,250 a month on 25,000 of LST)."""
    net = "(%s * %s + (%s or 0))" % (PAY_ABBR, rate, ALLOWANCES)
    nssf = "(0 if %s else %s)" % (NSSF_EXEMPT, _figure(NSSF_EMPLOYEE))
    nssf_employer = "(0 if %s else %s)" % (NSSF_EXEMPT, _figure(NSSF_EMPLOYER))
    gross = gross_up_formula(net, nssf)
    lst = lst_formula(net)
    return {"net": net, "gross": gross, "lst": lst,
            "paye": "floor(%s * (1 - %s) - %s + 0.500001)" % (gross, nssf, net),
            "employee": "floor((%s + %s) * %s + 0.500001)" % (gross, lst, nssf),
            "employer": "floor((%s + %s) * %s + 0.500001)" % (gross, lst, nssf_employer),
            "cover": "floor(%s * %s + 0.500001)" % (gross, nssf),
            # the same before they are rounded, as Luuka's sheet adds them up (usd_sheet_rules.py)
            "paye_exact": "(%s * (1 - %s) - %s)" % (gross, nssf, net),
            "employee_exact": "((%s + %s) * %s)" % (gross, lst, nssf),
            "employer_exact": "((%s + %s) * %s)" % (gross, lst, nssf_employer)}


def usd_gross_up_formulas(rate="custom_exchange_rate"):
    """{abbreviation: (table, formula)}: a USD structure's tax lines, grossed up (gross_up_amounts). Each line is
    its amount in USD to the cent, and Tax Paid by Company the sum of LST, PAYE and the NSSF 5% on the gross, so the
    employee is left the USD pay less the NSSF 5% on LST, as Luuka's own expatriate payroll (Luuka, 9 Nov 2026:
    "please make sure the payroll matches this one")."""
    amounts = gross_up_amounts(rate)

    def usd(amount):
        return "round(%s / %s, 2)" % (amount, rate)

    lines = {LST_ABBR: ("deductions", usd(amounts["lst"])), PAYE_ABBR: ("deductions", usd(amounts["paye"])),
             NSSF_ABBR: ("deductions", usd(amounts["employee"])),
             NSSF_EMPLOYER_ABBR: ("employer_contributions", usd(amounts["employer"]))}
    lines[COVER_ABBR] = ("earnings", " + ".join((lines[LST_ABBR][1], lines[PAYE_ABBR][1], usd(amounts["cover"]))))
    return lines


def allowances_in_company_currency(records, company_currency, rate):
    """What a month's allowances come to in the company's currency, for the gross-up: each recorded in it as it
    stands, one recorded in the slip's currency at the slip's rate. records: [{amount, currency}], the employee's
    Additional Salary earnings the slip pays."""
    total = 0.0
    for record in records or ():
        amount = _num(record.get("amount"))
        if (record.get("currency") or company_currency) != company_currency:
            amount *= _num(rate)
        total += amount
    return round(total, 2)


def additional_amount(amount, additional_currency, slip_currency, company_currency, rate):
    """An Additional Salary's amount on a slip, in the slip's currency: one recorded in the company's currency
    (an advance's recovery, a loan's, a penalty) is divided by the slip's rate on a slip in another currency, to the
    cent. Frappe HR puts the amount on the slip as it stands, whatever its currency, so a 360,000 shilling
    recovery would otherwise come off a USD slip as 360,000 dollars."""
    amount = _num(amount)
    if not foreign(slip_currency, company_currency):
        return amount
    if (additional_currency or company_currency) != company_currency or _num(rate) <= 0:
        return amount
    return round(amount / _num(rate), 2)


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
