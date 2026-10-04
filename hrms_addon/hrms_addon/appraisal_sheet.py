# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The appraisal sheet, for appraising away from the system (the
flowchart's other branch): Luuka's own form, one sheet per appraisal,
downloaded with what the system already knows and read back when HR
uploads it.

No Frappe import, so scripts/verify_performance.py builds a sheet and reads
it back without a bench. appraisals.py gathers each appraisal into the
plain dict build() takes, and writes what read() finds onto the appraisals.

THE SHEET

The balanced scorecard is laid out as LPL PMS FY 2026 lays it out, with the
four quarters Luuka asked for (Oct 2026): the header and the employee's
details, Section A with each perspective's KPIs under it and every KPI's own
weight, the perspectives below summing them up, the other assignments,
Section B, the overall score, the results of the year so far and the rating
scale, Part D's comments and Part E's development plan. The supervisory form
(LPL/HR/18) is laid out in the same style: Section A's factors and Section
B's objectives, each rated by the employee and the supervisor, Section C,
the General questions and the comments.

What the system fills in is locked and what the appraiser fills in is open,
with a check on what may be typed (a percentage, a score out of ten, a
rating on the scale). The scores work themselves out as it is filled in,
by the rules the system scores by (bsc_rules.py): a KPI scores its weight
times the percentage achieved, without the workbook's further tenth.

Only the quarter being appraised is open. The earlier quarters show what was
recorded for them, from the employee's earlier appraisals of the year.

READING IT BACK

A hidden column tags each row the upload reads, and the sheet's first
hidden cells name its appraisal, so a sheet is matched to its appraisal
whatever it has been renamed to, and a row is read for what it holds.
"""

import datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation

MARK = "hrms_addon appraisal sheet"
FORM_SUPERVISORY = "Supervisory Skills (LPL/HR/18)"
FORM_BSC = "Balanced Scorecard"
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
# hidden columns: what a row holds, whose it is, and a perspective's first row
TAG, KEY, FIRST = "R", "S", "T"
# the scorecard's layout, in a hidden cell: a sheet downloaded before every
# KPI carried its own weight (October 2026) is not read, it is refused
LAYOUT, LAYOUT_CELL = "kpi-weights", TAG + "5"

# Luuka's palette, as the PMS workbook paints it
NAVY, TEAL, TEAL_DARK, GOLD = "1A2B4A", "007B87", "005F6B", "C9A42B"
WHITE, LABEL, NOTE, SOFT = "FFFFFF", "EEF2F6", "E8EDF4", "E0F4F6"
CREAM, GREEN_SOFT, GREY_SOFT = "FFF8E1", "E8F5E9", "F9F9F9"
PERSPECTIVE_COLOURS = {
    "Financial": ("E3F2FD", "1A5276"),
    "Customer / Stakeholder": ("E8F5E9", "1E8449"),
    "Internal Business Processes": ("FFFDE7", "7D6608"),
    "Learning & Growth": ("F3E5F5", "6C3483"),
}
# (lowest total, band, colour, meaning): the scorecard's own scale
BSC_BANDS = (
    (90, "Excellent", NAVY, "Consistently exceeds all objectives & expectations"),
    (80, "Very Good", TEAL, "Frequently meets & exceeds targets"),
    (70, "Good", "2E8B57", "Fully meets most objectives"),
    (60, "Fair", "E87722", "Meets some but not all objectives"),
    (0, "Poor", "C00000", "Consistently fails to meet standards"),
)
# LPL/HR/18's own bands (appraisal_rules.BANDS)
SUPERVISORY_BANDS = ((90, "Excellent"), (75, "Very Good"), (60, "Good"), (50, "Average"), (0, "Below Average"))
RATINGS = ("1", "2", "3", "4", "5", "N/A")
MAX_OBJECTIVES = 8
# a percentage cell keeps 85% as 0.85; up to this it is read as such a
# fraction, above it as a percentage typed in plain
FRACTION_UP_TO = 2

# the supervisory form's columns, A to P
WIDTHS = {"A": 5, "B": 16, "C": 36, "D": 9, "E": 8, "F": 18, "G": 8, "H": 9, "I": 18, "J": 8, "K": 9, "L": 18,
          "M": 8, "N": 9, "O": 10, "P": 10}
# the scorecard's, A to Q: three for each of the four quarters
BSC_WIDTHS = {"A": 5, "B": 16, "C": 36, "D": 9, "E": 8, "F": 16, "G": 8, "H": 9, "I": 16, "J": 8, "K": 9, "L": 16,
              "M": 8, "N": 9, "O": 16, "P": 8, "Q": 9}
# the quarter -> (its comments column, its percentage achieved, its weighted score)
PERIOD_COLUMNS = {"Q1": ("F", "G", "H"), "Q2": ("I", "J", "K"), "Q3": ("L", "M", "N"), "Q4": ("O", "P", "Q")}
# Part D of the scorecard and the signatures of LPL/HR/18: (key, label)
BSC_SIGNATORIES = (("supervisor", "Appraiser / Line Manager"), ("employee", "Employee / Appraisee"),
                   ("hod", "HOD / Reviewing Manager"), ("hrm", "HR Manager"), ("ed", "Executive Director"))
SUPERVISORY_SIGNATORIES = (("employee", "Employee"), ("supervisor", "Supervisor"), ("hrm", "HR Manager"),
                           ("production", "Production Manager"), ("gm", "General Manager"))
QUESTIONS = (
    ("roles", "List down the roles and responsibilities of your position in the company."),
    ("skills", "What are the skills you possess as a supervisor?"),
    ("achievements", "Can you share any achievements from the time you were appointed a supervisor?"),
    ("challenges", "Can you share any challenges faced?"),
)
THIN = Side(style="thin", color="7F7F7F")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


# ── Building the workbook ─────────────────────────────────────────────
def build(appraisals, logo=None):
    """The workbook: one sheet per appraisal, as bytes.

    appraisals: plain dicts (appraisals.py _sheet_data); logo: the image's
    bytes, or None."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    titles = set()
    for data in appraisals:
        sheet = workbook.create_sheet(sheet_title(data, titles))
        if data.get("form_type") == FORM_BSC:
            _scorecard(sheet, data, logo)
        else:
            _supervisory(sheet, data, logo)
    if not workbook.sheetnames:
        workbook.create_sheet("Appraisals")
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()


