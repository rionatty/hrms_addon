# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence's stored summaries, and what every scorecard
reads from them (18 Nov 2026).

  Section Day Summary       what one submitted shift adds to its section's
                            day: written on submit, taken out on cancel
  Section Week Summary      a section's week, the workbook's Weekly Summary:
                            the sums of its days and its score from them,
                            written again whenever one of its days changes
  Section Downtime Summary  the minutes each submitted shift lost, by reason
                            and machine

The scorecards, the executive page, the brief and the trends read these with
GROUP BY through frappe.get_list, so a user held to a plant by a User
Permission sees that plant's figures, against that plant's head count. No
query is made per supervisor, section or employee, and no list of employee
numbers is passed where the rows carry their plant and section.

A period is scored from its totals (excellence_rules.period_scores), a plant
as the average of its sections.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import excellence_rules as rules
from hrms_addon.hrms_addon.queries import aggregate

DAY, WEEK, DOWNTIME = "Section Day Summary", "Section Week Summary", "Section Downtime Summary"
SHIFT_REPORT, SECTION, ASSIGNMENT = "Shift Report", "Work Section", "Section Assignment"
CASE, GRIEVANCE, INTERVENTION, PEOPLE_LOG = "Disciplinary Case", "Employee Grievance", "HR Intervention", "People Log"
ASSESSMENT, REQUIREMENT, SHEET = "Competency Assessment", "Employee Training Requirement", "Plant Day Sheet"
EMPLOYEE_SECTION = "custom_work_section"
REBUILD_PART = 200


def settings():
    from hrms_addon.hrms_addon import excellence

    return excellence.settings()


def _key(*parts):
    return "|".join(str(part) for part in parts)


def _sums():
    return [aggregate("SUM", field, field) for field in rules.SUMMARY_FIELDS]


# ── Writing ───────────────────────────────────────────────────────────
def write_shift(doc):
    """A submitted shift's day summary and downtime, and its section's week."""
    from hrms_addon.hrms_addon import excellence

    s = settings()
    section = frappe.get_cached_doc(SECTION, doc.work_section)
    standard = excellence.section_standard(section, doc.report_date)
    waste_cap, complaint_cap = rules.caps(standard, s)
    figures = {field: doc.get(field) for field in ("machines_running", "machine_hours", "hours_lost", "not_wearing",
                                                   "ot_cost", "regular_labour", "labour_cost", "labour_budget",
                                                   "absence_cost", "required_crew", "score")}
    figures.update(waste_cap=waste_cap, complaint_cap=complaint_cap,
                   absent=max(0, cint(doc.staff_planned) - cint(doc.staff_on_shift)),
                   factors={key: flt(doc.get("factor_" + key)) for key in rules.FACTOR_KEYS})
    values = rules.day_summary(doc.as_dict(), figures, s)
    day = getdate(doc.report_date)
    values.update(summary_date=day, shift=doc.shift, work_section=doc.work_section, branch=doc.branch,
                  company=doc.company, unit=doc.unit, week=rules.week_label(day), month=str(day)[:7],
                  supervisor=doc.get("supervisor"), supervisor_name=doc.get("supervisor_name"),
                  production_officer=doc.get("production_officer"), shift_report=doc.name,
                  plant_day_sheet=doc.get("plant_day_sheet"), score=doc.score, status=doc.status)
    _upsert(DAY, _key(doc.work_section, day, doc.shift), values)
    _write_downtime(doc, values)
    rebuild_week(doc.work_section, values["week"])


def remove_shift(doc):
    frappe.db.delete(DAY, {"shift_report": doc.name})
    frappe.db.delete(DOWNTIME, {"shift_report": doc.name})
    rebuild_week(doc.work_section, rules.week_label(doc.report_date))


def _upsert(doctype, key, values):
    if frappe.db.exists(doctype, key):
        frappe.db.set_value(doctype, key, values)
    else:
        frappe.get_doc(dict(values, doctype=doctype, summary_key=key)).insert(ignore_permissions=True)


def _write_downtime(doc, day):
    """The minutes lost by reason and machine: the shift's events, else its
    hours lost under its main reason."""
    frappe.db.delete(DOWNTIME, {"shift_report": doc.name})
    lost = {}
    events = doc.get("downtime") or []
    if events:
        for event in events:
            key = (event.get("downtime_reason") or "", event.get("machine") or "")
            lost[key] = lost.get(key, 0.0) + flt(event.get("minutes"))
    elif flt(doc.get("hours_lost")) > 0:
        lost[(doc.get("downtime_reason") or "", "")] = flt(doc.hours_lost) * 60
    if not lost:
        return
    named = sorted({reason for reason, _machine in lost if reason})
    reasons = {row.name: row for row in frappe.get_all("Downtime Reason", filters={"name": ["in", named]},
                                                       fields=["name", "category", "planned"])} if named else {}
    for (reason, machine), minutes in sorted(lost.items()):
        if minutes <= 0:
            continue
        found = reasons.get(reason) or {}
        frappe.get_doc({
            "doctype": DOWNTIME, "summary_key": _key(doc.name, reason or rules.NO_REASON, machine),
            "summary_date": day["summary_date"], "shift": doc.shift, "work_section": doc.work_section,
            "branch": doc.branch, "company": doc.company, "week": day["week"], "month": day["month"],
            "downtime_reason": reason or None, "category": found.get("category") or "",
            "planned": cint(found.get("planned")), "machine": machine or None, "minutes": minutes,
            "shift_report": doc.name,
        }).insert(ignore_permissions=True)


