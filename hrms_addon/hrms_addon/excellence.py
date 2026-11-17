# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence on the site; excellence_rules.py has the rules.

  Work Section     named "Section - Plant"; its labour rates can be worked
                   out from its people's pay in the month just ended
  Employee         a section belongs to a plant: moved to another plant, an
                   employee's section is cleared
  Shift Report     one per section, shift and day; filled from its section,
                   then scored. Submitted once checked
  People Log,      the week and the plant from the section; an intervention
  HR Intervention  works out its KPI change, days open, overdue, on time
  Disciplinary     the route its cause takes, the day a penalty is due by
  Case             and the legal flags (hooks.py, on validate)
  daily            interventions turning overdue are told to their owner;
                   open cases' legal flags are brought up to date

period_facts, supervisor_rows and shift_rows feed the scorecards.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import excellence_rules as rules

SETTINGS = "Manufacturing Excellence Settings"
SECTION, SHIFT_REPORT, PEOPLE_LOG = "Work Section", "Shift Report", "People Log"
INTERVENTION, CASE, GRIEVANCE = "HR Intervention", "Disciplinary Case", "Employee Grievance"
EMPLOYEE_SECTION = "custom_work_section"
REQUIREMENT = "Employee Training Requirement"

SHIFT_FIELDS = ["name", "report_date", "shift", "work_section", "branch", "unit", "supervisor", "supervisor_name",
                "target", "actual_output", "housekeeping", "machines", "machines_running", "stop_hours",
                "downtime_reason", "waste_value", "complaint_value", "safety_incidents", "near_misses",
                "staff_planned", "staff_on_shift", "unauthorised_absent", "late_arrivals", "early_departures",
                "wearing_ppe", "ot_hours", "score", "labour_cost", "ot_cost", "labour_budget", "absence_cost",
                "machine_hours", "hours_lost", "required_crew"] + ["factor_" + key for key in rules.FACTOR_KEYS]


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


# ── Work Section ──────────────────────────────────────────────────────
def section_autoname(doc):
    doc.section_name = (doc.section_name or "").strip()
    doc.name = "%s - %s" % (doc.section_name, doc.branch)


def section_validate(doc):
    doc.section_name = (doc.section_name or "").strip()
    for message in rules.section_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(SECTION))
    if doc.department and doc.company:
        owner = frappe.db.get_value("Department", doc.department, "company")
        if owner and owner != doc.company:
            frappe.throw(_("{0} belongs to {1}, not {2}.").format(doc.department, owner, doc.company),
                         title=_(SECTION))


@frappe.whitelist()
def rates_from_payroll(section):
    """The section's labour cost per person-shift and per overtime hour, from
    its people's submitted salary slips in the month just ended: gross pay
    over the people paid over the paid days."""
    doc = frappe.get_doc(SECTION, section)
    doc.check_permission("write")
    s = settings()
    first = getdate(today()).replace(day=1)
    end = add_days(first, -1)
    start = getdate(end).replace(day=1)
    people = frappe.get_all("Employee", filters={EMPLOYEE_SECTION: section}, pluck="name")
    if not people:
        frappe.throw(_("Nobody is in {0} yet: set the section on its employees first.").format(section),
                     title=_(SECTION))
    slips = frappe.get_all("Salary Slip", filters={"employee": ["in", people], "docstatus": 1,
                                                    "end_date": ["between", [start, end]]},
                           fields=["employee", "base_gross_pay"])
    if not slips:
        frappe.throw(_("No submitted salary slip of {0}'s people ends in {1}.").format(
            section, getdate(start).strftime("%B %Y")), title=_(SECTION))
    gross = sum(flt(slip.base_gross_pay) for slip in slips)
    heads = len({slip.employee for slip in slips})
    doc.labour_rate, doc.overtime_rate = rules.labour_rates(gross, heads, s)
    doc.rates_note = _("{0} people paid {1} in {2}, over {3} paid days. Overtime at {4} times the hour of {5}"
                       " hours.").format(heads, frappe.format_value(gross, {"fieldtype": "Currency"}),
                                         getdate(start).strftime("%B %Y"), rules._plain(s["paid_days"]),
                                         rules._plain(s["ot_multiplier"]), rules._plain(s["ot_base_hours"]))
    doc.save()
    return {"labour_rate": doc.labour_rate, "overtime_rate": doc.overtime_rate, "note": doc.rates_note}