def sheet_title(data, taken):
    """The employee's name as a sheet's title: Excel allows 31 characters
    and none of []:*?/\\ and every title once."""
    name = str(data.get("employee_name") or data.get("name") or "Appraisal")
    name = "".join(" " if char in "[]:*?/\\" else char for char in name)
    name = " ".join(name.split())[:31] or "Appraisal"
    title, nth = name, 2
    while title.lower() in taken:
        suffix = " (%d)" % nth
        title = name[:31 - len(suffix)] + suffix
        nth += 1
    taken.add(title.lower())
    return title


def _style(cell, fill=None, bold=False, size=9, colour="000000", align="left", wrap=True, fmt=None, locked=True):
    cell.font = Font(name="Arial", size=size, bold=bold, color=colour)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    cell.border = BORDER
    if fmt:
        cell.number_format = fmt
    cell.protection = Protection(locked=locked)
    return cell


def _put(sheet, span, value=None, **style):
    """A value in a cell or a merged span, styled; `span` is "A1" or "A1:D4"."""
    first = span.split(":")[0]
    cell = sheet[first]
    cell.value = value
    _style(cell, **style)
    if ":" in span:
        for row in sheet[span]:
            for other in row:
                other.border = BORDER
        sheet.merge_cells(span)
    return cell


def _open(sheet, span, value=None, **style):
    """A cell the appraiser fills in: unlocked."""
    return _put(sheet, span, value, locked=False, **style)


def _edge(sheet):
    """The sheet's last column: the scorecard's four quarters reach Q, the
    supervisory form stops at P."""
    return "Q" if sheet[TAG + "3"].value == FORM_BSC else "P"


def _band_row(sheet, row, text, fill=NAVY, size=11, height=18, align="center", colour=WHITE):
    sheet.row_dimensions[row].height = height
    _put(sheet, "A%d:%s%d" % (row, _edge(sheet), row), text, fill=fill, bold=True, size=size, colour=colour,
         align=align)


def _setup(sheet, data):
    for column, width in (BSC_WIDTHS if data.get("form_type") == FORM_BSC else WIDTHS).items():
        sheet.column_dimensions[column].width = width
    for column in (TAG, KEY, FIRST):
        sheet.column_dimensions[column].hidden = True
    sheet[TAG + "1"] = MARK
    sheet[TAG + "2"] = data.get("name")
    sheet[TAG + "3"] = data.get("form_type")
    sheet[TAG + "4"] = data.get("period")
    if data.get("form_type") == FORM_BSC:
        sheet[LAYOUT_CELL] = LAYOUT
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True


def _protect(sheet, last_row):
    sheet.print_area = "A1:%s%d" % (_edge(sheet), last_row)
    sheet.protection.sheet = True
    # widths and heights may still be changed to read a long comment
    sheet.protection.formatColumns = False
    sheet.protection.formatRows = False


def _tag(sheet, row, tag, key=None, first=False):
    sheet["%s%d" % (TAG, row)] = tag
    if key is not None:
        sheet["%s%d" % (KEY, row)] = key
    if first:
        sheet["%s%d" % (FIRST, row)] = "first"


def _header(sheet, data, title, logo):
    for row in range(1, 5):
        sheet.row_dimensions[row].height = 15.75
    edge = _edge(sheet)
    _put(sheet, "A1:D4", None, fill=WHITE)
    _put(sheet, "E1:%s2" % edge, str(data.get("company") or "").upper(), fill=NAVY, bold=True, size=15, colour=WHITE,
         align="center")
    _put(sheet, "E3:%s4" % edge, title, fill=TEAL, bold=True, size=10, colour=WHITE, align="center")
    if logo:
        _logo(sheet, logo)


def _logo(sheet, logo):
    """The company's logo in the header's first cells, kept to their height.
    A logo that cannot be read leaves the cells empty rather than failing
    the download."""
    try:
        from openpyxl.drawing.image import Image

        image = Image(BytesIO(logo))
        height = 78
        width = image.width * height / image.height if image.height else 0
        if width > 440:
            height, width = height * 440 / width, 440
        image.width, image.height = int(width), int(height)
        sheet.add_image(image, "A1")
    except Exception:  # noqa: BLE001 - a picture never stops the sheet
        return


def _details(sheet, rows):
    """The employee's details under the header: (label, value, label,
    value, which of the two values is filled in by hand)."""
    for row, (left, left_value, right, right_value, typed) in enumerate(rows, 5):
        sheet.row_dimensions[row].height = 15
        _put(sheet, "A%d:B%d" % (row, row), left, fill=LABEL, bold=True)
        put = _open if typed == "left" else _put
        put(sheet, "C%d:G%d" % (row, row), left_value, fill=WHITE,
            fmt="dd/mm/yyyy" if isinstance(left_value, datetime.date) or typed == "left" else None)
        _put(sheet, "H%d:J%d" % (row, row), right, fill=LABEL, bold=True)
        _put(sheet, "K%d:%s%d" % (row, _edge(sheet), row), right_value, fill=WHITE)


def _how_to(sheet, text):
    sheet.row_dimensions[9].height = 43.5
    _put(sheet, "A9:%s9" % _edge(sheet), text, fill=NOTE, size=8)


def _footer(sheet, row, parts):
    sheet.row_dimensions[row].height = 12.75
    _put(sheet, "A%d:%s%d" % (row, _edge(sheet), row), "  |  ".join(str(part) for part in parts if part), fill=NAVY,
         size=8, colour=WHITE, align="center")


def _validation(sheet, kind, title, message):
    if kind == "percent":
        check = DataValidation(type="decimal", operator="between", formula1="0", formula2="1", allow_blank=True)
    elif kind == "score":
        check = DataValidation(type="decimal", operator="between", formula1="0", formula2="10", allow_blank=True)
    else:
        check = DataValidation(type="list", formula1='"%s"' % ",".join(RATINGS), allow_blank=True)
    check.showErrorMessage = True
    check.errorTitle = title
    check.error = message
    sheet.add_data_validation(check)
    return check


