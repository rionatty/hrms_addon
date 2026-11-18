# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A plant's day on one sheet (Manufacturing Excellence, 18 Nov 2026).

The workbook had the Manufacturing Excellence Officer type a row for every
section and shift, about twenty a plant a day: 1,560 forms a month for three
plants as separate Shift Reports. A Plant Day Sheet is one document per
plant and date, about 78 a month, held unique by its name (Plant date).

  sheet_validate     its rows made: every active section of the plant that
                     takes shift reports, Day then Night, with the target and
                     machines of the standard in force and the supervisor on
                     the roster; checked, and its totals worked out
  sheet_on_update    each row written onto its section's Shift Report (made
                     the first time), which the shift's crew, downtime events
                     and output lines then go on; what the report works out
                     comes back onto the row (mirror)
  fetch_clock        every shift's crew from the clock, in the background
  paste_rows         rows copied from a spreadsheet, matched by section and
                     shift
  submit             the one approval: refused while a row is neither entered
                     nor marked Not Worked; the Shift Reports are submitted in
                     the background, which writes the summaries
  make_day_sheets    every morning, yesterday's sheet of each plant, so a
                     missing row shows on the dashboard
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, today

from hrms_addon.hrms_addon import excellence_rules as rules

SHEET, ROW, SHIFT_REPORT, SECTION = "Plant Day Sheet", "Plant Day Sheet Row", "Shift Report", "Work Section"
JOB = "hrms_addon_me_sheet::%s::%s"
TYPED = rules.SHEET_TYPED + ("supervisor",)
CLOCK = ("staff_planned", "staff_on_shift", "unauthorised_absent", "not_marked", "late_arrivals", "early_departures",
         "ot_hours", "safety_incidents", "near_misses")
FROM_REPORT = CLOCK + ("score", "status", "labour_cost", "actual_output", "waste_qty", "waste_value", "wearing_ppe",
                       "supervisor")
DRAFT, APPROVED, CANCELLED = "Draft", "Approved", "Cancelled"


def sheet_autoname(doc):
    doc.name = "%s %s" % (doc.branch, getdate(doc.sheet_date))


def _sections(branch):
    return frappe.get_all(SECTION, filters={"branch": branch, "is_active": 1, "shift_reports": 1},
                          fields=["name", "section_name", "company"], order_by="section_name asc",
                          limit_page_length=0)


def sheet_validate(doc):
    from hrms_addon.hrms_addon import excellence

    s = excellence.settings()
    sections = _sections(doc.branch)
    if not sections and not doc.get("rows"):
        frappe.throw(_("No active section of {0} takes shift reports.").format(doc.branch), title=_(SHEET))
    if not doc.get("company") and sections:
        doc.company = sections[0].company
    doc.week = rules.week_label(doc.sheet_date)
    if doc.docstatus == 0:
        for section, shift in rules.sheet_rows_to_add([row.name for row in sections],
                                                      [row.as_dict() for row in doc.get("rows") or []]):
            doc.append("rows", {"work_section": section, "shift": shift})
    plant = {row.name for row in sections}
    for row in doc.get("rows") or []:
        if row.work_section not in plant and frappe.db.get_value(SECTION, row.work_section, "branch") != doc.branch:
            frappe.throw(_("{0} is not a section of {1}.").format(row.work_section, doc.branch), title=_(SHEET))
    _fill_rows(doc, s)
    errors = rules.sheet_errors(doc.sheet_date, today(), [row.as_dict() for row in doc.get("rows") or []])
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SHEET))
    _totals(doc, s)
    if doc.docstatus == 0:
        doc.status = DRAFT


def _fill_rows(doc, s):
    """Each row's target and machines from the standard in force, its
    supervisor from the roster; a row without its shift report yet is scored
    from what was typed (the report's own score replaces it once saved)."""
    from hrms_addon.hrms_addon import excellence

    for row in doc.get("rows") or []:
        section = frappe.get_cached_doc(SECTION, row.work_section)
        standard = excellence.section_standard(section, doc.sheet_date)
        row.target = standard.get("target_per_shift")
        row.machines = standard.get("machines")
        if row.get("machines_running") in (None, ""):
            row.machines_running = row.machines
        if not row.get("supervisor"):
            row.supervisor = rules.lead_on(excellence.roster(section), doc.sheet_date, row.shift)
        if cint(row.get("not_worked")) or not rules.row_entered(row.as_dict()):
            if cint(row.get("not_worked")):
                row.score, row.status, row.labour_cost = 0, "", 0
            continue
        if not row.get("shift_report"):
            entry = dict(row.as_dict(), staff_planned=row.get("staff_planned") or standard.get("crew_per_shift"))
            figures = rules.shift_figures(entry, standard, s)
            row.score, row.status, row.labour_cost = figures["score"], figures["status"], figures["labour_cost"]


