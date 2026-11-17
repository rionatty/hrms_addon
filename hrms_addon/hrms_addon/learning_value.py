# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LMS phase 5 on the site; learning_value_rules.py has the rules.

  Training Event   its cost lines added up, with the trainees' time worked out
                   from their sections' labour cost; saved, submitted,
                   changed or cancelled, the year's budgets are brought up to
                   date
  Training Budget  named Year Company (Plant) (Department); what is spent,
                   committed and left, how much is used; HR and Finance told
                   once when it reaches its alert level
  daily            every budget of the year brought up to date
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import learning_value_rules as rules

EVENT, BUDGET, COST_ROWS = "Training Event", "Training Budget", "Training Event Cost"
FINANCE_ROLES = ("Finance Officer", "Accounts Manager")


def _shift_hours():
    from hrms_addon.hrms_addon import excellence

    return excellence.settings()["shift_hours"]


def _hours(doc):
    from hrms_addon.hrms_addon import learning_rules

    programme = frappe.db.get_value("Training Program", doc.get("training_program"), "custom_duration_hours") \
        if doc.get("training_program") else None
    return learning_rules.event_hours(doc.get("start_time"), doc.get("end_time"), programme)


def _rates(employees):
    """Each trainee's person-hour cost, from their section's labour cost."""
    if not employees:
        return []
    sections = dict(frappe.get_all("Employee", filters={"name": ["in", employees]},
                                   fields=["name", "custom_work_section"], as_list=True))
    named = list({section for section in sections.values() if section}) or [""]
    rates = dict(frappe.get_all("Work Section", filters={"name": ["in", named]}, fields=["name", "labour_rate"],
                                as_list=True))
    hours = _shift_hours()
    return [rules.hourly_rate(rates.get(sections.get(employee)), hours) for employee in employees]


def event_costs(doc, method=None):
    """The session's direct costs, the trainees' time, and the cost of each."""
    present = [row.employee for row in doc.get("employees") or [] if row.employee and row.attendance == "Present"]
    cost = rules.session_cost([row.as_dict() for row in doc.get("custom_costs") or []], _rates(present),
                              _hours(doc), len(present))
    doc.custom_direct_cost = cost["direct"]
    doc.custom_time_cost = cost["time"]
    doc.custom_total_cost = cost["total"]
    doc.custom_cost_per_trainee = cost["per_trainee"]
    return cost


def event_changed(doc, method=None):
    """Every budget the session counts against, brought up to date."""
    if doc.get("start_time"):
        refresh_budgets(doc.get("company"), getdate(doc.start_time).year)


# ── Training Budget ───────────────────────────────────────────────────
def budget_autoname(doc):
    doc.name = " ".join(str(part) for part in (doc.year, doc.company, doc.get("branch"), doc.get("department"))
                        if part)


def budget_validate(doc):
    if flt(doc.amount) <= 0:
        frappe.throw(_("The budget must be more than nought."), title=_(BUDGET))
    if not 0 < flt(doc.alert_at) <= 100:
        frappe.throw(_("Alert at a share of the budget between 1 and 100."), title=_(BUDGET))
    spent, committed = _used(doc.as_dict())
    state = rules.budget_state(doc.amount, spent, committed, doc.alert_at)
    doc.update(state)
    tell, doc.alerted = rules.newly_alerting(doc.get("alerted"), state["status"])
    doc.flags.tell = tell


def budget_on_update(doc):
    if doc.flags.get("tell"):
        _tell(doc.as_dict())


def _sessions(company, year):
    events = frappe.get_all(EVENT, filters={"company": company, "docstatus": ["<", 2],
                                            "event_status": ["!=", "Cancelled"],
                                            "start_time": ["between", ["%d-01-01 00:00:00" % year,
                                                                       "%d-12-31 23:59:59" % year]]},
                            fields=["name", "company", "custom_branch", "custom_department", "docstatus",
                                    "event_status", "custom_direct_cost", "training_program"])
    names = [event.name for event in events] or [""]
    lines, invited = {}, {}
    for row in frappe.get_all(COST_ROWS, filters={"parenttype": EVENT, "parent": ["in", names]},
                              fields=["parent", "amount"]):
        lines.setdefault(row.parent, []).append(row)
    for row in frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "parent": ["in", names]},
                              fields=["parent"]):
        invited[row.parent] = invited.get(row.parent, 0) + 1
    per_person = dict(frappe.get_all("Training Program", filters={"name": ["in", list(
        {event.training_program for event in events if event.training_program}) or [""]]},
        fields=["name", "custom_cost_per_person"], as_list=True))
    found = []
    for event in events:
        held = event.docstatus == 1 and event.event_status == "Completed"
        cost = rules.direct_cost(lines.get(event.name)) if held else rules.planned_cost(
            lines.get(event.name), per_person.get(event.training_program), invited.get(event.name, 0))
        found.append({"name": event.name, "company": event.company, "year": year, "branch": event.custom_branch,
                      "department": event.custom_department, "held": held, "cost": cost})
    return found