def rebuild_week(section, week):
    """A section's week from its days: the workbook's Weekly Summary row."""
    s = settings()
    rows = frappe.get_all(DAY, filters={"work_section": section, "week": week}, fields=_sums())
    t = rules.totals([row for row in rows if flt(row.get("shifts"))], s)
    key = _key(section, week)
    if not t["shifts"]:
        frappe.db.delete(WEEK, {"summary_key": key})
        return
    year, number = week.split("-W")
    start, end = rules.period_bounds(rules.WEEK, int(year), int(number))
    scored = rules.period_scores(t, s)
    a = rules.averages(t, s)
    meta = frappe.db.get_value(SECTION, section, ["branch", "company", "unit"], as_dict=True) or {}
    values = {field: t[field] for field in rules.SUMMARY_FIELDS}
    values.update(week=week, week_start=start, work_section=section, branch=meta.get("branch"),
                  company=meta.get("company"), unit=meta.get("unit"), score=scored["score"], status=scored["status"],
                  weakest_area=rules.FACTOR_LABELS.get(scored["weakest"], ""),
                  achievement=_pct(a["achievement"]), uptime=_pct(a["uptime"]), attendance_rate=_pct(a["attendance"]),
                  ppe_rate=_pct(a["ppe"]), housekeeping_average=_pct(a["housekeeping"]),
                  er_cases=frappe.db.count(CASE, {"work_section": section, "docstatus": ["<", 2],
                                                  "incident_date": ["between", [str(start), str(end)]]}))
    for field, key_name in (("output_score", "output"), ("waste_score", "waste"), ("complaint_score", "complaints"),
                            ("uptime_score", "uptime"), ("attendance_score", "attendance"),
                            ("safety_score", "safety"), ("housekeeping_score", "housekeeping"),
                            ("ppe_score", "ppe")):
        values[field] = round(scored["factors"][key_name], 2)
    _upsert(WEEK, key, values)


def _pct(value):
    return round(value * 100, 2) if value is not None else 0


def rebuild(start, end, branch=None):
    """Every summary of a period written again from its submitted shifts, a
    part at a time: the migration of the first build's reports, and a check."""
    start, end = getdate(start), getdate(end)
    filters = {"report_date": ["between", [str(start), str(end)]], "docstatus": 1}
    if branch:
        filters["branch"] = branch
    names = frappe.get_all(SHIFT_REPORT, filters=filters, pluck="name", order_by="report_date asc",
                           limit_page_length=0)
    scope = {"summary_date": ["between", [str(start), str(end)]]}
    if branch:
        scope["branch"] = branch
    frappe.db.delete(DAY, scope)
    frappe.db.delete(DOWNTIME, scope)
    weeks = set()
    for index, name in enumerate(names, 1):
        doc = frappe.get_doc(SHIFT_REPORT, name)
        write_shift(doc)
        weeks.add((doc.work_section, rules.week_label(doc.report_date)))
        if index % REBUILD_PART == 0:
            frappe.db.commit()
    for section, week in weeks:
        rebuild_week(section, week)
    frappe.db.commit()
    return len(names)


def nightly():
    """The shifts submitted or cancelled in the last two days have their
    summaries as they should: a check behind the submit and cancel."""
    since = add_days(today(), -2)
    for row in frappe.get_all(SHIFT_REPORT, filters={"modified": [">=", str(since)], "docstatus": [">", 0]},
                              fields=["name", "docstatus"], limit_page_length=0):
        doc = frappe.get_doc(SHIFT_REPORT, row.name)
        if row.docstatus == 1:
            write_shift(doc)
        else:
            remove_shift(doc)
    frappe.db.commit()


def check_last_week():
    """Last week's section weeks written again from their days."""
    monday = rules.week_start(today())
    label = rules.week_label(add_days(monday, -7))
    for section in frappe.get_all(DAY, filters={"week": label}, pluck="work_section", distinct=True,
                                  limit_page_length=0):
        rebuild_week(section, label)
    frappe.db.commit()


def add_indexes():
    """on_doctype_update: the readers filter the summaries by plant and date,
    section and date, supervisor and date."""
    for doctype, fields in ((DAY, ["branch", "summary_date"]), (DAY, ["work_section", "summary_date"]),
                            (DAY, ["supervisor", "summary_date"]), (DOWNTIME, ["branch", "summary_date"]),
                            (WEEK, ["branch", "week_start"])):
        if not frappe.db.table_exists(doctype):
            continue
        try:
            frappe.db.add_index(doctype, fields)
        except Exception:
            frappe.log_error(title="Manufacturing Excellence: index on %s" % doctype)


# ── Reading: the scope and the sums ───────────────────────────────────
def scope_filters(start, end, company=None, branch=None, section=None, shift=None, supervisor=None,
                  date_field="summary_date"):
    filters = {date_field: ["between", [str(getdate(start)), str(getdate(end))]]}
    for field, value in (("company", company), ("branch", branch), ("work_section", section), ("shift", shift),
                         ("supervisor", supervisor)):
        if value:
            filters[field] = value
    return filters