def _row_summary(row, s, standards):
    """A row as the day summary its shift would make, for the sheet's own score."""
    entry = row.as_dict() if hasattr(row, "as_dict") else dict(row)
    figures = rules.shift_figures(entry, standards.get(entry.get("work_section")) or {}, s)
    return rules.day_summary(entry, figures, s)


def _totals(doc, s):
    from hrms_addon.hrms_addon import excellence

    rows = [row.as_dict() for row in doc.get("rows") or []]
    state = rules.sheet_state(rows)
    doc.entered_rows, doc.not_worked_rows, doc.missing_rows = state["entered"], state["not_worked"], state["missing"]
    doc.staff_planned = sum(cint(row.get("staff_planned")) for row in rows)
    doc.staff_on_shift = sum(cint(row.get("staff_on_shift")) for row in rows)
    doc.money_lost = sum(flt(row.get("waste_value")) + flt(row.get("complaint_value")) for row in rows
                         if not cint(row.get("not_worked")))
    doc.labour_cost = sum(flt(row.get("labour_cost")) for row in rows)
    standards = {}
    by_section = {}
    for row in rows:
        if cint(row.get("not_worked")) or not rules.row_entered(row):
            continue
        if row["work_section"] not in standards:
            standards[row["work_section"]] = excellence.section_standard(
                frappe.get_cached_doc(SECTION, row["work_section"]), doc.sheet_date)
        by_section.setdefault(row["work_section"], []).append(_row_summary(row, s, standards))
    scores = [rules.period_scores(rules.totals(summaries, s), s)["score"] for summaries in by_section.values()]
    doc.plant_score = rules.plant_score(scores) or 0


def sheet_on_update(doc):
    """Each row onto its Shift Report: made the first time, written again when
    what was typed changed; what the report works out comes back."""
    if doc.docstatus != 0:
        return
    before = doc.get_doc_before_save()
    was = {(row.work_section, row.shift): row for row in (before.get("rows") if before else None) or []}
    for row in doc.get("rows") or []:
        if cint(row.get("not_worked")):
            continue
        old = was.get((row.work_section, row.shift))
        changed = old is None or any(_differs(row.get(field), old.get(field)) for field in TYPED)
        if row.get("shift_report") and not changed:
            continue
        report = write_report(doc, row)
        if report is not None:
            _take_back(row, report)


def _differs(new, old):
    if isinstance(new, (int, float)) or isinstance(old, (int, float)):
        return flt(new) != flt(old)
    return (new or "") != (old or "")


def write_report(doc, row, save=True):
    """The row's Shift Report: its own, else a draft one for the same section,
    shift and day, else a new one; the typed figures written onto it."""
    report = None
    if row.get("shift_report") and frappe.db.exists(SHIFT_REPORT, row.shift_report):
        report = frappe.get_doc(SHIFT_REPORT, row.shift_report)
    else:
        key = "%s|%s|%s" % (row.work_section, getdate(doc.sheet_date), row.shift)
        found = frappe.db.get_value(SHIFT_REPORT, {"shift_key": key}, "name")
        report = frappe.get_doc(SHIFT_REPORT, found) if found else frappe.get_doc({
            "doctype": SHIFT_REPORT, "report_date": doc.sheet_date, "shift": row.shift,
            "work_section": row.work_section})
    if report.docstatus != 0:
        return report
    report.plant_day_sheet = doc.name
    for field in TYPED:
        value = row.get(field)
        if field == "comment":
            report.comment = value
        elif value not in (None, "") or field in rules.PASTE_NUMBERS:
            report.set(field, value)
    if save:
        report.save()
        frappe.db.set_value(ROW, row.name, "shift_report", report.name, update_modified=False)
        row.shift_report = report.name
    return report


def _take_back(row, report):
    values = {field: report.get(field) for field in FROM_REPORT}
    values["shift_report"] = report.name
    for field, value in values.items():
        row.set(field, value)
    if row.get("name"):
        frappe.db.set_value(ROW, row.name, values, update_modified=False)


