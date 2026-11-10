# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll in USD posted in shillings to the shilling (Luuka, 10 Nov 2026: "basic pay is in usd the rest supposed
to be posted in UGX").

Frappe HR posts each line of a USD payroll as its dollars at the payroll's rate. A USD slip's lines are shillings
worked out first and then put in dollars to the cent: PAYE, NSSF and LST by the USD structure's formulas, an allowance
or an advance recovered as recorded in shillings. At the rate, those cents come back a few shillings off, so the
taxes owed, the allowances and the advances would not be what they are. Each such line posts the shillings it was
worked out from instead. Basic is paid in dollars and posts as its dollars at the rate, as does any line not worked
out in shillings. The net pay stays in dollars, what the slips pay, and the few shillings between go to the company's
Round Off account.

No Frappe import, like the other *_rules.py modules, so scripts/verify_usd_posting.py runs it without a bench.
"""

DEBIT, CREDIT = "debit_in_account_currency", "credit_in_account_currency"


def line_parts(abbr, worked, recorded=None, abbrs=None):
    """The shillings a USD slip's line was worked out from, each part as it was put in dollars, or None for a line
    paid in dollars. worked: the slip's whole-shilling amounts {lst, paye, employee, employer, cover}; recorded: an
    Additional Salary's amount where it was recorded in shillings; abbrs: the USD structure's line abbreviations
    {cover, lst, paye, nssf, nssf_employer}. Tax Paid by Company is three parts, each put in dollars by itself."""
    if recorded is not None:
        return [recorded]
    names = abbrs or {}
    worked = worked or {}
    if abbr == names.get("cover"):
        return [worked.get("lst"), worked.get("paye"), worked.get("cover")]
    for key, figure in (("lst", "lst"), ("paye", "paye"), ("nssf", "employee"), ("nssf_employer", "employer")):
        if abbr == names.get(key):
            return [worked.get(figure)]
    return None


def exact_line(dollars, rate, parts):
    """What a slip's line posts in shillings: the shillings it was worked out from (parts), where the slip's dollars
    are those shillings at the rate to the cent; otherwise its dollars at the rate."""
    dollars, rate = round(_num(dollars), 2), _num(rate)
    if not parts or rate <= 0 or any(part is None for part in parts):
        return dollars * rate
    if round(sum(round(_num(part) / rate, 2) for part in parts), 2) == dollars:
        return float(sum(_num(part) for part in parts))
    return dollars * rate


def deltas(lines):
    """{(account, cost_center, side, reference): shillings to add}: each line's exact shillings less its dollars at
    the rate, split over its cost centres as Frappe HR splits the line. lines: [{"account", "side" (DEBIT or CREDIT),
    "reference" (an Employee Advance, or None), "dollars", "rate", "parts", "cost_centers": {cost_center: percent}}]."""
    out = {}
    for line in lines or ():
        rate = _num(line.get("rate"))
        gap = exact_line(line.get("dollars"), rate, line.get("parts")) - round(_num(line.get("dollars")), 2) * rate
        if not gap:
            continue
        for cost_center, percent in (line.get("cost_centers") or {None: 100}).items():
            key = (line.get("account"), cost_center, line.get("side"), line.get("reference"))
            out[key] = out.get(key, 0.0) + gap * _num(percent) / 100
    return out


def apply(rows, gaps, home_accounts, round_off=None):
    """The accrual entry's rows with the gaps put on them, and a Round Off row for what is left between debit and
    credit. rows: Frappe HR's rows ({"account", "cost_center", DEBIT or CREDIT, "exchange_rate", "reference_name"});
    home_accounts: the accounts in the company's own currency, the only ones moved; round_off: {"account",
    "cost_center"}. A gap goes on its own account's row for its cost centre, else on that account's largest row on
    its side. Returns (rows, unplaced), unplaced being the gaps no row took."""
    rows = [dict(row) for row in rows or ()]
    unplaced = {}
    for (account, cost_center, side, reference), gap in sorted((gaps or {}).items(), key=lambda item: str(item[0])):
        if account not in (home_accounts or ()):
            unplaced[(account, cost_center, side, reference)] = gap
            continue
        same = [row for row in rows if row.get("account") == account and side in row
                and (row.get("reference_name") or None) == reference]
        row = next((row for row in same if (row.get("cost_center") or None) == cost_center), None)
        if row is None and same:
            row = max(same, key=lambda item: _num(item.get(side)))
        if row is None:
            unplaced[(account, cost_center, side, reference)] = gap
            continue
        row[side] = round(_num(row.get(side)) + gap, 2)
    difference = balance(rows)
    if abs(difference) >= 0.005:
        if not round_off or not round_off.get("account"):
            raise ValueError("no Round Off account")
        side = CREDIT if difference > 0 else DEBIT
        rows.append({"account": round_off["account"], "cost_center": round_off.get("cost_center"),
                     "exchange_rate": 1, side: round(abs(difference), 2)})
    return rows, unplaced


def balance(rows):
    """Debit less credit, in the company's currency, as the Journal Entry works each row out (to the cent)."""
    total = 0.0
    for row in rows or ():
        rate = _num(row.get("exchange_rate")) or 1
        total += round(_num(row.get(DEBIT)) * rate, 2) - round(_num(row.get(CREDIT)) * rate, 2)
    return round(total, 2)


def round_off_message(company):
    return ("Set the Round Off Account of %s (Company > Accounts): a USD payroll's few shillings between its dollars "
            "and its shillings go there." % company)


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