@frappe.whitelist()
def section_defaults(section, shift=None):
    """What a new Shift Report takes from its section."""
    doc = frappe.get_cached_doc(SECTION, section)
    doc.check_permission("read")
    return {"target": doc.target_per_shift, "machines": doc.machines, "staff_planned": doc.crew_per_shift,
            "supervisor": rules.lead_supervisor([row.as_dict() for row in doc.supervisors], shift) if shift
            else None}


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


# ── Shift Report ──────────────────────────────────────────────────────
def shift_validate(doc):
    s = settings()
    section = frappe.get_cached_doc(SECTION, doc.work_section)
    doc.branch, doc.company, doc.unit = section.branch, section.company, section.unit
    for field, value in (("target", section.target_per_shift), ("machines", section.machines),
                         ("staff_planned", section.crew_per_shift)):
        if doc.get(field) in (None, ""):
            doc.set(field, value)
    if doc.get("machines_running") in (None, ""):
        doc.machines_running = doc.machines
    if not doc.supervisor:
        doc.supervisor = rules.lead_supervisor([row.as_dict() for row in section.supervisors], doc.shift)
    # a supervisor taken from the roster here comes after Frappe fetched the name
    doc.supervisor_name = frappe.db.get_value("Employee", doc.supervisor, "employee_name") if doc.supervisor else None
    if getdate(doc.report_date) > getdate(today()):
        frappe.throw(_("A Shift Report is for a shift that has been worked."), title=_(SHIFT_REPORT))
    for message in rules.entry_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(SHIFT_REPORT))
    clash = frappe.db.get_value(SHIFT_REPORT, {"work_section": doc.work_section, "report_date": doc.report_date,
                                               "shift": doc.shift, "docstatus": ["<", 2],
                                               "name": ["!=", doc.name or ""]}, "name")
    if clash:
        frappe.throw(_("The {0} shift of {1} on {2} is already in {3}.").format(
            doc.shift, doc.work_section, frappe.format_value(doc.report_date, {"fieldtype": "Date"}), clash),
            title=_(SHIFT_REPORT))
    doc.week = rules.week_label(doc.report_date)
    figures = rules.shift_figures(doc.as_dict(), section.as_dict(), s)
    for key in rules.FACTOR_KEYS:
        doc.set("factor_" + key, round(figures["factors"][key], 1))
    for field in ("machine_hours", "hours_lost", "not_wearing", "regular_labour", "ot_cost", "required_crew",
                  "labour_budget", "absence_cost", "score", "status"):
        doc.set(field, figures[field])
    doc.labour_cost = figures["labour_cost"]
    doc.labour_per_unit = figures["labour_per_unit"] or 0
    doc.output_per_person = figures["output_per_person"] or 0
    for field, key in (("uptime", "uptime"), ("achievement", "achievement"), ("attendance_rate", "attendance"),
                       ("ppe_rate", "ppe_rate"), ("adequacy", "adequacy")):
        doc.set(field, round(100 * (figures[key] or 0), 1))
    doc.weakest_area = rules.FACTOR_LABELS[figures["weakest"]]
    doc.weakest_action = figures["weakest_action"]
    doc.title = "%s %s %s" % (doc.work_section, doc.report_date, doc.shift)


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
    if not 0 <= flt(doc.get("score")) <= 100:
        frappe.throw(_("The score is a percentage, from 0 to 100."), title=_(PEOPLE_LOG))


def intervention_validate(doc):
    _place(doc, "supervisor")
    doc.week = rules.week_label(doc.raised_on)
    if doc.status in rules.DONE and not doc.get("closed_on"):
        doc.closed_on = today()
    if doc.status not in rules.DONE:
        doc.closed_on = None
    for message in rules.intervention_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(INTERVENTION))
    _intervention_state(doc, today())


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
    """The route the cause takes, the day a penalty is due by, the legal flags."""
    s = settings()
    if not doc.get("aware_on"):
        doc.aware_on = getdate(doc.creation) if doc.get("creation") else today()
    if not doc.get("work_section") and doc.get("employee"):
        doc.work_section = frappe.db.get_value("Employee", doc.employee, EMPLOYEE_SECTION)
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