# ── The balanced scorecard ────────────────────────────────────────────
def _scorecard(sheet, data, logo):
    quarter = data.get("period") if data.get("period") in QUARTERS else QUARTERS[0]
    year = data.get("year") or ""
    _setup(sheet, data)
    _header(sheet, data, "PERFORMANCE MANAGEMENT SYSTEM  ·  BSC APPRAISAL FORM  ·  FY %s" % year, logo)
    _details(sheet, (
        ("Role / Position:", data.get("designation"), "Department:", data.get("department"), None),
        ("Employee Name:", data.get("employee_name"), "Grade:", data.get("grade"), None),
        ("Appraiser Name & Title:", data.get("supervisor"), "Review Period:", data.get("review_period"), None),
        ("Date of Review:", data.get("review_date"), "HR Ref:", data.get("name"), "left"),
    ))
    _how_to(sheet, "HOW TO USE:  (1) Each KPI's weight comes from the role's scorecard; the perspectives weigh what "
                   "their KPIs weigh and total 80%%.  (2) Enter %s's %% Achieved against each KPI in the gold column, "
                   "and a comment; the weighted score works itself out.  (3) Score each competency 0 to 10 in "
                   "Section B.  (4) Earlier quarters show what was recorded then and cannot be changed; the year to "
                   "date is the average of the quarters appraised.  RATING: Excellent ≥90  ·  Very Good 80–89  ·  "
                   "Good 70–79  ·  Fair 60–69  ·  Poor <60" % quarter)
    total_row, first, last = _section_a(sheet, data, quarter)
    row = _perspectives(sheet, total_row + 2, first, last)
    row = _assignments(sheet, data, row + 2)
    section_b_row = _section_b(sheet, data, row + 2)
    row = _overall(sheet, data, quarter, total_row, section_b_row)
    row = _scale(sheet, row + 2)
    row = _signatures(sheet, data, row + 2, BSC_SIGNATORIES, "PART D  —  COMMENTS & SIGNATURES")
    row = _plan(sheet, data, row + 2)
    footer = row + 2
    _footer(sheet, footer, (data.get("company"), "PMS BSC Appraisal Form FY %s" % year, data.get("department"),
                            data.get("form_reference"), "CONFIDENTIAL", data.get("revision")))
    sheet.freeze_panes = "E1"
    _protect(sheet, footer)


def _groups(data):
    """[(perspective, [kpis])] in the order the perspectives first appear on
    the scorecard; one empty KPI when there are none, so the form still
    shows its lines."""
    order, kpis = [], {}
    for kpi in data.get("kpis") or []:
        if kpi.get("perspective") not in kpis:
            order.append(kpi.get("perspective"))
            kpis[kpi.get("perspective")] = []
        kpis[kpi.get("perspective")].append(kpi)
    return [(perspective, kpis[perspective]) for perspective in order] or [(None, [{"kpi": ""}])]


def _section_a(sheet, data, quarter):
    """Section A from row 10: every KPI with its own weight and the four
    quarters, only `quarter` open. Returns (the totals row, the first KPI
    row, the last)."""
    _band_row(sheet, 10, "SECTION A  —  OBJECTIVES & KPIs  (80% of Total Score)  |  Every KPI carries its own "
                         "weight")
    sheet.row_dimensions[11].height = 43.5
    comments_column, entered_column, _score_column = PERIOD_COLUMNS[quarter]
    open_columns = {entered_column, comments_column}
    heads = [("A", "#", TEAL), ("B", "BSC\nPerspective", TEAL), ("C", "KPI / Objective", TEAL),
             ("D", "Timing", TEAL), ("E", "Weight\n(total=80%)", TEAL)]
    for each in QUARTERS:
        said, entered, scored = PERIOD_COLUMNS[each]
        heads += [(said, "%s Comments" % each, TEAL), (entered, "%s %%\nAchieved" % each, TEAL_DARK),
                  (scored, "%s Wtd\nScore" % each, TEAL_DARK)]
    for column, text, fill in heads:
        is_open = column in open_columns
        _put(sheet, "%s11" % column, text, fill=GOLD if is_open else fill, bold=True, size=8,
             colour=NAVY if is_open else WHITE, align="center")
    percent_check = _validation(sheet, "percent", "Percentage achieved", "Enter the percentage achieved, 0% to 100%.")
    row, number = 12, 0
    for perspective, kpis in _groups(data):
        light, dark = PERSPECTIVE_COLOURS.get(perspective, (LABEL, NAVY))
        for index, kpi in enumerate(kpis):
            number += 1
            sheet.row_dimensions[row].height = 37.5
            _put(sheet, "A%d" % row, number, fill=LABEL, bold=True, align="center")
            if index == 0:
                _put(sheet, "B%d" % row, perspective, fill=light, bold=True, colour=dark, align="center")
            else:
                _put(sheet, "B%d" % row, "↳", fill=GREY_SOFT, colour="666666", align="center")
            _put(sheet, "C%d" % row, kpi.get("kpi"), fill=WHITE)
            _put(sheet, "D%d" % row, kpi.get("timing"), fill=LABEL, align="center")
            _put(sheet, "E%d" % row, kpi.get("weight"), fill=CREAM, bold=True, size=10, colour="1A5276",
                 align="center", fmt='0.00"%"')
            for each, fill in zip(QUARTERS, (SOFT, LABEL, SOFT, LABEL)):
                said, entered, scored = PERIOD_COLUMNS[each]
                put = _open if each == quarter else _put
                put(sheet, "%s%d" % (said, row), kpi.get("%s_comments" % each.lower()), fill=fill)
                put(sheet, "%s%d" % (entered, row), _fraction(kpi.get("%s_percent" % each.lower())),
                    fill=GREEN_SOFT, bold=True, colour="1E8449", align="center", fmt="0%")
                if each == quarter:
                    percent_check.add("%s%d" % (entered, row))
                _put(sheet, "%s%d" % (scored, row), '=IF(%s%d="","",E%d*%s%d)' % (entered, row, row, entered, row),
                     fill=SOFT, colour=NAVY, align="center", fmt="0.00")
            _tag(sheet, row, "kpi", perspective, first=index == 0)
            row += 1
    first, last = 12, row - 1
    total = row
    sheet.row_dimensions[total].height = 19.5
    _put(sheet, "A%d:D%d" % (total, total), "WEIGHT CHECK & QUARTERLY TOTALS", fill=TEAL, bold=True, colour=WHITE,
         align="right")
    _put(sheet, "E%d" % total, "=SUM(E%d:E%d)" % (first, last), fill=GOLD, bold=True, size=10, align="center",
         fmt='0.00"%"')
    _put(sheet, "F%d:G%d" % (total, total),
         '=IF(ROUND(E%d,2)=80,"✓ Total = 80%%","⚠ Total must = 80%%, currently "&E%d&"%%")' % (total, total),
         fill=NOTE)
    for each in QUARTERS:
        said, entered, scored = PERIOD_COLUMNS[each]
        if each != QUARTERS[0]:
            _put(sheet, "%s%d:%s%d" % (said, total, entered, total), "%s Total →" % each, fill=TEAL, size=8,
                 colour=WHITE, align="right")
        _put(sheet, "%s%d" % (scored, total),
             '=IF(COUNT(%s%d:%s%d)=0,"",SUM(%s%d:%s%d))' % (scored, first, scored, last, scored, first, scored, last),
             fill=TEAL, bold=True, size=11 if each == quarter else 10, colour=WHITE, align="center", fmt="0.00")
    return total, first, last


