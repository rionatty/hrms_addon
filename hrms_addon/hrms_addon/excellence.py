# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence on the site; excellence_rules.py has the rules.

  Work Section     named "Section - Plant". Its standards are dated rows:
                   changing the figures in force today keeps the earlier
                   ones. Its roster is dated too (Section Assignment). Its
                   labour rates can be worked out from its people's pay
  Employee         a section belongs to a plant: moved to another plant, an
                   employee's section is cleared
  Shift Report     one per section, shift and day, held unique by its key;
                   filled from its section's standard and roster on that
                   date, its crew from the clock (excellence_clock.py), its
                   downtime events and output lines; scored; on submit and
                   cancel its section's day and week summaries are written
                   again (excellence_summary.py)
  People Log,      the week and the plant from the section; who took part;
  HR Intervention  an intervention's KPI read week by week, its baseline and
                   latest from the readings
  Disciplinary     the route its cause takes, the day a penalty is due by,
  Case             the legal flags (hooks.py, on validate), its case type,
                   employment and the supervisor on shift
  daily            interventions turning overdue told to their owner once;
                   open cases' legal flags brought up to date with their
                   suspension history; yesterday's day sheets made
  weekly           Monday: last week's summaries checked, the
                   interventions' KPIs read, the HR Partner Briefs sent

The plant's day sheet is excellence_sheet.py; the summaries and what the
scorecards read, excellence_summary.py; the executive page,
excellence_page.py; the brief, excellence_brief.py.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import excellence_rules as rules

SETTINGS = "Manufacturing Excellence Settings"
SECTION, SHIFT_REPORT, PEOPLE_LOG = "Work Section", "Shift Report", "People Log"
INTERVENTION, CASE, GRIEVANCE = "HR Intervention", "Disciplinary Case", "Employee Grievance"
MACHINE, REASON, ORDER = "Machine", "Downtime Reason", "Plant Order"
EMPLOYEE_SECTION = "custom_work_section"
REQUIREMENT = "Employee Training Requirement"


def settings():
    try:
        stored = frappe.get_cached_doc(SETTINGS).as_dict()
    except Exception:
        stored = {}
    return rules.settings_from(stored)


def settings_validate(doc):
    for message in rules.settings_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(SETTINGS))


def setup_on_migrate():
    """The Manufacturing Excellence Officer's role."""
    from hrms_addon.hrms_addon import workflows

    workflows.grant_on_migrate(rules, "Manufacturing Excellence roles")


@frappe.whitelist()
def guide():
    """The KPI dictionary, the guide and the rules HR keeps to: the settings'
    and the executive page's Guide."""
    return {"kpis": [list(row) for row in rules.KPI_DICTIONARY], "guide": [list(row) for row in rules.GUIDE],
            "governance": [list(row) for row in rules.GOVERNANCE]}


# ── Work Section ──────────────────────────────────────────────────────
def section_autoname(doc):
    doc.section_name = (doc.section_name or "").strip()
    doc.name = "%s - %s" % (doc.section_name, doc.branch)


def section_validate(doc):
    """The standard in force today is what the section's own figures show: a
    change to them is kept as a standard from today, the earlier ones stay."""
    doc.section_name = (doc.section_name or "").strip()
    typed = {field: doc.get(field) for field in rules.STANDARD_FIELDS}
    rows = [_standard_row(row) for row in doc.get("standards") or []]
    before = doc.get_doc_before_save() if not doc.is_new() else None
    edited = before is not None and any(flt(before.get(field)) != flt(doc.get(field))
                                        for field in rules.STANDARD_FIELDS)
    if not rows or edited:
        rows, changed = rules.standards_after_edit(rows, typed, today())
        if changed:
            doc.set("standards", [])
            for row in sorted(rows, key=lambda row: getdate(row["effective_from"])):
                doc.append("standards", row)
    current = rules.standard_on([_standard_row(row) for row in doc.get("standards") or []], today(), typed)
    for field in rules.STANDARD_FIELDS:
        doc.set(field, current.get(field))
    for message in rules.section_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(SECTION))
    if doc.department and doc.company:
        owner = frappe.db.get_value("Department", doc.department, "company")
        if owner and owner != doc.company:
            frappe.throw(_("{0} belongs to {1}, not {2}.").format(doc.department, owner, doc.company),
                         title=_(SECTION))