# ── Every day ─────────────────────────────────────────────────────────
def daily():
    """Interventions past their target date are told to their owner once; the
    open cases' legal flags are worked out afresh."""
    from hrms_addon.hrms_addon import people

    day = today()
    for row in frappe.get_all(INTERVENTION, filters={"status": ["not in", list(rules.DONE)]},
                              fields=["name", "raised_on", "target_date", "status", "closed_on", "kpi", "baseline",
                                      "latest", "overdue", "responsible", "observation"]):
        state = rules.intervention_state(row, day)
        if state["overdue"] != cint(row.overdue) or state["days_open"] is not None:
            frappe.db.set_value(INTERVENTION, row.name, {"overdue": state["overdue"],
                                                         "days_open": state["days_open"] or 0},
                                update_modified=False)
        if state["overdue"] and not cint(row.overdue) and row.responsible:
            people.notify([row.responsible], INTERVENTION, row.name,
                          _("HR intervention past its target date: {0}").format(row.observation))
    s = settings()
    for row in frappe.get_all(CASE, filters={"docstatus": 0, "aware_on": ["is", "set"]},
                              fields=["name", "aware_on", "decided_on", "outcome", "status", "cause", "severity",
                                      "suspension_days", "suspension_from", "legal_flags"]):
        flags = "\n".join(rules.case_flags(row, day, s))
        if flags != (row.legal_flags or ""):
            frappe.db.set_value(CASE, row.name, "legal_flags", flags, update_modified=False)


# ── What the scorecards read ──────────────────────────────────────────
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
    return frappe.get_all(SECTION, filters=filters, fields=["name", "branch", "labour_type",
                                                            "approved_establishment"])


def shift_rows(start, end, company=None, branch=None, section=None, shift=None, supervisor=None):
    filters = {"docstatus": ["<", 2], "report_date": ["between", [start, end]]}
    for field, value in (("company", company), ("branch", branch), ("work_section", section), ("shift", shift),
                         ("supervisor", supervisor)):
        if value:
            filters[field] = value
    return frappe.get_list(SHIFT_REPORT, filters=filters, fields=SHIFT_FIELDS, order_by="report_date asc",
                           limit_page_length=0)


def _rosters(names):
    if not names:
        return {}
    found = {}
    for row in frappe.get_all("Work Section Supervisor", filters={"parenttype": SECTION, "parent": ["in", names]},
                              fields=["parent", "employee", "shift", "active", "idx"], order_by="idx asc"):
        found.setdefault(row.parent, []).append(row)
    return found