def _used(budget, sessions=None):
    sessions = _sessions(budget.get("company"), int(budget.get("year"))) if sessions is None else sessions
    mine = [row for row in sessions if rules.in_scope(budget, row)]
    return (sum(row["cost"] for row in mine if row["held"]), sum(row["cost"] for row in mine if not row["held"]))


def refresh_budgets(company=None, year=None):
    filters = {}
    if company:
        filters["company"] = company
    if year:
        filters["year"] = year
    sessions = {}
    for budget in frappe.get_all(BUDGET, filters=filters, fields=["name", "company", "year", "branch", "department",
                                                                  "amount", "alert_at", "alerted"]):
        key = (budget.company, int(budget.year))
        if key not in sessions:
            sessions[key] = _sessions(*key)
        state = rules.budget_state(budget.amount, *_used(budget, sessions[key]), alert_at=budget.alert_at)
        tell, alerted = rules.newly_alerting(budget.alerted, state["status"])
        frappe.db.set_value(BUDGET, budget.name, dict(state, alerted=alerted), update_modified=False)
        if tell:
            _tell(dict(budget, **state))


def _tell(budget):
    from hrms_addon.hrms_addon import people

    users = people.people_for("HR Manager", budget.get("branch"))
    for role in FINANCE_ROLES:
        users += people.people_for(role, budget.get("branch"))
    users = list(dict.fromkeys(user for user in users if user))
    if users:
        people.notify(users, BUDGET, budget.get("name"), _("Training budget {0} is {1}% used: {2}").format(
            budget.get("name"), budget.get("utilisation"), _(budget.get("status"))))


def daily():
    refresh_budgets(year=getdate(today()).year)


# ── What the reports read ─────────────────────────────────────────────
EVENT_FIELDS = ["name", "event_name", "training_program", "supplier", "start_time", "end_time", "custom_branch",
                "company", "custom_evaluation_score", "custom_direct_cost", "custom_time_cost", "custom_total_cost"]


def sessions_in(filters):
    """The sessions held in the period, through the user's permissions."""
    conditions = {"docstatus": 1, "event_status": ["!=", "Cancelled"],
                  "start_time": ["between", [str(getdate(filters.get("from_date"))) + " 00:00:00",
                                             str(getdate(filters.get("to_date"))) + " 23:59:59"]]}
    if filters.get("company"):
        conditions["company"] = filters.get("company")
    if filters.get("branch"):
        conditions["custom_branch"] = filters.get("branch")
    return frappe.get_list(EVENT, filters=conditions, fields=EVENT_FIELDS, limit_page_length=0,
                           order_by="start_time asc")


def value_by(events, key):
    """{group: the four levels, the benefit score, the costs, the benefit and
    the ROI} for sessions grouped by key(session)."""
    from hrms_addon.hrms_addon import learning_delivery_rules as delivery, training_rules
    from hrms_addon.hrms_addon.learning_delivery import IMPACT, REVIEW

    names = [event.name for event in events] or [""]
    present = {}
    for row in frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "parent": ["in", names],
                                                                 "attendance": "Present"}, fields=["parent"]):
        present[row.parent] = present.get(row.parent, 0) + 1
    results = {row.name: row.training_event for row in frappe.get_all(
        "Training Result", filters={"docstatus": 1, "training_event": ["in", names]}, fields=["name", "training_event"])}
    marks = frappe.get_all("Training Result Employee", filters={"parenttype": "Training Result",
                                                                "parent": ["in", list(results) or [""]]},
                           fields=["parent", "custom_effective"])
    group_of = {event.name: key(event) for event in events}
    groups = {}
    for event in events:
        group = groups.setdefault(group_of[event.name], {"events": [], "results": [], "reviews": [], "impacts": [],
                                                         "direct": 0.0, "time": 0.0, "benefit": 0.0})
        group["events"].append({"present": present.get(event.name, 0),
                                "evaluation_score": event.custom_evaluation_score})
        group["direct"] += flt(event.custom_direct_cost)
        group["time"] += flt(event.custom_time_cost)
    for row in marks:
        groups[group_of[results[row.parent]]]["results"].append({"effective": row.custom_effective})
    for row in frappe.get_all(REVIEW, filters={"training_event": ["in", names]},
                              fields=["training_event", "status", "score", "applied"]):
        groups[group_of[row.training_event]]["reviews"].append(row)
    for row in frappe.get_all(IMPACT, filters={"training_event": ["in", names]},
                              fields=["training_event", "result", "benefit"]):
        groups[group_of[row.training_event]]["impacts"].append(row)
        groups[group_of[row.training_event]]["benefit"] += flt(row.benefit)
    found = {}
    for name, group in groups.items():
        levels = delivery.effectiveness(group["events"], group["results"], group["reviews"], group["impacts"],
                                        training_rules.EFFECTIVE)
        levels["kpi_share"] = rules.kpi_share(levels["kpis"], levels["kpis_improved"])
        total = round(group["direct"] + group["time"], 2)
        found[name] = dict(levels, score=rules.benefit_score(levels), direct=round(group["direct"], 2),
                           time=round(group["time"], 2), total=total,
                           per_trainee=round(total / levels["trainees"], 2) if levels["trainees"] else 0.0,
                           benefit=round(group["benefit"], 2), roi=rules.roi(group["benefit"], total))
    return found