def _perspectives(sheet, row, first, last):
    """The perspectives below the KPIs, summing them up by the hidden key
    each KPI row carries: each one's weight and, for every quarter, its
    weighted score. Returns its last row."""
    _band_row(sheet, row, "PERSPECTIVES  —  SUMMED UP FROM THE KPIs ABOVE", fill=TEAL, size=10, height=15.75)
    row += 1
    sheet.row_dimensions[row].height = 27.75
    _put(sheet, "A%d:D%d" % (row, row), "Perspective", fill=TEAL, bold=True, colour=WHITE, align="center")
    _put(sheet, "E%d" % row, "Weight", fill=TEAL, bold=True, size=8, colour=WHITE, align="center")
    for each in QUARTERS:
        said, _entered, scored = PERIOD_COLUMNS[each]
        _put(sheet, "%s%d:%s%d" % (said, row, scored, row), "%s Wtd Score" % each, fill=TEAL_DARK, bold=True, size=8,
             colour=WHITE, align="center")
    keys = "$%s$%d:$%s$%d" % (KEY, first, KEY, last)
    seen = []
    for at in range(first, last + 1):
        perspective = sheet["%s%d" % (KEY, at)].value
        if perspective and perspective not in seen:
            seen.append(perspective)
    for perspective in seen:
        row += 1
        sheet.row_dimensions[row].height = 19.5
        light, dark = PERSPECTIVE_COLOURS.get(perspective, (LABEL, NAVY))
        _put(sheet, "A%d:D%d" % (row, row), perspective, fill=light, bold=True, colour=dark)
        _put(sheet, "E%d" % row, "=SUMIF(%s,$A%d,$E$%d:$E$%d)" % (keys, row, first, last), fill=CREAM, bold=True,
             size=10, colour="1A5276", align="center", fmt='0.00"%"')
        for each, fill in zip(QUARTERS, (SOFT, LABEL, SOFT, LABEL)):
            said, entered, scored = PERIOD_COLUMNS[each]
            _put(sheet, "%s%d:%s%d" % (said, row, scored, row),
                 '=IF(COUNTIFS(%s,$A%d,$%s$%d:$%s$%d,"<>")=0,"",SUMIF(%s,$A%d,$%s$%d:$%s$%d))'
                 % (keys, row, entered, first, entered, last, keys, row, scored, first, scored, last),
                 fill=fill, bold=True, colour=NAVY, align="center", fmt="0.00")
    return row


def _assignments(sheet, data, row):
    _band_row(sheet, row, "OTHER ASSIGNMENTS / SPECIAL TASKS  (Record only — informational, not scored "
                          "separately)", size=10)
    row += 1
    sheet.row_dimensions[row].height = 27.75
    edge = _edge(sheet)
    for span, text in (("A%d:B%d", "S/No & Task"), ("C%d:F%d", "Assignment Given"), ("G%d:I%d", "Expected Outcome"),
                       ("J%d:M%d", "Employee Comments"), ("N%d:" + edge + "%d", "Supervisor Comments")):
        _put(sheet, span % (row, row), text, fill=TEAL, bold=True, colour=WHITE, align="center")
    rows = list(data.get("assignments") or [])
    rows += [{}] * max(3 - len(rows), 1 if len(rows) >= 3 else 0)
    for number, assignment in enumerate(rows, 1):
        row += 1
        sheet.row_dimensions[row].height = 30
        _put(sheet, "A%d" % row, number, fill=LABEL, bold=True, align="center")
        _open(sheet, "B%d" % row, assignment.get("task"), fill=WHITE)
        _open(sheet, "C%d:F%d" % (row, row), assignment.get("assignment_given"), fill=WHITE)
        _open(sheet, "G%d:I%d" % (row, row), assignment.get("expected_outcome"), fill=WHITE)
        _open(sheet, "J%d:M%d" % (row, row), assignment.get("employee_comments"), fill=WHITE)
        _open(sheet, "N%d:%s%d" % (row, edge, row), assignment.get("supervisor_comments"), fill=WHITE)
        _tag(sheet, row, "assignment")
    return row


