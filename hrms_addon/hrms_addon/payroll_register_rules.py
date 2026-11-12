# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One payroll's Salary Register, for the Salary Register tab on the Payroll
Entry (payroll_register.py).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_payroll_register.py exercises it without a bench.

Frappe HR's Salary Register is asked for a period and a company, so it lists
every payroll run in them. On a payroll's own tab (1 Nov 2026; Luuka: "add a
tab for salary register here") it is kept to that payroll's salary slips,
and a salary component none of them has is given no column, as the register
gives none to a component no slip in it has.

The Employees tab shows each employee's figures beside them (Luuka: "under
employee tab add number of working days, paid days, absent, and absent amount
and basic salary", "per employee"), read from their slip. The days are the
calendar's, Sundays and holidays included, as the slip shows them
(pay_days_rules.calendar_days). The Basic Salary is the month's whole Basic,
before anything is taken off for days not paid, as Luuka's own Basic Salary
column has it. A row with no slip yet shows what its slip will
(slip_figures_rules.py).
"""

AMOUNT = "Currency"
# the register's own amounts, shown whatever they come to; every other amount column is a salary component's
TOTALS = ("absent_amount", "gross_pay", "total_loan_repayment", "total_deduction", "net_pay")
# a row of the Employees table's figure, and the slip's field it is read from
SLIP_FIGURES = {"custom_working_days": "custom_days_in_period", "custom_paid_days": "custom_days_paid",
                "custom_absent_days": "absent_days", "custom_absent_amount": "custom_absent_amount",
                # a weekly casual's hours (Luuka, 12 Nov 2026: "add hours worked on the weekly payroll")
                "custom_hours_worked": "custom_weekly_hours"}
BASIC_SALARY = "custom_basic_salary"
# a row with nothing to show: Frappe sends a blank number as nought all the same
NO_FIGURES = dict.fromkeys((*SLIP_FIGURES, BASIC_SALARY), 0)


def register_of(columns, data, slips):
    """(columns, rows): the register's rows for the slips named, and its columns less any salary component none of
    those rows has an amount for."""
    slips = set(slips or ())
    rows = [row for row in data or [] if isinstance(row, dict) and row.get("salary_slip_id") in slips]
    kept = [column for column in columns or [] if isinstance(column, dict) and (
        column.get("fieldtype") != AMOUNT or column.get("fieldname") in TOTALS
        or any(_num(row.get(column.get("fieldname"))) for row in rows))]
    return kept, rows


def sheet(columns, rows, total=False):
    """The register as a spreadsheet's rows: the column labels, then a row per slip, hidden columns left out. With
    `total`, a last row of what each column of figures comes to, as the team's own sheet ends."""
    shown = [column for column in columns or [] if not column.get("hidden")]
    out = [[column.get("label") for column in shown]] + [
        [row.get(column.get("fieldname")) for column in shown] for row in rows or []]
    if total and rows:
        out.append([TOTAL if column.get("fieldname") == TOTAL_UNDER
                    else round(sum(_num(row.get(column.get("fieldname"))) for row in rows), 2) if _summed(column) else None
                    for column in shown])
    return out


# ── A weekly payroll: the casuals' master payroll ─────────────────────
# Luuka, 12 Nov 2026, with the team's own Casual Master Payroll: "i hope the register for casuals it not less than
# this these fields are the most inportnat for casuals, also add overtme hours on it". A weekly payroll's register is
# laid out as that sheet is, a row a casual, in its columns and their order: SrNo, PAYROLL NO, the name, DEPARTMENT,
# HOURS WORKED, WAGE RATE, BASIC, PIECE RATE AMT1 to AMT3, the overtime hours, OT1-AMOUNT, ARREARS, GROSS AMOUNT, SALARY
# ADVANCE, NETT PAY, TIN and NSSF. Every figure is the salary slip's own.
TOTAL, TOTAL_UNDER = "Total", "employee_name"
FIGURES = ("Int", "Float", "Currency")
SERIAL, HOURS, RATE, BASIC_PAY, OVERTIME_HOURS, OVERTIME_PAY, ARREARS_PAY, GROSS, NET, LOAN = (
    "serial", "hours_worked", "wage_rate", "basic", "overtime_hours", "overtime_amount", "arrears", "gross_pay", "net_pay",
    "total_loan_repayment")