def mirror(report):
    """A shift report's figures onto its day sheet's row."""
    sheet = report.get("plant_day_sheet")
    if not sheet or frappe.db.get_value(SHEET, sheet, "docstatus") in (None, 2):
        return
    row = frappe.db.get_value(ROW, {"parent": sheet, "parenttype": SHEET, "work_section": report.work_section,
                                    "shift": report.shift}, "name")
    if row:
        values = {field: report.get(field) for field in FROM_REPORT}
        values["shift_report"] = report.name
        frappe.db.set_value(ROW, row, values, update_modified=False)


def refresh_totals(name):
    """The sheet's totals from its rows as they are now."""
    from hrms_addon.hrms_addon import excellence

    doc = frappe.get_doc(SHEET, name)
    _totals(doc, excellence.settings())
    doc.db_set({field: doc.get(field) for field in ("entered_rows", "not_worked_rows", "missing_rows",
                                                     "staff_planned", "staff_on_shift", "money_lost", "labour_cost",
                                                     "plant_score")}, update_modified=False)


# ── The clock and a spreadsheet ───────────────────────────────────────
@frappe.whitelist()
def fetch_clock(sheet):
    """Every shift's crew from the clock, in the background."""
    doc = frappe.get_doc(SHEET, sheet)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft day sheet takes its crews from the clock."), title=_(SHEET))
    doc.db_set({"job_status": _("Queued"), "job_problems": None}, notify=True)
    frappe.enqueue("hrms_addon.hrms_addon.excellence_sheet.run_fetch", queue="long", timeout=3600,
                   job_id=JOB % ("fetch", doc.name), deduplicate=True, enqueue_after_commit=True, sheet=doc.name)
    return {"queued": True}


def run_fetch(sheet):
    """The background job: each shift's report made if need be, its crew
    filled from the clock and saved, a shift at a time."""
    from hrms_addon.hrms_addon import excellence_clock

    doc = frappe.get_doc(SHEET, sheet)
    rows = [row for row in doc.get("rows") or [] if not cint(row.get("not_worked"))]
    doc.db_set("job_status", _("Fetching from the clock"), commit=True, notify=True)
    problems = []
    for number, row in enumerate(rows, 1):
        try:
            report = write_report(doc, row, save=False)
            if report.docstatus == 0:
                excellence_clock.fill(report)
                report.save(ignore_permissions=True)
                frappe.db.set_value(ROW, row.name, "shift_report", report.name, update_modified=False)
                mirror(report)
            frappe.db.commit()
        except Exception as error:
            frappe.db.rollback()
            problems.append("%s %s: %s" % (rules.section_label(row.work_section), row.shift, _reason(error)))
        frappe.publish_progress(number * 100.0 / len(rows), title=_("Fetching from the clock"), doctype=SHEET,
                                docname=sheet, description=_("{0} of {1} shifts").format(number, len(rows)))
    refresh_totals(sheet)
    frappe.get_doc(SHEET, sheet).db_set({"clock_fetched_on": now_datetime(),
                                         "job_status": _("Fetched from the clock"),
                                         "job_problems": "\n".join(problems) or None}, commit=True, notify=True)


def _reason(error):
    return frappe.utils.strip_html(str(error))[:300] if hasattr(frappe.utils, "strip_html") else str(error)[:300]


@frappe.whitelist()
def paste_rows(sheet, text):
    """Rows copied from a spreadsheet: {"updates": [{"key", "values"}],
    "errors"}, for the form to put into the grid."""
    doc = frappe.get_doc(SHEET, sheet)
    doc.check_permission("write")
    rows = [{"key": row.name, "work_section": row.work_section, "shift": row.shift} for row in doc.get("rows") or []]
    found = rules.parse_paste(text, rows)
    reasons = {value for update in found["updates"] for key, value in update["values"].items()
               if key == "downtime_reason"}
    known = set(frappe.get_all("Downtime Reason", filters={"name": ["in", list(reasons)]}, pluck="name")) \
        if reasons else set()
    for update in found["updates"]:
        reason = update["values"].get("downtime_reason")
        if reason and reason not in known:
            found["errors"].append(_("{0} is not a downtime reason.").format(reason))
            update["values"].pop("downtime_reason")
    return found


# ── The approval ──────────────────────────────────────────────────────
def sheet_before_submit(doc):
    """Every row entered or marked Not Worked, each with its Shift Report."""
    state = rules.sheet_state([row.as_dict() for row in doc.get("rows") or []])
    if state["missing"]:
        missing = ", ".join("%s %s" % (rules.section_label(section), shift)
                            for section, shift in state["missing_rows"])
        frappe.throw(_("Shifts not entered: {0}. Enter them or mark them Not Worked.").format(missing),
                     title=_(SHEET))
    for row in doc.get("rows") or []:
        if not cint(row.get("not_worked")) and not row.get("shift_report"):
            report = write_report(doc, row)
            if report is not None:
                _take_back(row, report)
    doc.status = APPROVED


