# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Luuka's Per Piece workbook, read (openpyxl, no Frappe import, so
scripts/verify_piece_pay.py reads one without a bench).

THE LAYOUT, AS LUUKA KEEPS IT (PET PACKAGING BOTTLES)

One sheet a week, named for its days: "29th-Oct-04th-Nov-26",
"22nd-28th-October-2026", Thursday to Wednesday.

  row 1   the week again, as a title: sometimes left from the week before,
          so the sheet's name is what dates it
  row 2   NAME; NUMBER OF BAGS PACKED over the bag columns; AMOUNT PER BAG
          PACKED over their amounts; TOTAL AMOUNT; ARREARS
  row 3   NO.; over each bag column the price of a bag (200, 180, 170)
  then    a row a person: the name, the bags at each price, the amounts
          (formulas), the total and any arrears
  last    TOTAL

READING ONE

The columns are found by their headings: the person by NAME, or by an
Employee Id column where a sheet has one; the bags by the heading over them
(BAGS or PIECES), as far as the AMOUNT heading; each bag column's price is
the number under it. A sheet is dated by its name, else by its title; one
dated by neither (EXTRA LABOUR) is named as unread. Only the weeks asked for
have their rows read, so a workbook of four years reads quickly. Whatever is
on them is checked by output_rules.take_pieces.
"""

import datetime
import io
import re
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
          "nov": 11, "dec": 12}
# the headings a column is found by, in the row that has NAME
NAME = ("name", "names", "emp names", "employee name")
# Luuka's casual worksheet heads its Employee Id column PAYROLL NO
EMPLOYEE_ID = ("employee id", "emp id", "emp no", "emp. no", "employee no", "employee number", "id no", "payroll no")
# Luuka's Per Piece template has no such column: its NO. holds the employee number (Luuka, 11 Nov 2026: "this is the
# client template", the number "in the NO. column"). It is headed on the NAME row or on the prices' row below it
NUMBER = ("no.", "no", "s/no", "s.no", "sn")
BAGS = ("bag", "piece")
AMOUNT = ("amount per",)
TOTAL = ("total amount", "total")
ARREARS = ("arrear",)
# a week runs Thursday to Wednesday; a span outside this is a misread name
WEEK_DAYS = (5, 9)
HEADER_ROWS = 10


MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")


def week_title(start, end):
    """A week as Luuka's template titles it, and as week_of reads it back: 03rd-09th-September-2026, or
    29th-October-04th-November-2026 across two months, or 28th-December-2026-03rd-January-2027 across two years."""
    def day(value):
        suffix = "th" if 11 <= value.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(value.day % 10, "th")
        return "%02d%s" % (value.day, suffix)

    if start.year != end.year:
        return "%s-%s-%d-%s-%s-%d" % (day(start), MONTH_NAMES[start.month - 1], start.year, day(end),
                                      MONTH_NAMES[end.month - 1], end.year)
    if start.month != end.month:
        return "%s-%s-%s-%s-%d" % (day(start), MONTH_NAMES[start.month - 1], day(end), MONTH_NAMES[end.month - 1],
                                   end.year)
    return "%s-%s-%s-%d" % (day(start), day(end), MONTH_NAMES[end.month - 1], end.year)


def template(start, end, prices, people):
    """The week's sheet to fill in, as .xlsx bytes, in Luuka's own layout (their "Casuals 03 sept"): the week in C1;
    NAME, the bags packed at each price, the amount at each price, TOTAL AMOUNT and ARREARS; NO. above the people,
    holding each one's employee number, which is what pays them; then TOTAL. The amounts and totals are formulas, so
    the sheet adds up as the bags are typed in. prices: the Per Piece categories' prices that week, highest first;
    people: [{"employee", "employee_name"}]."""
    prices = list(prices or ())
    width = len(prices)
    book = Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    bold = Font(bold=True)
    side = Side(style="thin", color="000000")
    box = Border(left=side, right=side, top=side, bottom=side)
    bags_at, amount_at = 3, 3 + width
    total_at, arrears_at = amount_at + width, amount_at + width + 1
    sheet.cell(row=1, column=3, value=week_title(start, end)).font = bold
    heads = {2: "NAME", bags_at: "NUMBER OF BAGS PACKED", amount_at: "AMOUNT PER BAG PACKED", total_at: "TOTAL AMOUNT",
             arrears_at: "ARREARS"}
    for column, title in heads.items():
        cell = sheet.cell(row=2, column=column, value=title)
        cell.font, cell.alignment = bold, Alignment(horizontal="center", wrap_text=True)
    for first in (bags_at, amount_at):
        if width > 1:
            sheet.merge_cells(start_row=2, start_column=first, end_row=2, end_column=first + width - 1)
    sheet.cell(row=3, column=1, value="NO.").font = bold
    for at, price in enumerate(prices):
        for first in (bags_at, amount_at):
            cell = sheet.cell(row=3, column=first + at, value=price)
            cell.font, cell.number_format = bold, "#,##0"
    row = 3
    for row, person in enumerate(people or (), start=4):
        number = sheet.cell(row=row, column=1, value=str(person.get("employee") or ""))
        number.data_type = "s"
        name = sheet.cell(row=row, column=2, value=str(person.get("employee_name") or ""))
        name.data_type = "s"
        for at in range(width):
            bags, amount = get_column_letter(bags_at + at), get_column_letter(amount_at + at)
            sheet["%s%d" % (amount, row)] = "=IF(%s%d=\"\",0,%s%d*%s$3)" % (bags, row, bags, row, bags)
        sheet.cell(row=row, column=total_at, value="=SUM(%s%d:%s%d)" % (
            get_column_letter(amount_at), row, get_column_letter(amount_at + width - 1), row))
    last = row
    end_row = last + 1
    sheet.cell(row=end_row, column=2, value="TOTAL").font = bold
    if last >= 4:
        for column in (total_at, arrears_at):
            letter = get_column_letter(column)
            cell = sheet.cell(row=end_row, column=column, value="=SUM(%s4:%s%d)" % (letter, letter, last))
            cell.font = bold
    for line in range(2, end_row + 1):
        for column in range(1, arrears_at + 1):
            cell = sheet.cell(row=line, column=column)
            cell.border = box
            if line >= 4 and column >= bags_at:
                cell.number_format = "#,##0"
    for column, size in ((1, 12), (2, 32)):
        sheet.column_dimensions[get_column_letter(column)].width = size
    for column in range(bags_at, arrears_at + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 12 if column < total_at else 14
    sheet.freeze_panes = "C4"
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def read(content, wanted=None):
    """The workbook's weeks.

    content: the .xlsx bytes; wanted: (start, end) -> bool, which weeks to
    read the rows of (all when None).

    Returns {"weeks": [{"sheet", "start", "end", "prices", "rows": [{"row",
    "name", "employee_id", "bags": {price: value}, "total", "arrears"}]}],
    "skipped": the number of weeks not wanted, "unread": [sheet names dated
    by nothing]}. Raises ValueError for a file that is no workbook."""
    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError) as error:
        raise ValueError("This is not an Excel workbook (.xlsx): %s" % error)
    weeks, unread, skipped = [], [], 0
    try:
        for sheet in book.worksheets:
            head = [list(row) for row in sheet.iter_rows(min_row=1, max_row=HEADER_ROWS, values_only=True)]
            week = week_of(sheet.title) or week_of(_title(head))
            if not week:
                unread.append(sheet.title.strip())
                continue
            if wanted is not None and not wanted(*week):
                skipped += 1
                continue
            found = _read_sheet(sheet, head)
            if found is None:
                unread.append(sheet.title.strip())
                continue
            weeks.append(dict(found, sheet=sheet.title.strip(), start=week[0], end=week[1]))
    finally:
        book.close()
    return {"weeks": weeks, "skipped": skipped, "unread": unread}


# how a sheet's name lays its week out, tried in turn (D a day, M a month in words or figures, Y a year)
PATTERNS = (("D", "M", "Y", "D", "M", "Y"),  # 27-04-23 to 3-05-23, 28th-Dec-23 to 3rd-Jan-2024
            ("D", "M", "D", "M", "Y"),       # 29th-Oct-04th-Nov-26, 26th-03 to 01st-04th-2026
            ("D", "D", "M", "Y"))            # 1st-7th-Jan-2026, 11th-17th-04-24, 30th to 05th-August-2026


def week_of(text):
    """(start, end) of the week a sheet's name or title gives, or None.

    The figures and month words are read in order against the layouts
    Luuka's names take (PATTERNS); ordinal endings, "to" and anything after
    the week ("(2)") are passed over. Where both days share one month and
    the first is the larger, the week began in the month before. A span
    that is no week is no week: a misread name must not date a sheet."""
    tokens = []
    for token in re.findall(r"[A-Za-z]+|\d+", str(text or "")):
        if token.isdigit():
            tokens.append(("n", int(token), len(token)))
        elif token[:3].lower() in MONTHS:
            tokens.append(("m", MONTHS[token[:3].lower()], 0))
    for pattern in PATTERNS:
        found = _fit(tokens[:len(pattern)], pattern)
        if found:
            return found
    return None


def _fit(tokens, pattern):
    if len(tokens) != len(pattern):
        return None
    days, months, years = [], [], []
    for (kind, value, digits), slot in zip(tokens, pattern):
        if slot == "D" and kind == "n" and digits <= 2 and 1 <= value <= 31:
            days.append(value)
        elif slot == "M" and (kind == "m" or (digits <= 2 and 1 <= value <= 12)):
            months.append(value)
        elif slot == "Y" and kind == "n" and digits in (2, 4):
            years.append(value if digits == 4 else 2000 + value)
        else:
            return None
    if not all(2000 <= year <= 2100 for year in years):
        return None
    end_year = years[-1]
    end_month = months[-1]
    if len(months) == 2:
        start_month = months[0]
    else:
        start_month = end_month if days[0] <= days[1] else (end_month - 2) % 12 + 1
    start_year = years[0] if len(years) == 2 else (end_year - 1 if start_month > end_month else end_year)
    try:
        start, end = datetime.date(start_year, start_month, days[0]), datetime.date(end_year, end_month, days[1])
    except ValueError:
        return None
    if not WEEK_DAYS[0] <= (end - start).days + 1 <= WEEK_DAYS[1]:
        return None
    return start, end


def _title(head):
    for row in head[:2]:
        for value in row:
            if _text(value):
                return _text(value)
    return ""


def _read_sheet(sheet, head):
    """A week's rows, or None where no NAME heading and bag prices are found."""
    found = None
    for index, values in enumerate(head):
        labels = [_text(value).lower() for value in values]
        if any(label in NAME for label in labels):
            found = index, labels
            break
    if found is None:
        return None
    index, labels = found
    name_col = next(col for col, label in enumerate(labels) if label in NAME)
    bags_col = next((col for col, label in enumerate(labels) if any(word in label for word in BAGS)), None)
    amount_col = next((col for col, label in enumerate(labels)
                       if any(label.startswith(word) for word in AMOUNT)), None)
    if bags_col is None or amount_col is None or amount_col <= bags_col or index + 1 >= len(head):
        return None
    id_col = next((col for col, label in enumerate(labels) if label in EMPLOYEE_ID), None)
    if id_col is None:
        below = [_text(value).lower() for value in head[index + 1]]
        for row_labels in (labels, below):
            id_col = next((col for col, label in enumerate(row_labels) if label in NUMBER), None)
            if id_col is not None:
                break
    total_col = next((col for col, label in enumerate(labels) if label in TOTAL), None)
    arrears_col = next((col for col, label in enumerate(labels) if any(word in label for word in ARREARS)), None)
    price_row = head[index + 1]
    prices = {}
    for col in range(bags_col, amount_col):
        price = _number(price_row[col] if col < len(price_row) else None)
        if price and price > 0:
            prices[col] = price
    if not prices:
        return None
    rows = []
    first = index + 3  # 1-based: the NAME row, the prices, then the people
    for number, values in enumerate(sheet.iter_rows(min_row=first, values_only=True), first):
        values = list(values)
        name = _text(values[name_col] if name_col < len(values) else None)
        if name.upper() == "TOTAL":
            break
        employee_id = _text(values[id_col]) if id_col is not None and id_col < len(values) else ""
        bags = {price: values[col] if col < len(values) else None for col, price in prices.items()}
        if not name and not employee_id:
            continue
        rows.append({"row": number, "name": name, "employee_id": employee_id or None, "bags": bags,
                     "total": _number(values[total_col]) if total_col is not None and total_col < len(values) else None,
                     "arrears": _number(values[arrears_col]) if arrears_col is not None and arrears_col < len(values)
                     else None})
    return {"prices": list(prices.values()), "rows": rows}


def _text(value):
    return re.sub(r"\s+", " ", str(value)).strip() if value is not None else ""


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