def _section_b(sheet, data, row):
    """Section B; returns its check row, which carries its score."""
    _band_row(sheet, row, "SECTION B  —  COMPETENCIES  (20% of Total Score)  |  Score each 0–10  |  Weights "
                          "must sum to 20%")
    row += 1
    sheet.row_dimensions[row].height = 27.75
    edge = _edge(sheet)
    for span, text in (("A%d:C%d", "Competency"), ("D%d:I%d", "Behavioural Indicators"), ("J%d:K%d", "Weight\n(%%)"),
                       ("L%d:M%d", "Score\n(0–10)"), ("N%d:" + edge + "%d", "Weighted\nScore")):
        _put(sheet, span % (row, row), text.replace("%%", "%"), fill=GOLD if span.startswith("L") else TEAL,
             bold=True, colour=NAVY if span.startswith("L") else WHITE, align="center")
    check = _validation(sheet, "score", "Competency score", "Score each competency from 0 to 10.")
    first = row + 1
    for index, competency in enumerate(data.get("competencies") or []):
        row += 1
        sheet.row_dimensions[row].height = 36
        _put(sheet, "A%d:C%d" % (row, row), competency.get("competency"), fill=NOTE, bold=True)
        _put(sheet, "D%d:I%d" % (row, row), competency.get("indicators"), fill=SOFT if index % 2 == 0 else WHITE,
             size=8)
        _put(sheet, "J%d:K%d" % (row, row), competency.get("weight"), fill=CREAM, bold=True, size=10,
             colour="1A5276", align="center", fmt='0"%"')
        _open(sheet, "L%d:M%d" % (row, row), competency.get("score"), fill=WHITE, bold=True, size=10, align="center",
              fmt="0.0")
        check.add("L%d" % row)
        _put(sheet, "N%d:%s%d" % (row, edge, row), '=IF(L%d="","",J%d*L%d/10)' % (row, row, row), fill=SOFT,
             bold=True, size=10, colour=NAVY, align="center", fmt="0.00")
        _tag(sheet, row, "competency", competency.get("competency"))
    last = max(row, first)
    row += 1
    sheet.row_dimensions[row].height = 18
    _put(sheet, "A%d:I%d" % (row, row), "COMPETENCY WEIGHT CHECK & SECTION B SCORE", fill=TEAL, bold=True,
         colour=WHITE, align="right")
    _put(sheet, "J%d:K%d" % (row, row), "=SUM(J%d:J%d)" % (first, last), fill=GOLD, bold=True, size=10,
         align="center", fmt='0"%"')
    _put(sheet, "L%d:M%d" % (row, row), '=IF(J%d=20,"✓ 20%%","⚠ Must = 20%%")' % row, fill=NOTE, size=8)
    _put(sheet, "N%d:%s%d" % (row, edge, row), '=IF(COUNT(N%d:N%d)=0,"",SUM(N%d:N%d))' % (first, last, first, last),
         fill=TEAL, bold=True, size=11, colour=WHITE, align="center", fmt="0.00")
    return row


def _overall(sheet, data, quarter, total_row, section_b_row):
    """The overall score for the quarter appraised and the scorecard's
    rating of it, then the year so far: each quarter's overall, the earlier
    ones as their own appraisals recorded them, and the year to date, the
    average of the quarters appraised. Returns its last row."""
    row = section_b_row + 2
    _band_row(sheet, row, "OVERALL PERFORMANCE SCORE   =   Section A (×0.8 already embedded in weights) + "
                          "Section B")
    bands = [(floor, name) for floor, name, _c, _m in BSC_BANDS]
    score_column = PERIOD_COLUMNS[quarter][2]
    lines = (
        ("Section A Score  (sum of weighted KPI scores, %s)" % quarter,
         '=IFERROR(%s%d,"")' % (score_column, total_row)),
        ("Section B Score  (sum of weighted competency scores)", '=IFERROR(N%d,"")' % section_b_row),
    )
    first = row + 1
    for label, formula in lines:
        row += 1
        sheet.row_dimensions[row].height = 19.5
        _put(sheet, "A%d:P%d" % (row, row), label, fill=LABEL, colour=NAVY, align="right")
        _put(sheet, "Q%d" % row, formula, fill=LABEL, bold=True, size=10, colour=NAVY, align="center", fmt="0.0")
    row += 1
    overall = row
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:P%d" % (row, row), "OVERALL SCORE  (Section A + Section B, %s)" % quarter, fill=GOLD, bold=True,
         size=10, colour=WHITE, align="right")
    _put(sheet, "Q%d" % row, '=IF(AND(Q%d="",Q%d=""),"",N(Q%d)+N(Q%d))' % (first, first + 1, first, first + 1),
         fill=GOLD, bold=True, size=13, colour=WHITE, align="center", fmt="0.0")
    row += 1
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:P%d" % (row, row), "RATING", fill=LABEL, bold=True, colour=NAVY, align="right")
    _put(sheet, "Q%d" % row, _band_formula("Q%d" % overall, bands), fill=LABEL, bold=True, colour=NAVY,
         align="center")
    # the year so far
    row += 2
    _band_row(sheet, row, "RESULTS THIS YEAR  —  the year to date is the average of the quarters appraised",
              fill=TEAL, size=10, height=15.75)
    row += 1
    sheet.row_dimensions[row].height = 15.75
    _put(sheet, "A%d:E%d" % (row, row), "Quarter", fill=TEAL, bold=True, colour=WHITE, align="center")
    for each in QUARTERS:
        said, _entered, scored = PERIOD_COLUMNS[each]
        _put(sheet, "%s%d:%s%d" % (said, row, scored, row), each, fill=GOLD if each == quarter else TEAL_DARK,
             bold=True, colour=NAVY if each == quarter else WHITE, align="center")
    row += 1
    scores = row
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:E%d" % (row, row), "Overall score", fill=LABEL, bold=True, colour=NAVY, align="right")
    results = data.get("results") or {}
    for each in QUARTERS:
        said, _entered, scored = PERIOD_COLUMNS[each]
        if each == quarter:
            value = '=IFERROR(Q%d,"")' % overall
        else:
            value = results.get(each) if QUARTERS.index(each) < QUARTERS.index(quarter) else None
        _put(sheet, "%s%d:%s%d" % (said, row, scored, row), value, fill=CREAM if each == quarter else LABEL,
             bold=True, size=10, colour=NAVY, align="center", fmt="0.0")
    row += 1
    year = row
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:P%d" % (row, row), "YEAR TO DATE  (average of the quarters appraised)", fill=GOLD, bold=True,
         size=10, colour=WHITE, align="right")
    _put(sheet, "Q%d" % row, '=IFERROR(AVERAGE(F%d:Q%d),"")' % (scores, scores), fill=GOLD, bold=True, size=13,
         colour=WHITE, align="center", fmt="0.0")
    row += 1
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:P%d" % (row, row), "YEAR TO DATE RATING", fill=LABEL, bold=True, colour=NAVY, align="right")
    _put(sheet, "Q%d" % row, _band_formula("Q%d" % year, bands), fill=LABEL, bold=True, colour=NAVY, align="center")
    return row


def _band_formula(cell, bands):
    formula = '"%s"' % bands[-1][1]
    for floor, name in reversed(bands[:-1]):
        formula = 'IF(%s>=%s,"%s",%s)' % (cell, floor, name, formula)
    return '=IF(%s="","",%s)' % (cell, formula)


