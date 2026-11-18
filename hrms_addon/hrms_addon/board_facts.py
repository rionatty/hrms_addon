# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack's facts on the site. board_facts_rules.py has the rules
(scripts/verify_board_facts.py); this reads the site, writes the rows and
asks them back.

  build_month      the job: a month's HR Employee Month, HR Movement, HR
                   Pay Fact and HR Safety Fact rows built from the site on
                   the long queue, written in chunks of 500 with a commit
                   after each, the progress on the month's HR Monthly
                   Snapshot. About a dozen queries a month, every aggregate
                   a GROUP BY, never a query per employee.
  queue            a month's build put on the long queue, once (job id)
  nightly          the month running and the open months before it built
                   again; a locked or imported month never is
  lock / unlock    an approved HR Board Report locks its months
  month_figures    the figures by plant and month the pack, the dashboard
                   and the reports read: a GROUP BY over the facts
  cut_figures      head count and movements by any cut (plant, department,
                   section, gender, age, tenure, population)
  data_quality     what keeps the figures from adding up: employees with no
                   plant, leavers with no date, hires with no requisition,
                   slips with no plant

Imported rows (the months before the system: one row per group of people,
`heads` many) are typed or brought in with Data Import; their month's header
says Imported and is never built from the site.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now, today

from hrms_addon.hrms_addon import board_facts_rules as rules

SNAPSHOT = "HR Monthly Snapshot"
EMPLOYEE_MONTH, MOVEMENT, PAY, SAFETY = "HR Employee Month", "HR Movement", "HR Pay Fact", "HR Safety Fact"
FACTS = (EMPLOYEE_MONTH, MOVEMENT, PAY, SAFETY)
SETTINGS = "Board Report Settings"
FINANCE, FINANCE_LINE = "Board Finance Figures", "Board Finance Line"
JOB = "hrms_addon.hrms_addon.board_facts.build_month"
# the composite indexes the GROUP BYs read by (on_doctype_update)
INDEXES = {
    EMPLOYEE_MONTH: (("company", "month", "branch"), ("company", "month", "opening_branch"), ("employee", "month")),
    MOVEMENT: (("company", "month", "movement_type"), ("employee", "effective_date")),
    PAY: (("company", "month", "branch"),),
    SAFETY: (("company", "month", "branch"),),
}
# and on the tables a build reads (patches/v1_0/board_fact_indexes.py)
SOURCE_INDEXES = {
    "Salary Slip": (("company", "end_date"),),
    "Attendance": (("company", "attendance_date"),),
    "Version": (("ref_doctype", "creation"),),
    "Safety Incident": (("company", "incident_on"),),
}
# a cut whose opening is read where the month began, not where it ended
OPENING_CUTS = {"branch": "opening_branch", "population": "opening_population"}
# the fields an HR Employee Month row is written with
MONTH_FIELDS = ("employee", "employee_name", "branch", "department", "work_section", "designation", "grade",
                "employment_type", "pay_category", "population", "gender", "age_band", "tenure_band", "is_foreign",
                "opening_branch", "opening_population") + rules.COUNTS + ("hire_reason", "job_requisition",
                                                                          "exit_reason", "exit_type", "regrettable") \
    + rules.MEASURES
MOVEMENT_FIELDS = ("movement_type", "effective_date", "employee", "employee_name", "heads", "branch", "from_branch",
                   "to_branch", "department", "designation", "work_section", "population", "from_population",
                   "to_population", "from_category", "to_category", "hire_reason", "job_requisition", "job_applicant",
                   "exit_reason", "exit_type", "regrettable", "tenure_years", "tenure_band", "source_doctype",
                   "source_name")
PAY_FIELDS = ("branch", "work_section", "population", "component_group", "salary_component", "amount", "heads")
SAFETY_FIELDS = ("branch", "department", "severity", "hazard", "off_site", "incidents", "days_lost")


# ── Settings ──────────────────────────────────────────────────────────
def settings():
    """What the builds and the pack read: the hours in a day, the open
    months, the trend tolerance, each earning's group."""
    try:
        stored = frappe.get_cached_doc(SETTINGS)
    except Exception:
        stored = None

    def get(key):
        return stored.get(key) if stored else None

    return {"hours_per_day": flt(get("hours_per_day")) or 8.0, "days_per_month": cint(get("days_per_month")) or 26,
            "refresh_months": cint(get("refresh_months")) if get("refresh_months") not in (None, "") else 3,
            "tolerance": flt(get("trend_tolerance")) or 10.0,
            "groups": {row.salary_component: row.component_group for row in (get("component_groups") or [])}}


# ── The month's header ────────────────────────────────────────────────
def header(company, month, source=rules.SYSTEM):
    """The month's HR Monthly Snapshot, made where there is none."""
    month = rules.month_start(getdate(month))
    name = frappe.db.get_value(SNAPSHOT, {"company": company, "month_start": month}, "name")
    if name:
        return name
    doc = frappe.get_doc({"doctype": SNAPSHOT, "company": company, "month_start": month, "source": source,
                          "status": rules.IMPORTED if source == rules.IMPORTED else rules.NOT_BUILT})
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def snapshot_autoname(doc):
    doc.name = "%s %s" % (doc.company, rules.month_start(getdate(doc.month_start)).strftime("%Y-%m"))


def snapshot_validate(doc):
    doc.month_start = rules.month_start(getdate(doc.month_start))
    if doc.get("source") == rules.IMPORTED:
        doc.status = rules.IMPORTED
    elif doc.status == rules.IMPORTED:
        doc.status = rules.NOT_BUILT
    if doc.is_new():
        return
    before = doc.get_doc_before_save()
    if before and before.get("source") != doc.get("source") and _rows(doc.company, doc.month_start):
        frappe.throw(_("{0} has rows already: it stays {1}.").format(doc.name, _(before.get("source"))),
                     title=_(SNAPSHOT))


def snapshot_on_trash(doc):
    if cint(doc.locked):
        frappe.throw(_("{0} is locked by an approved board report.").format(doc.name), title=_(SNAPSHOT))
    for doctype in FACTS:
        frappe.db.delete(doctype, {"company": doc.company, "month": doc.month_start})