def _standard_row(row):
    data = dict(row) if isinstance(row, dict) else row.as_dict()
    found = {field: data.get(field) for field in rules.STANDARD_FIELDS}
    found["effective_from"] = data.get("effective_from")
    found["note"] = data.get("note")
    return found


def section_standard(section, day):
    """The standard of a section (a Work Section document) in force on a day."""
    rows = [_standard_row(row) for row in section.get("standards") or []]
    fallback = {field: section.get(field) for field in rules.STANDARD_FIELDS}
    return rules.standard_on(rows, day, fallback)


def roster(section):
    """A section's dated roster, as rows the rules read; the roster from
    before dates counts from the beginning while there is no dated one."""
    rows = [row.as_dict() for row in section.get("assignments") or []]
    if not rows:
        rows = [{"employee": row.employee, "role": rules.SUPERVISOR, "shift": row.shift, "from_date": "2000-01-01",
                 "to_date": None} for row in section.get("supervisors") or [] if cint(row.active)]
    return rows


@frappe.whitelist()
def rates_from_payroll(section):
    """The section's labour cost per person-shift and per overtime hour from
    its people's salary structures (their pay without overtime) over the
    paid days. Kept as a standard from today."""
    from hrms_addon.hrms_addon import excellence_clock

    doc = frappe.get_doc(SECTION, section)
    doc.check_permission("write")
    s = settings()
    people = frappe.get_all("Employee", filters={EMPLOYEE_SECTION: section, "status": "Active"}, pluck="name")
    if not people:
        frappe.throw(_("Nobody is in {0} yet: set the section on its employees first.").format(section),
                     title=_(SECTION))
    rates = excellence_clock.day_rates(people, today(), s)
    paid = [rate for rate in rates.values() if rate]
    if not paid:
        frappe.throw(_("None of {0}'s people has a salary structure assigned.").format(section), title=_(SECTION))
    rate = round(sum(paid) / len(paid), 2)
    doc.labour_rate, doc.overtime_rate = rate, rules.overtime_rate_of(rate, s)
    doc.rates_note = _("{0} of {1} people with a salary structure; their monthly pay without overtime over {2} paid "
                       "days. Overtime at {3} times the hour of {4} hours.").format(
        len(paid), len(people), rules._plain(s["paid_days"]), rules._plain(s["ot_multiplier"]),
        rules._plain(s["ot_base_hours"]))
    doc.save()
    return {"labour_rate": doc.labour_rate, "overtime_rate": doc.overtime_rate, "note": doc.rates_note}


@frappe.whitelist()
def section_defaults(section, shift=None, report_date=None):
    """What a new Shift Report takes from its section on its date."""
    doc = frappe.get_cached_doc(SECTION, section)
    doc.check_permission("read")
    day = report_date or today()
    standard = section_standard(doc, day)
    rows = roster(doc)
    return {"target": standard.get("target_per_shift"), "machines": standard.get("machines"),
            "staff_planned": standard.get("crew_per_shift"),
            "supervisor": rules.lead_on(rows, day, shift) if shift else None,
            "production_officer": rules.lead_on(rows, day, shift, rules.PRODUCTION_OFFICER) if shift else None}


def employee_validate(doc, method=None):
    """A section is in one plant: an employee moved to another plant loses it."""
    section = doc.get(EMPLOYEE_SECTION)
    if not section or not doc.get("branch"):
        return
    plant = frappe.db.get_value(SECTION, section, "branch")
    if plant and plant != doc.branch:
        doc.set(EMPLOYEE_SECTION, None)
        frappe.msgprint(_("{0} is a section of {1}, so it was taken off. Pick one of {2}'s sections.").format(
            section, plant, doc.branch), alert=True)


def machine_validate(doc):
    doc.machine_code = (doc.machine_code or "").strip()


def order_validate(doc):
    if doc.get("finishing_section"):
        doc.branch, doc.company, doc.unit = frappe.db.get_value(SECTION, doc.finishing_section,
                                                                ["branch", "company", "unit"])
    for message in rules.order_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(ORDER))


# ── Shift Report ──────────────────────────────────────────────────────
def shift_key(doc):
    return "%s|%s|%s" % (doc.work_section, getdate(doc.report_date), doc.shift)


