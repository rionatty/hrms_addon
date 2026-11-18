# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack as a PowerPoint deck and an Excel workbook, from an HR
Board Report: its figures (board_pack.quarter_figures, kept as JSON on the
report) and HR's own words. The deck follows Luuka's own (LPL HR Board
Report Q3 2026): the same sections in the same order, native charts and
tables, so the board reads what it is used to and HR can still edit it.
On top of theirs: a traffic light on every rating and KPI, each change
coloured by whether it is good or bad news, the eight quarters to this one,
the plants' scorecard, the figures their deck left out (the months over
target, the permanent share, output per employee, near misses, days lost),
talent risk and succession from the talent records, and each slide's
definitions at its foot.

The deck needs python-pptx on the server (bench pip install python-pptx);
the workbook needs only openpyxl, which Frappe already carries.
"""

import io
import os

import frappe
from frappe import _

NAVY, GOLD, GREY, INK, PALE, WHITE = "14395E", "B8860B", "6B7280", "1F272E", "F3F5F8", "FFFFFF"
GREEN, AMBER, RED = "1F7A4D", "B7791F", "A62B25"
SERIES = ("14395E", "E8A317", "2E86AB", "7A9E3B", "A62B25", "8E6C8A")
RATING_COLOURS = {"On Track": GREEN, "Watch": AMBER, "Action Needed": RED, "Action": RED, "Building": NAVY}
UP, DOWN = "up", "down"
SECTIONS = (
    ("Executive Summary", "Board HR health rating, the plants' scorecard and eight quarters of trends"),
    ("Head Count: Quarter & Year-on-Year", "Quarter snapshot; the same months a year before"),
    ("Recruitment, Exits & Churn", "Hiring, leavers, churn by employment type & reconciliation"),
    ("Year-on-Year Comparative", "Recruitment, exits, wage bill & safety against a year before"),
    ("Wage Bill, Overtime & Labour Cost", "Components, overtime trends, staff cost as % of revenue"),
    ("HR Metrics That Drive Business", "The board's seven KPIs, talent risk and succession"),
    ("Learning, Development & Training ROI", "The quarter's programmes and their value"),
    ("EHS & In Memoriam", "Safety trends and colleagues we lost this quarter"),
    ("Strategic People Agenda & Outlook", "HR as business partner: achievements, actions, priorities"),
)
DEFINITIONS = {
    "head_count": "Head count: employed when the month's last day is over. Casual: paid by the week (Weekly or Per "
                  "Piece). Expatriates are permanent staff.",
    "recruitment": "Addition: hired against a requisition for a new post or new addition. Replacement: against one "
                   "for a leaver. Unclassified: no requisition.",
    "exits": "Monthly attrition = exits ÷ average of opening and closing head count. Quarter = average of its three "
             "months. Red: over the target.",
    "churn": "Quarter churn = the type's exits ÷ average of its opening and closing. Reconciliation: opening + hires "
             "− exits + transfers in − transfers out.",
    "comparative": "The same three months a year before. Wage cost per employee = wage bill ÷ average head count ÷ 3.",
    "wage": "Wage bill: gross pay of submitted slips in shillings, an expatriate's converted at the slip's rate. "
            "Cost per kg = wage bill ÷ kg produced.",
    "components": "Permanent staff by component, then expatriates and casuals: the rows add up to the wage bill.",
    "labour": "Staff cost: Finance's for each plant and month where typed, else the payroll wage bill.",
    "metrics": "Lights against the target set in Board KPI Target; with none, against a year before.",
    "safety": "Incidents exclude near misses. LTIFR = lost-time injuries per million hours worked. Days lost: sick "
              "days or the doctor's rest, the longer.",
    "trends": "Each quarter from the facts of its three months; a quarter not built yet is blank.",
}


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


def good_or_bad(value, good):
    """The colour of a change: green where it is good news, red where it is
    bad, grey where it is none or nothing; navy where it is neither."""
    if value is None or not float(value):
        return GREY
    if good is None:
        return NAVY
    return GREEN if (float(value) > 0) == (good == UP) else RED


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


def _get(row, key, default=None):
    if row is None:
        return default
    value = row.get(key) if hasattr(row, "get") else getattr(row, key, None)
    return default if value is None else value


# ── The deck ──────────────────────────────────────────────────────────
def deck(doc, figures, logo=None):
    """The deck's bytes."""
    if not figures:
        frappe.throw(_("Get the figures first: the deck is made from them."), title=_("HR Board Report"))
    try:
        from pptx import Presentation  # noqa: F401
    except ImportError:
        frappe.throw(_("The deck needs python-pptx on the server. Run: bench pip install python-pptx"),
                     title=_("HR Board Report"))
    builder = _Deck(doc, figures, logo)
    return builder.build()