def _rows(company, month):
    return frappe.db.count(EMPLOYEE_MONTH, {"company": company, "month": rules.month_start(getdate(month))})


@frappe.whitelist(methods=["POST"])
def build(name):
    """The month built again on the long queue, from the form."""
    doc = frappe.get_doc(SNAPSHOT, name)
    doc.check_permission("write")
    if not rules.may_build(doc.locked, doc.source):
        frappe.throw(_("{0} is locked or imported: it stands as it is.").format(doc.name), title=_(SNAPSHOT))
    queue(doc.company, doc.month_start)
    return rules.QUEUED


@frappe.whitelist(methods=["POST"])
def build_months(company, from_date):
    """Every month from from_date's to the month running, each on the long
    queue: how the months before the board pack are filled in."""
    if not frappe.has_permission(SNAPSHOT, "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    queued = 0
    for month in rules.months_between(getdate(from_date), getdate(today())):
        name = header(company, month)
        stored = frappe.db.get_value(SNAPSHOT, name, ["locked", "source"], as_dict=True)
        if rules.may_build(stored.locked, stored.source):
            queue(company, month)
            queued += 1
    return queued


def queue(company, month):
    """The month's build on the long queue, once however often it is asked."""
    month = rules.month_start(getdate(month))
    name = header(company, month)
    frappe.db.set_value(SNAPSHOT, name, {"status": rules.QUEUED, "progress": 0, "build_error": None},
                        update_modified=False)
    frappe.enqueue(JOB, queue="long", timeout=3600, job_id="board-facts::%s::%s" % (company, month),
                   deduplicate=True, enqueue_after_commit=True, company=company, month=str(month))
    return name


def nightly():
    """The month running and the open months before it, built again from the
    site, for each company with people; a month left queued or failed too."""
    back = settings()["refresh_months"]
    for company in frappe.get_all("Employee", filters={"status": "Active"}, pluck="company", distinct=True):
        if not company:
            continue
        try:
            months = rules.refresh_due(rules.months_between(rules.add_months(today(), -back), today()), today(), back)
            stuck = frappe.get_all(SNAPSHOT, filters={"company": company, "status": ["in", [rules.QUEUED, rules.FAILED]],
                                                      "locked": 0, "source": rules.SYSTEM}, pluck="month_start")
            for month in sorted({rules.month_start(getdate(day)) for day in list(months) + list(stuck)}):
                name = header(company, month)
                stored = frappe.db.get_value(SNAPSHOT, name, ["locked", "source"], as_dict=True)
                if rules.may_build(stored.locked, stored.source):
                    queue(company, month)
        except Exception:
            frappe.log_error(title="HRMS Addon: the board pack's nightly build")
    frappe.db.commit()


def _progress(name, percent, status=rules.BUILDING):
    frappe.db.set_value(SNAPSHOT, name, {"status": status, "progress": round(percent)}, update_modified=False)
    frappe.db.commit()
    frappe.publish_progress(percent, title=_("Building {0}").format(name), doctype=SNAPSHOT, docname=name)


# ── The job ───────────────────────────────────────────────────────────
def build_month(company, month):
    """A month's facts built from the site: the people, their movements, pay,
    hours, absence and training, the pay by component and the incidents.
    The month is read as at its last day, or today while it runs."""
    month = rules.month_start(getdate(month))
    name = header(company, month)
    stored = frappe.db.get_value(SNAPSHOT, name, ["locked", "source"], as_dict=True)
    if not rules.may_build(stored.locked, stored.source):
        return name
    try:
        _progress(name, 2)
        counts = _build(company, month, name)
        frappe.db.set_value(SNAPSHOT, name, dict(counts, status=rules.BUILT, progress=100, built_on=now(),
                                                 as_at=rules.as_at(month, today()), build_error=None),
                            update_modified=False)
        summarise(name)
        frappe.db.commit()
    except Exception as error:
        frappe.db.rollback()
        frappe.db.set_value(SNAPSHOT, name, {"status": rules.FAILED, "build_error": str(error)[:500]},
                            update_modified=False)
        frappe.db.commit()
        frappe.log_error(title="HRMS Addon: building the board pack's month %s" % name)
    return name


def _build(company, month, name):
    first, last = month, rules.month_end(month)
    day = rules.as_at(month, today())
    s = settings()
    people = [person for person in _people(company, first, day)]
    names = [person["name"] for person in people]
    moves = _moves(first, set(names))
    _progress(name, 15)
    pay = _pay_by_employee(company, first, last, s["groups"])
    hours = _attendance(company, first, day, s["hours_per_day"])
    training = _training(company, first, day)
    leavers = [person["name"] for person in people if person.get("relieving_date")
               and first <= getdate(person["relieving_date"]) <= day]
    separations = _separations(leavers)
    hires = _hire_reasons([person for person in people if person.get("date_of_joining")
                           and first <= getdate(person["date_of_joining"]) <= day])
    _progress(name, 35)
    month_rows, movement_rows = [], []
    for person in people:
        mine = moves.get(person["name"]) or []
        measures = dict(pay.get(person["name"]) or {}, **(hours.get(person["name"]) or {}))
        measures["training_hours"] = training.get(person["name"], 0.0)
        row = rules.employee_month(person, first, day, mine, measures, separations.get(person["name"]),
                                   hires.get(person["name"]))
        if row:
            month_rows.append(row)
        movement_rows += rules.movement_rows(person, first, day, mine, separations.get(person["name"]),
                                             hires.get(person["name"]))
    _replace(EMPLOYEE_MONTH, company, month, name, month_rows, MONTH_FIELDS, 35, 65,
             naming=lambda row: rules.fact_name(month, row["employee"]))
    _replace(MOVEMENT, company, month, name, movement_rows, MOVEMENT_FIELDS, 65, 75)
    pay_rows = _pay_facts(company, month, first, last, s["groups"])
    _replace(PAY, company, month, name, pay_rows, PAY_FIELDS, 75, 85)
    safety_rows = _safety_facts(company, first, day)
    _replace(SAFETY, company, month, name, safety_rows, SAFETY_FIELDS, 85, 95)
    return {"employee_rows": len(month_rows), "movement_rows": len(movement_rows), "pay_rows": len(pay_rows),
            "safety_rows": len(safety_rows)}


def _replace(doctype, company, month, snapshot, rows, fields, start, end, naming=None):
    """The month's system rows of a fact table written afresh, a chunk at a
    time with a commit after each; imported rows are left alone."""
    frappe.db.delete(doctype, {"company": company, "month": month, "source": rules.SYSTEM})
    frappe.db.commit()
    _insert(doctype, company, month, snapshot, rows, fields, rules.SYSTEM, naming,
            lambda share: _progress(snapshot, start + (end - start) * share))


def _insert(doctype, company, month, snapshot, rows, fields, source, naming=None, progress=None):
    """Rows written straight in, 500 at a time, a commit after each."""
    stamp, user = now(), frappe.session.user
    columns = ["name", "creation", "modified", "owner", "modified_by", "docstatus", "idx", "company", "month",
               "source", "snapshot"] + list(fields)
    parts = rules.chunks(rows)
    for number, part in enumerate(parts, 1):
        values = []
        for row in part:
            values.append([naming(row) if naming else frappe.generate_hash(length=12), stamp, stamp, user, user, 0,
                           0, company, month, source, snapshot] + [row.get(field) for field in fields])
        frappe.db.bulk_insert(doctype, columns, values)
        frappe.db.commit()
        if progress:
            progress(number / len(parts))


def convert_legacy(name, plant_rows):
    """A month of the old board pack (its HR Snapshot Plant rows) as imported
    fact rows; the month is Imported from then on, never built from the site
    (patches/v1_0/board_facts_from_snapshots.py)."""
    doc = frappe.get_doc(SNAPSHOT, name)
    month = rules.month_start(getdate(doc.month_start))
    if frappe.db.count(EMPLOYEE_MONTH, {"company": doc.company, "month": month}):
        return False
    people, pay, safety = [], [], []
    for row in plant_rows:
        found = rules.legacy_rows(row)
        people += found[0]
        pay += found[1]
        safety += found[2]
    _insert(EMPLOYEE_MONTH, doc.company, month, name, people, MONTH_FIELDS, rules.IMPORTED)
    _insert(PAY, doc.company, month, name, pay, PAY_FIELDS, rules.IMPORTED)
    _insert(SAFETY, doc.company, month, name, safety, SAFETY_FIELDS, rules.IMPORTED)
    frappe.db.set_value(SNAPSHOT, name, {"source": rules.IMPORTED, "status": rules.IMPORTED,
                                         "employee_rows": len(people), "pay_rows": len(pay),
                                         "safety_rows": len(safety)}, update_modified=False)
    summarise(name)
    return True


# ── What a build reads ────────────────────────────────────────────────
def _has(doctype, field):
    return frappe.get_meta(doctype).has_field(field)


def _people(company, first, day):
    """Everyone with the company at any time from the month's start to the
    day it is read as at, as they are now."""
    wanted = {"name": "name", "employee_name": "employee_name", "branch": "branch", "department": "department",
              "designation": "designation", "gender": "gender", "date_of_birth": "date_of_birth",
              "date_of_joining": "date_of_joining", "relieving_date": "relieving_date", "grade": "grade",
              "employment_type": "employment_type", "custom_work_section": "work_section",
              "custom_pay_category": "pay_category", "custom_is_foreign": "foreign", "job_applicant": "job_applicant"}
    fields = [field for field in wanted if field in ("name", "employee_name") or _has("Employee", field)]
    out = []
    for row in frappe.get_all("Employee", filters={"company": company, "date_of_joining": ["<=", day]},
                              fields=fields, limit_page_length=0):
        if row.get("relieving_date") and getdate(row.relieving_date) < first:
            continue
        out.append({wanted[field]: row.get(field) for field in fields})
    return out


def _moves(first, names):
    """{employee: [moves]} from the month's start to today: submitted
    Employee Transfers, and the Employee's history of changes to plant and
    pay category, the transfer's own kept where both say the same move."""
    transfers = frappe.get_all("Employee Transfer", filters={"docstatus": 1, "transfer_date": [">=", first]},
                               fields=["name", "employee", "transfer_date"], limit_page_length=0)
    transfers = [row for row in transfers if row.employee in names]
    details = {}
    if transfers:
        for row in frappe.get_all("Employee Property History",
                                  filters={"parenttype": "Employee Transfer",
                                           "parent": ["in", [row.name for row in transfers]]},
                                  fields=["parent", "fieldname", "current", "new"], limit_page_length=0):
            details.setdefault(row.parent, []).append(row)
    from_transfers = rules.transfer_moves([dict(row, details=details.get(row.name)) for row in transfers])
    versions = frappe.db.sql(
        """SELECT `name`, `docname`, `creation`, `data` FROM `tabVersion`
        WHERE `ref_doctype` = 'Employee' AND `creation` >= %(since)s
        AND (`data` LIKE %(branch)s OR `data` LIKE %(category)s)""",
        {"since": "%s 00:00:00" % first, "branch": '%"branch"%', "category": '%"custom_pay_category"%'},
        as_dict=True)
    from_versions = rules.version_moves([row for row in versions if row.docname in names])
    out = {}
    for move in rules.merge_moves(from_transfers, from_versions):
        out.setdefault(move["employee"], []).append(move)
    return out


def _rate(alias="s"):
    return "COALESCE(NULLIF({0}.`exchange_rate`, 0), 1)".format(alias)


def _gross(alias="s"):
    """A slip's gross in the company's currency: an expatriate's converted."""
    return "COALESCE(NULLIF({0}.`base_gross_pay`, 0), {0}.`gross_pay` * {1})".format(alias, _rate(alias))


def _pay_by_employee(company, first, last, groups):
    """{employee: {"gross_pay", "ot_pay", "paid"}}: the slips submitted in
    the month, a GROUP BY each."""
    values = {"company": company, "first": first, "last": last}
    out = {}
    for row in frappe.db.sql(
            """SELECT s.`employee` AS employee, SUM({gross}) AS gross, COUNT(*) AS slips
            FROM `tabSalary Slip` s
            WHERE s.`company` = %(company)s AND s.`docstatus` = 1 AND s.`end_date` BETWEEN %(first)s AND %(last)s
            GROUP BY s.`employee`""".format(gross=_gross()), values, as_dict=True):
        out[row.employee] = {"gross_pay": flt(row.gross), "paid": 1 if cint(row.slips) else 0, "ot_pay": 0.0}
    overtime = tuple(component for component, group in groups.items() if group in ("Overtime", "Special Overtime"))
    if overtime:
        for row in frappe.db.sql(
                """SELECT s.`employee` AS employee, SUM(d.`amount` * {rate}) AS amount
                FROM `tabSalary Slip` s
                JOIN `tabSalary Detail` d ON d.`parent` = s.`name` AND d.`parenttype` = 'Salary Slip'
                    AND d.`parentfield` = 'earnings'
                WHERE s.`company` = %(company)s AND s.`docstatus` = 1 AND s.`end_date` BETWEEN %(first)s AND %(last)s
                    AND d.`statistical_component` = 0 AND d.`do_not_include_in_total` = 0
                    AND d.`salary_component` IN %(overtime)s
                GROUP BY s.`employee`""".format(rate=_rate()), dict(values, overtime=overtime), as_dict=True):
            out.setdefault(row.employee, {"gross_pay": 0.0, "paid": 0})["ot_pay"] = flt(row.amount)
    return out


def _attendance(company, first, day, hours_per_day):
    """{employee: hours, days worked and absent, overtime hours, days on the
    clock}: the month's submitted attendance, one GROUP BY."""
    overtime = "COALESCE(a.`actual_overtime_duration`, 0)" if _has("Attendance", "actual_overtime_duration") else "0"
    out = {}
    for row in frappe.db.sql(
            """SELECT a.`employee` AS employee, COUNT(*) AS days,
                SUM(CASE WHEN a.`status` IN ('Present', 'Work From Home') THEN 1
                    WHEN a.`status` = 'Half Day' THEN 0.5 ELSE 0 END) AS worked,
                SUM(CASE WHEN a.`status` = 'Absent' THEN 1 ELSE 0 END) AS absent,
                SUM(CASE WHEN COALESCE(a.`working_hours`, 0) > 0 THEN a.`working_hours` ELSE 0 END) AS hours,
                SUM(CASE WHEN COALESCE(a.`working_hours`, 0) > 0 THEN 0
                    WHEN a.`status` IN ('Present', 'Work From Home') THEN 1
                    WHEN a.`status` = 'Half Day' THEN 0.5 ELSE 0 END) AS unclocked,
                SUM({overtime}) AS ot_hours,
                SUM(CASE WHEN a.`in_time` IS NOT NULL THEN 1 ELSE 0 END) AS clocked
            FROM `tabAttendance` a
            WHERE a.`company` = %(company)s AND a.`docstatus` = 1
                AND a.`attendance_date` BETWEEN %(first)s AND %(day)s
            GROUP BY a.`employee`""".format(overtime=overtime), {"company": company, "first": first, "day": day},
            as_dict=True):
        out[row.employee] = rules.attendance_measures(row, hours_per_day)
    return out


def _training(company, first, day):
    """{employee: hours}: the sessions held in the month that they attended,
    each at the hours the learning module gives it."""
    from hrms_addon.hrms_addon import learning_rules

    events = frappe.get_all("Training Event", filters={
        "company": company, "docstatus": 1, "event_status": ["!=", "Cancelled"],
        "start_time": ["between", ["%s 00:00:00" % first, "%s 23:59:59" % day]]},
        fields=["name", "start_time", "end_time", "training_program"], limit_page_length=0)
    if not events:
        return {}
    names = [event.name for event in events]
    programme_hours = {}
    if _has("Training Program", "custom_duration_hours"):
        programme_hours = dict(frappe.get_all(
            "Training Program", filters={"name": ["in", list({event.training_program for event in events
                                                              if event.training_program}) or [""]]},
            fields=["name", "custom_duration_hours"], as_list=True))
    results = dict(frappe.get_all("Training Result", filters={"docstatus": 1, "training_event": ["in", names]},
                                  fields=["name", "training_event"], as_list=True))
    recorded = {}
    if results:
        for row in frappe.get_all("Training Result Employee", filters={"parenttype": "Training Result",
                                                                       "parent": ["in", list(results)]},
                                  fields=["parent", "employee", "hours"], limit_page_length=0):
            recorded[(results[row.parent], row.employee)] = flt(row.hours)
    event_of = {event.name: event for event in events}
    out = {}
    for row in frappe.get_all("Training Event Employee", filters={"parenttype": "Training Event", "parent": ["in", names],
                                                                  "attendance": "Present"},
                              fields=["parent", "employee"], limit_page_length=0):
        event = event_of[row.parent]
        out[row.employee] = out.get(row.employee, 0.0) + learning_rules.event_hours(
            event.start_time, event.end_time, programme_hours.get(event.training_program),
            recorded.get((row.parent, row.employee)))
    return out


def _separations(leavers):
    """{employee: {"name", "reason", "exit_type", "regrettable"}} from their
    latest separation that is not cancelled."""
    if not leavers:
        return {}
    meta = frappe.get_meta("Employee Separation")
    wanted = {"custom_reason": "reason", "custom_exit_type": "exit_type", "custom_regrettable": "regrettable"}
    fields = ["name", "employee", "modified"] + [field for field in wanted if meta.has_field(field)]
    out = {}
    for row in frappe.get_all("Employee Separation", filters={"employee": ["in", leavers], "docstatus": ["!=", 2]},
                              fields=fields, order_by="modified asc", limit_page_length=0):
        out[row.employee] = dict({"name": row.name}, **{wanted[field]: row.get(field) for field in fields
                                                        if field in wanted})
    return out


def _hire_reasons(hires):
    """{employee: {"reason", "job_requisition", "job_applicant"}}: the reason
    of the requisition each was hired against, through their applicant and
    the opening applied for."""
    hires = [person for person in hires if person.get("job_applicant")]
    if not hires:
        return {}
    openings = dict(frappe.get_all("Job Applicant", filters={"name": ["in", [p["job_applicant"] for p in hires]]},
                                   fields=["name", "job_title"], as_list=True))
    requisitions = dict(frappe.get_all("Job Opening", filters={"name": ["in", [v for v in openings.values() if v]
                                                                         or [""]]},
                                       fields=["name", "job_requisition"], as_list=True))
    reasons = {}
    if _has("Job Requisition", "custom_reason_type"):
        reasons = dict(frappe.get_all("Job Requisition", filters={"name": ["in", [v for v in requisitions.values() if v]
                                                                             or [""]]},
                                      fields=["name", "custom_reason_type"], as_list=True))
    out = {}
    for person in hires:
        requisition = requisitions.get(openings.get(person["job_applicant"]))
        out[person["name"]] = {"reason": reasons.get(requisition), "job_requisition": requisition,
                               "job_applicant": person["job_applicant"]}
    return out


def _pay_facts(company, month, first, last, groups):
    """The month's HR Pay Fact rows: one GROUP BY over the slips' earnings
    and one over the slips, by plant, section and population, the employee's
    month row giving the section and population."""
    meta = frappe.get_meta("Employee")
    category = "e.`custom_pay_category`" if meta.has_field("custom_pay_category") else "NULL"
    foreign = "e.`custom_is_foreign`" if meta.has_field("custom_is_foreign") else "0"
    section = "e.`custom_work_section`" if meta.has_field("custom_work_section") else "NULL"
    keys = """COALESCE(NULLIF(s.`branch`, ''), m.`branch`), COALESCE(m.`work_section`, {section}),
        m.`population`, {category}, {foreign}""".format(section=section, category=category, foreign=foreign)
    joins = """LEFT JOIN `tabHR Employee Month` m ON m.`employee` = s.`employee` AND m.`company` = s.`company`
            AND m.`month` = %(month)s
        LEFT JOIN `tabEmployee` e ON e.`name` = s.`employee`"""
    where = """s.`company` = %(company)s AND s.`docstatus` = 1 AND s.`end_date` BETWEEN %(first)s AND %(last)s"""
    values = {"company": company, "month": month, "first": first, "last": last}
    details = frappe.db.sql(
        """SELECT COALESCE(NULLIF(s.`branch`, ''), m.`branch`) AS branch,
            COALESCE(m.`work_section`, {section}) AS work_section, m.`population` AS population,
            {category} AS pay_category, {foreign} AS foreign_flag, d.`salary_component` AS salary_component,
            SUM(d.`amount` * {rate}) AS amount, COUNT(DISTINCT s.`employee`) AS heads
        FROM `tabSalary Slip` s
        JOIN `tabSalary Detail` d ON d.`parent` = s.`name` AND d.`parenttype` = 'Salary Slip'
            AND d.`parentfield` = 'earnings'
        {joins}
        WHERE {where} AND d.`statistical_component` = 0 AND d.`do_not_include_in_total` = 0
        GROUP BY {keys}, d.`salary_component`""".format(section=section, category=category, foreign=foreign,
                                                         rate=_rate(), joins=joins, where=where, keys=keys),
        values, as_dict=True)
    grosses = frappe.db.sql(
        """SELECT COALESCE(NULLIF(s.`branch`, ''), m.`branch`) AS branch,
            COALESCE(m.`work_section`, {section}) AS work_section, m.`population` AS population,
            {category} AS pay_category, {foreign} AS foreign_flag,
            SUM({gross}) AS gross, COUNT(DISTINCT s.`employee`) AS heads
        FROM `tabSalary Slip` s
        {joins}
        WHERE {where}
        GROUP BY {keys}""".format(section=section, category=category, foreign=foreign, gross=_gross(), joins=joins,
                                  where=where, keys=keys),
        values, as_dict=True)
    for row in list(details) + list(grosses):
        row["population"] = row.get("population") or rules.population(row.get("pay_category"), row.get("foreign_flag"))
    return rules.pay_rows(details, grosses, groups)


def _safety_facts(company, first, day):
    """The month's HR Safety Fact rows: one GROUP BY over the incidents, the
    days lost the longer of the sick days and the rest the doctors gave."""
    return [dict(row) for row in frappe.db.sql(
        """SELECT i.`branch` AS branch, i.`department` AS department, i.`severity` AS severity,
            i.`hazard` AS hazard, COALESCE(i.`off_site`, 0) AS off_site, COUNT(*) AS incidents,
            SUM(CASE WHEN COALESCE(r.`rest`, 0) > COALESCE(i.`sick_days`, 0) THEN COALESCE(r.`rest`, 0)
                ELSE COALESCE(i.`sick_days`, 0) END) AS days_lost
        FROM `tabSafety Incident` i
        LEFT JOIN (SELECT `parent`, SUM(`rest_days`) AS rest FROM `tabSafety Medical Report`
            WHERE `parenttype` = 'Safety Incident' AND `recommendation` = 'Rest' GROUP BY `parent`) r
            ON r.`parent` = i.`name`
        WHERE i.`company` = %(company)s AND i.`docstatus` < 2
            AND i.`incident_on` BETWEEN %(start)s AND %(end)s
        GROUP BY i.`branch`, i.`department`, i.`severity`, i.`hazard`, COALESCE(i.`off_site`, 0)""",
        {"company": company, "start": "%s 00:00:00" % first, "end": "%s 23:59:59" % day}, as_dict=True)]


# ── The header's totals ───────────────────────────────────────────────
def summarise(name):
    """The month's totals, its reconciliation by plant and its data quality,
    from the same GROUP BYs the pack reads."""
    doc = frappe.get_doc(SNAPSHOT, name)
    month = rules.month_start(getdate(doc.month_start))
    figures = month_figures(doc.company, month, month).get(month) or {}
    openings = {plant: {"opening": row.get("opening"), "transferred": row.get("transfers_out")}
                for plant, row in figures.items()}
    closings = {plant: {"closing": row.get("closing"), "hired": row.get("hires"), "exited": row.get("exits"),
                        "transferred": row.get("transfers_in"), "paid": row.get("payroll_heads")}
                for plant, row in figures.items()}
    rows, total = rules.reconciliation(openings, closings)
    doc.set("reconciliation", [dict(row, branch=row["branch"]) for row in rows
                               if any(row[field] for field in ("opening", "closing", "hires", "exits"))])
    doc.total_opening, doc.total_hires, doc.total_exits = total["opening"], total["hires"], total["exits"]
    doc.total_transfers = total["transfers_in"]
    doc.total_conversions = sum(cint(row.get("conversions")) for row in figures.values())
    doc.total_closing, doc.total_payroll_heads = total["closing"], total["payroll_heads"]
    doc.total_wage_bill = sum(flt(row.get("wage_bill")) for row in figures.values())
    doc.reconciliation_variance, doc.payroll_variance = total["variance"], total["payroll_variance"]
    for key, count in data_quality(doc.company, month, rules.month_end(month)).items():
        doc.set(key, count)
    doc.flags.ignore_permissions = True
    doc.flags.from_build = True
    doc.save()
    return doc


@frappe.whitelist(methods=["POST"])
def refresh_totals(name):
    frappe.get_doc(SNAPSHOT, name).check_permission("write")
    summarise(name)


# ── Imported rows ─────────────────────────────────────────────────────
def fact_validate(doc):
    """A row typed or imported for a month before the system: its month's
    header made Imported, never one built from the site, never a locked one."""
    if doc.is_new():
        doc.source = rules.IMPORTED
    elif doc.get("source") == rules.SYSTEM:
        frappe.throw(_("This row is built from the site: build its month again instead."), title=_(doc.doctype))
    if doc.doctype == MOVEMENT:
        doc.month = rules.month_start(getdate(doc.effective_date))
    doc.month = rules.month_start(getdate(doc.month))
    name = header(doc.company, doc.month, source=rules.IMPORTED)
    stored = frappe.db.get_value(SNAPSHOT, name, ["source", "locked"], as_dict=True)
    if cint(stored.locked):
        frappe.throw(_("{0} is locked by an approved board report.").format(name), title=_(doc.doctype))
    if stored.source != rules.IMPORTED:
        frappe.throw(_("{0} is built from the site: import only the months before it.").format(name),
                     title=_(doc.doctype))
    doc.snapshot = name
    if doc.doctype in (EMPLOYEE_MONTH, MOVEMENT):
        if doc.get("employee"):
            doc.heads = 1
        elif cint(doc.get("heads")) < 1:
            frappe.throw(_("Heads: how many people the row counts."), title=_(doc.doctype))
    if doc.doctype == EMPLOYEE_MONTH:
        for field in rules.COUNTS:
            if cint(doc.get(field)) < 0:
                frappe.throw(_("{0} cannot be below nought.").format(doc.meta.get_label(field)), title=_(doc.doctype))
        if not doc.get("opening_branch"):
            doc.opening_branch = doc.get("branch")
        if not doc.get("opening_population"):
            doc.opening_population = doc.get("population")
        if doc.get("employee") and not doc.get("population"):
            doc.population = rules.population(doc.get("pay_category"), doc.get("is_foreign"))


def fact_on_update(doc):
    _summarise_later(doc.company, doc.month)


def fact_on_trash(doc):
    if doc.get("source") == rules.SYSTEM and not doc.flags.from_build:
        frappe.throw(_("This row is built from the site: build its month again instead."), title=_(doc.doctype))
    if frappe.db.get_value(SNAPSHOT, {"company": doc.company, "month_start": doc.month}, "locked"):
        frappe.throw(_("The month is locked by an approved board report."), title=_(doc.doctype))
    _summarise_later(doc.company, doc.month)


def _summarise_later(company, month):
    name = frappe.db.get_value(SNAPSHOT, {"company": company, "month_start": rules.month_start(getdate(month))}, "name")
    if name:
        frappe.enqueue("hrms_addon.hrms_addon.board_facts.summarise", queue="default", job_id="board-summary::" + name,
                       deduplicate=True, enqueue_after_commit=True, name=name)


# ── Locking ───────────────────────────────────────────────────────────
def lock(company, months, report):
    """An approved report's months, locked: never built again."""
    for month in months:
        name = header(company, month)
        frappe.db.set_value(SNAPSHOT, name, {"locked": 1, "locked_by": report}, update_modified=False)


def unlock(report):
    """A cancelled report lets go of the months it locked."""
    for name in frappe.get_all(SNAPSHOT, filters={"locked_by": report}, pluck="name"):
        frappe.db.set_value(SNAPSHOT, name, {"locked": 0, "locked_by": None}, update_modified=False)


def ready(company, months):
    """{month: whether its figures may be read}: built or imported."""
    stored = {rules.month_start(getdate(row.month_start)): row.status for row in frappe.get_all(
        SNAPSHOT, filters={"company": company, "month_start": ["in", [rules.month_start(m) for m in months]]},
        fields=["month_start", "status"])}
    return {rules.month_start(month): stored.get(rules.month_start(month)) in rules.READY for month in months}


# ── Reading the facts back ────────────────────────────────────────────
def month_figures(company, first, last, branch=None):
    """{month: {plant: figures}} from the facts and Finance's lines: a GROUP
    BY over each, by month and plant. A row with no plant is NO_PLANT's."""
    first, last = rules.month_start(getdate(first)), rules.month_start(getdate(last))
    values = {"company": company, "first": first, "last": last, "branch": branch}
    plant_filter = " AND `branch` = %(branch)s" if branch else ""
    out = {}

    def row_of(month, plant):
        month = rules.month_start(getdate(month))
        return out.setdefault(month, {}).setdefault(rules.plant(plant), {})

    for row in frappe.db.sql(
            """SELECT `month`, COALESCE(`branch`, '') AS plant,
                SUM(`closing`) AS closing,
                SUM(CASE WHEN `population` = 'Casual' THEN `closing` ELSE 0 END) AS casual,
                SUM(CASE WHEN `population` = 'Expatriate' THEN `closing` ELSE 0 END) AS expatriate,
                SUM(CASE WHEN `gender` = 'Male' THEN `closing` ELSE 0 END) AS male,
                SUM(CASE WHEN `gender` = 'Female' THEN `closing` ELSE 0 END) AS female,
                SUM(`hired`) AS hires,
                SUM(CASE WHEN `population` = 'Casual' THEN `hired` ELSE 0 END) AS hires_casual,
                SUM(CASE WHEN `hire_reason` = 'Replacement' THEN `hired` ELSE 0 END) AS replacements,
                SUM(CASE WHEN `hire_reason` = 'Addition' THEN `hired` ELSE 0 END) AS additions,
                SUM(CASE WHEN `hire_reason` IN ('Replacement', 'Addition') THEN 0 ELSE `hired` END) AS unclassified,
                SUM(`exited`) AS exits,
                SUM(CASE WHEN `population` = 'Casual' THEN `exited` ELSE 0 END) AS exits_casual,
                SUM(CASE WHEN `regrettable` = 1 THEN `exited` ELSE 0 END) AS regrettable,
                SUM(CASE WHEN `exit_type` = 'Voluntary' THEN `exited` ELSE 0 END) AS voluntary,
                SUM(CASE WHEN `exit_type` = 'Involuntary' THEN `exited` ELSE 0 END) AS involuntary,
                SUM(`transferred`) AS transfers_in,
                SUM(CASE WHEN `opening_population` = 'Casual' AND `population` <> 'Casual'
                    THEN `converted` ELSE 0 END) AS conversions,
                SUM(`paid`) AS payroll_heads, SUM(`hours_worked`) AS hours_worked,
                SUM(`days_worked`) AS days_worked, SUM(`days_absent`) AS days_absent, SUM(`ot_hours`) AS ot_hours,
                SUM(`training_hours`) AS training_hours, SUM(`attendance_days`) AS attendance_days,
                SUM(`clock_days`) AS clock_days
            FROM `tabHR Employee Month`
            WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s{plants}
            GROUP BY `month`, COALESCE(`branch`, '')""".format(plants=plant_filter), values, as_dict=True):
        row_of(row.month, row.plant).update({key: flt(value) for key, value in row.items()
                                             if key not in ("month", "plant")})
    for row in frappe.db.sql(
            """SELECT `month`, COALESCE(`opening_branch`, '') AS plant, SUM(`opening`) AS opening,
                SUM(CASE WHEN `opening_population` = 'Casual' THEN `opening` ELSE 0 END) AS casual_opening,
                SUM(`transferred`) AS transfers_out
            FROM `tabHR Employee Month`
            WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s{plants}
            GROUP BY `month`, COALESCE(`opening_branch`, '')""".format(
                plants=" AND `opening_branch` = %(branch)s" if branch else ""), values, as_dict=True):
        row_of(row.month, row.plant).update({"opening": flt(row.opening), "casual_opening": flt(row.casual_opening),
                                             "transfers_out": flt(row.transfers_out)})
    groups = {"Basic": "basic", "Per Meter": "per_meter", "Overtime": "overtime",
              "Special Overtime": "special_overtime", "Arrears": "arrears", "Other": "other_pay"}
    for row in frappe.db.sql(
            """SELECT `month`, COALESCE(`branch`, '') AS plant, COALESCE(`population`, '') AS population,
                `component_group`, SUM(`amount`) AS amount
            FROM `tabHR Pay Fact`
            WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s{plants}
            GROUP BY `month`, COALESCE(`branch`, ''), COALESCE(`population`, ''), `component_group`""".format(
                plants=plant_filter), values, as_dict=True):
        figures = row_of(row.month, row.plant)
        amount = flt(row.amount)
        figures["wage_bill"] = figures.get("wage_bill", 0.0) + amount
        if row.population == rules.EXPATRIATE:
            figures["expatriates"] = figures.get("expatriates", 0.0) + amount
        elif row.population == rules.CASUAL:
            figures["casual_pay"] = figures.get("casual_pay", 0.0) + amount
        else:
            field = groups.get(row.component_group, "other_pay")
            figures[field] = figures.get(field, 0.0) + amount
        if row.component_group in ("Overtime", "Special Overtime"):
            figures["overtime_all"] = figures.get("overtime_all", 0.0) + amount
    severity_fields = {rules.NEAR_MISS: "near_misses", rules.FIRST_AID: "first_aid", rules.MEDICAL: "medical",
                       rules.LOST_TIME: "lost_time", rules.FATALITY: "fatalities"}
    for row in frappe.db.sql(
            """SELECT `month`, COALESCE(`branch`, '') AS plant, COALESCE(`severity`, '') AS severity,
                SUM(`incidents`) AS incidents, SUM(`days_lost`) AS days_lost,
                SUM(CASE WHEN `off_site` = 1 THEN `incidents` ELSE 0 END) AS off_site
            FROM `tabHR Safety Fact`
            WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s{plants}
            GROUP BY `month`, COALESCE(`branch`, ''), COALESCE(`severity`, '')""".format(plants=plant_filter),
            values, as_dict=True):
        figures = row_of(row.month, row.plant)
        count = flt(row.incidents)
        if row.severity in severity_fields:
            field = severity_fields[row.severity]
            figures[field] = figures.get(field, 0.0) + count
        if row.severity != rules.NEAR_MISS:
            figures["incidents"] = figures.get("incidents", 0.0) + count
            figures["off_site"] = figures.get("off_site", 0.0) + flt(row.off_site)
        figures["days_lost"] = figures.get("days_lost", 0.0) + flt(row.days_lost)
    for row in frappe.db.sql(
            """SELECT l.`month_start` AS month, COALESCE(l.`branch`, '') AS plant, SUM(l.`revenue`) AS revenue,
                SUM(l.`output_kg`) AS output_kg, SUM(l.`staff_cost`) AS staff_cost
            FROM `tabBoard Finance Line` l
            JOIN `tabBoard Finance Figures` f ON f.`name` = l.`parent`
            WHERE l.`parenttype` = 'Board Finance Figures' AND f.`company` = %(company)s
                AND l.`month_start` BETWEEN %(first)s AND %(last)s{plants}
            GROUP BY l.`month_start`, COALESCE(l.`branch`, '')""".format(
                plants=" AND l.`branch` = %(branch)s" if branch else ""), values, as_dict=True):
        row_of(row.month, row.plant).update({"revenue": flt(row.revenue), "output_kg": flt(row.output_kg),
                                             "staff_cost": flt(row.staff_cost)})
    # a plant and month the clock gave no hours at all: its people at the standard month, so LTIFR still reads
    standard = settings()
    for plants in out.values():
        for figures in plants.values():
            if not flt(figures.get("hours_worked")) and flt(figures.get("closing")):
                figures["hours_worked"] = rules.standard_hours(figures["closing"], standard["hours_per_day"],
                                                               standard["days_per_month"])
                figures["hours_estimated"] = 1
    return out


def cut_figures(company, first, last, by="branch", branch=None, population=None, branches=None):
    """Head count and movements by a cut of HR Employee Month: [{cut,
    opening, closing, hires, exits, transferred, converted, regrettable,
    training_hours, days_absent}], the opening the first month's, the
    closing the last month's, the movements summed over the months."""
    if by not in rules.CUTS:
        frappe.throw(_("Pick a way to group the people."))
    first, last = rules.month_start(getdate(first)), rules.month_start(getdate(last))
    conditions = ["`company` = %(company)s", "`month` BETWEEN %(first)s AND %(last)s"]
    if branch:
        conditions.append("`branch` = %(branch)s")
    elif branches:
        conditions.append("`branch` IN %(branches)s")
    if population:
        conditions.append("`population` = %(population)s")
    rows = frappe.db.sql(
        """SELECT `month`, COALESCE(`{by}`, '') AS cut, SUM(`opening`) AS opening, SUM(`closing`) AS closing,
            SUM(`hired`) AS hires, SUM(`exited`) AS exits, SUM(`transferred`) AS transferred,
            SUM(`converted`) AS converted, SUM(CASE WHEN `regrettable` = 1 THEN `exited` ELSE 0 END) AS regrettable,
            SUM(`training_hours`) AS training_hours, SUM(`days_absent`) AS days_absent,
            SUM(`attendance_days`) AS attendance_days
        FROM `tabHR Employee Month` WHERE {where}
        GROUP BY `month`, COALESCE(`{by}`, '')""".format(by=by, where=" AND ".join(conditions)),
        {"company": company, "first": first, "last": last, "branch": branch, "population": population,
         "branches": tuple(branches or ())}, as_dict=True)
    out = {}
    for row in rows:
        month = rules.month_start(getdate(row.month))
        mine = out.setdefault(row.cut or "", {"cut": row.cut or "", "opening": 0, "closing": 0, "hires": 0,
                                              "exits": 0, "transferred": 0, "converted": 0, "regrettable": 0,
                                              "training_hours": 0.0, "days_absent": 0.0, "attendance_days": 0.0})
        if month == first and by not in OPENING_CUTS:
            mine["opening"] += cint(row.opening)
        if month == last:
            mine["closing"] += cint(row.closing)
        for field in ("hires", "exits", "transferred", "converted", "regrettable"):
            mine[field] += cint(row.get(field))
        for field in ("training_hours", "days_absent", "attendance_days"):
            mine[field] += flt(row.get(field))
    if by in OPENING_CUTS:
        # who opened the month where, as it began: a transfer or a conversion in the month moves them after it
        for row in frappe.db.sql(
                """SELECT COALESCE(`{column}`, '') AS cut, SUM(`opening`) AS opening
                FROM `tabHR Employee Month` WHERE {where} AND `month` = %(first)s
                GROUP BY COALESCE(`{column}`, '')""".format(column=OPENING_CUTS[by], where=" AND ".join(
                    condition.replace("`branch`", "`opening_branch`").replace("`population`", "`opening_population`")
                    for condition in conditions)),
                {"company": company, "first": first, "last": last, "branch": branch, "population": population,
                 "branches": tuple(branches or ())}, as_dict=True):
            out.setdefault(row.cut or "", {"cut": row.cut or "", "opening": 0, "closing": 0, "hires": 0, "exits": 0,
                                           "transferred": 0, "converted": 0, "regrettable": 0, "training_hours": 0.0,
                                           "days_absent": 0.0, "attendance_days": 0.0})["opening"] += cint(row.opening)
    return sorted(out.values(), key=lambda row: (row["cut"] == "", -row["closing"], row["cut"]))


def data_quality(company, first, last):
    """{check: count} of what keeps the figures from adding up."""
    counts = {
        "blank_branch": frappe.db.count("Employee", {"company": company, "status": "Active", "branch": ["is", "not set"]}),
        "left_without_date": frappe.db.count("Employee", {"company": company, "status": "Left",
                                                          "relieving_date": ["is", "not set"]}),
        "slips_without_branch": frappe.db.count("Salary Slip", {"company": company, "docstatus": 1,
                                                                "end_date": ["between", [first, last]],
                                                                "branch": ["is", "not set"]}),
    }
    found = frappe.db.sql(
        """SELECT SUM(`hired`) AS hires FROM `tabHR Employee Month`
        WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s
            AND `hired` > 0 AND (`hire_reason` IS NULL OR `hire_reason` = '' OR `hire_reason` = 'Unclassified')""",
        {"company": company, "first": rules.month_start(getdate(first)), "last": rules.month_start(getdate(last))},
        as_dict=True)
    counts["hires_without_requisition"] = cint(found[0].hires) if found else 0
    return counts


# ── Indexes ───────────────────────────────────────────────────────────
def add_indexes(doctype=None):
    """The composite indexes the GROUP BYs read by: a fact table's own on its
    sync (on_doctype_update), the tables a build reads by the patch. A speed
    up only, so a table that will not take one holds nothing else up."""
    wanted = {doctype: INDEXES.get(doctype, ())} if doctype else SOURCE_INDEXES
    for name, indexes in wanted.items():
        if not frappe.db.table_exists(name):
            continue
        for fields in indexes:
            try:
                frappe.db.add_index(name, list(fields), index_name="ha_" + "_".join(fields))
            except Exception:
                frappe.log_error(title="HRMS Addon: index on %s (%s)" % (name, ", ".join(fields)))