def shift_validate(doc):
    s = settings()
    if getdate(doc.report_date) > getdate(today()):
        frappe.throw(_("A Shift Report is for a shift that has been worked."), title=_(SHIFT_REPORT))
    section = frappe.get_cached_doc(SECTION, doc.work_section)
    standard = section_standard(section, doc.report_date)
    doc.branch, doc.company, doc.unit = section.branch, section.company, section.unit
    for field, value in (("target", standard.get("target_per_shift")), ("machines", standard.get("machines")),
                         ("staff_planned", standard.get("crew_per_shift"))):
        if doc.get(field) in (None, ""):
            doc.set(field, value)
    if doc.get("machines_running") in (None, ""):
        doc.machines_running = doc.machines
    rows = roster(section)
    if not doc.supervisor:
        doc.supervisor = rules.lead_on(rows, doc.report_date, doc.shift)
    if not doc.get("production_officer"):
        doc.production_officer = rules.lead_on(rows, doc.report_date, doc.shift, rules.PRODUCTION_OFFICER)
    # a supervisor taken from the roster here comes after Frappe fetched the name
    doc.supervisor_name = frappe.db.get_value("Employee", doc.supervisor, "employee_name") if doc.supervisor else None
    outputs, downtime, crew = doc.get("outputs") or [], doc.get("downtime") or [], doc.get("crew") or []
    if outputs:
        doc.actual_output = sum(flt(line.good_qty) for line in outputs)
        doc.waste_qty = sum(flt(line.waste_qty) for line in outputs)
        doc.waste_value = sum(flt(line.waste_value) for line in outputs)
    minutes = sum(flt(row.minutes) for row in downtime) if downtime else None
    counted = rules.crew_totals([row.as_dict() for row in crew]) if crew else None
    if counted:
        doc.staff_planned, doc.staff_on_shift = counted["planned"], counted["on_shift"]
        doc.unauthorised_absent, doc.not_marked = counted["unauthorised"], counted["not_marked"]
        doc.late_arrivals, doc.early_departures = counted["late"], counted["early"]
        doc.ot_hours = round(counted["ot_hours"], 2)
        doc.safety_incidents, doc.near_misses = counted["incidents"], counted["near_misses"]
        if counted["no_ppe"]:
            doc.wearing_ppe = counted["on_shift"] - counted["no_ppe"]
    entry = doc.as_dict()
    entry["has_downtime_rows"] = bool(downtime)
    checked = dict(entry)
    if doc.get("plant_day_sheet") and not crew and not cint(doc.staff_on_shift):
        # a day sheet's people come from the clock: PPE is checked against them once fetched
        checked["wearing_ppe"] = checked["unauthorised_absent"] = 0
    for message in rules.entry_errors(checked):
        frappe.throw(_(message), title=_(SHIFT_REPORT))
    if doc.docstatus < 2:
        doc.shift_key = shift_key(doc)
        clash = frappe.db.get_value(SHIFT_REPORT, {"shift_key": doc.shift_key, "name": ["!=", doc.name or ""]}, "name")
        if clash:
            frappe.throw(_("The {0} shift of {1} on {2} is already in {3}.").format(
                doc.shift, doc.work_section, frappe.format_value(doc.report_date, {"fieldtype": "Date"}), clash),
                title=_(SHIFT_REPORT))
    doc.week = rules.week_label(doc.report_date)
    figures = rules.shift_figures(entry, standard, s, crew=counted, downtime_minutes=minutes)
    for key in rules.FACTOR_KEYS:
        doc.set("factor_" + key, round(figures["factors"][key], 1))
    for field in ("machine_hours", "hours_lost", "not_wearing", "regular_labour", "ot_cost", "required_crew",
                  "labour_budget", "absence_cost", "score", "status", "absent"):
        doc.set(field, figures[field])
    doc.labour_cost = figures["labour_cost"]
    doc.labour_per_unit = figures["labour_per_unit"] or 0
    doc.output_per_person = figures["output_per_person"] or 0
    for field, key in (("uptime", "uptime"), ("achievement", "achievement"), ("attendance_rate", "attendance"),
                       ("ppe_rate", "ppe_rate"), ("adequacy", "adequacy")):
        doc.set(field, round(100 * (figures[key] or 0), 1))
    doc.weakest_area = rules.FACTOR_LABELS[figures["weakest"]]
    doc.weakest_action = figures["weakest_action"]
    shares = rules.allocate([line.as_dict() for line in outputs], doc.labour_cost, doc.ot_hours, doc.ot_cost,
                            doc.complaint_value)
    for line, share in zip(outputs, shares):
        line.labour_share, line.ot_hours_share = share["labour"], share["ot_hours"]
        line.ot_cost_share, line.complaint_share = share["ot_cost"], share["complaints"]
        line.report_date, line.work_section, line.branch = doc.report_date, doc.work_section, doc.branch
    doc.title = "%s %s %s" % (doc.work_section, doc.report_date, doc.shift)