def _due_days(start, end, s):
    last = min(getdate(end), getdate(add_days(today(), -1)))
    return rules.working_days(start, last, int(rules._num(s["shifts_per_week"]) // 2) or 6)


def _intervention_facts(scope, start, end, s, supervisor=None):
    filters = {}
    if supervisor:
        filters["supervisor"] = supervisor
    elif scope.get("section"):
        filters["work_section"] = scope["section"]
    elif scope.get("branch"):
        filters["branch"] = scope["branch"]
    elif scope.get("company"):
        filters["company"] = scope["company"]
    rows = frappe.get_list(INTERVENTION, filters=filters, limit_page_length=0,
                           fields=["name", "raised_on", "target_date", "closed_on", "status", "on_time", "verified",
                                   "result", "pillar", "overdue", "estimated_saving"])
    due_by = min(getdate(end), getdate(today()))
    due = [row for row in rows if row.target_date and getdate(row.target_date) <= due_by]
    supervision = rules.PILLAR_LABELS["supervision"]
    return {
        "interventions_due": len(due),
        "interventions_on_time": sum(1 for row in due if row.on_time == "Yes"),
        "interventions_closed": sum(1 for row in rows if row.closed_on),
        "interventions_improved": sum(1 for row in rows if cint(row.verified) and row.result == rules.IMPROVED),
        "interventions_open_supervision": sum(1 for row in rows if row.pillar == supervision
                                              and row.status not in rules.DONE),
        "interventions_raised": sum(1 for row in rows if row.raised_on
                                    and getdate(start) <= getdate(row.raised_on) <= getdate(end)),
        "interventions_completed": sum(1 for row in rows if row.closed_on
                                       and getdate(start) <= getdate(row.closed_on) <= getdate(end)),
        "interventions_overdue": sum(1 for row in rows if cint(row.overdue)),
        "savings": sum(flt(row.estimated_saving) for row in rows if cint(row.verified)),
    }


def _log_counts(start, end, sections, shift=None, supervisor=None):
    """{type: entries} in the People Log; an entry with no shift counts for both."""
    filters = {"log_date": ["between", [start, end]]}
    if supervisor:
        filters["supervisor"] = supervisor
    elif sections is not None:
        filters["work_section"] = ["in", sections or [""]]
    counts = {}
    for row in frappe.get_list(PEOPLE_LOG, filters=filters, fields=["log_type", "shift"], limit_page_length=0):
        if not shift or row.shift in (shift, None, ""):
            counts[row.log_type] = counts.get(row.log_type, 0) + 1
    return counts


def _pulse(end, sections):
    filters = {"log_type": rules.PULSE, "log_date": ["between", [add_days(end, -92), end]]}
    if sections is not None:
        filters["work_section"] = ["in", sections or [""]]
    scores = frappe.get_list(PEOPLE_LOG, filters=filters, pluck="score", limit_page_length=0)
    return (sum(flt(score) for score in scores) / len(scores) / 100.0) if scores else None


def _case_facts(start, end, people, s, shift=None):
    if not people:
        return {"cases": 0, "conduct_route": 0, "coaching_route": 0, "non_grievance_cases": 0, "repeats": 0,
                "days_to_resolve": None, "legal_flags": 0, "overdue_cases": 0, "conduct_cases": 0}
    since = rules.add_months(getdate(start), -int(s["lookback_months"]))
    rows = frappe.get_all(CASE, filters={"employee": ["in", people], "docstatus": ["<", 2],
                                         "incident_date": ["between", [since, end]]},
                          fields=["name", "employee", "incident_date", "cause", "severity", "shift", "status",
                                  "aware_on", "decided_on", "outcome", "suspension_days", "suspension_from",
                                  "docstatus", "creation", "legal_flags"])
    day, start, end = getdate(today()), getdate(start), getdate(end)
    window = [row for row in rows if not shift or row.shift in (shift, None, "")]
    period = [row for row in window if start <= getdate(row.incident_date) <= end]
    repeats = 0
    for row in period:
        before = rules.add_months(getdate(row.incident_date), -int(s["lookback_months"]))
        mine = [other for other in rows if other.employee == row.employee
                and before < getdate(other.incident_date) <= getdate(row.incident_date)]
        repeats += len(mine) >= 2
    decided = [row for row in period if row.decided_on]
    days = [(getdate(row.decided_on) - getdate(row.aware_on or row.incident_date)).days for row in decided]
    # an open case's flags as they stand today; a decided one's as its decision left them
    flagged = 0
    for row in rows:
        if row.docstatus == 0 and row.status not in ("Closed", "Cancelled"):
            flagged += bool(rules.case_flags(row, day, s))
        elif row.decided_on and start <= getdate(row.decided_on) <= end:
            flagged += bool((row.legal_flags or "").strip())
    overdue = sum(1 for row in rows if row.docstatus == 0 and row.status not in ("Closed", "Cancelled")
                  and (day - getdate(row.aware_on or row.creation)).days > s["case_days"])
    return {
        "cases": len(period),
        "conduct_route": sum(1 for row in period if rules.is_conduct(row.cause, row.severity)),
        "coaching_route": sum(1 for row in period if row.cause and not rules.is_conduct(row.cause, row.severity)),
        "non_grievance_cases": len(period),
        "repeats": repeats,
        "days_to_resolve": round(sum(days) / float(len(days)), 1) if days else None,
        "legal_flags": flagged,
        "overdue_cases": overdue,
        "conduct_cases": sum(1 for row in period if row.cause == rules.INADEQUATE_SUPERVISION),
    }


def _grievance_facts(people, s):
    if not people:
        return {"open_grievances": 0, "grievances_open_long": 0}
    rows = frappe.get_all(GRIEVANCE, filters={"raised_by": ["in", people], "docstatus": 0},
                          fields=["name", "date", "creation"])
    day = getdate(today())
    return {"open_grievances": len(rows),
            "grievances_open_long": sum(1 for row in rows
                                        if (day - getdate(row.date or row.creation)).days > s["case_days"])}


def _coverage(people):
    if not people:
        return 0, 0
    from hrms_addon.hrms_addon import learning_rules

    rows = frappe.get_all(REQUIREMENT, filters={"employee": ["in", people]},
                          fields=["requirement_type", "status", "completed_on", "valid_until"])
    return learning_rules.coverage_of(rows, today())


def period_facts(start, end, company=None, branch=None, section=None, shift=None):
    """Everything the HR Excellence scorecard weighs, for a period and a
    company, plant, section and shift."""
    s = settings()
    start, end = getdate(start), getdate(end)
    sections = sections_in(company, branch, section)
    names = [row.name for row in sections]
    reporting = [row.name for row in sections_in(company, branch, section, reporting=True)]
    rows = shift_rows(start, end, company, branch, section, shift)
    t = rules.totals(rows, s)
    people = frappe.get_all("Employee", filters={EMPLOYEE_SECTION: ["in", names or [""]], "status": "Active"},
                            fields=["name", EMPLOYEE_SECTION]) if names else []
    labour = {row.name: row.labour_type for row in sections}
    ids = [row.name for row in people]
    gone = frappe.get_all("Employee", filters={EMPLOYEE_SECTION: ["in", names or [""]],
                                               "relieving_date": ["between", [start, end]]},
                          fields=["name", "custom_employee_status"]) if names else []
    rosters = _rosters(names)
    supervisors = {row.employee for parent in rosters.values() for row in parent
                   if cint(row.active) and (not shift or row.shift == shift)}
    shifts = 1 if shift else 2
    logs = _log_counts(start, end, names if (section or branch or company) else None, shift)
    facts = {
        "totals": t,
        "headcount": len(ids),
        "establishment": sum(cint(row.approved_establishment) for row in sections),
        "direct_share": (sum(1 for row in people if labour.get(row.get(EMPLOYEE_SECTION)) == rules.DIRECT)
                         / float(len(people))) if people else None,
        "coverage": _coverage(ids),
        "due_reports": _due_days(start, end, s) * shifts * len(reporting),
        "sessions": sum(logs.get(kind, 0) for kind in rules.COACHING_TYPES),
        "supervisors": len(supervisors),
        "weeks": ((end - start).days + 1) / 7.0,
        "pulse": _pulse(end, names if (section or branch or company) else None),
        "exits": len(gone),
        "voluntary_exits": sum(1 for row in gone if row.get("custom_employee_status") == "Resigned"),
        "months": ((end - start).days + 1) / 30.4,
        "recognitions": logs.get(rules.RECOGNITION, 0),
        "suggestions": logs.get(rules.SUGGESTION, 0),
        "implemented": logs.get(rules.IMPLEMENTED, 0),
        "safety_trainings": logs.get(rules.SAFETY_TRAINING, 0),
    }
    facts.update(_intervention_facts({"company": company, "branch": branch, "section": section}, start, end, s))
    facts.update(_case_facts(start, end, ids, s, shift))
    facts.update(_grievance_facts(ids, s))
    return facts, s


def supervisor_rows(start, end, company=None, branch=None, section=None, shift=None):
    """Each supervisor with shift reports in the period, or leading a shift:
    their production score and people-management index."""
    s = settings()
    start, end = getdate(start), getdate(end)
    sections = [row.name for row in sections_in(company, branch, section, reporting=True)]
    rosters = _rosters(sections)
    slots = {}
    for parent, roster in rosters.items():
        for shift_name, employee in rules.leads(roster).items():
            if employee and (not shift or shift_name == shift):
                slots.setdefault(employee, []).append((parent, shift_name))
    rows = shift_rows(start, end, company, branch, section, shift)
    mine = {}
    for row in rows:
        if row.supervisor:
            mine.setdefault(row.supervisor, []).append(row)
    days = _due_days(start, end, s)
    people = sorted(set(mine) | set(slots))
    if not people:
        return [], s
    names = dict(frappe.get_all("Employee", filters={"name": ["in", people]}, fields=["name", "employee_name"],
                                as_list=True))
    cases = frappe.get_all(CASE, filters={"docstatus": ["<", 2], "cause": rules.INADEQUATE_SUPERVISION,
                                          "incident_date": ["between", [start, end]]},
                           fields=["work_section", "shift"])
    found = []
    for person in people:
        t = rules.totals(mine.get(person, []), s)
        held = slots.get(person, [])
        conduct = sum(1 for case in cases if (case.work_section, case.shift) in held)
        logs = _log_counts(start, end, None, shift, supervisor=person)
        facts = {"totals": t, "due": days * len(held), "conduct_cases": conduct,
                 "sessions": sum(logs.get(kind, 0) for kind in rules.COACHING_TYPES), "supervisors": 1,
                 "weeks": ((end - start).days + 1) / 7.0}
        facts.update(_intervention_facts({}, start, end, s, supervisor=person))
        index = rules.supervisor_index(facts, s)
        averages = rules.averages(t)
        found.append({"supervisor": person, "supervisor_name": names.get(person),
                      "sections": ", ".join(sorted({row.work_section for row in mine.get(person, [])}
                                                   | {parent for parent, _shift in held})),
                      "shifts": t["count"], "due": facts["due"], "score": averages["score"],
                      "score_status": rules.rag(averages["score"], s), "parts": index["parts"],
                      "index": index["index"], "status": index["status"]})
    return found, s
