# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""PAYE on a second job (secondary_employment.py).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_secondary_employment.py checks it without a bench.

Luuka, 8 Nov 2026: "if someone has two jobs there pay is calculated
different". The Income Tax regulations, in force since 1 July 2012 as URA
says: an employee with more than one employer tells them which is the main
one. The main employer taxes them on the bands; every other employer
withholds a flat rate of their pay, with no tax-free amount. URA restated
the rate as 40% on 9 September 2026. Local Service Tax is deducted before
tax is worked out, so Luuka's register takes 40% of the gross less LST:
an example in the register, 40% of (18,000,000 - 25,000) = 7,190,000.

The rate is Payroll Settings' Secondary Employment PAYE Rate, not written
into a formula (as the NSSF age is not): a salary formula reads it as
secondary_paye_rate. The Employee's Secondary Employment,
custom_secondary_employment, says their main employer is another; the PAYE
line then gives the rate of taxable pay less LST, rounded to the shilling as
the bands are, and the bands for everyone else.
"""

RATE = 40                                  # URA's, until Payroll Settings are saved with the field
RATE_NAME = "secondary_paye_rate"          # Payroll Settings' Secondary Employment PAYE Rate, a percent
SECONDARY = "custom_secondary_employment"  # the Employee's tick: their main employer is another
PAYE_LINES = ("PAYE", "PAYEE")             # the component, by its name before and after Luuka's rename


def rate_of(stored):
    """The rate from what Payroll Settings hold. A Single's field reads
    nothing until the settings are saved with it, so a value never saved is
    URA's 40, not none; never below nought."""
    if stored in (None, ""):
        return RATE
    try:
        return max(float(stored), 0.0)
    except (TypeError, ValueError):
        return 0.0


def worked_from_taxable_pay(formula):
    """Whether a PAYE formula is worked from taxable pay less LST, as Luuka's
    shilling structures are. The USD structure's is worked from the USD pay
    at the month's rate, and is left on its bands."""
    return bool(formula) and "TXP" in formula and "LST" in formula


def secondary_formula(formula):
    """The PAYE line's formula with a second job's flat rate in front of it:
    the same formula where it already reads the rate, where there is none,
    or where it is not worked from taxable pay."""
    if not formula or RATE_NAME in formula or not worked_from_taxable_pay(formula):
        return formula
    return "floor(%s * (TXP - LST) / 100 + 0.500001) if %s else (%s)" % (RATE_NAME, SECONDARY, formula.strip())