def shift_on_update(doc):
    """A draft day sheet shows what its shift reports work out."""
    if doc.get("plant_day_sheet"):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.mirror(doc)


def shift_on_submit(doc):
    from hrms_addon.hrms_addon import excellence_summary

    excellence_summary.write_shift(doc)
    if doc.get("plant_day_sheet"):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.mirror(doc)


def shift_on_cancel(doc):
    """Its summaries go, and its key with them: an amendment takes the key."""
    from hrms_addon.hrms_addon import excellence_summary

    excellence_summary.remove_shift(doc)
    doc.db_set("shift_key", None, update_modified=False)


def shift_on_trash(doc):
    rows = frappe.get_all("Plant Day Sheet Row", filters={"shift_report": doc.name}, pluck="name")
    for name in rows:
        frappe.db.set_value("Plant Day Sheet Row", name, "shift_report", None, update_modified=False)


@frappe.whitelist()
def fetch_crew(name):
    """The shift's crew from the clock, on the Shift Report."""
    from hrms_addon.hrms_addon import excellence_clock

    doc = frappe.get_doc(SHIFT_REPORT, name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft shift report takes its crew from the clock."), title=_(SHIFT_REPORT))
    excellence_clock.fill(doc)
    doc.save()
    return {"planned": doc.staff_planned, "on_shift": doc.staff_on_shift, "not_marked": doc.not_marked}


# ── People Log and HR Intervention ────────────────────────────────────
def _place(doc, employee_field):
    """The plant and company from the section, else the employee's."""
    if not doc.get("work_section") and doc.get(employee_field):
        doc.work_section = frappe.db.get_value("Employee", doc.get(employee_field), EMPLOYEE_SECTION)
    if doc.get("work_section"):
        doc.branch, doc.company = frappe.db.get_value(SECTION, doc.work_section, ["branch", "company"])
    elif doc.get(employee_field):
        doc.branch, doc.company = frappe.db.get_value("Employee", doc.get(employee_field), ["branch", "company"])
    if not doc.get("company"):
        doc.company = (frappe.defaults.get_user_default("Company")
                       or frappe.db.get_single_value("Global Defaults", "default_company"))
    if not doc.get("company"):
        frappe.throw(_("Pick the section."), title=_(doc.doctype))


def log_validate(doc):
    _place(doc, "employee" if doc.get("employee") else "supervisor")
    doc.week = rules.week_label(doc.log_date)
    if not doc.get("recorded_by"):
        doc.recorded_by = frappe.session.user
    if doc.log_type == rules.PULSE and not doc.get("work_section"):
        frappe.throw(_("A pulse survey is a section's: pick the section."), title=_(PEOPLE_LOG))
    for message in rules.log_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(PEOPLE_LOG))
    attendees = doc.get("attendees") or []
    if attendees:
        doc.participants = sum(1 for row in attendees if cint(row.get("attended", 1)))


def intervention_validate(doc):
    _place(doc, "supervisor")
    doc.week = rules.week_label(doc.raised_on)
    if doc.status in rules.DONE and not doc.get("closed_on"):
        doc.closed_on = today()
    if doc.status not in rules.DONE:
        doc.closed_on = None
    _typed_readings(doc)
    readings = [row.as_dict() for row in doc.get("kpi_readings") or []]
    if readings:
        baseline, latest = rules.readings_baseline_latest(readings)
        doc.baseline = baseline
        if latest is not None:
            doc.latest = latest
    if doc.get("section_week") and not doc.get("signal_period"):
        doc.signal_period = frappe.db.get_value("Section Week Summary", doc.section_week, "week")
    for message in rules.intervention_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(INTERVENTION))
    _intervention_state(doc, today())


