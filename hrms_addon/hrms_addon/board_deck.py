# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack as a PowerPoint deck and an Excel workbook, from an HR
Board Report: its figures (board_pack.quarter_figures, kept as JSON on the
report) and HR's own words. The deck follows Luuka's own (LPL HR Board
Report Q3 2026): the same sections in the same order, native charts and
tables, so the board reads what it is used to and HR can still edit it.

The deck needs python-pptx on the server (bench pip install python-pptx);
the workbook needs only openpyxl, which Frappe already carries.
"""

import io

import frappe
from frappe import _

NAVY, GOLD, GREY, INK, PALE, WHITE = "14395E", "B8860B", "6B7280", "1F272E", "F3F5F8", "FFFFFF"
GREEN, AMBER, RED = "1F7A4D", "B7791F", "A62B25"
SERIES = ("14395E", "E8A317", "2E86AB", "7A9E3B", "A62B25", "8E6C8A")
RATING_COLOURS = {"On Track": GREEN, "Watch": AMBER, "Action Needed": RED, "Action": RED, "Building": NAVY}
SECTIONS = (
    ("Executive Summary", "Board HR health rating & headline results"),
    ("Head Count: Quarter & Year-on-Year", "Quarter snapshot; the same months a year before"),
    ("Recruitment, Exits & Churn", "Hiring, leavers, churn by employment type & reconciliation"),
    ("Year-on-Year Comparative", "Recruitment, exits, wage bill & safety against a year before"),
    ("Wage Bill, Overtime & Labour Cost", "Components, overtime trends, staff cost as % of revenue"),
    ("HR Metrics That Drive Business", "The board's seven KPIs"),
    ("Learning, Development & Training ROI", "The quarter's programmes and their value"),
    ("EHS & In Memoriam", "Safety trends and colleagues we lost this quarter"),
    ("Strategic People Agenda & Outlook", "HR as business partner: achievements, risks, priorities"),
)


# ── Numbers as the board reads them ───────────────────────────────────
def n(value):
    return "–" if value is None else "{:,.0f}".format(float(value))


def pct(value, places=1):
    return "–" if value is None else ("{:.%df}%%" % places).format(float(value))


def signed(value, places=0, suffix=""):
    if value is None:
        return "–"
    value = float(value)
    text = ("{:,.%df}" % places).format(abs(value)) + suffix
    return ("+" if value > 0 else "−" if value < 0 else "") + text


def arrow(value, suffix="%"):
    if value is None:
        return "–"
    return ("▲ " if value > 0 else "▼ " if value < 0 else "— ") + signed(value, 1, suffix)


def arrow_count(value):
    """A change in people: whole numbers, with its arrow."""
    if value is None:
        return "–"
    return ("▲ " if value > 0 else "▼ " if value < 0 else "— ") + signed(value)


def millions(value):
    return "–" if value is None else "{:,.0f}".format(float(value) / 1e6)


def billions(value):
    return "–" if value is None else "{:,.2f}B".format(float(value) / 1e9)


def change(now, before):
    if not before:
        return None
    return round(100.0 * (float(now or 0) - float(before)) / float(before), 1)


def lines(text):
    return [line.strip(" -•\t") for line in (text or "").splitlines() if line.strip(" -•\t")]


def plant_name(plant):
    return plant if plant else _("Total")


# ── The deck ──────────────────────────────────────────────────────────
def deck(doc, figures):
    """The deck's bytes."""
    if not figures:
        frappe.throw(_("Get the figures first: the deck is made from them."), title=_("HR Board Report"))
    try:
        from pptx import Presentation  # noqa: F401
    except ImportError:
        frappe.throw(_("The deck needs python-pptx on the server. Run: bench pip install python-pptx"),
                     title=_("HR Board Report"))
    builder = _Deck(doc, figures)
    return builder.build()


