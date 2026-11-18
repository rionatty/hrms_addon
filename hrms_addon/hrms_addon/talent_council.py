# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Talent Council pack of a review: the print format (print_format/
talent_council_pack, on the Talent Review) and the same as slides.

  talent_council_pack  the jinja method the print reads: the review's figures
                 (talent_command.figures) and the decisions taken in it
  decisions      what the review came to: the placements finalised by their
                 suggested decision, the successors the council endorsed,
                 the pools confirmed, what the plans cost
  download_deck  the pack as a PowerPoint deck (python-pptx, as the HR
                 board pack's deck), native tables and charts HR can edit
"""

import io

import frappe
from frappe import _
from frappe.utils import cint, flt, format_date, today

from hrms_addon.hrms_addon import talent_command

REVIEW = "Talent Review"
NAVY, GOLD, GREY, INK, PALE, WHITE = "14395E", "B8860B", "6B7280", "1F272E", "F3F5F8", "FFFFFF"
TINTS = {"Red": "F8DADA", "Orange": "FCE5D2", "Yellow": "FBF1D3", "Blue": "DCE8F7", "Green": "D7F0DC"}
# the grid as it is drawn: high potential at the top, performance rising to the right
ROWS = ((3, 6, 9), (2, 5, 8), (1, 4, 7))


def _allowed(review):
    from hrms_addon.hrms_addon import talent_board

    return bool(review) and talent_board.can_see_boxes() and frappe.has_permission(REVIEW, "read", doc=review)


def talent_council_pack(review):
    """The council pack's figures, for whoever may read the review and the
    boxes; nothing for anybody else."""
    if not _allowed(review):
        return {}
    company = frappe.db.get_value(REVIEW, review, "company")
    data = talent_command.figures(review, company)
    data["decisions"] = decisions(review, company)
    data["remarks"] = frappe.db.get_value(REVIEW, review, "council_remarks")
    data["rows"] = [list(row) for row in ROWS]
    return data


def decisions(review, company=None):
    values = {"review": review, "company": company}
    where = " and p.company = %(company)s" if company else ""
    placed = frappe.db.sql("""
        select coalesce(p.suggested_decision, '') as decision, count(*) as n from `tabTalent Placement` p
        where p.talent_review = %(review)s and p.docstatus = 1 {where} group by p.suggested_decision
        order by n desc""".format(where=where), values, as_dict=True)
    endorsed = frappe.db.sql("""
        select coalesce(c.council_decision, '') as decision, count(*) as n from `tabSuccession Candidate` c
        join `tabSuccession Position` p on p.name = c.parent
        where c.parenttype = 'Succession Position' and p.docstatus < 2 {where}
        group by c.council_decision order by n desc""".format(where=where), values, as_dict=True)
    pools = frappe.db.sql("""
        select p.pool_name, p.pool_type, p.status, p.active_members, p.confirmed_members from `tabTalent Pool` p
        where p.talent_review = %(review)s {where} order by p.pool_name""".format(where=where), values, as_dict=True)
    gaps = frappe.db.sql("""
        select count(*) from `tabSuccession Position` p where p.docstatus = 1 and p.gap_confirmed = 1 {where}""".format(
        where=where), values)[0][0]
    return {"placements": placed, "successors": endorsed, "pools": pools, "gaps_recruited": cint(gaps)}


# ── The deck ──────────────────────────────────────────────────────────
@frappe.whitelist()
def download_deck(review):
    """The council pack of a review as a PowerPoint deck."""
    doc = frappe.get_doc(REVIEW, review)
    doc.check_permission("read")
    if not _allowed(review):
        frappe.throw(_("The council pack is for HR, the Talent Council and the executives."), frappe.PermissionError)
    try:
        from pptx import Presentation  # noqa: F401
    except ImportError:
        frappe.throw(_("The deck needs python-pptx on the server. Run: bench pip install python-pptx"),
                     title=_("Talent Council Pack"))
    content = _Deck(doc, talent_council_pack(review)).build()
    frappe.local.response.filename = "%s Council Pack.pptx" % (doc.title or doc.name)
    frappe.local.response.filecontent = content
    frappe.local.response.type = "binary"


def _n(value):
    return "–" if value is None else "{:,.0f}".format(flt(value))


def _pct(value):
    return "–" if value is None else "{:.0f}%".format(flt(value))


class _Deck:
    def __init__(self, doc, data):
        from pptx import Presentation
        from pptx.util import Inches

        self.doc, self.data = doc, data
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.page = 0

    def _rgb(self, hex_colour):
        from pptx.dml.color import RGBColor

        return RGBColor.from_string(hex_colour)

    def slide(self, title, subtitle=None):
        from pptx.util import Inches

        self.page += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bar = slide.shapes.add_shape(1, 0, 0, self.prs.slide_width, Inches(0.12))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self._rgb(NAVY)
        bar.line.fill.background()
        self.text(slide, 0.5, 0.3, 9, 0.3, "TALENT COUNCIL", size=10, bold=True, colour=GOLD)
        self.text(slide, 0.5, 0.55, 12.3, 0.6, title, size=24, bold=True, colour=NAVY)
        if subtitle:
            self.text(slide, 0.5, 1.12, 12.3, 0.35, subtitle, size=12, colour=GREY)
        self.text(slide, 9.0, 7.08, 3.8, 0.3, "%s  ·  %d" % (self.doc.title or self.doc.name, self.page), size=8,
                  colour=GREY, align="right")
        return slide

    def text(self, slide, x, y, w, h, content, size=12, bold=False, colour=INK, align=None, fill=None):
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Inches, Pt

        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        if fill:
            box.fill.solid()
            box.fill.fore_color.rgb = self._rgb(fill)
        frame = box.text_frame
        frame.word_wrap = True
        for index, item in enumerate(content if isinstance(content, (list, tuple)) else [content]):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            run = paragraph.add_run()
            run.text = item or ""
            run.font.size, run.font.bold = Pt(size), bold
            run.font.color.rgb = self._rgb(colour)
            if align == "right":
                paragraph.alignment = PP_ALIGN.RIGHT
            elif align == "center":
                paragraph.alignment = PP_ALIGN.CENTER
        return box

    def tiles(self, slide, items, y=1.6, h=1.15):
        width = (12.3 - 0.2 * (len(items) - 1)) / max(len(items), 1)
        for index, (value, label, note) in enumerate(items):
            x = 0.5 + index * (width + 0.2)
            self.text(slide, x, y, width, h, "", fill=PALE)
            self.text(slide, x + 0.12, y + 0.08, width - 0.24, 0.5, str(value), size=22, bold=True, colour=NAVY)
            self.text(slide, x + 0.12, y + 0.58, width - 0.24, 0.28, label.upper(), size=8, bold=True, colour=GOLD)
            if note:
                self.text(slide, x + 0.12, y + 0.82, width - 0.24, 0.3, note, size=8, colour=GREY)

    def table(self, slide, x, y, w, rows, widths=None, size=10, row_height=0.3, fills=None):
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
            for c, value in enumerate(row):
                cell = table.cell(r, c)
                cell.text = value
                cell.fill.solid()
                fill = (fills or {}).get((r, c))
                cell.fill.fore_color.rgb = self._rgb(NAVY if r == 0 and not fills else fill or
                                                     (PALE if r % 2 == 0 else WHITE))
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(size)
                        run.font.bold = r == 0
                        run.font.color.rgb = self._rgb(WHITE if r == 0 and not fills else INK)
        return table

    def chart(self, slide, x, y, w, h, categories, series):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        from pptx.util import Inches, Pt

        data = CategoryChartData()
        data.categories = list(categories)
        for name, values in series:
            data.add_series(name, [flt(value) for value in values])
        frame = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), data)
        chart = frame.chart
        chart.has_legend = len(series) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(9)
        chart.font.size = Pt(9)
        palette = ("14395E", "E8A317", "2E86AB", "7A9E3B", "A62B25", "8E6C8A")
        for index, plot in enumerate(chart.plots[0].series):
            plot.format.fill.solid()
            plot.format.fill.fore_color.rgb = self._rgb(palette[index % len(palette)])
        return chart

    def build(self):
        for step in (self.cover, self.summary, self.grid, self.plants, self.top_talent, self.flight_risk,
                     self.succession, self.movement, self.pipeline, self.decisions):
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
        self.text(slide, 0.8, 2.0, 11, 0.8, "TALENT COUNCIL", size=40, bold=True, colour=WHITE)
        self.text(slide, 0.8, 2.75, 11, 0.8, "REVIEW PACK", size=40, bold=True, colour="E8A317")
        self.text(slide, 0.8, 3.9, 11, 0.5, self.doc.title or self.doc.name, size=20, colour=WHITE)
        self.text(slide, 0.8, 4.5, 11, 0.4, format_date(today()), size=13, colour="DCE4EF")

    def summary(self):
        facts = self.data.get("facts") or {}
        slide = self.slide("Where Talent Stands", "The review's people on the grid, the risk and the cover")
        self.tiles(slide, [(tile["value"], tile["label"], tile.get("note")) for tile in (self.data.get("kpis") or [])[:6]])
        from hrms_addon.hrms_addon import talent_command_rules

        board = talent_command_rules.board_figures(facts)
        self.text(slide, 0.5, 3.0, 12.3, 0.4, "RATING:  %s" % board["risk_rating"].upper(), size=16, bold=True,
                  colour=NAVY)
        self.text(slide, 0.5, 3.5, 12.3, 2.5, ["•  " + note for note in board["notes"]] or ["–"], size=13)

    def grid(self):
        names = self.data.get("names") or {}
        colours = self.data.get("colours") or {}
        company = (self.data.get("by_plant") or [{}])[0]
        boxes = {row["box"]: row for row in company.get("boxes") or []}
        slide = self.slide("The Nine Boxes", "The whole company, against the distribution guide")
        rows = [["Potential", "Low performance", "Meeting", "Exceeding"]]
        fills = {}
        for r, line in enumerate(ROWS, 1):
            rows.append([("High", "Moderate", "Low")[r - 1]] + [
                "%d %s\n%s people · %s (guide %s)" % (box, names.get(str(box), names.get(box, "")),
                                                      _n(boxes.get(box, {}).get("n")),
                                                      _pct(boxes.get(box, {}).get("share")),
                                                      _pct(boxes.get(box, {}).get("guide")))
                for box in line])
            for c, box in enumerate(line, 1):
                fills[(r, c)] = TINTS.get(colours.get(str(box), colours.get(box)), PALE)
        fills.update({(0, c): PALE for c in range(4)})
        self.table(slide, 0.5, 1.6, 12.3, rows, widths=(1.4, 3.6, 3.6, 3.6), size=11, row_height=1.15, fills=fills)

    def plants(self):
        groups = self.data.get("by_plant") or []
        slide = self.slide("Plants Side by Side", "Each plant's share of every box, and the guide")
        header = ["Plant", "People"] + [str(box) for box in range(1, 10)] + ["Top talent"]
        rows = [header] + [[group["group"], _n(group["total"])] + [_pct(row["share"]) for row in group["boxes"]]
                           + [_pct(group["top_share"])] for group in groups]
        guide = groups[0]["boxes"] if groups else []
        rows.append(["Guide", ""] + [_pct(row.get("guide")) for row in guide] + [""])
        self.table(slide, 0.5, 1.6, 12.3, rows, widths=[2.2, 1] + [0.9] * 9 + [1.2], size=9)
        if len(groups) > 1:
            self.chart(slide, 0.5, 4.2, 12.3, 2.7, [str(box) for box in range(1, 10)],
                       [(group["group"], [row["share"] for row in group["boxes"]]) for group in groups[1:5]])

    def top_talent(self):
        rows = self.data.get("top") or []
        slide = self.slide("Top Talent", "Boxes 6, 8 and 9, the highest first")
        table = [["Name", "Job Title", "Plant", "Box", "Performance", "Potential", "Flight Risk"]] + [
            [row.get("employee_name"), row.get("designation"), row.get("branch"), "%s %s" % (row.get("box"),
                                                                                            row.get("box_name") or ""),
             _n(row.get("performance_score")), _n(row.get("potential_score")), row.get("flight_risk") or ""]
            for row in rows[:15]]
        self.table(slide, 0.5, 1.6, 12.3, table, widths=(2.6, 2.4, 1.4, 2.2, 1.2, 1.2, 1.3), size=9)

    def flight_risk(self):
        rows = self.data.get("risk") or []
        facts = self.data.get("facts") or {}
        slide = self.slide("Flight Risk", "%s top talent at risk, %s without a retention action" % (
            _n(facts.get("at_risk")), _n(facts.get("unprotected"))))
        table = [["Name", "Job Title", "Plant", "Box", "Flight Risk", "Impact of Loss", "Open Actions"]] + [
            [row.get("employee_name"), row.get("designation"), row.get("branch"), row.get("box"),
             row.get("flight_risk"), row.get("impact_of_loss") or "", _n(row.get("actions"))] for row in rows[:15]]
        self.table(slide, 0.5, 1.6, 12.3, table, widths=(2.6, 2.6, 1.4, 0.8, 1.3, 1.5, 1.3), size=9)

    def succession(self):
        bench = self.data.get("bench") or {}
        heat = self.data.get("heat") or {}
        slide = self.slide("Succession Cover", "Bench strength, and the roles by impact and probability of loss")
        self.tiles(slide, [(bench.get("roles", 0), "Critical roles", ""),
                           (_pct(bench.get("ready_now_share")), "Ready-now cover", "%s roles" % bench.get("ready_now", 0)),
                           (_pct(bench.get("two_share")), "Two or more successors", ""),
                           (bench.get("none", 0), "Nobody named", ""),
                           (len(self.data.get("overlap") or []), "Named for several roles", "")], h=1.0)
        rows = [["Impact \\ Probability", "Low", "Medium", "High"]]
        fills = {}
        for r, line in enumerate(heat.get("rows") or [], 1):
            rows.append([line["impact"]] + [str(cell["count"]) for cell in line["cells"]])
            for c, cell in enumerate(line["cells"], 1):
                danger = (3 - r) + (c - 1)
                fills[(r, c)] = ("D7F0DC", "FBF1D3", "FCE5D2", "F8DADA", "F8DADA")[min(danger, 4)]
        fills.update({(0, c): PALE for c in range(4)})
        self.table(slide, 0.5, 2.9, 5.4, rows, widths=(1.8, 1.2, 1.2, 1.2), size=11, row_height=0.6, fills=fills)
        roles = [["Role", "Plant", "Holder", "Risk", "Cover"]] + [
            [row.get("designation"), row.get("branch"), row.get("incumbent_name"), _n(row.get("role_risk")),
             row.get("coverage")] for row in (self.data.get("roles") or [])[:10]]
        self.table(slide, 6.2, 2.9, 6.6, roles, widths=(2.2, 1.2, 1.8, 0.7, 0.9), size=9)

    def movement(self):
        matrix = self.data.get("matrix") or []
        moved = self.data.get("movement") or {}
        slide = self.slide("Movement Since the Review Before", "From each box (rows) to each box (columns)")
        rows = [["From \\ To"] + [str(box) for box in range(1, 10)] + ["Left"]] + [
            [row["name"]] + [str(value or "") for value in row["cells"]] + [str(row["gone"] or "")] for row in matrix]
        self.table(slide, 0.5, 1.6, 8.6, rows, widths=[1.6] + [0.7] * 10, size=9, row_height=0.42)
        self.text(slide, 9.4, 1.6, 3.4, 3.5, ["Stayed: %s" % _n(moved.get("same")), "Up: %s" % _n(moved.get("up")),
                                              "Down: %s" % _n(moved.get("down")),
                                              "Across: %s" % _n(moved.get("across")),
                                              "New: %s" % _n(moved.get("new")), "Left: %s" % _n(moved.get("gone"))],
                  size=13)

    def pipeline(self):
        funnel = self.data.get("funnel") or []
        slide = self.slide("Graduate Pipeline", "Each cohort by stage")
        stages = ("Recruited", "In Induction", "In Rotation", "Under Assessment", "Confirmed", "Exited")
        rows = [["Cohort", "Trainees"] + list(stages)] + [
            [row["cohort"], _n(row["total"])] + [_n(row["stages"].get(stage)) for stage in stages] for row in funnel[:12]]
        self.table(slide, 0.5, 1.6, 12.3, rows, widths=[2.4, 1] + [1.2] * 6, size=9)
        investment = self.data.get("investment") or {}
        self.text(slide, 0.5, 6.3, 12.3, 0.4, "Development plans: %s approved, %s spent, %s plans" % (
            _n(investment.get("approved")), _n(investment.get("actual")), _n(investment.get("plans"))), size=12,
                  bold=True, colour=NAVY)

    def decisions(self):
        found = self.data.get("decisions") or {}
        slide = self.slide("Decisions", "What the review came to")
        placed = [["Placements finalised", "People"]] + [[row["decision"] or "None", _n(row["n"])]
                                                        for row in found.get("placements") or []]
        self.table(slide, 0.5, 1.6, 4.0, placed, widths=(2.8, 1.2), size=10)
        endorsed = [["Successors", "People"]] + [[row["decision"] or "Not decided", _n(row["n"])]
                                                for row in found.get("successors") or []]
        self.table(slide, 4.8, 1.6, 3.6, endorsed, widths=(2.4, 1.2), size=10)
        pools = [["Pool", "Status", "Members"]] + [[row["pool_name"], row["status"], _n(row["active_members"])]
                                                   for row in found.get("pools") or []]
        self.table(slide, 8.7, 1.6, 4.1, pools, widths=(2.0, 1.1, 1.0), size=10)
        self.text(slide, 0.5, 5.2, 12.3, 1.6, self.data.get("remarks") or "", size=12)