def health_by_plant(filters):
    """Each plant's learning and capability health over the last twelve months,
    the whole company first."""
    from hrms_addon.hrms_addon import learning

    s = learning.settings()
    conditions = {"status": "Active"}
    if filters.get("company"):
        conditions["company"] = filters.get("company")
    people = frappe.get_all("Employee", filters=conditions, fields=["name", "branch"])
    plants = sorted({person.branch for person in people if person.branch})
    rows = [_health(_("All Plants"), [person.name for person in people], None, filters, s)]
    for plant in plants:
        rows.append(_health(plant, [person.name for person in people if person.branch == plant], plant, filters, s))
    return rows


def _health(label, ids, plant, filters, s):
    from frappe.utils import add_months

    from hrms_addon.hrms_addon import competency_rules, learning_rules
    from hrms_addon.hrms_addon.competency import ASSESSMENT
    from hrms_addon.hrms_addon.learning_delivery import REVIEW

    day = getdate(today())
    since = add_months(day, -12)
    ids = ids or [""]
    done, required = learning_rules.coverage_of(frappe.get_all(
        "Employee Training Requirement", filters={"employee": ["in", ids]},
        fields=["requirement_type", "status", "completed_on", "valid_until"]), day)
    certificates = frappe.get_all("Employee Certification", filters={
        "employee": ["in", ids], "status": ["in", [learning_rules.VALID, learning_rules.DUE_SOON,
                                                  learning_rules.EXPIRED]]}, pluck="status")
    held = {"docstatus": 1, "event_status": ["!=", "Cancelled"],
            "start_time": ["between", [str(since) + " 00:00:00", str(day) + " 23:59:59"]]}
    if filters.get("company"):
        held["company"] = filters.get("company")
    if plant:
        held["custom_branch"] = plant
    events = frappe.get_all(EVENT, filters=held, fields=["name", "custom_evaluation_score"])
    marked = frappe.get_all("Training Event Employee", filters={
        "parenttype": EVENT, "parent": ["in", [event.name for event in events] or [""]],
        "attendance": ["in", ["Present", "Absent"]]}, pluck="attendance")
    reactions = [flt(event.custom_evaluation_score) for event in events if event.custom_evaluation_score]
    reviews = frappe.get_all(REVIEW, filters={"employee": ["in", ids], "status": "Done",
                                              "reviewed_on": ["between", [since, day]]}, pluck="score")
    assessments = frappe.get_all(ASSESSMENT, filters={"employee": ["in", ids],
                                                      "status": ["!=", competency_rules.SUPERSEDED]},
                                 fields=["skill", "status", "critical"])
    competent, assessed = competency_rules.coverage(assessments)
    cover_settings = {"cover_per_shift": int(s.get("cover_per_shift") or 2), "cover_shifts": int(s.get("cover_shifts") or 2)}
    critical = {}
    for row in assessments:
        if row.critical:
            critical.setdefault(row.skill, 0)
            critical[row.skill] += row.status == competency_rules.COMPETENT
    covered = [competency_rules.cover(count, cover_settings) == competency_rules.OK for count in critical.values()]
    parts = {
        "compliance": rules.percent(done, required),
        "certificates": rules.percent(sum(1 for status in certificates if status != learning_rules.EXPIRED),
                                      len(certificates)),
        "attendance": rules.percent(marked.count("Present"), len(marked)),
        "reaction": round(sum(reactions) / len(reactions), 1) if reactions else None,
        "application": round(sum(flt(score) for score in reviews) / len(reviews), 1) if reviews else None,
        "competency": rules.percent(competent, assessed),
        "cover": rules.percent(sum(covered), len(covered)),
    }
    score, status = rules.health(parts, s.get("matrix_green_from") or 85, s.get("matrix_amber_from") or 65)
    return dict(parts, plant=label, score=score, status=status)