class _Deck:
    def __init__(self, doc, figures):
        from pptx import Presentation
        from pptx.util import Inches

        self.doc, self.f = doc, figures
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.page = 0
        self.tag = "%s %s" % (figures.get("quarter") or doc.quarter, figures.get("year") or doc.year)

    # parts every slide uses
    def _rgb(self, hex_colour):
        from pptx.dml.color import RGBColor

        return RGBColor.from_string(hex_colour)

    def slide(self, section, title, subtitle=None):
        from pptx.util import Inches

        self.page += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bar = slide.shapes.add_shape(1, 0, 0, self.prs.slide_width, Inches(0.12))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self._rgb(NAVY)
        bar.line.fill.background()
        if section:
            self.text(slide, 0.5, 0.3, 9, 0.3, section.upper(), size=10, bold=True, colour=GOLD)
        self.text(slide, 0.5, 0.55, 12.3, 0.6, title, size=24, bold=True, colour=NAVY)
        if subtitle:
            self.text(slide, 0.5, 1.12, 12.3, 0.35, subtitle, size=12, colour=GREY)
        self.text(slide, 0.5, 7.08, 8, 0.3, "LUUKA PLASTICS LIMITED  |  HR BOARD REPORT", size=8, colour=GREY)
        self.text(slide, 9.0, 7.08, 3.8, 0.3, "%s  ·  %d" % (self.tag, self.page), size=8, colour=GREY, align="right")
        return slide

    def text(self, slide, x, y, w, h, content, size=12, bold=False, colour=INK, align=None, fill=None, bullets=False):
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Inches, Pt

        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        if fill:
            box.fill.solid()
            box.fill.fore_color.rgb = self._rgb(fill)
        frame = box.text_frame
        frame.word_wrap = True
        items = content if isinstance(content, (list, tuple)) else [content]
        for index, item in enumerate(items or [""]):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            run = paragraph.add_run()
            run.text = ("•  " if bullets and item else "") + (item or "")
            run.font.size, run.font.bold = Pt(size), bold
            run.font.color.rgb = self._rgb(colour)
            if align == "right":
                paragraph.alignment = PP_ALIGN.RIGHT
            elif align == "center":
                paragraph.alignment = PP_ALIGN.CENTER
        return box

    def band(self, slide, label, content, y, h=0.62, colour=NAVY):
        from pptx.util import Pt

        box = self.text(slide, 0.5, y, 12.3, h, "", size=11, fill=PALE)
        paragraph = box.text_frame.paragraphs[0]
        run = paragraph.runs[0]
        run.text = label.upper() + ":   "
        run.font.bold, run.font.size = True, Pt(11)
        run.font.color.rgb = self._rgb(colour)
        rest = paragraph.add_run()
        rest.text = content or "–"
        rest.font.size = Pt(11)
        rest.font.color.rgb = self._rgb(INK)

    def tiles(self, slide, items, y=1.6, h=1.15):
        width = (12.3 - 0.2 * (len(items) - 1)) / max(len(items), 1)
        for index, (value, label, note) in enumerate(items):
            x = 0.5 + index * (width + 0.2)
            self.text(slide, x, y, width, h, "", fill=PALE)
            self.text(slide, x + 0.15, y + 0.08, width - 0.3, 0.5, value, size=24, bold=True, colour=NAVY)
            self.text(slide, x + 0.15, y + 0.58, width - 0.3, 0.28, label.upper(), size=9, bold=True, colour=GOLD)
            if note:
                self.text(slide, x + 0.15, y + 0.82, width - 0.3, 0.3, note, size=9, colour=GREY)

    def table(self, slide, x, y, w, rows, widths=None, size=10, row_height=0.32):
        from pptx.util import Inches, Pt

        rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
        shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                                       Inches(row_height * len(rows)))
        table = shape.table
        if widths:
            total = float(sum(widths))
            for index, width in enumerate(widths):
                table.columns[index].width = Inches(w * width / total)
        for r, row in enumerate(rows):
            last = r == len(rows) - 1 and row and row[0].upper() in ("TOTAL", "COMPANY", "GRAND TOTAL")
            for c, value in enumerate(row):
                cell = table.cell(r, c)
                cell.text = value
                cell.fill.solid()
                cell.fill.fore_color.rgb = self._rgb(NAVY if r == 0 else (PALE if last or r % 2 == 0 else WHITE))
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(size)
                        run.font.bold = r == 0 or last
                        run.font.color.rgb = self._rgb(WHITE if r == 0 else INK)
                        if r and value in RATING_COLOURS:
                            run.font.color.rgb = self._rgb(RATING_COLOURS[value])
                            run.font.bold = True
        return table

    def chart(self, slide, kind, x, y, w, h, categories, series, number_format=None):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        from pptx.util import Inches, Pt

        data = CategoryChartData()
        data.categories = list(categories)
        for name, values in series:
            data.add_series(name, [None if value is None else float(value) for value in values])
        kind = XL_CHART_TYPE.LINE_MARKERS if kind == "line" else XL_CHART_TYPE.COLUMN_CLUSTERED
        frame = slide.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), data)
        chart = frame.chart
        chart.has_legend = len(series) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(9)
        chart.font.size = Pt(9)
        for index, plot_series in enumerate(chart.plots[0].series):
            colour = self._rgb(SERIES[index % len(SERIES)])
            if kind == XL_CHART_TYPE.LINE_MARKERS:
                plot_series.format.line.color.rgb = colour
                plot_series.marker.format.fill.solid()
                plot_series.marker.format.fill.fore_color.rgb = colour
            else:
                plot_series.format.fill.solid()
                plot_series.format.fill.fore_color.rgb = colour
        if number_format:
            chart.value_axis.tick_labels.number_format = number_format
            chart.value_axis.tick_labels.number_format_is_linked = False
        return chart

    # the slides
    def build(self):
        for step in (self.cover, self.contents, self.summary, self.head_count, self.head_count_yoy, self.recruitment,
                     self.exits, self.churn, self.comparative, self.wage_bill, self.components, self.labour_cost,
                     self.metrics, self.learning, self.training_value, self.safety, self.memoriam,
                     self.achievements, self.agenda, self.outlook, self.closing):
            step()
        out = io.BytesIO()
        self.prs.save(out)
        return out.getvalue()

    def cover(self):
        from pptx.util import Inches

        self.page += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        back = slide.shapes.add_shape(1, 0, 0, self.prs.slide_width, self.prs.slide_height)
        back.fill.solid()
        back.fill.fore_color.rgb = self._rgb(NAVY)
        back.line.fill.background()
        stripe = slide.shapes.add_shape(1, Inches(0.8), Inches(3.55), Inches(1.6), Inches(0.08))
        stripe.fill.solid()
        stripe.fill.fore_color.rgb = self._rgb(GOLD)
        stripe.line.fill.background()
        self.text(slide, 0.8, 1.9, 11, 0.8, "HR PERFORMANCE", size=40, bold=True, colour=WHITE)
        self.text(slide, 0.8, 2.65, 11, 0.8, "BOARD REPORT", size=40, bold=True, colour="E8A317")
        self.text(slide, 0.8, 3.85, 11, 0.5, self.f.get("label") or "", size=20, colour=WHITE)
        presented = frappe.utils.format_date(self.doc.presented_on) if self.doc.get("presented_on") else ""
        self.text(slide, 0.8, 4.45, 11, 0.4, "Prepared by %s%s" % (self.doc.get("prepared_by") or "HR Department",
                                                                   ("  |  Presented " + presented) if presented else ""),
                  size=13, colour="DCE4EF")

    def contents(self):
        slide = self.slide(None, "Agenda", self.f.get("label"))
        for index, (title, subtitle) in enumerate(SECTIONS):
            column, row = divmod(index, 5)
            x, y = 0.5 + column * 6.3, 1.7 + row * 1.0
            self.text(slide, x, y, 0.8, 0.6, "%02d" % (index + 1), size=24, bold=True, colour=GOLD)
            self.text(slide, x + 0.9, y, 5.2, 0.35, title, size=15, bold=True, colour=NAVY)
            self.text(slide, x + 0.9, y + 0.36, 5.2, 0.35, subtitle, size=11, colour=GREY)

    def summary(self):
        slide = self.slide("Executive Summary", "State of Human Capital  %s" % self.tag,
                           "A view of workforce health and its business impact, %s" % (self.f.get("label") or ""))
        self.text(slide, 0.5, 1.6, 6.2, 0.3, "HEADLINE", size=10, bold=True, colour=GOLD)
        self.text(slide, 0.5, 1.9, 6.2, 2.2, self.doc.get("headline") or "–", size=12)
        self.text(slide, 0.5, 4.2, 6.2, 0.3, "KEY ACHIEVEMENTS", size=10, bold=True, colour=GOLD)
        self.text(slide, 0.5, 4.5, 6.2, 2.4, lines(self.doc.get("key_achievements")) or ["–"], size=11, bullets=True)
        rows = [["BOARD HR HEALTH RATING", "RATING", "NOTE"]] + [
            [row.area, row.rating or "–", row.note or ""] for row in self.doc.get("ratings") or []]
        self.table(slide, 7.0, 1.6, 5.8, rows, widths=(2.2, 1.2, 3.4), size=9, row_height=0.5)

    def head_count(self):
        rows = self.f.get("head_count") or []
        total = rows[-1] if rows else {}
        slide = self.slide("Section 02", "Head Count Report · %s" % self.f.get("label", ""),
                           "Company-wide workforce at the quarter's end, against the quarter before")
        self.tiles(slide, [
            (n(total.get("total")), "Total workforce", "All plants · %s vs the quarter before" % signed(total.get("qoq"))),
            (n(total.get("permanent")), "Permanent staff", "%s of workforce" % pct(total.get("permanent_share_end"))),
            (n(total.get("casual")), "Casual workers", "%s of workforce" % pct(100 - (total.get("permanent_share_end") or 0)
                                                                              if total.get("total") else None)),
            (pct(100.0 * (total.get("male") or 0) / total["total"], 0) if total.get("total") else "–", "Male workforce",
             "%s female" % n(total.get("female"))),
        ])
        table = [["PLANT", "PERMANENT", "CASUAL", "TOTAL", "% OF TOTAL", "MALE", "FEMALE", "QoQ"]]
        for row in rows:
            table.append([plant_name(row["plant"]).upper() if not row["plant"] else row["plant"], n(row["permanent"]),
                          n(row["casual"]), n(row["total"]), pct(row["share"]), n(row["male"]), n(row["female"]),
                          arrow_count(row.get("qoq"))])
        self.table(slide, 0.5, 3.0, 12.3, table, widths=(2.4, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3))
        monthly = self.f.get("monthly_head_count") or []
        self.text(slide, 0.5, 3.4 + 0.32 * len(table), 12.3, 0.35,
                  "MONTHLY:  " + "  →  ".join(n(value) for value in monthly), size=11, bold=True, colour=NAVY)
        self.band(slide, "Key insight", self.doc.get("head_count_insight"), 6.3)

    def head_count_yoy(self):
        slide = self.slide("Section 02  ·  Board request", "Head Count Comparison · Year on Year",
                           "The same three months, a year before, by plant")
        before = self.f.get("monthly_head_count_last_year") or []
        now = self.f.get("monthly_head_count") or []
        if not before:
            self.band(slide, "Not yet", "Last year's months are not in the system: import them as HR Monthly Snapshots "
                                        "and get the figures again.", 1.7)
            return
        months = self._month_names()
        self.tiles(slide, [
            (n(before[-1]), "A year before", " · ".join(n(value) for value in before[:-1])),
            (n(now[-1] if now else None), "This quarter's end", " · ".join(n(value) for value in now[:-1])),
            (arrow(change(now[-1], before[-1])) if now else "–", "Year-on-year growth",
             "%s employees" % signed((now[-1] - before[-1]) if now else None)),
        ])
        self.chart(slide, "column", 0.5, 2.95, 5.6, 3.3, months,
                   [(str(int(self.f.get("year", 0)) - 1), before), (str(self.f.get("year", "")), now)])
        table = [["PLANT"] + [month.upper()[:3] for month in months] + ["PERM SHARE"]]
        for row in self.f.get("yoy_head_count") or []:
            table.append([row["plant"]] + ["%s → %s" % (n(old), n(new)) for old, new in row["months"]]
                         + ["%s → %s" % (pct(row["permanent_share"][0]), pct(row["permanent_share"][1]))])
        self.table(slide, 6.3, 2.95, 6.5, table, size=9)
        notes = lines(self.doc.get("yoy_notes"))
        if notes:
            self.band(slide, "What the board should note", "  ·  ".join(notes), 6.35)

    def recruitment(self):
        rows = self.f.get("recruitment") or []
        total = rows[-1] if rows else {}
        slide = self.slide("Section 03", "Recruitment Overview · %s" % self.f.get("label", ""),
                           "Hiring volume, additions and replacements, against the quarter before and a year before")
        self.tiles(slide, [
            (n(total.get("total")), "Hires this quarter",
             "Replacements %s + additions %s" % (n(total.get("replacements")), n(total.get("additions")))),
            (pct(100.0 * (total.get("replacements") or 0) / total["total"], 0) if total.get("total") else "–",
             "Replacement hiring", "%s backfilled leavers" % n(total.get("replacements"))),
            (arrow(change(total.get("total"), total.get("previous"))), "Quarter on quarter",
             "%s → %s" % (n(total.get("previous")), n(total.get("total")))),
            (arrow(change(total.get("total"), total.get("last_year"))), "Year on year",
             "%s → %s" % (n(total.get("last_year")), n(total.get("total")))),
        ])
        table = [["PLANT", "REPLACEMENTS", "ADDITIONS", "PERMANENT", "CASUAL", "TOTAL", "QUARTER BEFORE", "QoQ",
                  "A YEAR BEFORE", "YoY"]]
        for row in rows:
            table.append([row["plant"] or "GRAND TOTAL", n(row["replacements"]), n(row["additions"]), n(row["permanent"]),
                          n(row["casual"]), n(row["total"]), n(row.get("previous")),
                          arrow(change(row["total"], row.get("previous"))), n(row.get("last_year")),
                          arrow(change(row["total"], row.get("last_year")))])
        self.table(slide, 0.5, 3.0, 12.3, table, size=9)
        self.band(slide, "Key insight", self.doc.get("recruitment_insight"), 5.55)
        if self.doc.get("demand_roles"):
            self.band(slide, "Top demand roles", self.doc.demand_roles, 6.25, colour=GOLD)

    def exits(self):
        rows = self.f.get("exits") or []
        total = rows[-1] if rows else {}
        months = self._month_names()
        slide = self.slide("Section 03", "Exit & Attrition Analysis · %s" % self.f.get("label", ""),
                           "Exits and monthly attrition by plant · Target: under %s a month" % pct(self.f.get("target"), 0))
        monthly = total.get("months") or []
        highest = max((entry for entry in monthly if entry.get("rate") is not None), key=lambda e: e["rate"],
                      default={})
        self.tiles(slide, [
            (n(total.get("total")), "Exits this quarter",
             " · ".join("%s %s" % (name[:3], n(entry["exits"])) for name, entry in zip(months, monthly))),
            (pct(total.get("average")), "Average monthly attrition", "A year before: %s" % pct(total.get("last_year_average"))),
            (pct(highest.get("rate")), "Highest month", " → ".join(pct(entry.get("rate")) for entry in monthly)),
            (n(total.get("regrettable")), "Regrettable", "%s of exits" % pct(100.0 * (total.get("regrettable") or 0)
                                                                              / total["total"] if total.get("total") else None)),
        ])
        series = [(row["plant"], [entry.get("rate") for entry in row["months"]]) for row in rows[:-1]]
        series.append((_("Company"), [entry.get("rate") for entry in monthly]))
        self.chart(slide, "column", 0.5, 2.95, 5.4, 2.6, months, series, number_format='0.0"%"')
        table = [["PLANT"] + [month.upper() for month in months] + ["EXITS", "AVG / MONTH", "A YEAR BEFORE"]]
        for row in rows:
            table.append([row["plant"] or "COMPANY"] + ["%s  (%s)" % (n(e["exits"]), pct(e.get("rate")))
                                                         for e in row["months"]]
                         + [n(row["total"]), pct(row.get("average")), n(row.get("last_year"))])
        self.table(slide, 6.1, 2.95, 6.7, table, size=9)
        if self.doc.get("regrettable_note"):
            self.band(slide, "Regrettable exits", self.doc.regrettable_note, 5.65, h=0.55, colour=RED)
        self.band(slide, "Key insight", self.doc.get("exits_insight"), 6.3)

    def churn(self):
        rows = self.f.get("churn") or []
        slide = self.slide("Section 03", "Churn by Employment Type & Workforce Reconciliation",
                           "Who is leaving, permanent against casual, and whether the movements tally to the head count")
        plants = [row["plant"] or _("Company") for row in rows]
        series = [(_("Permanent"), [row["permanent"][1] for row in rows]), (_("Casual"), [row["casual"][1] for row in rows])]
        if rows and "permanent_last_year" in rows[0]:
            series = [(_("Permanent a year before"), [row["permanent_last_year"][1] for row in rows]), series[0],
                      (_("Casual a year before"), [row["casual_last_year"][1] for row in rows]), series[1]]
        self.chart(slide, "column", 0.5, 1.6, 6.0, 3.1, plants, series, number_format='0.0"%"')
        table = [["PLANT", "PERMANENT", "CASUAL"]] + [[row["plant"] or "COMPANY",
                                                         "%s  (%s)" % (n(row["permanent"][0]), pct(row["permanent"][1])),
                                                         "%s  (%s)" % (n(row["casual"][0]), pct(row["casual"][1]))]
                                                        for row in rows]
        self.table(slide, 6.8, 1.6, 6.0, table, size=10)
        recon = [["PLANT", "OPENING", "+ HIRES", "− EXITS", "= EXPECTED", "REPORTED", "VARIANCE"]]
        for row in self.f.get("reconciliation") or []:
            recon.append([row["plant"] or "TOTAL", n(row["opening"]), "+" + n(row["hires"]), "−" + n(row["exits"]),
                          n(row["expected"]), n(row["reported"]), signed(row["variance"])])
        self.table(slide, 0.5, 4.85, 12.3, recon, size=9, row_height=0.27)
        self.band(slide, "Reading the numbers", self.doc.get("churn_insight"), 6.38, h=0.58)

    def comparative(self):
        slide = self.slide("Section 04  ·  Board request", "Year-on-Year Comparative",
                           "Recruitment, exits, wage bill, head count and safety for the same three months a year before")
        if self.f.get("last_year_missing"):
            self.band(slide, "Not yet", "Last year's months are not in the system: import them as HR Monthly Snapshots.",
                      1.7)
            return
        plants = self.f.get("plants") or []
        heads = {row["plant"]: row for row in self.f.get("yoy_head_count") or []}
        hire = {row["plant"]: row for row in self.f.get("recruitment") or []}
        gone = {row["plant"]: row for row in self.f.get("exits") or []}
        churned = {row["plant"]: row for row in self.f.get("churn") or []}
        pay = {row["plant"]: row for row in self.f.get("wage_bill") or []}
        safe = {row["plant"]: row for row in self.f.get("safety") or []}
        total_now = (self.f.get("monthly_head_count") or [None])[-1]
        total_before = (self.f.get("monthly_head_count_last_year") or [None])[-1]
        self.tiles(slide, [
            (arrow(change(total_now, total_before)), "Head count YoY", "%s → %s" % (n(total_before), n(total_now))),
            (arrow(change(hire[None]["total"], hire[None]["last_year"])), "Recruitment YoY",
             "%s → %s hires" % (n(hire[None]["last_year"]), n(hire[None]["total"]))),
            (arrow(change(gone[None]["total"], gone[None]["last_year"])), "Exits YoY",
             "%s → %s" % (n(gone[None]["last_year"]), n(gone[None]["total"]))),
            (arrow(pay[None]["yoy"]), "Wage bill YoY", "UGX %sM → %sM" % (millions(pay[None]["last_year"]),
                                                                          millions(pay[None]["wage_bill"]))),
        ])

        def pair(before, now, fmt=n):
            return "%s → %s" % (fmt(before), fmt(now))

        table = [["METRIC"] + [plant.upper() for plant in plants] + ["A YEAR BEFORE", "THIS QUARTER", "YoY"]]
        last_month = [row["months"][-1] for row in [heads[plant] for plant in plants]] if plants else []
        table.append(["Head count (quarter end)"] + [pair(month[0], month[1]) for month in last_month]
                     + [n(total_before), n(total_now), arrow(change(total_now, total_before))])
        table.append(["Recruitment"] + [pair(hire[p]["last_year"], hire[p]["total"]) for p in plants]
                     + [n(hire[None]["last_year"]), n(hire[None]["total"]),
                        arrow(change(hire[None]["total"], hire[None]["last_year"]))])
        table.append(["Exits (all)"] + [pair(gone[p]["last_year"], gone[p]["total"]) for p in plants]
                     + [n(gone[None]["last_year"]), n(gone[None]["total"]),
                        arrow(change(gone[None]["total"], gone[None]["last_year"]))])
        casual = lambda plant, key: (churned[plant].get(key) or (None, None))[0]  # noqa: E731
        table.append(["of which casual"] + [pair(casual(p, "casual_last_year"), casual(p, "casual")) for p in plants]
                     + [n(casual(None, "casual_last_year")), n(casual(None, "casual")),
                        arrow(change(casual(None, "casual"), casual(None, "casual_last_year")))])
        table.append(["Avg monthly attrition"] + [pair(gone[p]["last_year_average"], gone[p]["average"], pct) for p in plants]
                     + [pct(gone[None]["last_year_average"]), pct(gone[None]["average"]),
                        signed((gone[None]["average"] or 0) - (gone[None]["last_year_average"] or 0), 1, " pts")])
        table.append(["Wage bill (UGX M)"] + [pair(pay[p]["last_year"], pay[p]["wage_bill"], millions) for p in plants]
                     + [millions(pay[None]["last_year"]), millions(pay[None]["wage_bill"]), arrow(pay[None]["yoy"])])
        table.append(["Overtime, all types (UGX M)"]
                     + [pair(pay[p]["overtime_last_year"], pay[p]["overtime"], millions) for p in plants]
                     + [millions(pay[None]["overtime_last_year"]), millions(pay[None]["overtime"]),
                        arrow(change(pay[None]["overtime"], pay[None]["overtime_last_year"]))])
        table.append(["Wage cost / employee / month (UGX K)"]
                     + [pair(_k(pay[p]["per_employee_month_last_year"]), _k(pay[p]["per_employee_month"])) for p in plants]
                     + [n(_k(pay[None]["per_employee_month_last_year"])), n(_k(pay[None]["per_employee_month"])),
                        arrow(change(pay[None]["per_employee_month"], pay[None]["per_employee_month_last_year"]))])
        table.append(["Workplace incidents"] + [pair(safe[p]["last_year"], safe[p]["total"]) for p in plants]
                     + [n(safe[None]["last_year"]), n(safe[None]["total"]),
                        arrow(change(safe[None]["total"], safe[None]["last_year"]))])
        self.table(slide, 0.5, 2.95, 12.3, table, size=9, row_height=0.33)
        self.band(slide, "Key insight", self.doc.get("yoy_insight"), 6.3)

    def wage_bill(self):
        rows = self.f.get("wage_bill") or []
        months = self._month_names()
        slide = self.slide("Section 05", "Wage Bill Analysis · %s" % self.f.get("label", ""),
                           "Labour cost, output and cost per kg by plant")
        self.chart(slide, "column", 0.5, 1.6, 6.2, 4.3, months,
                   [("%s (UGX M)" % row["plant"], [round((entry["wage_bill"] or 0) / 1e6, 1) for entry in row["months"]])
                    for row in rows[:-1]])
        y = 1.6
        for row in rows[:-1]:
            self.text(slide, 7.0, y, 5.8, 0.3, row["plant"], size=13, bold=True, colour=NAVY)
            self.text(slide, 7.0, y + 0.3, 5.8, 0.3, "Quarter: UGX %sM   QoQ %s  ·  YoY %s" % (
                millions(row["wage_bill"]), signed(row.get("qoq"), 1, "%"), signed(row.get("yoy"), 1, "%")),
                size=10, colour=GOLD, bold=True)
            details = ["%s output: %s kg  →  Cost/kg: UGX %s" % (name[:3], n(entry["output_kg"]), n(entry["cost_per_kg"]))
                       for name, entry in zip(months, row["months"])]
            self.text(slide, 7.0, y + 0.6, 5.8, 0.75, details, size=9)
            y += 1.45
        self.band(slide, "Trend", self.doc.get("wage_insight"), 6.3)

    def components(self):
        slide = self.slide("Section 05", "Wage Bill Components & Overtime Trends",
                           "What is driving the increase, and where overtime spikes")
        series = self.f.get("overtime_series") or {}
        if series:
            self.chart(slide, "line", 0.5, 1.6, 6.0, 3.6, self.f.get("overtime_months") or [],
                       [(year, [round(value / 1e6, 1) for value in values]) for year, values in sorted(series.items())])
            self.text(slide, 0.5, 1.4, 6.0, 0.25, "Total overtime by month (UGX M)", size=10, bold=True, colour=GREY)
        table = [["COMPONENT", "A YEAR BEFORE", "THIS QUARTER", "YoY", "SHARE OF INCREASE"]]
        for row in self.f.get("components") or []:
            table.append([row["group"], millions(row.get("last_year")), millions(row["now"]), arrow(row.get("yoy")),
                          pct(row.get("share_of_increase"), 0)])
        total = (self.f.get("wage_bill") or [{}])[-1]
        table.append(["TOTAL (UGX M)", millions(total.get("last_year")), millions(total.get("wage_bill")),
                      arrow(total.get("yoy")), "100%" if total.get("last_year") else "–"])
        self.table(slide, 6.8, 1.6, 6.0, table, size=9)
        self.band(slide, "Overtime pattern", self.doc.get("overtime_insight"), 5.6, h=0.55)
        self.band(slide, "Control plan", self.doc.get("control_plan"), 6.25, colour=GOLD)

    def labour_cost(self):
        rows = self.f.get("labour_cost") or []
        total = rows[-1] if rows else {}
        months = self._month_names()
        slide = self.slide("Section 05  ·  Board request", "Labour Cost as a % of Revenue",
                           "Staff costs over revenue by plant, %s" % self.f.get("label", ""))
        self.tiles(slide, [
            (pct(total.get("share")), "Staff cost ÷ revenue", "Quarter before: %s" % pct(total.get("previous_share"))),
            (billions(total.get("revenue")), "Revenue (UGX)", "%s on the quarter before" % arrow(
                change(total.get("revenue"), total.get("previous_revenue")))),
            (billions(total.get("staff_cost")), "Staff costs (UGX)",
             _("From Finance") if total.get("from_finance") else _("Payroll wage bill")),
            ("%sM" % millions(total.get("revenue_per_employee")) if total.get("revenue_per_employee") else "–",
             "Revenue / employee", _("UGX, the quarter")),
            ("UGX %s" % n(total.get("cost_per_kg")), "Labour cost / kg", _("Plant wage bill")),
        ])
        self.chart(slide, "line", 0.5, 2.95, 5.4, 2.6, months,
                   [(row["plant"], row.get("monthly_share") or []) for row in rows[:-1]], number_format='0.0"%"')
        table = [["PLANT", "REVENUE", "STAFF COST", "%", "QUARTER BEFORE %", "REV / EMPLOYEE", "COST / KG"]]
        for row in rows:
            table.append([row["plant"] or "TOTAL", billions(row["revenue"]), billions(row["staff_cost"]), pct(row["share"]),
                          pct(row.get("previous_share")),
                          "%sM" % millions(row["revenue_per_employee"]) if row.get("revenue_per_employee") else "–",
                          n(row.get("cost_per_kg"))])
        self.table(slide, 6.1, 2.95, 6.7, table, size=9)
        self.band(slide, "Method", self.doc.get("labour_method"), 5.65, h=0.55, colour=GREY)
        self.band(slide, "Key insight", self.doc.get("labour_insight"), 6.3)

    def metrics(self):
        slide = self.slide("Section 06  ·  Board request", "HR Metrics That Drive Business Results",
                           "The measures the board asked to see: this quarter's reading, what it signals, and status")
        rows = [["#", "METRIC", "READING", "WHAT IT TELLS THE BOARD", "STATUS"]] + [
            [row.number, row.metric, row.reading or "", row.tells or "", row.status or ""]
            for row in self.doc.get("metrics") or []]
        self.table(slide, 0.5, 1.6, 12.3, rows, widths=(0.5, 2.4, 4.0, 4.4, 1.0), size=9, row_height=0.6)
        self.band(slide, "The CEO-level view", self.doc.get("ceo_view"), 6.3)

    def learning(self):
        slide = self.slide("Section 07", "Learning & Development · %s" % self.tag,
                           "Training delivered in the quarter across the plants")
        columns = (("Quality, Systems & Compliance", self.doc.get("ld_quality")),
                   ("People & Leadership", self.doc.get("ld_people")),
                   ("Commercial & Financial", self.doc.get("ld_commercial")))
        if not any(text for _title, text in columns):
            held = ["%s (%s, %s attended)" % (row["event"], row["day"], row["attended"])
                    for row in self.f.get("training_held") or []]
            columns = (("Training held this quarter", "\n".join(held[:12])), ("", ""), ("", ""))
        for index, (title, text) in enumerate(columns):
            x = 0.5 + index * 4.15
            if title:
                self.text(slide, x, 1.6, 3.95, 0.35, title, size=13, bold=True, colour=NAVY)
                self.text(slide, x, 2.0, 3.95, 3.5, lines(text) or ["–"], size=10, bullets=True)
        self.band(slide, "Key insight", self.doc.get("ld_insight"), 5.65, h=0.55)
        self.band(slide, "Pipeline", self.doc.get("ld_pipeline"), 6.3, colour=GOLD)

    def training_value(self):
        rows = self.doc.get("training_value") or []
        if not rows:
            return
        slide = self.slide("Section 07", "Training Value & ROI",
                           "Each programme's value: participation, learning, application, result")
        table = [["RANK", "PROGRAMME", "REACH", "P · L · A · R", "VALUE EVIDENCE", "SCORE / 5"]]
        for rank, row in enumerate(sorted(rows, key=lambda row: -(row.score or 0)), 1):
            dots = " ".join("●" if row.get(field) else "○" for field in ("participation", "learning", "application",
                                                                          "result"))
            table.append([rank, row.programme, row.reach or "", dots, row.evidence or "", "%.1f" % (row.score or 0)])
        self.table(slide, 0.5, 1.6, 12.3, table, widths=(0.6, 3.6, 2.2, 1.4, 3.6, 0.9), size=9, row_height=0.45)

    def safety(self):
        rows = self.f.get("safety") or []
        total = rows[-1] if rows else {}
        months = self._month_names()
        slide = self.slide("Section 08", "Environmental Health & Safety · %s" % self.tag,
                           "Incidents by plant, against the same months a year before")
        self.tiles(slide, [
            (n(total.get("total")), "Incidents this quarter", "All plants"),
            (n(total.get("last_year")), "A year before", "The same months"),
            (arrow(change(total.get("total"), total.get("last_year"))), "Year on year", ""),
            (n(total.get("lost_time")), "Lost-time incidents", "%s fatalities" % n(total.get("fatalities"))),
        ])
        self.chart(slide, "line", 0.5, 2.95, 5.6, 2.8, months, [(row["plant"], row["months"]) for row in rows[:-1]])
        table = [["PLANT", "A YEAR BEFORE", "THIS QUARTER", "CHANGE"]] + [
            [row["plant"] or "TOTAL", n(row.get("last_year")), n(row["total"]),
             arrow(change(row["total"], row.get("last_year")))] for row in rows]
        self.table(slide, 6.3, 2.95, 6.5, table, size=10)
        actions = lines(self.doc.get("ehs_actions"))
        if actions:
            self.band(slide, "Our actions", "  ".join("%d. %s" % (i, a) for i, a in enumerate(actions, 1)), 5.85, h=0.5)
        if self.doc.get("ehs_critical"):
            self.band(slide, "Critical", self.doc.ehs_critical, 6.4, h=0.55, colour=RED)

    def memoriam(self):
        rows = self.doc.get("memoriam") or []
        if not rows:
            return
        slide = self.slide(None, "In Memoriam")
        for index, row in enumerate(rows[:4]):
            y = 1.7 + index * 1.3
            self.text(slide, 0.5, y, 12.3, 0.45, row.person, size=20, bold=True, colour=NAVY)
            self.text(slide, 0.5, y + 0.45, 12.3, 0.3, "  ·  ".join(value for value in (
                row.role, row.plant, (_("Passed %s") % frappe.utils.format_date(row.passed_on)) if row.passed_on else "")
                if value), size=12, colour=GOLD)
            if row.note:
                self.text(slide, 0.5, y + 0.78, 12.3, 0.45, row.note, size=11, colour=GREY)
        self.text(slide, 0.5, 6.6, 12.3, 0.4, _("May their souls rest in peace."), size=12, colour=GREY, align="center")

    def achievements(self):
        notes = self.doc.get("plant_notes") or []
        milestones = lines(self.doc.get("company_milestones"))
        if not notes and not milestones:
            return
        slide = self.slide("Section 09", "Achievements & Notable Events · %s" % self.tag,
                           "Milestones across the plants")
        width = 12.3 / max(len(notes), 1)
        for index, row in enumerate(notes[:4]):
            self.text(slide, 0.5 + index * width, 1.6, width - 0.2, 0.35, row.plant or "", size=13, bold=True, colour=NAVY)
            self.text(slide, 0.5 + index * width, 2.0, width - 0.2, 2.6, lines(row.notes) or ["–"], size=10, bullets=True)
        if milestones:
            self.text(slide, 0.5, 4.8, 12.3, 0.35, _("Company-wide milestones"), size=13, bold=True, colour=GOLD)
            self.text(slide, 0.5, 5.2, 12.3, 1.7, milestones, size=10, bullets=True)

    def agenda(self):
        rows = self.doc.get("agenda") or []
        if not rows:
            return
        slide = self.slide("Section 09", "Strategic People Agenda · HR as Business Partner",
                           "How HR's levers map to the business imperatives")
        table = [["BUSINESS IMPERATIVE", "HR LEVER", "PROGRESS", "NEXT MILESTONE"]] + [
            [row.imperative or "", row.lever or "", row.progress or "", row.milestone or ""] for row in rows]
        self.table(slide, 0.5, 1.6, 12.3, table, size=9, row_height=0.62)

    def outlook(self):
        slide = self.slide("Section 09", "Key Challenges & Outlook", "Risks the board should watch, and HR's priorities")
        self.text(slide, 0.5, 1.6, 6.0, 0.35, _("Key Challenges"), size=14, bold=True, colour=RED)
        self.text(slide, 0.5, 2.0, 6.0, 4.8, lines(self.doc.get("challenges")) or ["–"], size=11, bullets=True)
        self.text(slide, 6.8, 1.6, 6.0, 0.35, _("Priorities"), size=14, bold=True, colour=GREEN)
        self.text(slide, 6.8, 2.0, 6.0, 4.8, lines(self.doc.get("priorities")) or ["–"], size=11, bullets=True)

    def closing(self):
        self.page += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        back = slide.shapes.add_shape(1, 0, 0, self.prs.slide_width, self.prs.slide_height)
        back.fill.solid()
        back.fill.fore_color.rgb = self._rgb(NAVY)
        back.line.fill.background()
        plants = "  ·  ".join(self.f.get("plants") or [])
        heads = (self.f.get("monthly_head_count") or [None])[-1]
        self.text(slide, 0.8, 3.0, 11.7, 0.6, "  ·  ".join(part for part in (
            _("HR Department"), self.doc.get("company"), _("{0} Board Report").format(self.tag)) if part),
                  size=18, colour=WHITE, align="center")
        self.text(slide, 0.8, 3.7, 11.7, 0.5, "%s%s" % (plants, ("  ·  %s Employees" % n(heads)) if heads else ""),
                  size=13, colour="DCE4EF", align="center")

    def _month_names(self):
        quarter = self.f.get("quarter") or self.doc.quarter
        first = ("Q1", "Q2", "Q3", "Q4").index(quarter) * 3
        return [("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December")[first + index] for index in range(3)]