def _typed_readings(doc):
    """A baseline or latest value typed by hand is kept as a Manual reading:
    the readings are the KPI's history, the baseline the first of them."""
    if not doc.get("kpi"):
        return
    readings = doc.get("kpi_readings") or []
    new = doc.is_new()
    if doc.get("baseline") not in (None, "") and not readings and (new or doc.has_value_changed("baseline")):
        doc.append("kpi_readings", {"reading_date": doc.raised_on, "value": flt(doc.baseline),
                                    "source": rules.MANUAL, "note": _("Baseline")})
    if doc.get("latest") not in (None, "") and (new or doc.has_value_changed("latest")):
        day = getdate(today())
        same = [row for row in (doc.get("kpi_readings") or [])[1:] if getdate(row.reading_date) == day
                and row.source == rules.MANUAL]
        if same:
            same[-1].value = flt(doc.latest)
        else:
            doc.append("kpi_readings", {"reading_date": day, "value": flt(doc.latest), "source": rules.MANUAL})


def _intervention_state(doc, day):
    state = rules.intervention_state(doc.as_dict(), day)
    doc.change = state["change"] or 0
    doc.result = state["result"] or ""
    doc.days_open = state["days_open"] or 0
    doc.overdue = state["overdue"]
    doc.on_time = state["on_time"]
    return state


# ── Disciplinary Case ─────────────────────────────────────────────────
def case_validate(doc, method=None):
    """The route the cause takes, the day a penalty is due by, the legal
    flags; the case type, the employment and the supervisor on shift."""
    s = settings()
    if not doc.get("aware_on"):
        doc.aware_on = getdate(doc.creation) if doc.get("creation") else today()
    if not doc.get("case_type"):
        doc.case_type = rules.CASE_TYPES[0]
    if doc.get("employee"):
        found = frappe.db.get_value("Employee", doc.employee, [EMPLOYEE_SECTION, "employment_type"], as_dict=True) \
            or {}
        if not doc.get("work_section"):
            doc.work_section = found.get(EMPLOYEE_SECTION)
        doc.employment = rules.CASUAL if "casual" in (found.get("employment_type") or "").lower() else rules.PERMANENT
    if doc.get("work_section") and doc.get("shift") and not doc.get("supervisor_on_shift"):
        section = frappe.get_cached_doc(SECTION, doc.work_section)
        doc.supervisor_on_shift = rules.lead_on(roster(section), doc.get("incident_date") or today(), doc.shift)
    if doc.get("supervisor_on_shift"):
        doc.supervisor_on_shift_name = frappe.db.get_value("Employee", doc.supervisor_on_shift, "employee_name")
    doc.suggested_route = rules.route_for(doc.get("cause"), doc.get("severity"))
    doc.penalty_due_by = rules.penalty_due_by(doc.aware_on, s)
    flags = rules.case_flags(doc.as_dict(), today(), s, _suspended_before(doc, s))
    was = set((doc.get("legal_flags") or "").splitlines())
    doc.legal_flags = "\n".join(flags)
    fresh = [flag for flag in flags if flag not in was]
    if fresh:
        frappe.msgprint("<br>".join(_(flag) for flag in fresh), title=_("Legal Flags"), indicator="orange")


def _suspended_before(doc, s):
    if not doc.get("suspension_from") or not doc.get("employee"):
        return 0
    others = frappe.get_all(CASE, filters={"employee": doc.employee, "docstatus": ["<", 2],
                                           "suspension_from": ["is", "set"], "name": ["!=", doc.name or ""]},
                            fields=["name", "suspension_from", "suspension_days"])
    return rules.suspended_before(others, doc.suspension_from, s, exclude=doc.name)


# ── One section on the other modules' documents ──────────────────────
def fill_section(doc, method=None):
    """An Overtime Request's section as a Work Section, beside the text it
    always had: the section named, else the one most of its people are in.
    Each line takes its employee's (a fetch, as the Daily Production Report
    takes its supervisor's)."""
    lines = doc.get("employees") or []
    named = [line.employee for line in lines if line.get("employee") and not line.get("work_section")]
    sections = dict(frappe.get_all("Employee", filters={"name": ["in", named]},
                                   fields=["name", EMPLOYEE_SECTION], as_list=True)) if named else {}
    for line in lines:
        if line.get("employee") and not line.get("work_section"):
            line.work_section = sections.get(line.employee)
    if not doc.get("work_section"):
        doc.work_section = (_section_named(doc.get("section"), doc.get("branch"))
                            or _most_common([line.get("work_section") for line in lines]))


def _section_named(text, branch):
    text = (text or "").strip()
    if not text:
        return None
    filters = {"section_name": text}
    if branch:
        filters["branch"] = branch
    return frappe.db.get_value(SECTION, filters, "name")