def sheet_on_submit(doc):
    doc.db_set("job_status", _("Queued"), update_modified=False)
    frappe.enqueue("hrms_addon.hrms_addon.excellence_sheet.run_submit", queue="long", timeout=3600,
                   job_id=JOB % ("submit", doc.name), deduplicate=True, enqueue_after_commit=True, sheet=doc.name)


def run_submit(sheet):
    """The approval in the background: each shift's report submitted (its
    summaries written), a draft report of a shift not worked deleted."""
    doc = frappe.get_doc(SHEET, sheet)
    rows = doc.get("rows") or []
    problems, submitted = [], 0
    doc.db_set("job_status", _("Submitting the shift reports"), commit=True, notify=True)
    for number, row in enumerate(rows, 1):
        try:
            if cint(row.get("not_worked")):
                if row.get("shift_report") and frappe.db.get_value(SHIFT_REPORT, row.shift_report, "docstatus") == 0:
                    frappe.delete_doc(SHIFT_REPORT, row.shift_report, ignore_permissions=True, force=True)
                    frappe.db.set_value(ROW, row.name, "shift_report", None, update_modified=False)
            elif row.get("shift_report"):
                report = frappe.get_doc(SHIFT_REPORT, row.shift_report)
                if report.docstatus == 0:
                    report.flags.ignore_permissions = True
                    report.submit()
                    submitted += 1
            frappe.db.commit()
        except Exception as error:
            frappe.db.rollback()
            problems.append("%s %s: %s" % (rules.section_label(row.work_section), row.shift, _reason(error)))
        frappe.publish_progress(number * 100.0 / len(rows), title=_("Submitting the shift reports"), doctype=SHEET,
                                docname=sheet, description=_("{0} of {1} shifts").format(number, len(rows)))
    frappe.get_doc(SHEET, sheet).db_set({"job_status": _("{0} shift reports submitted").format(submitted),
                                         "job_problems": "\n".join(problems) or None}, commit=True, notify=True)


def sheet_on_cancel(doc):
    doc.db_set("status", CANCELLED, update_modified=False)
    frappe.enqueue("hrms_addon.hrms_addon.excellence_sheet.run_cancel", queue="long", timeout=3600,
                   job_id=JOB % ("cancel", doc.name), deduplicate=True, enqueue_after_commit=True, sheet=doc.name)


def run_cancel(sheet):
    """The approval taken back: the sheet's submitted shift reports cancelled
    (their summaries go with them)."""
    for name in frappe.get_all(SHIFT_REPORT, filters={"plant_day_sheet": sheet, "docstatus": 1}, pluck="name"):
        try:
            report = frappe.get_doc(SHIFT_REPORT, name)
            report.flags.ignore_permissions = True
            report.cancel()
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Plant Day Sheet %s: cancel %s" % (sheet, name))


def sheet_on_trash(doc):
    """A draft sheet deleted takes its draft shift reports with it."""
    for name in frappe.get_all(SHIFT_REPORT, filters={"plant_day_sheet": doc.name, "docstatus": 0}, pluck="name"):
        frappe.delete_doc(SHIFT_REPORT, name, ignore_permissions=True, force=True)


# ── Every morning ─────────────────────────────────────────────────────
def make_day_sheets(day):
    """Yesterday's sheet of each plant with sections that take shift reports,
    where there is none yet."""
    day = getdate(day)
    plants = sorted(set(frappe.get_all(SECTION, filters={"is_active": 1, "shift_reports": 1}, pluck="branch",
                                       limit_page_length=0)) - {None, ""})
    for branch in plants:
        if frappe.db.exists(SHEET, {"branch": branch, "sheet_date": str(day), "docstatus": ["<", 2]}):
            continue
        try:
            frappe.get_doc({"doctype": SHEET, "branch": branch, "sheet_date": day}).insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Plant Day Sheet %s %s" % (branch, day))


def add_keys():
    """on_doctype_update: one row a section and shift on a sheet."""
    if not frappe.db.table_exists(ROW):
        return
    try:
        frappe.db.add_unique(ROW, ["parent", "work_section", "shift"], constraint_name="unique_sheet_section_shift")
    except Exception:
        frappe.log_error(title="Plant Day Sheet Row: unique key")