def grouped(filters, by, doctype=DAY):
    """{key: totals} of the summaries the user may read matching the filters,
    for each value of the fields in `by` (a tuple of them when several)."""
    by = list(by)
    rows = frappe.get_list(doctype, filters=filters, fields=by + _sums(), group_by=", ".join(by) if by else None,
                           order_by=None, limit_page_length=0)
    s = settings()
    found = {}
    for row in rows:
        if not flt(row.get("shifts")):
            continue
        key = tuple(row.get(field) for field in by) if len(by) > 1 else (row.get(by[0]) if by else None)
        found[key] = rules.totals([row], s)
    return found


def scope_totals(filters):
    """The scope's totals, its output and labour kept by unit."""
    parts = grouped(filters, ("unit",))
    total = rules.add_totals(*parts.values()) if parts else rules.totals([], settings())
    total["_s"] = settings()
    return total


def section_totals(filters):
    """{section: totals} with each section's unit."""
    return {section: total for (section, _unit), total in grouped(filters, ("work_section", "unit")).items()}


def day_rows(start, end, company=None, branch=None, section=None, shift=None, supervisor=None):
    """The submitted shifts of a period, as their day summaries."""
    return frappe.get_list(DAY, filters=scope_filters(start, end, company, branch, section, shift, supervisor),
                           fields=["name", "summary_date", "shift", "work_section", "branch", "unit", "supervisor",
                                   "shift_report"] + list(rules.SUMMARY_FIELDS),
                           order_by="summary_date asc", limit_page_length=0)


# ── The people side of a scope ────────────────────────────────────────
def _employee_filters(company=None, branch=None, section=None):
    filters = {EMPLOYEE_SECTION: section} if section else {EMPLOYEE_SECTION: ["is", "set"]}
    if company:
        filters["company"] = company
    if branch:
        filters["branch"] = branch
    return filters


def headcount(company=None, branch=None, section=None):
    """{section: active employees}."""
    filters = dict(_employee_filters(company, branch, section), status="Active")
    rows = frappe.get_list("Employee", filters=filters,
                           fields=[EMPLOYEE_SECTION, aggregate("COUNT", "*", "count")], group_by=EMPLOYEE_SECTION,
                           order_by=None, limit_page_length=0)
    return {row.get(EMPLOYEE_SECTION): cint(row.get("count")) for row in rows}


def establishment(sections, day):
    """{section: the approved establishment in force on the day}."""
    if not sections:
        return {}
    names = [row.name for row in sections]
    rows = {}
    for row in frappe.get_all("Section Standard", filters={"parenttype": SECTION, "parent": ["in", names]},
                              fields=["parent", "effective_from"] + list(rules.STANDARD_FIELDS),
                              limit_page_length=0):
        rows.setdefault(row.parent, []).append(row)
    return {row.name: cint(rules.standard_on(rows.get(row.name, []), day, row).get("approved_establishment"))
            for row in sections}


def exits(start, end, company=None, branch=None, section=None):
    """{section: (exits, resignations)} in the period."""
    filters = dict(_employee_filters(company, branch, section),
                   relieving_date=["between", [str(getdate(start)), str(getdate(end))]])
    found = {}
    for row in frappe.get_list("Employee", filters=filters,
                               fields=[EMPLOYEE_SECTION, "custom_employee_status", aggregate("COUNT", "*", "count")],
                               group_by="%s, custom_employee_status" % EMPLOYEE_SECTION, order_by=None,
                               limit_page_length=0):
        gone, resigned = found.get(row.get(EMPLOYEE_SECTION), (0, 0))
        found[row.get(EMPLOYEE_SECTION)] = (gone + cint(row.count),
                                            resigned + (cint(row.count) if row.get("custom_employee_status")
                                                        == "Resigned" else 0))
    return found


def competency(company=None, branch=None, section=None):
    """{section: ((competent, assessed), (critical competent, critical assessed))}
    over the current assessments."""
    filters = {"status": ["!=", "Superseded"]}
    for field, value in (("company", company), ("branch", branch), ("work_section", section)):
        if value:
            filters[field] = value
    found = {}
    for row in frappe.get_list(ASSESSMENT, filters=filters,
                               fields=["work_section", "status", "critical", aggregate("COUNT", "*", "count")],
                               group_by="work_section, status, critical", order_by=None, limit_page_length=0):
        (done, assessed), (critical_done, critical_assessed) = found.get(row.work_section, ((0, 0), (0, 0)))
        count = cint(row.count)
        competent = count if row.status == "Competent" else 0
        if cint(row.critical):
            critical_done, critical_assessed = critical_done + competent, critical_assessed + count
        found[row.work_section] = ((done + competent, assessed + count), (critical_done, critical_assessed))
    return found


def coverage(company=None, branch=None, section=None):
    """(done, required) of the required training of the scope's people:
    done and still valid today."""
    filters = {"status": ["!=", "Not Applicable"], "requirement_type": ["!=", "Recommended"]}
    if company:
        filters["company"] = company
    if branch:
        filters["branch"] = branch
    if section:
        people = frappe.get_all("Employee", filters={EMPLOYEE_SECTION: section, "status": "Active"}, pluck="name",
                                limit_page_length=0)
        if not people:
            return 0, 0
        filters["employee"] = ["in", people]
    required = _count(REQUIREMENT, filters)
    if not required:
        return 0, 0
    day = today()
    done = _count(REQUIREMENT, dict(filters, status="Compliant"))
    done += _count(REQUIREMENT, dict(filters, status="Due Soon", completed_on=["is", "set"],
                                     valid_until=[">=", day]))
    done += _count(REQUIREMENT, dict(filters, status="Due Soon", completed_on=["is", "set"],
                                     valid_until=["is", "not set"]))
    return done, required