def _most_common(values):
    counts = {}
    for value in values:
        if value:
            counts[value] = counts.get(value, 0) + 1
    return max(sorted(counts), key=lambda value: counts[value]) if counts else None


# ── Every day, every Monday ───────────────────────────────────────────
def daily():
    """Interventions turning overdue told to their owner once (only those
    whose flag changes are written); open cases' legal flags worked out with
    each employee's suspension history; yesterday's day sheets made."""
    from hrms_addon.hrms_addon import excellence_sheet, people

    day = today()
    for row in frappe.get_all(INTERVENTION, filters={"status": ["not in", list(rules.DONE)],
                                                     "target_date": ["is", "set"]},
                              fields=["name", "raised_on", "target_date", "status", "closed_on", "overdue",
                                      "responsible", "observation"], limit_page_length=0):
        state = rules.intervention_state(row, day)
        if state["overdue"] == cint(row.overdue):
            continue
        frappe.db.set_value(INTERVENTION, row.name, "overdue", state["overdue"], update_modified=False)
        if state["overdue"] and row.responsible:
            people.notify([row.responsible], INTERVENTION, row.name,
                          _("HR intervention past its target date: {0}").format(row.observation))
    refresh_case_flags(day)
    excellence_sheet.make_day_sheets(add_days(day, -1))


def refresh_case_flags(day=None):
    """The open cases' legal flags as they stand, the suspension cap counted
    with the employee's other cases (read once for all of them)."""
    s = settings()
    day = day or today()
    cases = frappe.get_all(CASE, filters={"docstatus": 0, "aware_on": ["is", "set"]},
                           fields=["name", "employee", "aware_on", "decided_on", "outcome", "status", "cause", "severity",
                                   "suspension_days", "suspension_from", "legal_flags"], limit_page_length=0)
    if not cases:
        return
    employees = sorted({case.employee for case in cases if case.employee})
    since = add_days(day, -int(s["suspension_window_days"]) * 2)
    history = rules.suspension_history(frappe.get_all(
        CASE, filters={"docstatus": ["<", 2], "suspension_from": [">=", since], "employee": ["in", employees]},
        fields=["name", "employee", "suspension_from", "suspension_days"], limit_page_length=0)) if employees else {}
    for case in cases:
        before = rules.suspended_before(history.get(case.employee, []), case.suspension_from, s, exclude=case.name) \
            if case.suspension_from else 0
        flags = "\n".join(rules.case_flags(case, day, s, before))
        if flags != (case.legal_flags or ""):
            frappe.db.set_value(CASE, case.name, "legal_flags", flags, update_modified=False)


def weekly():
    """Monday morning: last week's summaries checked, the interventions' KPIs
    read, the HR Partner Briefs built and sent."""
    from hrms_addon.hrms_addon import excellence_brief, excellence_summary

    excellence_summary.check_last_week()
    excellence_summary.read_kpis()
    excellence_brief.monday()


# ── What the scorecards read (excellence_summary.py) ─────────────────
def sections_in(company=None, branch=None, section=None, reporting=False):
    filters = {"is_active": 1}
    if company:
        filters["company"] = company
    if branch:
        filters["branch"] = branch
    if section:
        filters["name"] = section
    if reporting:
        filters["shift_reports"] = 1
    # read as the user: one held to a plant counts that plant's sections alone
    return frappe.get_list(SECTION, filters=filters, fields=["name", "branch", "labour_type", "unit",
                                                            "approved_establishment", "section_name"],
                          order_by="section_name asc", limit_page_length=0)


def shift_rows(start, end, company=None, branch=None, section=None, shift=None, supervisor=None):
    """The submitted shifts of a period as their Section Day Summary rows,
    which rules.totals() sums."""
    from hrms_addon.hrms_addon import excellence_summary

    return excellence_summary.day_rows(start, end, company, branch, section, shift, supervisor)


def period_facts(start, end, company=None, branch=None, section=None, shift=None):
    from hrms_addon.hrms_addon import excellence_summary

    return excellence_summary.period_facts(start, end, company, branch, section, shift)


def supervisor_rows(start, end, company=None, branch=None, section=None, shift=None):
    from hrms_addon.hrms_addon import excellence_summary

    return excellence_summary.supervisor_rows(start, end, company, branch, section, shift)