def _scale(sheet, row):
    _band_row(sheet, row, "PERFORMANCE RATING SCALE", fill=TEAL, size=10, height=13.5)
    spans = ("A%d:C%d", "D%d:F%d", "G%d:I%d", "J%d:L%d", "M%d:" + _edge(sheet) + "%d")
    sheet.row_dimensions[row + 1].height = 12.75
    sheet.row_dimensions[row + 2].height = 21.75
    for span, (floor, name, colour, meaning) in zip(spans, BSC_BANDS):
        label = {90: "%s  ≥90", 80: "%s  80–89", 70: "%s  70–79", 60: "%s  60–69",
                 0: "%s  <60"}[floor] % name
        _put(sheet, span % (row + 1, row + 1), label, fill=colour, bold=True, size=8, colour=WHITE, align="center")
        _put(sheet, span % (row + 2, row + 2), meaning, fill=LABEL, size=8, align="center")
    return row + 2


def _signatures(sheet, data, row, signatories, title):
    _band_row(sheet, row, title, height=15.75)
    remarks, names = data.get("remarks") or {}, data.get("names") or {}
    for key, label in signatories:
        row += 1
        sheet.row_dimensions[row].height = 30
        _put(sheet, "A%d:B%d" % (row, row), label, fill=LABEL, bold=True)
        _open(sheet, "C%d:I%d" % (row, row), remarks.get(key), fill=WHITE)
        name = names.get(key) or "_______________________"
        _put(sheet, "J%d:%s%d" % (row, _edge(sheet), row), "Name: %s   Sig: __________________   Date: ________" % name,
             fill=WHITE, size=8)
        _tag(sheet, row, "remark", key)
    return row


def _plan(sheet, data, row):
    _band_row(sheet, row, "PART E  —  DEVELOPMENT PLAN", height=15.75)
    edge = _edge(sheet)
    plan = data.get("plan") or {}
    row += 1
    sheet.row_dimensions[row].height = 12.75
    for span, text in (("A%d:E%d", "Continue / Strengths"), ("F%d:J%d", "Stop / Weaknesses"),
                       ("K%d:" + edge + "%d", "Start / Gaps to Fill")):
        _put(sheet, span % (row, row), text, fill=TEAL, bold=True, colour=WHITE, align="center")
    row += 1
    sheet.row_dimensions[row].height = 43.5
    _open(sheet, "A%d:E%d" % (row, row), plan.get("continue"), fill=WHITE)
    _open(sheet, "F%d:J%d" % (row, row), plan.get("stop"), fill=WHITE)
    _open(sheet, "K%d:%s%d" % (row, edge, row), plan.get("start"), fill=WHITE)
    _tag(sheet, row, "plan")
    row += 2
    sheet.row_dimensions[row].height = 12.75
    for span, text in (("A%d:F%d", "Development Action"), ("G%d:I%d", "Duration"), ("J%d:L%d", "By When"),
                       ("M%d:N%d", "By Whom"),
                       ("O%d:" + edge + "%d", "Est. Cost (%s)" % (data.get("currency") or "UGX"))):
        _put(sheet, span % (row, row), text, fill=TEAL, bold=True, colour=WHITE, align="center")
    actions = list(data.get("actions") or [])
    actions += [{}] * max(3 - len(actions), 1 if len(actions) >= 3 else 0)
    for action in actions:
        row += 1
        sheet.row_dimensions[row].height = 24
        _open(sheet, "A%d:F%d" % (row, row), action.get("action"), fill=WHITE)
        _open(sheet, "G%d:I%d" % (row, row), action.get("duration"), fill=WHITE)
        _open(sheet, "J%d:L%d" % (row, row), _date(action.get("by_when")), fill=WHITE, fmt="dd/mm/yyyy")
        _open(sheet, "M%d:N%d" % (row, row), action.get("by_whom"), fill=WHITE)
        _open(sheet, "O%d:%s%d" % (row, edge, row), action.get("estimated_cost"), fill=WHITE, fmt="#,##0")
        _tag(sheet, row, "action")
    return row


# ── The supervisory form (LPL/HR/18) ──────────────────────────────────
def _supervisory(sheet, data, logo):
    year = data.get("year") or ""
    own = bool(data.get("self_appraisal", 1))
    _setup(sheet, data)
    _header(sheet, data, "PERFORMANCE MANAGEMENT SYSTEM  ·  SUPERVISORY SKILLS EVALUATION FORM (LPL/HR/18)  "
                         "·  FY %s" % year, logo)
    _details(sheet, (
        ("Role / Position:", data.get("designation"), "Department:", data.get("department"), None),
        ("Employee Name:", data.get("employee_name"), "Plant:", data.get("branch"), None),
        ("Supervisor Name & Title:", data.get("supervisor"), "Review Period:", data.get("review_period"), None),
        ("Date of Review:", data.get("review_date"), "HR Ref:", data.get("name"), "left"),
    ))
    first_step = ("(1) The employee rates themselves on every factor and objective, 1 to 5, or N/A where it does "
                  "not fit the job, and answers the General questions.  (2) The supervisor gives their own rating "
                  "and a comment on each.") if own else \
        "(1) The supervisor rates the employee on every factor and objective, 1 to 5, or N/A where it does not " \
        "fit the job, with a comment on each."
    _how_to(sheet, "HOW TO USE:  %s  The scores work themselves out.  RATING: 5 Excellent (90-100%%)  ·  4 Very "
                   "Good (75-89%%)  ·  3 Good (60-74%%)  ·  2 Average (50-59%%)  ·  1 Below Average "
                   "(40%% and below)" % first_step)
    rating_check = _validation(sheet, "rating", "Rating", "Rate from 1 to 5, or N/A.")
    factor_score = _rated_section(sheet, 10, "SECTION A  —  RATABLE FACTORS  (60% of Total Score)", "Factor",
                                  data.get("factors") or [], "factor", own, rating_check, 60, fixed=True)
    objectives = list(data.get("objectives") or [])
    objectives += [{}] * max(MAX_OBJECTIVES - len(objectives), 0)
    objective_score = _rated_section(sheet, factor_score + 2, "SECTION B  —  OBJECTIVES / KPIs  (40% of Total "
                                                              "Score)", "Objective / KPI", objectives, "objective",
                                     own, rating_check, 40, fixed=False)
    row = _section_c(sheet, objective_score + 2, factor_score, objective_score, own)
    row = _general(sheet, data, row + 2, own)
    row = _signatures(sheet, data, row + 2, SUPERVISORY_SIGNATORIES, "COMMENTS & SIGNATURES")
    footer = row + 2
    _footer(sheet, footer, (data.get("company"), "Supervisory Skills Evaluation Form LPL/HR/18 Rev 01",
                            data.get("department"), "CONFIDENTIAL"))
    _protect(sheet, footer)