def _count(doctype, filters):
    rows = frappe.get_list(doctype, filters=filters, fields=[aggregate("COUNT", "*", "count")], order_by=None)
    return cint(rows[0].get("count")) if rows else 0


def _log_filters(start, end, company=None, branch=None, section=None):
    filters = {"log_date": ["between", [str(getdate(start)), str(getdate(end))]]}
    for field, value in (("company", company), ("branch", branch), ("work_section", section)):
        if value:
            filters[field] = value
    return filters


def log_counts(start, end, company=None, branch=None, section=None, shift=None, by_supervisor=False):
    """{type: entries} in the People Log (an entry with no shift counts for
    both), or {supervisor: {type: entries}}."""
    by = ["log_type", "shift"] + (["supervisor"] if by_supervisor else [])
    found = {}
    for row in frappe.get_list(PEOPLE_LOG, filters=_log_filters(start, end, company, branch, section),
                               fields=by + [aggregate("COUNT", "*", "count")], group_by=", ".join(by), order_by=None,
                               limit_page_length=0):
        if shift and row.shift not in (shift, None, ""):
            continue
        target = found.setdefault(row.supervisor, {}) if by_supervisor else found
        target[row.log_type] = target.get(row.log_type, 0) + cint(row.count)
    return found


def pulse(end, company=None, branch=None, section=None):
    filters = dict(_log_filters(add_days(end, -92), end, company, branch, section), log_type=rules.PULSE)
    rows = frappe.get_list(PEOPLE_LOG, filters=filters, fields=[aggregate("SUM", "score", "total"),
                                                                aggregate("COUNT", "*", "count")], order_by=None)
    if not rows or not cint(rows[0].get("count")):
        return None
    return flt(rows[0].get("total")) / cint(rows[0].get("count")) / 100.0


def roster_rows(section_names, start, end, role=rules.SUPERVISOR):
    """The dated roster of these sections touching the period: [{"section",
    "employee", "shift", "from", "to"}]."""
    if not section_names:
        return []
    by_section = {}
    for row in frappe.get_all(ASSIGNMENT, filters={"parenttype": SECTION, "parent": ["in", section_names]},
                              fields=["parent", "employee", "role", "shift", "from_date", "to_date"],
                              order_by="idx asc", limit_page_length=0):
        by_section.setdefault(row.parent, []).append(row)
    found = []
    for section, rows in by_section.items():
        for window in rules.roster_windows(rows, start, end, role):
            window["section"] = section
            found.append(window)
    return found


def intervention_facts(start, end, company=None, branch=None, section=None, supervisor=None, rows=None):
    """The interventions of a scope, counted as the HR Excellence scorecard and
    the supervisor's index read them."""
    if rows is None:
        filters = {}
        for field, value in (("company", company), ("branch", branch), ("work_section", section),
                             ("supervisor", supervisor)):
            if value:
                filters[field] = value
        rows = frappe.get_list(INTERVENTION, filters=filters, limit_page_length=0,
                               fields=["name", "raised_on", "target_date", "closed_on", "status", "on_time", "verified",
                                       "result", "pillar", "overdue", "estimated_saving", "supervisor"])
    start, end = getdate(start), getdate(end)
    due_by = min(end, getdate(today()))
    due = [row for row in rows if row.target_date and getdate(row.target_date) <= due_by]
    supervision = rules.PILLAR_LABELS["supervision"]
    return {
        "interventions_due": len(due),
        "interventions_on_time": sum(1 for row in due if row.on_time == "Yes"),
        "interventions_closed": sum(1 for row in rows if row.closed_on),
        "interventions_improved": sum(1 for row in rows if cint(row.verified) and row.result == rules.IMPROVED),
        "interventions_open_supervision": sum(1 for row in rows if row.pillar == supervision
                                              and row.status not in rules.DONE),
        "interventions_raised": sum(1 for row in rows if row.raised_on and start <= getdate(row.raised_on) <= end),
        "interventions_completed": sum(1 for row in rows if row.closed_on and start <= getdate(row.closed_on) <= end),
        "interventions_overdue": sum(1 for row in rows if cint(row.overdue)),
        "interventions_open": sum(1 for row in rows if row.status not in rules.DONE),
        "savings": sum(flt(row.estimated_saving) for row in rows if cint(row.verified)),
    }


CASE_FIELDS = ["name", "employee", "employee_name", "incident_date", "cause", "severity", "shift", "status", "aware_on",
               "decided_on", "outcome", "docstatus", "creation", "legal_flags", "work_section", "branch", "case_type",
               "case_cost", "quantity", "employment", "supervisor_on_shift", "supervisor_on_shift_name",
               "misconduct_type", "suspension_days", "suspension_from", "plant_order"]


def cases_between(since, end, company=None, branch=None, section=None):
    """The cases of a scope the user may read, from `since` to `end`."""
    filters = {"docstatus": ["<", 2], "incident_date": ["between", [str(getdate(since)), str(getdate(end))]]}
    for field, value in (("company", company), ("branch", branch), ("work_section", section)):
        if value:
            filters[field] = value
    return frappe.get_list(CASE, filters=filters, fields=CASE_FIELDS, order_by="incident_date asc",
                           limit_page_length=0)


