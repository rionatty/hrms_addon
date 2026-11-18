# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Learning Command Centre's month as a PowerPoint deck (python-pptx, as
the board pack uses: bench pip install python-pptx). Native tables and charts,
so management can still edit it: the figures, the health and its parts, the
plants side by side, twelve months of trends, the certificates running out
and the insights.
"""

import io

import frappe
from frappe import _

NAVY, GOLD, GREY, INK, PALE = "14395E", "B8860B", "6B7280", "1F272E", "F3F5F8"
PART_LABELS = (("mandatory", "Mandatory Compliance"), ("certification", "Certification Compliance"),
               ("coverage", "Training Coverage"), ("competency", "Competency Coverage"), ("attendance", "Attendance"),
               ("assessment", "Assessment Performance"), ("effectiveness", "Training Effectiveness"),
               ("budget_use", "Budget Utilisation"), ("critical", "Critical Skills Coverage"))


def pct(value):
    return "–" if value is None else "%g%%" % round(float(value), 1)


def num(value):
    return "–" if value is None else "{:,.0f}".format(float(value))


def deck(data):
    try:
        from pptx import Presentation  # noqa: F401
    except ImportError:
        frappe.throw(_("The deck needs python-pptx on the server. Run: bench pip install python-pptx"),
                     title=_("Learning Command Centre"))
    return _Deck(data).build()


class _Deck:
    def __init__(self, data):
        from pptx import Presentation
        from pptx.util import Inches

        self.data = data
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.page = 0

    def rgb(self, value):
        from pptx.dml.color import RGBColor

        return RGBColor.from_string(value)

    def slide(self, title, subtitle=None):
        from pptx.util import Inches

        self.page += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bar = slide.shapes.add_shape(1, 0, 0, self.prs.slide_width, Inches(0.12))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self.rgb(NAVY)
        bar.line.fill.background()
        self.text(slide, 0.5, 0.4, 12.3, 0.6, title, 24, True, NAVY)
        if subtitle:
            self.text(slide, 0.5, 1.0, 12.3, 0.35, subtitle, 12, False, GREY)
        self.text(slide, 0.5, 7.05, 8, 0.3, _("LEARNING COMMAND CENTRE  |  {0}").format(self.data.get("month", "")[:7]),
                  8, False, GREY)
        self.text(slide, 11.5, 7.05, 1.3, 0.3, str(self.page), 8, False, GREY)
        return slide

    def text(self, slide, x, y, w, h, content, size=12, bold=False, colour=INK, fill=None):
        from pptx.util import Inches, Pt

        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        if fill:
            box.fill.solid()
            box.fill.fore_color.rgb = self.rgb(fill)
        frame = box.text_frame
        frame.word_wrap = True
        for index, line in enumerate(content if isinstance(content, (list, tuple)) else [content]):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            run = paragraph.add_run()
            run.text = str(line or "")
            run.font.size, run.font.bold = Pt(size), bold
            run.font.color.rgb = self.rgb(colour)
        return box

    def tiles(self, slide, items, y):
        width = (12.3 - 0.2 * (len(items) - 1)) / max(len(items), 1)
        for index, (value, label) in enumerate(items):
            x = 0.5 + index * (width + 0.2)
            self.text(slide, x, y, width, 1.1, "", fill=PALE)
            self.text(slide, x + 0.1, y + 0.08, width - 0.2, 0.5, value, 22, True, NAVY)
            self.text(slide, x + 0.1, y + 0.62, width - 0.2, 0.4, label.upper(), 9, True, GOLD)

    def table(self, slide, x, y, w, rows, size=10):
        from pptx.util import Inches, Pt

        rows = [[str("" if cell is None else cell) for cell in row] for row in rows]
        shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                                       Inches(0.3 * len(rows)))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                cell = shape.table.cell(r, c)
                cell.text = value
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(size)
                        run.font.bold = r == 0
                        run.font.color.rgb = self.rgb("FFFFFF" if r == 0 else INK)
                cell.fill.solid()
                cell.fill.fore_color.rgb = self.rgb(NAVY if r == 0 else ("FFFFFF" if r % 2 else PALE))

    def chart(self, slide, kind, categories, series, x, y, w, h):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        from pptx.util import Inches

        data = CategoryChartData()
        data.categories = categories
        for name, values in series:
            data.add_series(name, [float(value or 0) for value in values])
        chart = slide.shapes.add_chart({"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS}[kind],
                                       Inches(x), Inches(y), Inches(w), Inches(h), data).chart
        chart.has_legend = len(series) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
        return chart

    def build(self):
        d, f, health = self.data, self.data.get("figures") or {}, self.data.get("health") or {}
        slide = self.slide(_("Learning and Capability"), _("{0}, {1}").format(d.get("company") or "", d["month"][:7]))
        self.tiles(slide, [(pct(health.get("score")), _("Learning Health")), (pct(f.get("compliance")), _("Compliance")),
                           (pct(f.get("mandatory")), _("Mandatory")), (pct(f.get("certification")), _("Certificates"))],
                   1.6)
        self.tiles(slide, [(num(f.get("headcount")), _("Employees")), (pct(f.get("coverage")), _("Trained in 12 Months")),
                           (num(f.get("hours")), _("Hours this Month")), (num(f.get("spend")), _("Spend this Month"))],
                   2.9)
        self.tiles(slide, [(num(f.get("overdue")), _("Overdue")), (num(f.get("expiring")), _("Certificates Expiring")),
                           (pct(f.get("attendance")), _("Attendance")), (pct(f.get("pass_rate")), _("Pass Rate"))], 4.2)
        slide = self.slide(_("Learning Health"), _("The nine parts, each weighed as Learning Settings say"))
        parts = health.get("parts") or {}
        self.table(slide, 0.5, 1.6, 5.5, [[_("Part"), _("Score")]] + [[_(label), pct(parts.get(key))]
                                                                       for key, label in PART_LABELS])
        self.chart(slide, "bar", [_(label) for _key, label in PART_LABELS],
                   [(_("Score"), [parts.get(key) for key, _label in PART_LABELS])], 6.4, 1.5, 6.4, 5.2)
        plants = d.get("plants") or []
        if plants:
            slide = self.slide(_("Plants Side by Side"))
            self.table(slide, 0.5, 1.5, 12.3, [[_("Plant"), _("Health"), _("Compliance"), _("Mandatory"),
                                                _("Certificates"), _("Trained"), _("Hours"), _("Spend"), _("Overdue")]]
                       + [[row["branch"], pct(row.get("health")), pct(row.get("compliance")), pct(row.get("mandatory")),
                           pct(row.get("certification")), pct(row.get("coverage")), num(row.get("hours")),
                           num(row.get("spend")), num(row.get("overdue"))] for row in plants])
            self.chart(slide, "bar", [row["branch"] for row in plants],
                       [(_("Compliance %"), [row.get("compliance") for row in plants]),
                        (_("Health"), [row.get("health") for row in plants])], 0.5, 1.8 + 0.3 * (len(plants) + 1),
                       12.3, 3.5)
        months = d.get("trends") or []
        if months:
            slide = self.slide(_("Twelve Months"))
            self.chart(slide, "line", [row["month"] for row in months],
                       [(_("Compliance %"), [row.get("compliance") for row in months]),
                        (_("Certificates %"), [row.get("certification") for row in months]),
                        (_("Health"), [row.get("health") for row in months])], 0.5, 1.4, 12.3, 5.4)
        alerts = d.get("alerts") or []
        insights = d.get("insights") or []
        slide = self.slide(_("What Needs Attention"))
        self.text(slide, 0.5, 1.4, 6.2, 5.5, ["%s  %s" % (item["severity"].upper(), item["text"])
                                              for item in insights[:14]] or [_("Nothing stands out.")], 11)
        if alerts:
            self.table(slide, 6.9, 1.4, 5.9, [[_("Employee"), _("Certificate"), _("Expires")]]
                       + [[row.get("employee_name"), row.get("certification"), str(row.get("expiry_date") or "")]
                          for row in alerts[:14]], 9)
        out = io.BytesIO()
        self.prs.save(out)
        return out.getvalue()