def _summed(column):
    return column.get("fieldtype") in FIGURES and not column.get("no_total")


def _column(fieldname, label, fieldtype="Currency", width=140, **more):
    column = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
    if fieldtype == "Currency":
        column["options"] = "currency"
    column.update(more)
    return column


def casual_register(slips, lines, people=None, pieces=None, names=None, abbr=None):
    """(columns, rows) of a weekly payroll's register, laid out as the team's Casual Master Payroll.

    slips: [{"name", "employee", "employee_name", "department", "currency", "hours", "rate", "overtime_hours",
    "gross_pay", "net_pay", "total_loan_repayment"}]; lines: the slips' earnings and deductions, [{"parent", "parentfield",
    "salary_component", "amount", "do_not_include_in_total"}]; people: {employee: {"tin", "nssf"}}; pieces: {slip:
    {size: what was paid for it}}, from the runs that worked the pieces out; names: {"basic", "overtime", "arrears":
    the earning each is paid under, "pieces": the earnings pieces are paid under}; abbr: the company's letters, left
    off a department's name.

    An earning that is none of those, and each deduction, has a column of its own, so the columns of a row add up
    to its gross and its net. Pieces a run does not account for stay under their earning's name. A column of
    earnings or deductions nobody has is left out, as the register leaves out a component no slip has."""
    names, people, pieces = names or {}, people or {}, pieces or {}
    piece_names = set(names.get("pieces") or ())
    known = {names.get("basic"): BASIC_PAY, names.get("overtime"): OVERTIME_PAY, names.get("arrears"): ARREARS_PAY}
    known.pop(None, None)
    sizes = sorted({size for found in pieces.values() for size, value in (found or {}).items() if _num(value)})
    size_field = {size: "piece_%d" % number for number, size in enumerate(sizes, 1)}
    rows, earned, taken = {}, [], []
    for slip in slips or []:
        who = people.get(slip.get("employee")) or {}
        rows[slip.get("name")] = {
            "salary_slip_id": slip.get("name"), "employee": slip.get("employee"),
            "employee_name": slip.get("employee_name"), "department": _plain(slip.get("department"), abbr),
            "currency": slip.get("currency"), HOURS: _num(slip.get("hours")), RATE: _num(slip.get("rate")),
            BASIC_PAY: 0.0, OVERTIME_HOURS: _num(slip.get("overtime_hours")), OVERTIME_PAY: 0.0, ARREARS_PAY: 0.0,
            GROSS: _num(slip.get("gross_pay")), NET: _num(slip.get("net_pay")), "tin": who.get("tin"),
            LOAN: _num(slip.get("total_loan_repayment")),
            "nssf": who.get("nssf"), "_pieces": 0.0}
        for size in sizes:
            rows[slip.get("name")][size_field[size]] = round(_num((pieces.get(slip.get("name")) or {}).get(size)), 2)
    for line in lines or []:
        row, component, value = rows.get(line.get("parent")), line.get("salary_component"), _num(line.get("amount"))
        if row is None or not component or not value:
            continue
        if line.get("parentfield") == "deductions":
            if int(_num(line.get("do_not_include_in_total"))):
                continue
            if component not in taken:
                taken.append(component)
            field = "deduction_%d" % (taken.index(component) + 1)
        elif component in known:
            field = known[component]
        elif component in piece_names:
            field = "_pieces"
        else:
            if component not in earned:
                earned.append(component)
            field = "earning_%d" % (earned.index(component) + 1)
        row[field] = round(_num(row.get(field)) + value, 2)
    # the pieces no run accounts for, under their earning's own name
    loose = False
    for row in rows.values():
        rest = round(row.pop("_pieces") - sum(_num(row.get(size_field[size])) for size in sizes), 2)
        row["piece_rest"] = rest if abs(rest) >= 0.01 else 0.0
        loose = loose or bool(row["piece_rest"])
    ordered = sorted(rows.values(), key=lambda row: (str(row.get("department") or ""), str(row.get("employee_name") or ""),
                                                     str(row.get("employee") or "")))
    for number, row in enumerate(ordered, 1):
        row[SERIAL] = number
    columns = [
        _column(SERIAL, "Sr No", "Int", 70, no_total=1),
        _column("employee", "Payroll No", "Link", 130, options="Employee"),
        _column("employee_name", "Employee Name", "Data", 200), _column("department", "Department", "Data", 180),
        _column(HOURS, "Hours Worked", "Float", 130), _column(RATE, "Wage Rate", "Currency", 130, no_total=1),
        _column(BASIC_PAY, "Basic")]
    columns += [_column(size_field[size], size) for size in sizes]
    if loose:
        columns.append(_column("piece_rest", sorted(piece_names)[0] if len(piece_names) == 1 else "Pieces"))
    columns += [_column(OVERTIME_HOURS, "Overtime Hours", "Float", 140), _column(OVERTIME_PAY, "OT Amount"),
                _column(ARREARS_PAY, "Arrears")]
    columns += [_column("earning_%d" % number, component) for number, component in enumerate(earned, 1)]
    columns.append(_column(GROSS, "Gross Amount"))
    columns += [_column("deduction_%d" % number, component) for number, component in enumerate(taken, 1)]
    # a slip keeps what it repays of a loan apart from its deductions: a column where anybody repays one
    if any(row[LOAN] for row in ordered):
        columns.append(_column(LOAN, "Loan Repayment"))
    columns += [_column(NET, "Net Pay"), _column("tin", "TIN", "Data", 120), _column("nssf", "NSSF", "Data", 140),
                _column("salary_slip_id", "Salary Slip", "Link", 170, options="Salary Slip")]
    for row in ordered:
        for column in columns:
            if column["fieldtype"] in FIGURES:
                row.setdefault(column["fieldname"], 0.0)
    return columns, ordered