def case_facts(start, end, company=None, branch=None, section=None, shift=None, s=None):
    """What the cases of a scope add to the HR Excellence scorecard. A case's
    legal flags are as stored: the daily job keeps an open case's flags up
    to date with the employee's suspension history."""
    s = s or settings()
    start, end = getdate(start), getdate(end)
    since = rules.add_months(start, -int(s["lookback_months"]))
    rows = cases_between(since, end, company, branch, section)
    counts = rules.window_counts(rows, s["lookback_months"])
    day = getdate(today())
    window = [row for row in rows if not shift or row.shift in (shift, None, "")]
    period = [row for row in window if start <= getdate(row.incident_date) <= end]
    decided = [row for row in period if row.decided_on]
    days = [(getdate(row.decided_on) - getdate(row.aware_on or row.incident_date)).days for row in decided]
    open_rows = [row for row in window if row.docstatus == 0 and row.status not in rules.CASE_CLOSED]
    flagged = sum(1 for row in open_rows if (row.legal_flags or "").strip())
    flagged += sum(1 for row in window if row.decided_on and start <= getdate(row.decided_on) <= end
                   and (row.legal_flags or "").strip() and row not in open_rows)
    non_grievance = [row for row in period if row.case_type != "Grievance"]
    return {
        "cases": len(period),
        "conduct_route": sum(1 for row in period if rules.is_conduct(row.cause, row.severity)),
        "coaching_route": sum(1 for row in non_grievance if row.cause and not rules.is_conduct(row.cause,
                                                                                                row.severity)),
        "non_grievance_cases": len(non_grievance),
        "repeats": sum(1 for row in period if counts.get(row.name, 0) >= 2),
        "days_to_resolve": round(sum(days) / float(len(days)), 1) if days else None,
        "legal_flags": flagged,
        "overdue_cases": sum(1 for row in open_rows
                             if (day - getdate(row.aware_on or row.creation)).days > s["case_days"]),
        "conduct_cases": sum(1 for row in period if row.cause == rules.INADEQUATE_SUPERVISION),
        "case_cost": sum(flt(row.case_cost) for row in period),
    }


def grievance_rows(company=None, branch=None, section=None):
    """The open grievances of a scope the user may read."""
    filters = {"docstatus": 0}
    if branch:
        filters["custom_branch"] = branch
    if section:
        filters["custom_work_section"] = section
    rows = frappe.get_list(GRIEVANCE, filters=filters, fields=["name", "date", "creation", "custom_work_section",
                                                                "status"], limit_page_length=0)
    return [row for row in rows if row.status not in rules.GRIEVANCE_DONE]


def grievance_facts(company=None, branch=None, section=None, s=None):
    s = s or settings()
    rows = grievance_rows(company, branch, section)
    day = getdate(today())
    return {"open_grievances": len(rows),
            "grievances_open_long": sum(1 for row in rows
                                        if (day - getdate(row.date or row.creation)).days > s["case_days"])}