class _Deck:
    def __init__(self, doc, figures, logo=None):
        from pptx import Presentation
        from pptx.util import Inches

        self.doc, self.f, self.logo = doc, figures, logo if logo and os.path.exists(logo) else None
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.page = 0
        self.tag = "%s %s" % (figures.get("quarter") or doc.quarter, figures.get("year") or doc.year)

    # parts every slide uses
    def _rgb(self, hex_colour):
        from pptx.dml.color import RGBColor

        return RGBColor.from_string(hex_colour)

    def slide(self, section, title, subtitle=None, foot=None):
        from pptx.util import Inches

        self.page += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bar = slide.shapes.add_shape(1, 0, 0, self.prs.slide_width, Inches(0.12))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self._rgb(NAVY)
        bar.line.fill.background()
        if section:
            self.text(slide, 0.5, 0.3, 9, 0.3, section.upper(), size=10, bold=True, colour=GOLD)
        self.text(slide, 0.5, 0.55, 10.4, 0.6, title, size=24, bold=True, colour=NAVY)
        if subtitle:
            self.text(slide, 0.5, 1.12, 10.4, 0.35, subtitle, size=12, colour=GREY)
        self.mark(slide)
        if foot and DEFINITIONS.get(foot):
            self.text(slide, 0.5, 6.86, 12.3, 0.24, DEFINITIONS[foot], size=7, colour=GREY)
        self.text(slide, 0.5, 7.08, 8, 0.3, "LUUKA PLASTICS LIMITED  |  HR BOARD REPORT", size=8, colour=GREY)
        self.text(slide, 9.0, 7.08, 3.8, 0.3, "%s  ·  %d" % (self.tag, self.page), size=8, colour=GREY, align="right")
        return slide

    def mark(self, slide, x=11.05, y=0.22, w=1.8, h=0.75):
        """The company's logo in the corner, or the place kept for it."""
        from pptx.util import Inches

        if self.logo:
            try:
                slide.shapes.add_picture(self.logo, Inches(x), Inches(y), height=Inches(h))
                return
            except Exception:
                pass
        box = slide.shapes.add_shape(5, Inches(x), Inches(y), Inches(w), Inches(h))
        box.fill.background()
        box.line.color.rgb = self._rgb("C9D2DE")
        box.line.dash_style = 4
        frame = box.text_frame
        frame.text = "LOGO"
        run = frame.paragraphs[0].runs[0]
        from pptx.util import Pt

        run.font.size, run.font.bold = Pt(10), True
        run.font.color.rgb = self._rgb("9AA6B6")

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

    def dot(self, slide, x, y, rating, size=0.18):
        """A traffic light."""
        from pptx.util import Inches

        light = slide.shapes.add_shape(9, Inches(x), Inches(y), Inches(size), Inches(size))
        light.fill.solid()
        light.fill.fore_color.rgb = self._rgb(RATING_COLOURS.get(rating or "", "D1D5DB"))
        light.line.fill.background()
        return light

    def legend(self, slide, x, y):
        for index, (label, rating) in enumerate((("On track", "On Track"), ("Watch", "Watch"),
                                                 ("Action needed", "Action Needed"))):
            self.dot(slide, x + index * 1.45, y + 0.06, rating, 0.14)
            self.text(slide, x + index * 1.45 + 0.18, y, 1.2, 0.28, label, size=9, colour=GREY)

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
        """Figure tiles: (value, label, note) or (value, label, note, colour of the value)."""
        width = (12.3 - 0.2 * (len(items) - 1)) / max(len(items), 1)
        for index, item in enumerate(items):
            value, label, note = item[:3]
            colour = item[3] if len(item) > 3 and item[3] else NAVY
            x = 0.5 + index * (width + 0.2)
            self.text(slide, x, y, width, h, "", fill=PALE)
            self.text(slide, x + 0.15, y + 0.08, width - 0.3, 0.5, value, size=24, bold=True, colour=colour)
            self.text(slide, x + 0.15, y + 0.58, width - 0.3, 0.28, label.upper(), size=9, bold=True, colour=GOLD)
            if note:
                self.text(slide, x + 0.15, y + 0.82, width - 0.3, 0.3, note, size=9, colour=GREY)

    def table(self, slide, x, y, w, rows, widths=None, size=10, row_height=0.32, colours=None):
        """A native table; colours: {(row, column): hex} for a cell's text."""
        from pptx.util import Inches, Pt

        rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
        colours = colours or {}
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
                        if (r, c) in colours:
                            run.font.color.rgb = self._rgb(colours[(r, c)])
                            run.font.bold = True
        return table

    def chart(self, slide, kind, x, y, w, h, categories, series, number_format=None, legend=True):
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
        chart.has_title = False
        chart.has_legend = legend and len(series) > 1
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

    def total(self, key):
        rows = self.f.get(key) or []
        return next((row for row in rows if row.get("plant") is None), {})

    def plant_rows(self, key):
        return [row for row in self.f.get(key) or [] if row.get("plant") is not None]

    # the slides
    def build(self):
        for step in (self.cover, self.contents, self.summary, self.scorecard, self.trends, self.head_count,
                     self.head_count_yoy, self.recruitment, self.exits, self.churn, self.comparative, self.wage_bill,
                     self.components, self.labour_cost, self.metrics, self.talent, self.learning, self.training_value,
                     self.safety, self.memoriam, self.achievements, self.agenda, self.outlook, self.closing):
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
        self.mark(slide, x=10.6, y=0.5, w=2.2, h=1.0)
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
        self.text(slide, 0.5, 4.5, 6.2, 2.3, lines(self.doc.get("key_achievements")) or ["–"], size=11, bullets=True)
        self.text(slide, 7.0, 1.6, 5.8, 0.3, "BOARD HR HEALTH RATING", size=10, bold=True, colour=GOLD)
        ratings = list(self.doc.get("ratings") or [])
        for index, row in enumerate(ratings[:8]):
            y = 1.95 + index * 0.56
            self.dot(slide, 7.0, y + 0.06, _get(row, "rating"))
            self.text(slide, 7.3, y - 0.04, 5.5, 0.28, "%s%s" % (_get(row, "area", ""),
                                                                  "  ·  " + _get(row, "rating") if _get(row, "rating")
                                                                  else ""), size=11, bold=True, colour=NAVY)
            self.text(slide, 7.3, y + 0.21, 5.5, 0.3, _short(_get(row, "note", ""), 105), size=8.5, colour=GREY)
        self.legend(slide, 7.0, 6.5)

    def scorecard(self):
        """Each plant against each metric of the scorecard, in its light."""
        plants = [plant for plant in self.f.get("plants") or [] if plant]
        by_plant = self.f.get("by_plant") or {}
        if not plants or not by_plant:
            return
        from hrms_addon.hrms_addon import board_kpi_rules as kpi
        from hrms_addon.hrms_addon import board_pack_rules as rules

        slide = self.slide("Executive Summary", "The Plants' Scorecard · %s" % self.tag,
                           "Each plant against the measures the board watches", foot="metrics")
        year, quarter = int(self.f.get("year") or self.doc.year), self.f.get("quarter") or self.doc.quarter
        first = rules.month_bounds(*rules.quarter_months(year, quarter)[0])[0]
        last = rules.quarter_end(year, quarter)
        rows = [["MEASURE"] + [plant.upper() for plant in plants] + [_("COMPANY")]]
        colours = {}
        company = self.f.get("summary") or {}
        for r, metric in enumerate(kpi.SCORECARD, 1):
            line = [metric]
            field, _unit, direction, _kind = kpi.definition(metric)
            for c, plant in enumerate(plants + [None], 1):
                summary = by_plant.get(plant) if plant else company
                value = (summary or {}).get(field)
                target = kpi.target_for(self.f.get("targets"), metric, plant, first, last)
                found = kpi.light(value, target) if target else None
                if not found and plant:
                    found = kpi.trend_light(value, company.get(field), direction)
                line.append(kpi.show(metric, value))
                if found:
                    colours[(r, c)] = RATING_COLOURS[found]
            rows.append(line)
        self.table(slide, 0.5, 1.6, 12.3, rows, widths=[3.0] + [1.8] * (len(plants) + 1), size=10, row_height=0.42,
                   colours=colours)
        self.text(slide, 0.5, 1.65 + 0.42 * len(rows), 12.3, 0.3,
                  _("A plant's colour: against the company's own figure where no target is set for it."), size=9,
                  colour=GREY)
        self.legend(slide, 0.5, 6.4)

    def trends(self):
        trend = [row for row in self.f.get("trends") or []]
        if not trend:
            return
        slide = self.slide("Executive Summary", "Eight Quarters of Trends",
                           "Head count, attrition, the wage bill and safety, quarter by quarter", foot="trends")
        labels = [row["label"] for row in trend]

        def series(field, scale=1.0):
            return [None if (row["summary"] or {}).get(field) is None else round(row["summary"][field] / scale, 1)
                    for row in trend]

        self.text(slide, 0.5, 1.55, 6.0, 0.3, _("Head count at the quarter's end"), size=10, bold=True, colour=GREY)
        self.chart(slide, "column", 0.5, 1.8, 6.0, 2.35, labels, [(_("Head count"), series("head_count"))])
        self.text(slide, 6.8, 1.55, 6.0, 0.3, _("Monthly attrition, quarter average (%)"), size=10, bold=True,
                  colour=GREY)
        self.chart(slide, "line", 6.8, 1.8, 6.0, 2.35, labels, [(_("Attrition"), series("attrition"))],
                   number_format='0.0"%"')
        self.text(slide, 0.5, 4.25, 6.0, 0.3, _("Wage bill (UGX M)"), size=10, bold=True, colour=GREY)
        self.chart(slide, "column", 0.5, 4.5, 6.0, 2.3, labels, [(_("Wage bill"), series("wage_bill", 1e6))])
        self.text(slide, 6.8, 4.25, 6.0, 0.3, _("Incidents, near misses and LTIFR"), size=10, bold=True, colour=GREY)
        self.chart(slide, "line", 6.8, 4.5, 6.0, 2.3, labels,
                   [(_("Incidents"), series("incidents")), (_("Near misses"), series("near_misses")),
                    (_("LTIFR"), series("ltifr"))])

    def head_count(self):
        rows = self.f.get("head_count") or []
        total = self.total("head_count")
        slide = self.slide("Section 02", "Head Count Report · %s" % self.f.get("label", ""),
                           "Company-wide workforce at the quarter's end, against the quarter before", foot="head_count")
        self.tiles(slide, [
            (n(total.get("total")), "Total workforce", "All plants · %s vs the quarter before" % signed(total.get("qoq"))),
            (n(total.get("permanent")), "Permanent staff", "%s of workforce (was %s)" % (
                pct(total.get("permanent_share_end")), pct(total.get("permanent_share_start")))),
            (n(total.get("casual")), "Casual workers", "%s of workforce" % pct(100 - (total.get("permanent_share_end") or 0)
                                                                              if total.get("total") else None)),
            (n(total.get("conversions")), "Converted", "Casual to permanent this quarter"),
            (pct(100.0 * (total.get("male") or 0) / total["total"], 0) if total.get("total") else "–", "Male workforce",
             "%s female" % n(total.get("female"))),
        ])
        table = [["PLANT", "PERMANENT", "CASUAL", "TOTAL", "% OF TOTAL", "MALE", "FEMALE", "QoQ"]]
        for row in rows:
            table.append([row["plant"] or "TOTAL", n(row["permanent"]), n(row["casual"]), n(row["total"]),
                          pct(row["share"]), n(row["male"]), n(row["female"]), arrow_count(row.get("qoq"))])
        self.table(slide, 0.5, 3.0, 12.3, table, widths=(2.4, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3))
        y = 3.1 + 0.32 * len(table)
        monthly = self.f.get("monthly_head_count") or []
        self.text(slide, 0.5, y, 12.3, 0.3, "MONTHLY:  " + "  →  ".join(n(value) for value in monthly), size=11,
                  bold=True, colour=NAVY)
        chips = [row for row in rows if row.get("plant")]
        width = 12.3 / max(len(chips), 1)
        for index, row in enumerate(chips[:4]):
            colour = good_or_bad((row.get("permanent_share_end") or 0) - (row.get("permanent_share_start") or 0), UP)
            self.text(slide, 0.5 + index * width, y + 0.35, width - 0.15, 0.45,
                      "%s  ·  permanent share %s → %s" % (row["plant"], pct(row.get("permanent_share_start")),
                                                          pct(row.get("permanent_share_end"))),
                      size=10, bold=True, colour=colour, fill=PALE)
        self.band(slide, "Key insight", self.doc.get("head_count_insight"), 6.15, h=0.62)

    def head_count_yoy(self):
        slide = self.slide("Section 02  ·  Board request", "Head Count Comparison · Year on Year",
                           "The same three months, a year before, by plant", foot="comparative")
        before = self.f.get("monthly_head_count_last_year") or []
        now = self.f.get("monthly_head_count") or []
        if not before:
            self.band(slide, "Not yet", "Last year's months are not in the system: import them into HR Employee "
                                        "Month and get the figures again.", 1.7)
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
            table.append([row["plant"] or "TOTAL"] + ["%s → %s" % (n(old), n(new)) for old, new in row["months"]]
                         + ["%s → %s" % (pct(row["permanent_share"][0]), pct(row["permanent_share"][1]))])
        self.table(slide, 6.3, 2.95, 6.5, table, size=9)
        notes = lines(self.doc.get("yoy_notes"))
        if notes:
            self.band(slide, "What the board should note", "  ·  ".join(notes), 6.2, h=0.6)

    def recruitment(self):
        rows = self.f.get("recruitment") or []
        total = self.total("recruitment")
        hiring = self.f.get("hiring") or {}
        slide = self.slide("Section 03", "Recruitment Overview · %s" % self.f.get("label", ""),
                           "Hiring volume, additions and replacements, against the quarter before and a year before",
                           foot="recruitment")
        self.tiles(slide, [
            (n(total.get("total")), "Hires this quarter",
             "Replacements %s + additions %s" % (n(total.get("replacements")), n(total.get("additions")))),
            (pct(100.0 * (total.get("replacements") or 0) / total["total"], 0) if total.get("total") else "–",
             "Replacement hiring", "%s with no requisition" % n(total.get("unclassified"))),
            (arrow(change(total.get("total"), total.get("previous"))), "Quarter on quarter",
             "%s → %s" % (n(total.get("previous")), n(total.get("total")))),
            ("%s days" % n(hiring.get("time_to_fill")) if hiring.get("time_to_fill") is not None else "–",
             "Time to fill", "Requisition to joining"),
            (pct(hiring.get("retention_90")), "90-day retention", "%s hires due" % n(hiring.get("retention_cohort"))),
        ])
        table = [["PLANT", "REPLACEMENTS", "ADDITIONS", "NO REQUISITION", "PERMANENT", "CASUAL", "TOTAL",
                  "QUARTER BEFORE", "QoQ", "A YEAR BEFORE", "YoY"]]
        for row in rows:
            table.append([row["plant"] or "GRAND TOTAL", n(row["replacements"]), n(row["additions"]),
                          n(row.get("unclassified")), n(row["permanent"]), n(row["casual"]), n(row["total"]),
                          n(row.get("previous")), arrow(change(row["total"], row.get("previous"))),
                          n(row.get("last_year")), arrow(change(row["total"], row.get("last_year")))])
        self.table(slide, 0.5, 3.0, 12.3, table, size=9)
        self.band(slide, "Key insight", self.doc.get("recruitment_insight"), 5.45, h=0.62)
        if self.doc.get("demand_roles"):
            self.band(slide, "Top demand roles", self.doc.demand_roles, 6.12, h=0.62, colour=GOLD)

    def exits(self):
        rows = self.f.get("exits") or []
        total = self.total("exits")
        months = self._month_names()
        target = self.f.get("target")
        slide = self.slide("Section 03", "Exit & Attrition Analysis · %s" % self.f.get("label", ""),
                           "Exits and monthly attrition by plant · Target: under %s a month" % pct(target, 0)
                           if target is not None else "Exits and monthly attrition by plant", foot="exits")
        monthly = total.get("months") or []
        highest = max((entry for entry in monthly if entry.get("rate") is not None), key=lambda e: e["rate"],
                      default={})
        self.tiles(slide, [
            (n(total.get("total")), "Exits this quarter",
             " · ".join("%s %s" % (name[:3], n(entry["exits"])) for name, entry in zip(months, monthly))),
            (pct(total.get("average")), "Average monthly attrition", "A year before: %s" % pct(total.get("last_year_average")),
             RED if target is not None and (total.get("average") or 0) > target else NAVY),
            (pct(highest.get("rate")), "Highest month", " → ".join(pct(entry.get("rate")) for entry in monthly),
             RED if highest.get("over_target") else NAVY),
            (n(total.get("regrettable")), "Regrettable", "%s of exits (quarter before: %s)" % (
                pct(100.0 * (total.get("regrettable") or 0) / total["total"] if total.get("total") else None),
                n(total.get("previous_regrettable")))),
            ("%s / %s" % (n(total.get("voluntary")), n(total.get("involuntary"))), "Voluntary / involuntary", ""),
        ])
        series = [(row["plant"], [entry.get("rate") for entry in row["months"]]) for row in rows if row["plant"]]
        series.append((_("Company"), [entry.get("rate") for entry in monthly]))
        if target is not None:
            series.append((_("Target"), [target] * len(months)))
        self.chart(slide, "column", 0.5, 2.95, 5.4, 2.6, months, series, number_format='0.0"%"')
        table = [["PLANT"] + [month.upper() for month in months] + ["EXITS", "AVG / MONTH", "A YEAR BEFORE"]]
        colours = {}
        for r, row in enumerate(rows, 1):
            table.append([row["plant"] or "COMPANY"] + ["%s  (%s)" % (n(e["exits"]), pct(e.get("rate")))
                                                         for e in row["months"]]
                         + [n(row["total"]), pct(row.get("average")), n(row.get("last_year"))])
            for c, entry in enumerate(row["months"], 1):
                if entry.get("over_target"):
                    colours[(r, c)] = RED
        self.table(slide, 6.1, 2.95, 6.7, table, size=9, colours=colours)
        if self.doc.get("regrettable_note"):
            self.band(slide, "Regrettable exits", self.doc.regrettable_note, 5.6, h=0.55, colour=RED)
        self.band(slide, "Key insight", self.doc.get("exits_insight"), 6.2, h=0.6)

    def churn(self):
        rows = self.f.get("churn") or []
        slide = self.slide("Section 03", "Churn by Employment Type & Workforce Reconciliation",
                           "Who is leaving, permanent against casual, and whether the movements tally to the head count",
                           foot="churn")
        plants = [row["plant"] or _("Company") for row in rows]
        series = [(_("Permanent"), [row["permanent"][1] for row in rows]), (_("Casual"), [row["casual"][1] for row in rows])]
        if rows and "permanent_last_year" in rows[0]:
            series = [(_("Permanent a year before"), [row["permanent_last_year"][1] for row in rows]), series[0],
                      (_("Casual a year before"), [row["casual_last_year"][1] for row in rows]), series[1]]
        self.chart(slide, "column", 0.5, 1.6, 6.0, 2.9, plants, series, number_format='0.0"%"')
        table = [["PLANT", "PERMANENT", "CASUAL"]] + [[row["plant"] or "COMPANY",
                                                         "%s  (%s)" % (n(row["permanent"][0]), pct(row["permanent"][1])),
                                                         "%s  (%s)" % (n(row["casual"][0]), pct(row["casual"][1]))]
                                                        for row in rows]
        self.table(slide, 6.8, 1.6, 6.0, table, size=10)
        recon = [["PLANT", "OPENING", "+ HIRES", "− EXITS", "+ IN", "− OUT", "= EXPECTED", "REPORTED", "VARIANCE",
                  "PAID"]]
        colours = {}
        for r, row in enumerate(self.f.get("reconciliation") or [], 1):
            recon.append([row["plant"] or "TOTAL", n(row["opening"]), "+" + n(row["hires"]), "−" + n(row["exits"]),
                          "+" + n(row.get("transfers_in")), "−" + n(row.get("transfers_out")), n(row["expected"]),
                          n(row["reported"]), signed(row["variance"]), n(row.get("payroll_heads"))])
            if row.get("variance"):
                colours[(r, 8)] = RED
        self.table(slide, 0.5, 4.6, 12.3, recon, size=9, row_height=0.27, colours=colours)
        issues = [row for row in self.f.get("data_quality") or [] if row.get("count")]
        if issues:
            self.text(slide, 0.5, 4.62 + 0.27 * len(recon), 12.3, 0.25, _("To put right: ") + "  ·  ".join(
                "%s %s" % (row["label"], n(row["count"])) for row in issues), size=9, colour=RED)
        self.band(slide, "Reading the numbers", self.doc.get("churn_insight"), 6.22, h=0.58)

    def comparative(self):
        slide = self.slide("Section 04  ·  Board request", "Year-on-Year Comparative",
                           "Recruitment, exits, wage bill, head count and safety for the same three months a year before",
                           foot="comparative")
        if self.f.get("last_year_missing"):
            self.band(slide, "Not yet", "Last year's months are not in the system: import them into HR Employee Month, "
                                        "HR Pay Fact and HR Safety Fact.", 1.7)
            return
        plants = [plant for plant in self.f.get("plants") or []]
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
             "%s → %s" % (n(gone[None]["last_year"]), n(gone[None]["total"])),
             good_or_bad(change(gone[None]["total"], gone[None]["last_year"]), DOWN)),
            (arrow(pay[None]["yoy"]), "Wage bill YoY", "UGX %sM → %sM" % (millions(pay[None]["last_year"]),
                                                                          millions(pay[None]["wage_bill"])),
             good_or_bad(pay[None]["yoy"], DOWN)),
        ])

        def pair(before, now, fmt=n):
            return "%s → %s" % (fmt(before), fmt(now))

        table = [["METRIC"] + [plant.upper() for plant in plants] + ["A YEAR BEFORE", "THIS QUARTER", "YoY"]]
        colours = {}
        last_column = len(table[0]) - 1

        def add(label, cells, before, now, moved, good, fmt=n):
            table.append([label] + cells + [fmt(before), fmt(now), moved])
            colours[(len(table) - 1, last_column)] = good_or_bad(_number(moved), good)

        last_month = [heads[plant]["months"][-1] for plant in plants]
        add("Head count (quarter end)", [pair(month[0], month[1]) for month in last_month], total_before, total_now,
            arrow(change(total_now, total_before)), None)
        add("Recruitment", [pair(hire[p]["last_year"], hire[p]["total"]) for p in plants], hire[None]["last_year"],
            hire[None]["total"], arrow(change(hire[None]["total"], hire[None]["last_year"])), None)
        add("Exits (all)", [pair(gone[p]["last_year"], gone[p]["total"]) for p in plants], gone[None]["last_year"],
            gone[None]["total"], arrow(change(gone[None]["total"], gone[None]["last_year"])), DOWN)
        casual = lambda plant, key: (churned[plant].get(key) or (None, None))[0]  # noqa: E731
        add("of which casual", [pair(casual(p, "casual_last_year"), casual(p, "casual")) for p in plants],
            casual(None, "casual_last_year"), casual(None, "casual"),
            arrow(change(casual(None, "casual"), casual(None, "casual_last_year"))), DOWN)
        add("Avg monthly attrition", [pair(gone[p]["last_year_average"], gone[p]["average"], pct) for p in plants],
            gone[None]["last_year_average"], gone[None]["average"],
            signed((gone[None]["average"] or 0) - (gone[None]["last_year_average"] or 0), 1, " pts"), DOWN, pct)
        add("Wage bill (UGX M)", [pair(pay[p]["last_year"], pay[p]["wage_bill"], millions) for p in plants],
            pay[None]["last_year"], pay[None]["wage_bill"], arrow(pay[None]["yoy"]), DOWN, millions)
        add("Overtime, all types (UGX M)", [pair(pay[p]["overtime_last_year"], pay[p]["overtime"], millions)
                                            for p in plants],
            pay[None]["overtime_last_year"], pay[None]["overtime"],
            arrow(change(pay[None]["overtime"], pay[None]["overtime_last_year"])), DOWN, millions)
        add("Wage cost / employee / month (UGX K)",
            [pair(_k(pay[p]["per_employee_month_last_year"]), _k(pay[p]["per_employee_month"])) for p in plants],
            _k(pay[None]["per_employee_month_last_year"]), _k(pay[None]["per_employee_month"]),
            arrow(change(pay[None]["per_employee_month"], pay[None]["per_employee_month_last_year"])), DOWN)
        add("Workplace incidents", [pair(safe[p]["last_year"], safe[p]["total"]) for p in plants], safe[None]["last_year"],
            safe[None]["total"], arrow(change(safe[None]["total"], safe[None]["last_year"])), DOWN)
        self.table(slide, 0.5, 2.95, 12.3, table, size=9, row_height=0.31, colours=colours)
        self.band(slide, "Key insight", self.doc.get("yoy_insight"), 6.2, h=0.6)

    def wage_bill(self):
        rows = self.plant_rows("wage_bill")
        months = self._month_names()
        slide = self.slide("Section 05", "Wage Bill Analysis · %s" % self.f.get("label", ""),
                           "Labour cost, output and cost per kg by plant", foot="wage")
        self.chart(slide, "column", 0.5, 1.6, 6.2, 4.3, months,
                   [("%s (UGX M)" % row["plant"], [round((entry["wage_bill"] or 0) / 1e6, 1) for entry in row["months"]])
                    for row in rows])
        y = 1.6
        step = 4.5 / max(len(rows), 3)
        for row in rows[:4]:
            self.text(slide, 7.0, y, 5.8, 0.3, row["plant"], size=13, bold=True, colour=NAVY)
            self.text(slide, 7.0, y + 0.3, 5.8, 0.3, "Quarter: UGX %sM   QoQ %s  ·  YoY %s" % (
                millions(row["wage_bill"]), signed(row.get("qoq"), 1, "%"), signed(row.get("yoy"), 1, "%")),
                size=10, colour=good_or_bad(row.get("yoy"), DOWN) if row.get("yoy") is not None else GOLD, bold=True)
            details = ["%s output: %s kg  →  Cost/kg: UGX %s" % (name[:3], n(entry["output_kg"]), n(entry["cost_per_kg"]))
                       for name, entry in zip(months, row["months"])]
            self.text(slide, 7.0, y + 0.6, 5.8, 0.75, details, size=9)
            y += step
        self.band(slide, "Trend", self.doc.get("wage_insight"), 6.2, h=0.6)

    def components(self):
        slide = self.slide("Section 05", "Wage Bill Components & Overtime Trends",
                           "What is driving the increase, and where overtime spikes", foot="components")
        series = self.f.get("overtime_series") or {}
        if series:
            self.chart(slide, "line", 0.5, 1.6, 6.0, 3.6, self.f.get("overtime_months") or [],
                       [(year, [round(value / 1e6, 1) for value in values]) for year, values in sorted(series.items())])
            self.text(slide, 0.5, 1.4, 6.0, 0.25, "Total overtime by month (UGX M)", size=10, bold=True, colour=GREY)
        table = [["COMPONENT", "A YEAR BEFORE", "THIS QUARTER", "YoY", "SHARE OF BILL", "SHARE OF INCREASE"]]
        colours = {}
        for r, row in enumerate(self.f.get("components") or [], 1):
            label = row["group"] if row["group"] in ("Expatriates", "Casuals") else "%s (permanent)" % row["group"]
            table.append([label, millions(row.get("last_year")), millions(row["now"]), arrow(row.get("yoy")),
                          pct(row.get("share_of_bill"), 0), pct(row.get("share_of_increase"), 0)])
            colours[(r, 3)] = good_or_bad(row.get("yoy"), DOWN)
        total = self.total("wage_bill")
        table.append(["TOTAL (UGX M)", millions(total.get("last_year")), millions(total.get("wage_bill")),
                      arrow(total.get("yoy")), "100%", "100%" if total.get("last_year") else "–"])
        self.table(slide, 6.8, 1.6, 6.0, table, size=8.5, colours=colours)
        self.band(slide, "Overtime pattern", self.doc.get("overtime_insight"), 5.55, h=0.55)
        self.band(slide, "Control plan", self.doc.get("control_plan"), 6.17, h=0.6, colour=GOLD)

    def labour_cost(self):
        rows = self.f.get("labour_cost") or []
        total = self.total("labour_cost")
        months = self._month_names()
        slide = self.slide("Section 05  ·  Board request", "Labour Cost as a % of Revenue",
                           "Staff costs over revenue by plant, %s" % self.f.get("label", ""), foot="labour")
        source = {"All": _("From Finance"), "Part": _("Partly from Finance")}.get(total.get("from_finance"),
                                                                                    _("Payroll wage bill"))
        moved = (total.get("share") or 0) - (total.get("previous_share") or 0) if total.get("previous_share") else None
        self.tiles(slide, [
            (pct(total.get("share")), "Staff cost ÷ revenue", "Quarter before: %s" % pct(total.get("previous_share")),
             good_or_bad(moved, DOWN) if moved else NAVY),
            (billions(total.get("revenue")), "Revenue (UGX)", "%s on the quarter before" % arrow(
                change(total.get("revenue"), total.get("previous_revenue")))),
            (billions(total.get("staff_cost")), "Staff costs (UGX)", source),
            ("%sM" % millions(total.get("revenue_per_employee")) if total.get("revenue_per_employee") else "–",
             "Revenue / employee", _("UGX, the quarter")),
            (n(total.get("output_per_employee_month")), "Output / employee", _("kg a month")),
        ])
        self.chart(slide, "line", 0.5, 2.95, 5.4, 2.6, months,
                   [(row["plant"], row.get("monthly_share") or []) for row in rows if row["plant"]],
                   number_format='0.0"%"')
        table = [["PLANT", "REVENUE", "STAFF COST", "%", "QUARTER BEFORE %", "REV / EMPLOYEE", "KG / EMPLOYEE",
                  "COST / KG"]]
        colours = {}
        for r, row in enumerate(rows, 1):
            table.append([row["plant"] or "TOTAL", billions(row["revenue"]), billions(row["staff_cost"]), pct(row["share"]),
                          pct(row.get("previous_share")),
                          "%sM" % millions(row["revenue_per_employee"]) if row.get("revenue_per_employee") else "–",
                          n(row.get("output_per_employee_month")), n(row.get("cost_per_kg"))])
            if row.get("share") is not None and row.get("previous_share") is not None:
                colours[(r, 3)] = good_or_bad(row["share"] - row["previous_share"], DOWN)
        self.table(slide, 6.1, 2.95, 6.7, table, size=8.5, colours=colours)
        self.band(slide, "Method", self.doc.get("labour_method"), 5.6, h=0.55, colour=GREY)
        self.band(slide, "Key insight", self.doc.get("labour_insight"), 6.2, h=0.6)

    def metrics(self):
        slide = self.slide("Section 06  ·  Board request", "HR Metrics That Drive Business Results",
                           "The measures the board asked to see: this quarter's reading, what it signals, and status",
                           foot="metrics")
        rows = [["#", "METRIC", "READING", "WHAT IT TELLS THE BOARD", "STATUS"]]
        statuses = []
        for row in self.doc.get("metrics") or []:
            rows.append([_get(row, "number", ""), _get(row, "metric", ""), _get(row, "reading", ""),
                         _get(row, "tells", ""), _get(row, "status", "")])
            statuses.append(_get(row, "status"))
        self.table(slide, 0.5, 1.6, 12.3, rows, widths=(0.5, 2.4, 4.0, 4.4, 1.0), size=9, row_height=0.55)
        for index, status in enumerate(statuses, 1):
            self.dot(slide, 12.45, 1.6 + 0.55 * index + 0.2, status, 0.16)
        self.band(slide, "The CEO-level view", self.doc.get("ceo_view"), 6.2, h=0.6)

    def talent(self):
        talent = self.f.get("talent") or {}
        totals = talent.get("totals") or {}
        if not totals.get("critical_roles") and not totals.get("top_talent"):
            return
        slide = self.slide("Section 06", "Talent Risk & Succession Coverage",
                           "Critical roles and their successors, top talent and flight risk, from the talent records")
        self.tiles(slide, [
            (pct(totals.get("succession_coverage")), "Critical roles covered",
             "%s of %s" % (n(totals.get("covered_roles")), n(totals.get("critical_roles")))),
            (n(totals.get("ready_now")), "Successors ready now", "%s roles held by one person" % n(
                totals.get("single_person_roles"))),
            (n(totals.get("top_talent")), "Top talent", "%s high potential" % n(totals.get("high_potential"))),
            (n(totals.get("top_talent_at_risk")), "Top talent at high flight risk", "",
             RED if totals.get("top_talent_at_risk") else GREEN),
            (pct(totals.get("skills_gap")), "Critical skills below level", "%s assessed" % n(totals.get("skills_assessed"))),
        ])
        table = [["PLANT", "CRITICAL ROLES", "COVERED", "AT RISK", "GAP", "READY NOW", "ONE-PERSON ROLES",
                  "TOP TALENT", "AT HIGH RISK"]]
        colours = {}
        plants = talent.get("plants") or {}
        for r, (plant, row) in enumerate(sorted(plants.items()), 1):
            table.append([plant, n(row.get("critical_roles")), n(row.get("covered_roles")), n(row.get("at_risk_roles")),
                          n(row.get("gap_roles")), n(row.get("ready_now")), n(row.get("single_person_roles")),
                          n(row.get("top_talent")), n(row.get("top_talent_at_risk"))])
            if row.get("gap_roles"):
                colours[(r, 4)] = RED
            if row.get("top_talent_at_risk"):
                colours[(r, 8)] = RED
        table.append(["TOTAL"] + [n(totals.get(key)) for key in ("critical_roles", "covered_roles", "at_risk_roles",
                                                                  "gap_roles", "ready_now", "single_person_roles",
                                                                  "top_talent", "top_talent_at_risk")])
        self.table(slide, 0.5, 3.0, 12.3, table, size=9.5, colours=colours)

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
                self.text(slide, x, 2.0, 3.95, 3.3, lines(text) or ["–"], size=10, bullets=True)
        people = self.total("people")
        if people:
            self.text(slide, 0.5, 5.2, 12.3, 0.3, "%s training hours  ·  %s hours per employee" % (
                n(people.get("training_hours")), n(people.get("training_per_employee"))), size=11, bold=True,
                colour=NAVY)
        self.band(slide, "Key insight", self.doc.get("ld_insight"), 5.6, h=0.55)
        self.band(slide, "Pipeline", self.doc.get("ld_pipeline"), 6.2, h=0.6, colour=GOLD)

    def training_value(self):
        rows = list(self.doc.get("training_value") or [])
        if not rows:
            return
        slide = self.slide("Section 07", "Training Value & ROI",
                           "Each programme's value: participation, learning, application, result")
        table = [["RANK", "PROGRAMME", "REACH", "P · L · A · R", "VALUE EVIDENCE", "SCORE / 5"]]
        for rank, row in enumerate(sorted(rows, key=lambda row: -(_get(row, "score", 0) or 0)), 1):
            dots = " ".join("●" if _get(row, field) else "○" for field in ("participation", "learning", "application",
                                                                            "result"))
            table.append([rank, _get(row, "programme", ""), _get(row, "reach", ""), dots, _get(row, "evidence", ""),
                          "%.1f" % (_get(row, "score", 0) or 0)])
        self.table(slide, 0.5, 1.6, 12.3, table[:12], widths=(0.6, 3.6, 2.2, 1.4, 3.6, 0.9), size=9, row_height=0.42)

    def safety(self):
        rows = self.f.get("safety") or []
        total = self.total("safety")
        months = self._month_names()
        hazards = self.f.get("hazards") or {}
        slide = self.slide("Section 08", "Environmental Health & Safety · %s" % self.tag,
                           "Incidents by plant, against the same months a year before", foot="safety")
        moved = change(total.get("total"), total.get("last_year"))
        self.tiles(slide, [
            (n(total.get("total")), "Incidents this quarter", "A year before: %s" % n(total.get("last_year"))),
            (arrow(moved), "Year on year", "", good_or_bad(moved, DOWN)),
            (n(total.get("near_misses")), "Near misses reported", "Not counted as incidents"),
            (n(total.get("lost_time")), "Lost-time incidents", "%s fatalities  ·  %s days lost" % (
                n(total.get("fatalities")), n(total.get("days_lost")))),
            (n(total.get("ltifr")) if total.get("ltifr") is None else "%.2f" % total["ltifr"], "LTIFR",
             "Per million hours worked"),
        ])
        self.chart(slide, "line", 0.5, 2.95, 5.6, 2.6, months,
                   [(row["plant"], row["months"]) for row in rows if row["plant"]])
        table = [["PLANT", "A YEAR BEFORE", "THIS QUARTER", "CHANGE", "NEAR MISSES", "DAYS LOST", "TOP HAZARD"]]
        colours = {}
        for r, row in enumerate(rows, 1):
            table.append([row["plant"] or "TOTAL", n(row.get("last_year")), n(row["total"]),
                          arrow(change(row["total"], row.get("last_year"))), n(row.get("near_misses")),
                          n(row.get("days_lost")), hazards.get(row["plant"] or "", "")])
            colours[(r, 3)] = good_or_bad(change(row["total"], row.get("last_year")), DOWN)
        self.table(slide, 6.3, 2.95, 6.5, table, size=8.5, colours=colours)
        actions = lines(self.doc.get("ehs_actions"))
        if actions:
            self.band(slide, "Our actions", "  ".join("%d. %s" % (i, a) for i, a in enumerate(actions, 1)), 5.62,
                      h=0.5)
        self.band(slide, "Critical" if self.doc.get("ehs_critical") else "Key insight",
                  self.doc.get("ehs_critical") or self.doc.get("ehs_insight"), 6.17, h=0.6,
                  colour=RED if self.doc.get("ehs_critical") else NAVY)

    def memoriam(self):
        rows = list(self.doc.get("memoriam") or [])
        if not rows:
            return
        slide = self.slide(None, "In Memoriam")
        for index, row in enumerate(rows[:4]):
            y = 1.7 + index * 1.3
            self.text(slide, 0.5, y, 12.3, 0.45, _get(row, "person", ""), size=20, bold=True, colour=NAVY)
            passed = _get(row, "passed_on")
            self.text(slide, 0.5, y + 0.45, 12.3, 0.3, "  ·  ".join(value for value in (
                _get(row, "role"), _get(row, "plant"), (_("Passed %s") % frappe.utils.format_date(passed)) if passed else "")
                if value), size=12, colour=GOLD)
            if _get(row, "note"):
                self.text(slide, 0.5, y + 0.78, 12.3, 0.45, _get(row, "note"), size=11, colour=GREY)
        self.text(slide, 0.5, 6.5, 12.3, 0.4, _("May their souls rest in peace."), size=12, colour=GREY, align="center")

    def achievements(self):
        notes = list(self.doc.get("plant_notes") or [])
        milestones = lines(self.doc.get("company_milestones"))
        if not notes and not milestones:
            return
        slide = self.slide("Section 09", "Achievements & Notable Events · %s" % self.tag,
                           "Milestones across the plants")
        width = 12.3 / max(len(notes), 1)
        for index, row in enumerate(notes[:4]):
            self.text(slide, 0.5 + index * width, 1.6, width - 0.2, 0.35, _get(row, "plant", ""), size=13, bold=True,
                      colour=NAVY)
            self.text(slide, 0.5 + index * width, 2.0, width - 0.2, 2.6, lines(_get(row, "notes")) or ["–"], size=10,
                      bullets=True)
        if milestones:
            self.text(slide, 0.5, 4.8, 12.3, 0.35, _("Company-wide milestones"), size=13, bold=True, colour=GOLD)
            self.text(slide, 0.5, 5.2, 12.3, 1.6, milestones, size=10, bullets=True)

    def agenda(self):
        rows = self.f.get("actions") or []
        if not rows:
            return
        slide = self.slide("Section 09", "Strategic People Agenda · HR as Business Partner",
                           "How HR's levers map to the business imperatives, and where each stands")
        table = [["BUSINESS IMPERATIVE", "HR LEVER", "OWNER", "DUE", "STATUS", "PROGRESS", "NEXT MILESTONE"]]
        colours = {}
        status_colours = {"On Track": GREEN, "At Risk": RED, "Not Started": AMBER, "Done": NAVY, "Dropped": GREY}
        for r, row in enumerate(rows[:9], 1):
            table.append([row.get("imperative") or "", row.get("lever") or "", row.get("action_owner_name") or "",
                          "%s %s" % (row.get("due_quarter") or "", row.get("due_year") or ""), row.get("status") or "",
                          "%s%%  %s" % (int(row.get("progress") or 0), row.get("progress_note") or ""),
                          row.get("milestone") or ""])
            colours[(r, 4)] = status_colours.get(row.get("status"), INK)
        self.table(slide, 0.5, 1.6, 12.3, table, widths=(2.4, 2.4, 1.4, 0.9, 1.0, 2.4, 2.2), size=8.5,
                   row_height=0.55, colours=colours)

    def outlook(self):
        slide = self.slide("Section 09", "Key Challenges & Outlook", "Risks the board should watch, and HR's priorities")
        self.text(slide, 0.5, 1.6, 6.0, 0.35, _("Key Challenges"), size=14, bold=True, colour=RED)
        self.text(slide, 0.5, 2.0, 6.0, 4.6, lines(self.doc.get("challenges")) or ["–"], size=11, bullets=True)
        self.text(slide, 6.8, 1.6, 6.0, 0.35, _("Priorities"), size=14, bold=True, colour=GREEN)
        year, quarter = int(self.f.get("year") or 0), self.f.get("quarter") or "Q1"
        following = (year + 1, "Q1") if quarter == "Q4" else (year, "Q%d" % (int(quarter[1]) + 1))
        priorities = ["%s (%s)" % (row.get("imperative"), row.get("milestone") or row.get("lever") or "")
                      for row in self.f.get("actions") or []
                      if row.get("status") in ("Not Started", "On Track", "At Risk")
                      and (int(row.get("due_year") or 0), row.get("due_quarter") or "") <= following]
        self.text(slide, 6.8, 2.0, 6.0, 4.6, priorities or ["–"], size=11, bullets=True)

    def closing(self):
        self.page += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        back = slide.shapes.add_shape(1, 0, 0, self.prs.slide_width, self.prs.slide_height)
        back.fill.solid()
        back.fill.fore_color.rgb = self._rgb(NAVY)
        back.line.fill.background()
        plants = "  ·  ".join(plant for plant in self.f.get("plants") or [] if plant)
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