def _k(value):
    return None if value is None else round(float(value) / 1000.0)


# ── The workbook ──────────────────────────────────────────────────────
def workbook(doc, figures):
    """The pack's tables, a sheet each, for whoever works the numbers further."""
    if not figures:
        frappe.throw(_("Get the figures first: the workbook is made from them."), title=_("HR Board Report"))
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    book = Workbook()
    book.remove(book.active)
    head_fill = PatternFill("solid", fgColor=NAVY)

    def sheet(title, header, rows):
        page = book.create_sheet(title[:31])
        page.append(header)
        for cell in page[1]:
            cell.font = Font(bold=True, color=WHITE)
            cell.fill = head_fill
        for row in rows:
            page.append([("" if value is None else value) for value in row])
        for column in page.columns:
            page.column_dimensions[column[0].column_letter].width = max(12, min(40, max(len(str(c.value or ""))
                                                                                          for c in column) + 2))
        page.freeze_panes = "B2"

    plant = lambda value: value or "Total"  # noqa: E731
    sheet("Head Count", ["Plant", "Permanent", "Casual", "Total", "% of Total", "Male", "Female", "QoQ"],
          [[plant(r["plant"]), r["permanent"], r["casual"], r["total"], r["share"], r["male"], r["female"], r.get("qoq")]
           for r in figures.get("head_count") or []])
    sheet("Recruitment", ["Plant", "Replacements", "Additions", "Permanent", "Casual", "Total", "Quarter Before",
                          "A Year Before"],
          [[plant(r["plant"]), r["replacements"], r["additions"], r["permanent"], r["casual"], r["total"],
            r.get("previous"), r.get("last_year")] for r in figures.get("recruitment") or []])
    sheet("Exits", ["Plant", "Month 1 Exits", "Month 1 %", "Month 2 Exits", "Month 2 %", "Month 3 Exits", "Month 3 %",
                    "Quarter Exits", "Average %", "Regrettable", "A Year Before"],
          [[plant(r["plant"])] + [value for e in r["months"] for value in (e["exits"], e.get("rate"))]
           + [r["total"], r.get("average"), r.get("regrettable"), r.get("last_year")] for r in figures.get("exits") or []])
    sheet("Reconciliation", ["Plant", "Opening", "Hires", "Exits", "Expected", "Reported", "Variance"],
          [[plant(r["plant"]), r["opening"], r["hires"], r["exits"], r["expected"], r["reported"], r["variance"]]
           for r in figures.get("reconciliation") or []])
    sheet("Wage Bill", ["Plant", "Month 1", "Month 2", "Month 3", "Quarter", "Quarter Before", "A Year Before",
                        "Output kg", "Cost per kg"],
          [[plant(r["plant"])] + [e["wage_bill"] for e in r["months"]]
           + [r["wage_bill"], r.get("previous"), r.get("last_year"), sum(e["output_kg"] or 0 for e in r["months"]),
              r.get("cost_per_kg")] for r in figures.get("wage_bill") or []])
    sheet("Components", ["Component", "A Year Before", "This Quarter", "YoY %", "Share of Increase %"],
          [[r["group"], r.get("last_year"), r["now"], r.get("yoy"), r.get("share_of_increase")]
           for r in figures.get("components") or []])
    sheet("Labour Cost", ["Plant", "Revenue", "Staff Cost", "%", "Quarter Before %", "Revenue per Employee",
                          "Cost per kg"],
          [[plant(r["plant"]), r["revenue"], r["staff_cost"], r.get("share"), r.get("previous_share"),
            r.get("revenue_per_employee"), r.get("cost_per_kg")] for r in figures.get("labour_cost") or []])
    sheet("Safety", ["Plant", "Month 1", "Month 2", "Month 3", "Quarter", "A Year Before", "Lost Time", "Fatalities"],
          [[plant(r["plant"])] + list(r["months"]) + [r["total"], r.get("last_year"), r.get("lost_time"),
                                                      r.get("fatalities")] for r in figures.get("safety") or []])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
