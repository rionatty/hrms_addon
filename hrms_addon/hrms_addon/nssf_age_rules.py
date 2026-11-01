# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""No NSSF from the age the NSSF Act sets, unless the employee pays on
voluntarily (nssf_age.py).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_nssf_age.py exercises it without a bench.

The NSSF Act (Chapter 222) s.6(1): an eligible employee is "any employee of
or above the age of sixteen and below the age of fifty-five years". From
that age neither the employee's 5% nor the employer's 10% is due. The age is
Payroll Settings' NSSF Age Limit, not written into a formula (1 Nov 2026,
Luuka: "add a place holder no hardcoding it"): a salary formula reads it as
nssf_age_limit, and the employee's age at the end of the pay period as
employee_age. An employee past it who still wants to pay (Luuka: "this
should be per employee") has NSSF Voluntary ticked, custom_nssf_voluntary,
and both lines go on as before.
"""

import datetime

AGE_LIMIT = 55                       # the Act's, until Payroll Settings are saved with the field
LIMIT = "nssf_age_limit"             # Payroll Settings' NSSF Age Limit, 0 for none
AGE = "employee_age"                 # whole years at the end of the period, 0 where no date of birth is known
VOLUNTARY = "custom_nssf_voluntary"  # the Employee's NSSF Voluntary: pays on past the limit
NSSF_LINES = ("NSSF Employee", "NSSF Employer 10%")


def age_on(birth, on):
    """Whole years from a date of birth to a day; 0 where either is unknown or the birth is after the day."""
    birth, on = _day(birth), _day(on)
    if not birth or not on or birth > on:
        return 0
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def limit_of(stored):
    """The NSSF Age Limit from what Payroll Settings hold. A Single's field reads nothing until the settings are
    saved with it, so a value never saved is the Act's age, not "no limit"; never below nought."""
    if stored in (None, ""):
        return AGE_LIMIT
    try:
        return max(int(float(stored)), 0)
    except (TypeError, ValueError):
        return 0


def exempt_formula(formula):
    """An NSSF line's formula that gives nothing from the age limit on, unless the employee pays voluntarily: the
    same formula where it already reads the limit, or where there is none."""
    if not formula or LIMIT in formula:
        return formula
    return "0 if %s and %s >= %s and not %s else (%s)" % (LIMIT, AGE, LIMIT, VOLUNTARY, formula.strip())


def _day(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