def _rated_section(sheet, row, title, item_label, items, tag, own, rating_check, out_of, fixed):
    """A section rated by the employee and the supervisor; returns its score
    row, whose G carries the employee's score and I the supervisor's."""
    _band_row(sheet, row, title)
    row += 1
    sheet.row_dimensions[row].height = 30
    _put(sheet, "A%d" % row, "#", fill=TEAL, bold=True, size=8, colour=WHITE, align="center")
    _put(sheet, "B%d:F%d" % (row, row), item_label, fill=TEAL, bold=True, size=8, colour=WHITE, align="center")
    _put(sheet, "G%d:H%d" % (row, row), "Employee's Rating\n(1–5)", fill=GOLD if own else TEAL_DARK, bold=True,
         size=8, colour=NAVY if own else WHITE, align="center")
    _put(sheet, "I%d:J%d" % (row, row), "Supervisor's Rating\n(1–5)", fill=GOLD, bold=True, size=8, colour=NAVY,
         align="center")
    _put(sheet, "K%d:P%d" % (row, row), "Supervisor's Comment", fill=TEAL, bold=True, size=8, colour=WHITE,
         align="center")
    first = row + 1
    for number, item in enumerate(items, 1):
        row += 1
        sheet.row_dimensions[row].height = 30
        _put(sheet, "A%d" % row, number, fill=LABEL, bold=True, align="center")
        text = item.get("item")
        put = _put if (fixed or text) else _open
        put(sheet, "B%d:F%d" % (row, row), text, fill=WHITE)
        put = _open if own else _put
        put(sheet, "G%d:H%d" % (row, row), _rating_value(item.get("employee_rating")), fill=GREEN_SOFT, bold=True,
            colour="1E8449", align="center")
        _open(sheet, "I%d:J%d" % (row, row), _rating_value(item.get("supervisor_rating")), fill=CREAM, bold=True,
              colour=NAVY, align="center")
        _open(sheet, "K%d:P%d" % (row, row), item.get("supervisor_comment"), fill=WHITE)
        if own:
            rating_check.add("G%d" % row)
        rating_check.add("I%d" % row)
        _tag(sheet, row, tag)
    last = max(row, first)
    row += 1
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:F%d" % (row, row), "SCORE  (out of %d)" % out_of, fill=TEAL, bold=True, colour=WHITE,
         align="right")
    for column in ("G", "I"):
        span = "%s%d:%s%d" % (column, row, chr(ord(column) + 1), row)
        _put(sheet, span, '=IF(COUNT(%s%d:%s%d)=0,"",SUM(%s%d:%s%d)/(5*COUNT(%s%d:%s%d))*%d)'
             % (column, first, column, last, column, first, column, last, column, first, column, last, out_of),
             fill=TEAL, bold=True, size=10, colour=WHITE, align="center", fmt="0.0")
    _put(sheet, "K%d:P%d" % (row, row), None, fill=TEAL)
    return row


def _section_c(sheet, row, factor_score, objective_score, own):
    _band_row(sheet, row, "SECTION C  —  OVERALL SCORE")
    lines = [("Ratable Factors  (out of 60)", '=IFERROR(I%d,"")' % factor_score),
             ("Objectives / KPIs  (out of 40)", '=IFERROR(I%d,"")' % objective_score)]
    first = row + 1
    for label, formula in lines:
        row += 1
        sheet.row_dimensions[row].height = 19.5
        _put(sheet, "A%d:O%d" % (row, row), label, fill=LABEL, colour=NAVY, align="right")
        _put(sheet, "P%d" % row, formula, fill=LABEL, bold=True, size=10, colour=NAVY, align="center", fmt="0.0")
    row += 1
    total = row
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:O%d" % (row, row), "TOTAL SCORE  (%)", fill=GOLD, bold=True, size=10, colour=WHITE,
         align="right")
    _put(sheet, "P%d" % row, _total_formula("P%d" % first, "P%d" % (first + 1)), fill=GOLD, bold=True, size=13,
         colour=WHITE, align="center", fmt="0.0")
    row += 1
    sheet.row_dimensions[row].height = 19.5
    _put(sheet, "A%d:O%d" % (row, row), "OVERALL RATING", fill=LABEL, bold=True, colour=NAVY, align="right")
    _put(sheet, "P%d" % row, _band_formula("P%d" % total, list(SUPERVISORY_BANDS)), fill=LABEL, bold=True,
         colour=NAVY, align="center")
    if own:
        row += 1
        sheet.row_dimensions[row].height = 19.5
        _put(sheet, "A%d:O%d" % (row, row), "Employee's own total  (%)", fill=LABEL, colour=NAVY, align="right")
        _put(sheet, "P%d" % row, _total_formula("G%d" % factor_score, "G%d" % objective_score), fill=LABEL,
             bold=True, size=10, colour=NAVY, align="center", fmt="0.0")
    return row


def _total_formula(section_a, section_b):
    """LPL/HR/18's Section C: the two sections out of 60 and 40 as a
    percentage, a section with nothing rated left out (appraisal_rules.scores)."""
    return ('=IF(AND({a}="",{b}=""),"",(N({a})+N({b}))/(IF({a}="",0,60)+IF({b}="",0,40))*100)'
            .format(a=section_a, b=section_b))


def _general(sheet, data, row, own):
    _band_row(sheet, row, "GENERAL  (answered by the employee)")
    answers = data.get("answers") or {}
    for key, question in QUESTIONS:
        row += 1
        sheet.row_dimensions[row].height = 45
        _put(sheet, "A%d:F%d" % (row, row), question, fill=LABEL, bold=True)
        put = _open if own else _put
        put(sheet, "G%d:P%d" % (row, row), answers.get(key), fill=WHITE)
        _tag(sheet, row, "answer", key)
    return row