def pieces_by_size(paid, lines):
    """{slip: {size: what its pieces came to}}. paid: [{"slip", "source", "employee"}], a slip's pay written by a
    run or a report (its Additional Salary's reference) for one person; lines: that source's own lines, [{"source",
    "employee", "size", "amount"}]. A source is read once for a slip, however many earnings it wrote on it."""
    by_source = {}
    for line in lines or []:
        if line.get("size") and _num(line.get("amount")):
            seat = by_source.setdefault((line.get("source"), line.get("employee")), {})
            seat[line["size"]] = round(_num(seat.get(line["size"])) + _num(line.get("amount")), 2)
    out, seen = {}, set()
    for one in paid or []:
        key = (one.get("slip"), one.get("source"), one.get("employee"))
        if key in seen or not one.get("slip"):
            continue
        seen.add(key)
        for size, value in (by_source.get((one.get("source"), one.get("employee"))) or {}).items():
            seat = out.setdefault(one["slip"], {})
            seat[size] = round(_num(seat.get(size)) + value, 2)
    return out


def _plain(department, abbr):
    """A department without the company's letters ERPNext puts after it ("Extrusion - LPL")."""
    label, tail = str(department or ""), " - %s" % abbr if abbr else ""
    return label[:-len(tail)] if tail and label.endswith(tail) and len(label) > len(tail) else label


def figures_of(slips, basics):
    """{employee: the figures for their row of the Employees table}. slips: the payroll's, with their name, employee
    and the fields SLIP_FIGURES names; basics: {slip name: the month's Basic on it}."""
    figures = {}
    for slip in slips or []:
        row = {field: _num(slip.get(source)) for field, source in SLIP_FIGURES.items()}
        row[BASIC_SALARY] = _num((basics or {}).get(slip.get("name")))
        figures[slip.get("employee")] = row
    return figures


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
