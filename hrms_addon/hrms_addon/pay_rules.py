# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What an employee's monthly gross is made of.

The salary structure works out most of it (pay.py). An allowance paid every
month outside the structure, as a recurring Additional Salary, is part of
the gross all the same: it is on every month's slip. House Rent and
Transport are paid that way at Luuka, their own slip counts both in GROSS
PAY, and the salary advance is 40% of that figure, not of the Basic. A
payment made once (overtime, a bonus, an arrear) is not part of it: it is
not what the employee earns in a month.

  standing        the recurring earnings in force on a day
  gross_per_period the structure's gross for a pay period with them added,
                  the way a salary slip adds them: on top of the structure,
                  or in the place of the structure's own amount for that
                  component when the Additional Salary says it overwrites it
  per_month       a pay period's amount as a month's

No Frappe import: scripts/verify_pay.py loads this file on its own.
"""

import datetime

EARNING = "Earning"
# pay periods in a year, by the salary structure's payroll frequency
PERIODS_PER_YEAR = {"Monthly": 12, "Fortnightly": 26, "Bimonthly": 24, "Weekly": 52, "Daily": 365}


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def standing(rows, day, not_counted=()):
    """The Additional Salary rows that are part of the gross on `day`.

    rows: {"salary_component", "amount", "type", "is_recurring", "disabled",
    "from_date", "to_date", "overwrite"}. A row counts when it is an
    earning paid every period (recurring), not disabled, in force on the
    day, of more than nothing, and of a component the slip counts in its
    gross (`not_counted` names the statistical ones and those left out of
    the totals)."""
    day = _date(day)
    kept = []
    for row in rows or []:
        if (row.get("type") or EARNING) != EARNING or not int(_num(row.get("is_recurring"))):
            continue
        if int(_num(row.get("disabled"))) or row.get("salary_component") in not_counted:
            continue
        start, end = _date(row.get("from_date")), _date(row.get("to_date"))
        if not day or not start or start > day or (end and end < day):
            continue
        if _num(row.get("amount")) <= 0:
            continue
        kept.append(row)
    return kept


def gross_per_period(structure_gross, allowances, structure_amounts=None):
    """The gross of one pay period: the structure's, and each standing
    allowance on top of it. One that overwrites a component the structure
    already pays takes that component's place instead of adding to it.

    structure_amounts: {component: what the structure pays for it}."""
    structure_amounts = structure_amounts or {}
    gross = _num(structure_gross)
    replaced = set()
    for row in allowances or []:
        component, amount = row.get("salary_component"), _num(row.get("amount"))
        if int(_num(row.get("overwrite"))) and component in structure_amounts and component not in replaced:
            gross += amount - _num(structure_amounts[component])
            replaced.add(component)
        else:
            gross += amount
    return round(gross, 2)


def per_month(amount, frequency=None):
    """A pay period's amount as a month's: a weekly structure pays 52 times a
    year, and a month is a twelfth of that."""
    periods = PERIODS_PER_YEAR.get(frequency or "Monthly", 12)
    return round(_num(amount) * periods / 12.0, 2)


def periods_in_year(frequency=None):
    return PERIODS_PER_YEAR.get(frequency or "Monthly", 12)