# ── Reading it back ───────────────────────────────────────────────────
def read(content):
    """What each appraisal sheet in a workbook says:
    {appraisal name: {"form_type", "period", "sheet", ...what it holds}}.

    content: the workbook's bytes, or a path. A sheet this app did not make
    is left out; so is anything typed where it cannot be read."""
    source = BytesIO(content) if isinstance(content, (bytes, bytearray)) else content
    workbook = load_workbook(source, data_only=True)
    found = {}
    for sheet in workbook.worksheets:
        if _text(sheet[TAG + "1"].value) != MARK:
            continue
        name = _text(sheet[TAG + "2"].value)
        if not name:
            continue
        form_type = _text(sheet[TAG + "3"].value)
        period = _text(sheet[TAG + "4"].value)
        values = _read_scorecard(sheet, period) if form_type == FORM_BSC else _read_supervisory(sheet)
        values.update({"form_type": form_type, "period": period, "sheet": sheet.title})
        found[name] = values
    workbook.close()
    return found


def _rows(sheet):
    for row in range(1, sheet.max_row + 1):
        tag = _text(sheet["%s%d" % (TAG, row)].value)
        if tag:
            yield row, tag, sheet["%s%d" % (KEY, row)].value, _text(sheet["%s%d" % (FIRST, row)].value) == "first"


def _read_scorecard(sheet, quarter):
    """What a scorecard sheet says for its quarter: each KPI's percentage
    achieved and comments by (perspective, KPI), and the rest of the form.
    A sheet laid out before every KPI carried its own weight is not read:
    {"outdated": True}."""
    out = {"kpis": {}, "competencies": {}, "assignments": [], "remarks": {}, "plan": {}, "actions": [],
           "problems": []}
    if _text(sheet[LAYOUT_CELL].value) != LAYOUT or quarter not in PERIOD_COLUMNS:
        out["outdated"] = True
        return out
    comments_column, entered_column, _score = PERIOD_COLUMNS[quarter]
    for row, tag, key, _first in _rows(sheet):
        cell = lambda column: sheet["%s%d" % (column, row)].value  # noqa: E731
        if tag == "kpi":
            perspective, kpi = _text(key), _key(cell("C"))
            percent = _percent(cell(entered_column))
            if percent is not None and not 0 <= percent <= 100:
                out["problems"].append("%s (%s): the percentage achieved must be from 0 to 100." % (kpi, perspective))
                percent = None
            comments = _text(cell(comments_column))
            if percent is not None or comments:
                out["kpis"][(perspective, kpi)] = {"percent": percent, "comments": comments or None}
        elif tag == "competency":
            score = _number(cell("L"))
            if score is not None and not 0 <= score <= 10:
                out["problems"].append("%s: a competency is scored from 0 to 10." % _text(key))
                score = None
            if score is not None:
                out["competencies"][_text(key)] = score
        elif tag == "assignment":
            values = {"task": _text(cell("B")), "assignment_given": _text(cell("C")),
                      "expected_outcome": _text(cell("G")), "employee_comments": _text(cell("J")),
                      "supervisor_comments": _text(cell("N"))}
            if any(values.values()):
                out["assignments"].append(values)
        elif tag == "remark":
            if _text(cell("C")):
                out["remarks"][_text(key)] = _text(cell("C"))
        elif tag == "plan":
            out["plan"] = {"continue": _text(cell("A")), "stop": _text(cell("F")), "start": _text(cell("K"))}
        elif tag == "action":
            values = {"action": _text(cell("A")), "duration": _text(cell("G")), "by_when": _date(cell("J")),
                      "by_whom": _text(cell("M")), "estimated_cost": _number(cell("O"))}
            if values["action"]:
                out["actions"].append(values)
    return out


def _read_supervisory(sheet):
    out = {"factors": [], "objectives": [], "answers": {}, "remarks": {}, "problems": []}
    for row, tag, key, _first in _rows(sheet):
        cell = lambda column: sheet["%s%d" % (column, row)].value  # noqa: E731
        if tag in ("factor", "objective"):
            item = _text(cell("B"))
            if not item:
                continue
            ratings = {}
            for who, column in (("employee_rating", "G"), ("supervisor_rating", "I")):
                raw = cell(column)
                value = _rating(raw)
                if raw not in (None, "") and value is None:
                    out["problems"].append("%s: %r is not a rating from 1 to 5 or N/A." % (item, raw))
                ratings[who] = value
            out["factors" if tag == "factor" else "objectives"].append(
                dict(ratings, item=item, supervisor_comment=_text(cell("K"))))
        elif tag == "answer":
            if _text(cell("G")):
                out["answers"][_text(key)] = _text(cell("G"))
        elif tag == "remark":
            if _text(cell("C")):
                out["remarks"][_text(key)] = _text(cell("C"))
    return out


# ── Values ────────────────────────────────────────────────────────────
def _key(value):
    """Text as it is matched: spaces and line breaks count as one space."""
    return " ".join(str(value or "").split())


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split()) if "\n" not in str(value) else str(value).strip()


def _number(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _fraction(percent):
    """A percentage achieved as the sheet keeps it: 85 is 0.85, shown 85%."""
    number = _number(percent)
    return None if number is None else round(number / 100.0, 6)


def _percent(value):
    """What a percentage cell holds, back as a percentage: the sheet keeps
    85% as 0.85, and 140% pasted past the check as 1.4. A plain 85 pasted
    in is read as 85: no percentage achieved is 8,500."""
    if isinstance(value, str) and value.strip().endswith("%"):
        return _number(value)
    number = _number(value)
    if number is None:
        return None
    return round(number * 100.0, 2) if number <= FRACTION_UP_TO else round(number, 2)


def _rating(value):
    if value in (None, ""):
        return None
    number = _number(value)
    if number is not None and float(number).is_integer():
        text = str(int(number))
    else:
        text = _text(value)
    if text.upper() == "N/A":
        return "N/A"
    return text if text in RATINGS else None


def _rating_value(rating):
    """A rating as the sheet keeps it: a number, so the section scores add
    it up, or N/A."""
    if rating in (None, ""):
        return None
    return int(rating) if str(rating).isdigit() else str(rating)


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
