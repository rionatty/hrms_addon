"""The HR board pack on its facts (18 Nov 2026): what the old board pack kept is carried over.

  - a month imported or locked under the old pack: its HR Snapshot Plant rows (33 columns a plant) become imported
    fact rows, every total kept (board_facts_rules.legacy_rows), and the month is Imported from then on;
  - a month built from the site and still open: queued to be built again, now as facts;
  - each line of a report's Strategic People Agenda, and each of its priorities, becomes a Board Action;
  - a KPI marked Action is Action Needed, as the ratings are;
  - the monthly attrition target of Board Report Settings becomes a Board KPI Target.

The old tables are read with SQL: their doctypes are gone from the app, their tables are not. Each step stands alone,
so one that fails is in the Error Log and the migrate goes on."""

import frappe


def execute():
    for step in (_snapshots, _agenda, _priorities, _statuses, _attrition_target):
        try:
            step()
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="HRMS Addon: carrying the board pack over (%s)" % step.__name__)


def _snapshots():
    from hrms_addon.hrms_addon import board_facts

    if not frappe.db.table_exists("HR Snapshot Plant"):
        return
    for snapshot in frappe.get_all("HR Monthly Snapshot", fields=["name", "company", "month_start", "source", "locked"]):
        if snapshot.source == "Imported" or snapshot.locked:
            rows = frappe.db.sql("""SELECT * FROM `tabHR Snapshot Plant`
                WHERE `parent` = %s AND `parenttype` = 'HR Monthly Snapshot'""", snapshot.name, as_dict=True)
            board_facts.convert_legacy(snapshot.name, rows)
        else:
            board_facts.queue(snapshot.company, snapshot.month_start)


def _next(year, quarter):
    index = ("Q1", "Q2", "Q3", "Q4").index(quarter)
    return (int(year) + 1, "Q1") if index == 3 else (int(year), "Q%d" % (index + 2))


def _action(report, imperative, **values):
    imperative = (imperative or "").strip()[:140]
    if not imperative or frappe.db.exists("Board Action", {"board_report": report.name, "imperative": imperative}):
        return
    due_year, due_quarter = _next(report.year, report.quarter)
    doc = frappe.get_doc(dict({"doctype": "Board Action", "company": report.company, "imperative": imperative,
                               "status": "Not Started", "raised_year": report.year,
                               "raised_quarter": report.quarter, "due_year": due_year,
                               "due_quarter": due_quarter}, **values))
    doc.flags.ignore_permissions = True
    doc.insert()
    frappe.db.set_value("Board Action", doc.name, "board_report", report.name, update_modified=False)


def _agenda():
    if not frappe.db.table_exists("Board Agenda Line"):
        return
    for row in frappe.db.sql("""SELECT `parent`, `imperative`, `lever`, `progress`, `milestone`
            FROM `tabBoard Agenda Line` WHERE `parenttype` = 'HR Board Report' ORDER BY `parent`, `idx`""",
                             as_dict=True):
        report = frappe.db.get_value("HR Board Report", row.parent, ["name", "company", "year", "quarter"],
                                     as_dict=True)
        if report and report.year and report.quarter:
            _action(report, row.imperative, lever=row.lever, progress_note=row.progress, milestone=row.milestone)


def _priorities():
    if not frappe.db.has_column("HR Board Report", "priorities"):
        return
    for row in frappe.db.sql("""SELECT `name`, `company`, `year`, `quarter`, `priorities` FROM `tabHR Board Report`
            WHERE `docstatus` < 2 AND COALESCE(`priorities`, '') != ''""", as_dict=True):
        for line in (row.priorities or "").splitlines():
            if row.year and row.quarter:
                _action(row, line.strip(" -•\t"))


def _statuses():
    frappe.db.sql("""UPDATE `tabBoard Metric Line` SET `status` = 'Action Needed' WHERE `status` = 'Action'""")


def _attrition_target():
    found = frappe.db.sql("""SELECT `value` FROM `tabSingles`
        WHERE `doctype` = 'Board Report Settings' AND `field` = 'attrition_target'""")
    if not found or not found[0][0] or frappe.db.exists("Board KPI Target", {"metric": "Monthly Attrition"}):
        return
    for company in frappe.get_all("Company", pluck="name"):
        doc = frappe.get_doc({"doctype": "Board KPI Target", "company": company, "metric": "Monthly Attrition",
                              "from_date": "2025-01-01", "target": float(found[0][0]),
                              "direction": "Lower is Better", "amber_band": 0, "red_band": 1})
        doc.flags.ignore_permissions = True
        doc.insert()