def due_shifts(start, end, company=None, branch=None, section=None, shift=None, s=None):
    """(shift rows due in the period to yesterday, of them marked Not Worked on
    the day sheets)."""
    from hrms_addon.hrms_addon import excellence

    s = s or settings()
    reporting = excellence.sections_in(company, branch, section, reporting=True)
    last = min(getdate(end), getdate(add_days(today(), -1)))
    days = rules.working_days(start, last, int(rules._num(s["shifts_per_week"]) // 2) or 6)
    due = days * (1 if shift else 2) * len(reporting)
    idle = 0
    if not section and due:
        filters = {"sheet_date": ["between", [str(getdate(start)), str(last)]], "docstatus": ["<", 2]}
        if branch:
            filters["branch"] = branch
        if company:
            filters["company"] = company
        rows = frappe.get_list(SHEET, filters=filters, fields=[aggregate("SUM", "not_worked_rows", "idle")],
                               order_by=None)
        idle = cint(rows[0].get("idle")) if rows else 0
    return max(0, due - idle), idle


# ── The HR Excellence scorecard's facts ───────────────────────────────
def period_facts(start, end, company=None, branch=None, section=None, shift=None):
    """Everything the HR Excellence scorecard weighs, for a period and a
    company, plant, section and shift."""
    from hrms_addon.hrms_addon import excellence

    s = settings()
    start, end = getdate(start), getdate(end)
    t = scope_totals(scope_filters(start, end, company, branch, section, shift))
    sections = excellence.sections_in(company, branch, section)
    heads = headcount(company, branch, section)
    labour = {row.name: row.labour_type for row in sections}
    people = sum(heads.values())
    direct = sum(count for name, count in heads.items() if labour.get(name) == rules.DIRECT)
    gone = exits(start, end, company, branch, section)
    roster = roster_rows([row.name for row in sections], start, end)
    supervisors = {row["employee"] for row in roster if not shift or row["shift"] in (shift, rules.BOTH)}
    logs = log_counts(start, end, company, branch, section, shift)
    skills = competency(company, branch, section)
    due, _idle = due_shifts(start, end, company, branch, section, shift, s)
    facts = {
        "totals": t,
        "headcount": people,
        "establishment": sum(establishment(sections, end).values()),
        "direct_share": direct / float(people) if people else None,
        "coverage": coverage(company, branch, section),
        "competency": (sum(value[0][0] for value in skills.values()), sum(value[0][1] for value in skills.values())),
        "critical": (sum(value[1][0] for value in skills.values()), sum(value[1][1] for value in skills.values())),
        "due_reports": due,
        "reported": min(t["shifts"], due) if due else t["shifts"],
        "sessions": sum(logs.get(kind, 0) for kind in rules.COACHING_TYPES),
        "supervisors": len(supervisors),
        "weeks": ((end - start).days + 1) / 7.0,
        "pulse": pulse(end, company, branch, section),
        "exits": sum(value[0] for value in gone.values()),
        "voluntary_exits": sum(value[1] for value in gone.values()),
        "months": ((end - start).days + 1) / 30.4,
        "recognitions": logs.get(rules.RECOGNITION, 0),
        "suggestions": logs.get(rules.SUGGESTION, 0),
        "implemented": logs.get(rules.IMPLEMENTED, 0),
        "safety_trainings": logs.get(rules.SAFETY_TRAINING, 0),
        "can_read_cases": bool(frappe.has_permission(CASE, "read")),
    }
    facts.update(intervention_facts(start, end, company, branch, section))
    facts.update(case_facts(start, end, company, branch, section, shift, s))
    facts.update(grievance_facts(company, branch, section, s))
    return facts, s


# ── The supervisors ───────────────────────────────────────────────────
def supervisor_rows(start, end, company=None, branch=None, section=None, shift=None):
    """Each supervisor on the roster in the period, or who ran a shift in it:
    their production score from their shifts' totals, the eight parts of
    their people index, their development focus and HR's next step."""
    from hrms_addon.hrms_addon import excellence

    s = settings()
    start, end = getdate(start), getdate(end)
    by_supervisor = grouped(scope_filters(start, end, company, branch, section, shift), ("supervisor",))
    sections = excellence.sections_in(company, branch, section, reporting=True)
    roster = roster_rows([row.name for row in sections], start, end)
    last = min(end, getdate(add_days(today(), -1)))
    working = int(rules._num(s["shifts_per_week"]) // 2) or 6
    slots = {}
    for row in roster:
        if shift and row["shift"] not in (shift, rules.BOTH):
            continue
        mine = slots.setdefault(row["employee"], {"sections": set(), "shifts": set(), "due": 0})
        mine["sections"].add(row["section"])
        mine["shifts"].add(row["shift"])
        mine["due"] += rules.working_days(row["from"], min(row["to"], last), working) * (
            2 if row["shift"] == rules.BOTH and not shift else 1)
    people = sorted(set(key for key in by_supervisor if key) | set(slots))
    if not people:
        return [], s
    names = dict(frappe.get_all("Employee", filters={"name": ["in", people]}, fields=["name", "employee_name"],
                                as_list=True))
    conduct = {}
    for row in cases_between(start, end, company, branch, section):
        if row.cause == rules.INADEQUATE_SUPERVISION and row.supervisor_on_shift:
            conduct[row.supervisor_on_shift] = conduct.get(row.supervisor_on_shift, 0) + 1
    logs = log_counts(start, end, company, branch, section, shift, by_supervisor=True)
    grown = log_counts("2000-01-01", end, company, branch, section, None, by_supervisor=True)
    filters = {"supervisor": ["is", "set"]}
    for field, value in (("company", company), ("branch", branch), ("work_section", section)):
        if value:
            filters[field] = value
    actions = {}
    for row in frappe.get_list(INTERVENTION, filters=filters, limit_page_length=0,
                               fields=["name", "raised_on", "target_date", "closed_on", "status", "on_time",
                                       "verified", "result", "pillar", "overdue", "estimated_saving", "supervisor"]):
        actions.setdefault(row.supervisor, []).append(row)
    weeks = ((end - start).days + 1) / 7.0
    found = []
    for person in people:
        t = by_supervisor.get(person) or rules.totals([], s)
        slot = slots.get(person) or {"sections": set(), "shifts": set(), "due": 0}
        mine = logs.get(person, {})
        facts = {"totals": t, "due": slot["due"] or (t["shifts"] if t["shifts"] else 0), "reported": t["shifts"],
                 "conduct_cases": conduct.get(person, 0),
                 "sessions": sum(mine.get(kind, 0) for kind in rules.COACHING_TYPES), "supervisors": 1,
                 "weeks": weeks}
        facts.update(intervention_facts(start, end, rows=actions.get(person, [])))
        index = rules.supervisor_index(facts, s)
        scored = rules.period_scores(t, s)
        sections_run = sorted(slot["sections"]) or []
        found.append({
            "supervisor": person, "supervisor_name": names.get(person),
            "sections": ", ".join(rules.section_label(name) for name in sections_run),
            "section": sections_run[0] if sections_run else None,
            "shift": ", ".join(sorted(slot["shifts"])) if slot["shifts"] else "",
            "shifts": t["shifts"], "due": facts["due"], "score": scored["score"], "score_status": scored["status"],
            "weakest": rules.FACTOR_LABELS.get(scored["weakest"], ""), "next_step": scored["weakest_action"],
            "parts": index["parts"], "index": index["index"], "status": index["status"], "band": index["band"],
            "focus": index["focus"], "open_actions": facts["interventions_open"],
            "development": sum(grown.get(person, {}).get(kind, 0) for kind in rules.DEVELOPMENT_TYPES),
            "money_lost": t["waste_value"] + t["complaint_value"], "incidents": t["safety_incidents"],
            "not_wearing": t["not_wearing"], "attendance": rules.ratio(t["staff_on_shift"], t["staff_planned"]),
            "ppe": rules.ratio(t["wearing_ppe"], t["staff_on_shift"]),
        })
    return found, s


# ── The sections, as the workbook's HR Excellence by section ──────────
def section_rows(start, end, company=None, branch=None, shift=None, week=None):
    """Each active section with the fourteen indicators, the signals that occur
    together and the intervention to look at first."""
    from hrms_addon.hrms_addon import excellence

    s = settings()
    start, end = getdate(start), getdate(end)
    sections = excellence.sections_in(company, branch)
    totals = section_totals(scope_filters(start, end, company, branch, None, shift))
    heads = headcount(company, branch)
    posts = establishment(sections, end)
    skills = competency(company, branch)
    gone = exits(start, end, company, branch)
    cases = {}
    for row in cases_between(start, end, company, branch):
        if not shift or row.shift in (shift, None, ""):
            cases[row.work_section] = cases.get(row.work_section, 0) + 1
    grievances = {}
    for row in grievance_rows(company, branch):
        grievances[row.custom_work_section] = grievances.get(row.custom_work_section, 0) + 1
    found = []
    for section in sections:
        t = totals.get(section.name)
        a = rules.averages(t, s) if t else {}
        skill = skills.get(section.name)
        row = {
            "section": section.name, "section_name": section.section_name, "branch": section.branch,
            "headcount": heads.get(section.name, 0), "establishment": posts.get(section.name, 0),
            "deployment": a.get("deployment"), "attendance": a.get("attendance"),
            "unauthorised": a.get("unauthorised"), "ot_share": a.get("ot_share"),
            "budget_variance": a.get("budget_variance"), "output_per_person": a.get("output_per_person"),
            "ppe": a.get("ppe"), "competency": rules.ratio(*skill[0]) if skill else None,
            "cases": cases.get(section.name, 0), "open_grievances": grievances.get(section.name, 0),
            "exits": gone.get(section.name, (0, 0))[0], "unit": section.unit,
            "score": rules.period_scores(t, s)["score"] if t else None,
            "week_record": _key(section.name, week) if week else None,
        }
        row["variance"] = row["headcount"] - row["establishment"]
        row.update(rules.section_signals(row, s))
        found.append(row)
    return sorted(found, key=lambda row: (-row["count"], row["section"])), s


# ── Downtime, trends and the labour cost flags ────────────────────────
def downtime(start, end, company=None, branch=None, section=None, shift=None, by="downtime_reason"):
    """Downtime of a period by reason (or machine, or section): [{"reason",
    "category", "planned", "minutes", "shifts"}]."""
    filters = scope_filters(start, end, company, branch, section, shift)
    fields = [by, "shift_report", aggregate("SUM", "minutes", "minutes")]
    extra = ["category", "planned"] if by == "downtime_reason" else []
    rows = frappe.get_list(DOWNTIME, filters=filters, fields=fields[:1] + extra + fields[1:],
                           group_by=", ".join([by] + extra + ["shift_report"]), order_by=None, limit_page_length=0)
    found = {}
    for row in rows:
        mine = found.setdefault(row.get(by) or "", {"reason": row.get(by) or "", "category": row.get("category") or "",
                                                     "planned": cint(row.get("planned")), "minutes": 0.0,
                                                     "reports": set()})
        mine["minutes"] += flt(row.get("minutes"))
        mine["reports"].add(row.get("shift_report"))
    return [dict(value, shifts=len(value.pop("reports"))) for value in found.values()]


def week_trend(today_, company=None, branch=None, count=13):
    """The last whole weeks, oldest first: the plant score (its sections'
    average), money lost, attendance, PPE and incidents, from the week
    summaries."""
    s = settings()
    weeks = rules.last_weeks(today_, count)
    filters = {"week": ["in", [label for label, _start, _end in weeks]]}
    for field, value in (("company", company), ("branch", branch)):
        if value:
            filters[field] = value
    rows = frappe.get_list(WEEK, filters=filters, fields=["week", "work_section", "score"] + list(rules.SUMMARY_FIELDS),
                           limit_page_length=0)
    by_week = {}
    for row in rows:
        by_week.setdefault(row.week, []).append(row)
    found = []
    for label, start, end in weeks:
        mine = by_week.get(label, [])
        t = rules.totals(mine, s)
        a = rules.averages(t, s)
        found.append({"week": label, "start": start, "score": rules.plant_score([flt(row.score) for row in mine]),
                      "waste": t["waste_value"], "complaints": t["complaint_value"], "money_lost": t["money_lost"],
                      "attendance": a["attendance"], "ppe": a["ppe"], "incidents": t["safety_incidents"],
                      "ot_share": a["ot_share"], "labour": t["labour_cost"]})
    return found


def month_trend(today_, company=None, branch=None, count=12):
    """The last months, oldest first: the workforce's attendance, unauthorised
    absence, overtime, labour and its cost per kg, cases, grievances, exits
    and recognitions."""
    s = settings()
    months = rules.last_months(today_, count)
    first, last = months[0][1], months[-1][2]
    filters = scope_filters(first, last, company, branch)
    by_month = grouped(filters, ("month", "unit"))
    found = {}
    for (month, unit), t in by_month.items():
        found.setdefault(month, []).append(t)
    case_months, grievance_months, exit_months, recognition_months = {}, {}, {}, {}
    for row in cases_between(first, last, company, branch):
        key = str(row.incident_date)[:7]
        case_months[key] = case_months.get(key, 0) + 1
    filters_g = {"date": ["between", [str(first), str(last)]]}
    if branch:
        filters_g["custom_branch"] = branch
    for row in frappe.get_list(GRIEVANCE, filters=filters_g, fields=["date"], limit_page_length=0):
        key = str(row.date)[:7]
        grievance_months[key] = grievance_months.get(key, 0) + 1
    for row in frappe.get_list("Employee", filters=dict(_employee_filters(company, branch),
                                                        relieving_date=["between", [str(first), str(last)]]),
                               fields=["relieving_date"], limit_page_length=0):
        key = str(row.relieving_date)[:7]
        exit_months[key] = exit_months.get(key, 0) + 1
    for row in frappe.get_list(PEOPLE_LOG, filters=dict(_log_filters(first, last, company, branch),
                                                        log_type=rules.RECOGNITION),
                               fields=["log_date"], limit_page_length=0):
        key = str(row.log_date)[:7]
        recognition_months[key] = recognition_months.get(key, 0) + 1
    rows = []
    for label, start, _end in months:
        key = str(start)[:7]
        t = rules.add_totals(*found.get(key, []))
        a = rules.averages(t, s)
        rows.append({"month": label, "key": key, "attendance": a["attendance"], "unauthorised": a["unauthorised"],
                     "ot_hours": t["ot_hours"] if t["shifts"] else None, "ot_share": a["ot_share"],
                     "labour": t["labour_cost"] if t["shifts"] else None,
                     "labour_per_kg": rules._per(t, "Kg", "labour", "actual"), "cases": case_months.get(key, 0),
                     "grievances": grievance_months.get(key, 0), "exits": exit_months.get(key, 0),
                     "recognitions": recognition_months.get(key, 0), "money_lost": t["money_lost"]})
    return rows


def labour_view(start, end, company=None, branch=None):
    """Each section's week against the week before it, with the workbook's four
    flags: {section: {"now", "before", "flags"}}."""
    s = settings()
    start, end = getdate(start), getdate(end)
    days = (end - start).days + 1
    now = section_totals(scope_filters(start, end, company, branch))
    before = section_totals(scope_filters(add_days(start, -days), add_days(start, -1), company, branch))
    return {section: {"now": t, "before": before.get(section), "flags": rules.labour_flags(t, before.get(section), s)}
            for section, t in now.items()}


# ── The interventions' KPIs, read every Monday ────────────────────────
def read_kpis(day=None):
    """Each open intervention's KPI for the week just ended, from the
    summaries of its section (else its plant), as an Auto reading: its
    baseline and latest follow."""
    s = settings()
    monday = rules.week_start(day or today())
    start, end = add_days(monday, -7), add_days(monday, -1)
    rows = frappe.get_all(INTERVENTION, filters={"status": ["not in", list(rules.DONE)], "kpi": ["is", "set"]},
                          fields=["name", "kpi", "work_section", "branch", "company", "shift", "supervisor"],
                          limit_page_length=0)
    memo = {}
    for row in rows:
        shift = row.shift if row.shift in rules.SHIFTS else None
        scope = (row.company, row.branch, row.work_section, shift, row.supervisor if row.kpi
                 == "Supervisor People Score" else None)
        if scope not in memo:
            memo[scope] = _kpi_facts(start, end, scope, s)
        value = rules.kpi_value(row.kpi, memo[scope], s)
        if value is None:
            continue
        doc = frappe.get_doc(INTERVENTION, row.name)
        if any(getdate(reading.reading_date) == getdate(end) and reading.source == rules.AUTO
               for reading in doc.get("kpi_readings") or []):
            continue
        doc.append("kpi_readings", {"reading_date": end, "value": round(flt(value), 4), "source": rules.AUTO,
                                    "note": rules.week_label(end)})
        doc.flags.ignore_permissions = True
        _save_quietly(doc)
    frappe.db.commit()


def _save_quietly(doc):
    try:
        doc.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="HR Intervention %s: KPI reading" % doc.name)


def _kpi_facts(start, end, scope, s):
    company, branch, section, shift, supervisor = scope
    t = scope_totals(scope_filters(start, end, company, branch, section, shift))
    facts = {"totals": t, "coverage": coverage(company, branch, section),
             "open_grievances": grievance_facts(company, branch, section, s)["open_grievances"],
             "pulse": pulse(end, company, branch, section)}
    facts["repeats"] = case_facts(start, end, company, branch, section, shift, s)["repeats"]
    heads = headcount(company, branch, section)
    facts["headcount"] = sum(heads.values())
    facts["exits"] = sum(value[0] for value in exits(start, end, company, branch, section).values())
    if supervisor:
        rows, _s = supervisor_rows(start, end, company, branch, section, shift)
        facts["people_score"] = next((row["index"] for row in rows if row["supervisor"] == supervisor), None)
    else:
        facts["people_score"] = rules.supervisor_index({"totals": t, "due": 0}, s)["index"]
    return facts