def _short(text, size):
    """A line that fits its place: cut at the last word before size."""
    text = text or ""
    if len(text) <= size:
        return text
    return text[:size].rsplit(" ", 1)[0].rstrip(";,.") + "…"


def _number(text):
    """The signed number in a change as the deck prints it."""
    cleaned = str(text or "").replace("▲", "").replace("▼", "").replace("—", "").replace("−", "-").replace(",", "")
    cleaned = cleaned.replace("%", "").replace("pts", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


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
    sheet("Head Count", ["Plant", "Permanent", "Casual", "Expatriates", "Total", "% of Total", "Male", "Female", "QoQ",
                         "Converted"],
          [[plant(r["plant"]), r["permanent"], r["casual"], r.get("expatriate"), r["total"], r["share"], r["male"],
            r["female"], r.get("qoq"), r.get("conversions")] for r in figures.get("head_count") or []])
    sheet("Recruitment", ["Plant", "Replacements", "Additions", "No Requisition", "Permanent", "Casual", "Total",
                          "Quarter Before", "A Year Before"],
          [[plant(r["plant"]), r["replacements"], r["additions"], r.get("unclassified"), r["permanent"], r["casual"],
            r["total"], r.get("previous"), r.get("last_year")] for r in figures.get("recruitment") or []])
    sheet("Exits", ["Plant", "Month 1 Exits", "Month 1 %", "Month 2 Exits", "Month 2 %", "Month 3 Exits", "Month 3 %",
                    "Quarter Exits", "Average %", "Regrettable", "Voluntary", "Involuntary", "A Year Before"],
          [[plant(r["plant"])] + [value for e in r["months"] for value in (e["exits"], e.get("rate"))]
           + [r["total"], r.get("average"), r.get("regrettable"), r.get("voluntary"), r.get("involuntary"),
              r.get("last_year")] for r in figures.get("exits") or []])
    sheet("Reconciliation", ["Plant", "Opening", "Hires", "Exits", "Transfers In", "Transfers Out", "Expected",
                             "Reported", "Variance", "Paid"],
          [[plant(r["plant"]), r["opening"], r["hires"], r["exits"], r.get("transfers_in"), r.get("transfers_out"),
            r["expected"], r["reported"], r["variance"], r.get("payroll_heads")]
           for r in figures.get("reconciliation") or []])
    sheet("Wage Bill", ["Plant", "Month 1", "Month 2", "Month 3", "Quarter", "Quarter Before", "A Year Before",
                        "Output kg", "Cost per kg", "Overtime", "Overtime %"],
          [[plant(r["plant"])] + [e["wage_bill"] for e in r["months"]]
           + [r["wage_bill"], r.get("previous"), r.get("last_year"), sum(e["output_kg"] or 0 for e in r["months"]),
              r.get("cost_per_kg"), r.get("overtime"), r.get("overtime_share")] for r in figures.get("wage_bill") or []])
    sheet("Components", ["Component", "A Year Before", "This Quarter", "YoY %", "Share of Bill %",
                         "Share of Increase %"],
          [[r["group"], r.get("last_year"), r["now"], r.get("yoy"), r.get("share_of_bill"), r.get("share_of_increase")]
           for r in figures.get("components") or []])
    sheet("Labour Cost", ["Plant", "Revenue", "Staff Cost", "%", "Quarter Before %", "Revenue per Employee",
                          "Output per Employee a Month", "Cost per kg"],
          [[plant(r["plant"]), r["revenue"], r["staff_cost"], r.get("share"), r.get("previous_share"),
            r.get("revenue_per_employee"), r.get("output_per_employee_month"), r.get("cost_per_kg")]
           for r in figures.get("labour_cost") or []])
    sheet("Safety", ["Plant", "Month 1", "Month 2", "Month 3", "Quarter", "A Year Before", "Near Misses", "Lost Time",
                     "Fatalities", "Days Lost", "LTIFR"],
          [[plant(r["plant"])] + list(r["months"]) + [r["total"], r.get("last_year"), r.get("near_misses"),
                                                      r.get("lost_time"), r.get("fatalities"), r.get("days_lost"),
                                                      r.get("ltifr")] for r in figures.get("safety") or []])
    sheet("KPIs", ["No.", "KPI", "Measured By", "Value", "Target", "Light", "Reading"],
          [[r.get("number"), r.get("name"), r.get("metric"), r.get("value"), r.get("target"), r.get("light"),
            r.get("reading")] for r in figures.get("kpis") or []])
    sheet("Ratings", ["Area", "Rating", "Basis"],
          [[r.get("area"), r.get("rating"), r.get("basis")] for r in figures.get("ratings") or []])
    from hrms_addon.hrms_addon import board_pack_rules as rules

    sheet("Trends", ["Quarter"] + [field.replace("_", " ").title() for field in rules.SUMMARY_FIELDS],
          [[r.get("label")] + [(r.get("summary") or {}).get(field) for field in rules.SUMMARY_FIELDS]
           for r in figures.get("trends") or []])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
