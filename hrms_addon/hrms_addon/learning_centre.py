# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Learning Command Centre on the site; learning_centre_rules.py has the
rules (scripts/verify_learning_centre.py).

  counts_by_unit   one set of counts per plant and department, every count
                   made by the database (GROUP BY) or from one read for the
                   whole company: never a query per employee
  Learning Snapshot  the month's counts kept, line by line; made on the 1st
                   for the month just ended, and on demand for the month so far
  centre           the page's data: the version for the user (company, plant,
                   department, the supervisor's team, the employee's own), its
                   tiles, health, plants side by side, twelve months of
                   trends, certificates running out and the insights
  download_deck    the month as a PowerPoint (learning_deck.py)
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, today

from hrms_addon.hrms_addon import learning_centre_rules as rules

SNAPSHOT, LINE = "Learning Snapshot", "Learning Snapshot Line"
REQUIREMENT, CERTIFICATE, EVENT = "Employee Training Requirement", "Employee Certification", "Training Event"
HR_ROLES = ("HR Manager", "HR User", "System Manager")
SEE_ALL = ("HR Manager", "System Manager", "General Manager", "Executive Director", "Management Viewer", "Auditor")


def get_first_day(day):
    day = getdate(day)
    return day.replace(day=1)


def get_last_day(day):
    import calendar

    day = getdate(day)
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _agg(function, field, alias):
    from hrms_addon.hrms_addon import queries

    return queries.aggregate(function, field, alias)


def _grouped(doctype, filters, by, extra=None):
    """[{by..., "n", ...}] counted by the database."""
    fields = list(by) + [_agg("COUNT", "*", "n")] + list(extra or [])
    return frappe.get_all(doctype, filters=filters, fields=fields, group_by=", ".join(by), limit_page_length=0)


def _key(row, by=("branch", "department")):
    return tuple(row.get(field) or "" for field in by)


def counts_by_unit(company=None, month=None, branches=None):
    """{(plant, department): counts} for a month (its first day; this month
    so far by default), over the plants given (all where none)."""
    from hrms_addon.hrms_addon import competency, competency_rules, learning, learning_rules

    first = get_first_day(getdate(month or today()))
    last = min(get_last_day(first), getdate(today())) if first <= getdate(today()) else get_last_day(first)
    year_ago = add_months(last, -12)
    units = {}

    def bump(key, field, value):
        units.setdefault(key, rules.blank())[field] += flt(value)

    base = {}
    if company:
        base["company"] = company
    if branches:
        base["branch"] = ["in", list(branches)]
    people = frappe.get_all("Employee", filters=dict(base, status="Active"),
                            fields=["name", "branch", "department"], limit_page_length=0)
    where = {row.name: (row.branch or "", row.department or "") for row in people}
    for key in set(where.values()):
        units.setdefault(key, rules.blank())
    for row in _grouped("Employee", dict(base, status="Active"), ("branch", "department")):
        bump(_key(row), "headcount", row.n)
    for key, found in learning.compliance_counts(base, ("branch", "department"), last).items():
        for field in ("required", "done", "overdue", "due_soon"):
            bump(key, field, found[field])
    mandatory = frappe.get_all("Training Category", filters={"mandatory": 1}, pluck="name")
    if mandatory:
        for key, found in learning.compliance_counts(dict(base, training_category=["in", mandatory]),
                                                     ("branch", "department"), last).items():
            bump(key, "mandatory_required", found["required"])
            bump(key, "mandatory_done", found["done"])
    certs = dict(base, status=["in", [learning_rules.VALID, learning_rules.DUE_SOON, learning_rules.EXPIRED]])
    for row in _grouped(CERTIFICATE, certs, ("branch", "department", "status")):
        bump(_key(row), "cert_expired" if row.status == learning_rules.EXPIRED else "cert_valid", row.n)
    for row in _grouped(CERTIFICATE, dict(base, status=["in", [learning_rules.VALID, learning_rules.DUE_SOON]],
                                          expiry_date=["between", [str(last), str(add_days(last, 90))]]),
                        ("branch", "department")):
        bump(_key(row), "cert_expiring", row.n)
    # who attended any session held in the last twelve months
    held_filters = {"docstatus": 1, "event_status": ["!=", "Cancelled"],
                    "start_time": ["between", [str(year_ago) + " 00:00:00", str(last) + " 23:59:59"]]}
    if company:
        held_filters["company"] = company
    held = frappe.get_all(EVENT, filters=held_filters, fields=["name", "start_time", "custom_branch",
                                                               "custom_department", "custom_total_cost"],
                          limit_page_length=0)
    trained = set(frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "attendance": "Present",
                                                                     "parent": ["in", [e.name for e in held] or [""]]},
                                 pluck="employee", limit_page_length=0))
    for employee in trained:
        if employee in where:
            bump(where[employee], "trained", 1)
    month_events = [event for event in held if first <= getdate(event.start_time) <= last]
    for event in month_events:
        key = (event.custom_branch or "", event.custom_department or "")
        if branches and key[0] not in branches:
            continue
        bump(key, "spend", event.custom_total_cost)
        bump(key, "sessions", 1)
    # the month's days marked and hours, from the attendance rows
    days = {"session_date": ["between", [str(first), str(last)]]}
    if branches:
        days["branch"] = ["in", list(branches)]
    for row in _grouped("Training Attendance", days, ("branch", "department", "status"), [_agg("SUM", "hours", "h")]):
        if row.status in ("Attended", "Late"):
            bump(_key(row), "attended", row.n)
            bump(_key(row), "hours", row.h)
        if row.status not in ("Invited", "Registered"):
            bump(_key(row), "marked", row.n)
    # the year's tests: those assessed and passed, where the person works
    results = frappe.get_all("Training Result", filters={"docstatus": 1, "training_event": ["in", [e.name for e in held]
                                                                                            or [""]]}, pluck="name")
    for row in frappe.get_all("Training Result Employee", filters={"parenttype": "Training Result",
                                                                   "parent": ["in", results or [""]],
                                                                   "custom_effective": ["is", "set"]},
                              fields=["employee", "custom_effective"], limit_page_length=0):
        if row.employee in where:
            bump(where[row.employee], "assessed", 1)
            if row.custom_effective == "Effective":
                bump(where[row.employee], "passed", 1)
    for row in _grouped("Competency Assessment", dict(base, status=["!=", competency_rules.SUPERSEDED]),
                        ("branch", "department", "status")):
        bump(_key(row), "skills_assessed", row.n)
        if row.status == competency_rules.COMPETENT:
            bump(_key(row), "competent", row.n)
    s = competency.settings()
    for row in _grouped("Competency Assessment", dict(base, status=competency_rules.COMPETENT, critical=1),
                        ("branch", "skill")):
        key = (row.branch or "", "")
        bump(key, "critical_total", 1)
        if competency_rules.cover(row.n, s) == competency_rules.OK:
            bump(key, "critical_ok", 1)
    for row in _grouped("Training Application Review", dict(base, status="Done",
                                                            reviewed_on=["between", [str(year_ago), str(last)]]),
                        ("branch", "department"), [_agg("SUM", "score", "total")]):
        bump(_key(row), "reviews_done", row.n)
        bump(_key(row), "review_score", row.total)
    impacts = {"status": "Measured", "event_end": ["between", [str(year_ago), str(last)]]}
    if company:
        impacts["company"] = company
    for row in _grouped("Training Impact Review", impacts, ("branch", "result")):
        bump((row.branch or "", ""), "kpis_measured", row.n)
        if row.result == "Improved":
            bump((row.branch or "", ""), "kpis_improved", row.n)
    for key, amount in budget_for_month(company, first).items():
        bump(key, "budget", amount)
    if branches:
        units = {key: value for key, value in units.items() if key[0] in branches}
    return units


def budget_for_month(company, first):
    """{(plant, department): the month's budget}: its budget lines for the
    month, a budget with no lines a twelfth of it."""
    from hrms_addon.hrms_addon import learning_value_rules

    filters = {"year": getdate(first).year}
    if company:
        filters["company"] = company
    budgets = frappe.get_all("Training Budget", filters=filters, fields=["name", "branch", "department", "amount"],
                             limit_page_length=0)
    month = learning_value_rules.MONTHS[getdate(first).month - 1]
    lines = frappe.get_all("Training Budget Line", filters={"parenttype": "Training Budget",
                                                            "parent": ["in", [b.name for b in budgets] or [""]]},
                           fields=["parent", "branch", "department", "month", "amount"], limit_page_length=0)
    with_lines = {line.parent for line in lines}
    out = {}
    for line in lines:
        if line.month in (month, None, ""):
            share = 1.0 if line.month == month else 1.0 / 12
            key = (line.branch or "", line.department or "")
            out[key] = out.get(key, 0.0) + flt(line.amount) * share
    for budget in budgets:
        if budget.name not in with_lines:
            key = (budget.branch or "", budget.department or "")
            out[key] = out.get(key, 0.0) + flt(budget.amount) / 12.0
    return out


def lines_of(units):
    """The units as snapshot lines, with their health and its parts."""
    from hrms_addon.hrms_addon import learning, learning_rules

    s = learning.settings()
    weights = learning_rules.weights(s, "health_", learning_rules.HEALTH_PARTS)
    out = []
    for (branch, department), counts in sorted(units.items()):
        parts = rules.parts_of(counts)
        score, status = rules.health(parts, weights, s["matrix_green_from"], s["matrix_amber_from"])
        out.append(dict(counts, branch=branch, department=department, health_score=score, health_status=status,
                        **{"part_" + key: value for key, value in parts.items()}))
    return out


def totals(lines):
    from hrms_addon.hrms_addon import learning, learning_rules

    s = learning.settings()
    found = rules.blank()
    for line in lines:
        rules.add(found, line)
    parts = rules.parts_of(found)
    score, status = rules.health(parts, learning_rules.weights(s, "health_", learning_rules.HEALTH_PARTS),
                                 s["matrix_green_from"], s["matrix_amber_from"])
    return dict(found, parts=parts, health_score=score, health_status=status, figures=rules.figures(found))


# ── Learning Snapshot ─────────────────────────────────────────────────
def snapshot_autoname(doc):
    doc.name = "%s %s" % (doc.company, str(getdate(doc.month_start))[:7])


def snapshot_validate(doc):
    doc.month_start = get_first_day(getdate(doc.month_start))
    if doc.get("source") != "Imported" and not doc.get("lines"):
        fill(doc)


def fill(doc):
    """The snapshot's lines and totals from the site, as they stand."""
    found = lines_of(counts_by_unit(doc.company, doc.month_start))
    doc.set("lines", [])
    for line in found:
        doc.append("lines", {key: line.get(key) for key in ["branch", "department", "health_score"]
                             + list(rules.COUNTS) + ["part_" + key for key in rules.PARTS]})
    total = totals(found)
    for key in rules.COUNTS:
        doc.set(key, total[key])
    for key in rules.PARTS:
        doc.set("part_" + key, total["parts"][key])
    doc.health_score, doc.health_status = total["health_score"], total["health_status"]
    doc.built_on = frappe.utils.now()


def take_snapshot(company, month):
    name = frappe.db.get_value(SNAPSHOT, {"company": company, "month_start": str(get_first_day(getdate(month)))}, "name")
    doc = frappe.get_doc(SNAPSHOT, name) if name else frappe.get_doc({"doctype": SNAPSHOT, "company": company,
                                                                       "month_start": month, "source": "System"})
    if doc.get("source") == "Imported":
        return doc.name
    fill(doc)
    doc.flags.ignore_permissions = True
    doc.save() if name else doc.insert()
    return doc.name


def monthly():
    """On the 1st: the month just ended, for each company with people."""
    month = add_months(get_first_day(getdate(today())), -1)
    for company in frappe.get_all("Employee", filters={"status": "Active"}, pluck="company", distinct=True):
        if company:
            try:
                take_snapshot(company, month)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                frappe.log_error(title="Learning: the month's snapshot for %s" % company)


@frappe.whitelist(methods=["POST"])
def build_now(company=None, month=None):
    """The month so far (or a month asked for), built again now."""
    frappe.has_permission(SNAPSHOT, "create", throw=True)
    company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
        "Global Defaults", "default_company")
    return take_snapshot(company, month or today())


# ── The page ──────────────────────────────────────────────────────────
def _roles():
    return set(frappe.get_roles())


def _own_employee():
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user},
                               ["name", "branch", "department", "company"], as_dict=True)


def permitted_plants():
    """The plants the user may see: every plant for HR and management, else
    those of the employees their own permissions reach."""
    if _roles() & set(SEE_ALL):
        return None
    plants = sorted({row.branch for row in frappe.get_list("Employee", filters={"status": "Active"},
                                                           fields=["branch"], group_by="branch",
                                                           limit_page_length=0) if row.branch})
    return plants


@frappe.whitelist()
def centre(company=None, branch=None, month=None, view=None):
    """Everything the Learning Command Centre shows, for one version of it."""
    view = view if view in rules.VIEWS else rules.view_for(_roles())
    own = _own_employee()
    if view == "My Learning":
        return dict(my_learning(own), view=view)
    if view == "My Team":
        return dict(my_team(own), view=view)
    plants = permitted_plants()
    if branch:
        if plants is not None and branch not in plants:
            frappe.throw(_("Not permitted to see {0}.").format(branch), frappe.PermissionError)
        plants = [branch]
    elif view == "Plant" and own and own.branch and plants is not None:
        plants = [own.branch] if own.branch in plants else plants
    company = company or (own.company if own else None) or frappe.defaults.get_user_default("Company")
    units = counts_by_unit(company, month, plants)
    if view == "Department" and own and own.department and not (_roles() & set(SEE_ALL)):
        units = {key: value for key, value in units.items() if key[1] == own.department}
    lines = lines_of(units)
    total = totals(lines)
    by_plant = {}
    for line in lines:
        rules.add(by_plant.setdefault(line["branch"], rules.blank()), line)
    plant_rows = []
    for name, counts in sorted(by_plant.items()):
        parts = rules.parts_of(counts)
        score = rules.health(parts, _weights())[0]
        plant_rows.append(dict(rules.figures(counts), branch=name or _("No Plant"), health=score, parts=parts))
    return {"view": view, "company": company, "month": str(get_first_day(getdate(month or today()))),
            "figures": total["figures"], "health": {"score": total["health_score"], "status": total["health_status"],
                                                    "parts": total["parts"]},
            "plants": plant_rows, "departments": [dict(rules.figures(line), branch=line["branch"],
                                                       department=line["department"], health=line["health_score"])
                                                  for line in lines if line["department"]],
            "trends": trends(company, plants), "alerts": certificate_alerts(plants),
            "insights": insights_for(company, lines, plants), "plants_allowed": plants}


def _weights():
    from hrms_addon.hrms_addon import learning, learning_rules

    return learning_rules.weights(learning.settings(), "health_", learning_rules.HEALTH_PARTS)


def trends(company, plants=None):
    """Twelve months from the snapshots kept: compliance, certificates,
    hours, spend and health, each month's lines added up for the plants
    shown."""
    rows = frappe.get_all(SNAPSHOT, filters={"company": company} if company else {},
                          fields=["name", "month_start"], order_by="month_start desc", limit_page_length=12)
    if not rows:
        return []
    lines = frappe.get_all(LINE, filters={"parenttype": SNAPSHOT, "parent": ["in", [row.name for row in rows]]},
                           fields=["parent", "branch"] + list(rules.COUNTS), limit_page_length=0)
    months = {row.name: dict(rules.blank(), month_start=row.month_start) for row in rows}
    for line in lines:
        if plants is None or line.branch in plants:
            rules.add(months[line.parent], line)
    out = []
    for counts in sorted(months.values(), key=lambda row: str(row["month_start"])):
        found = rules.figures(counts)
        out.append({"month": str(counts["month_start"])[:7], "compliance": found["compliance"],
                    "certification": found["certification"], "hours": found["hours"], "spend": found["spend"],
                    "health": rules.health(rules.parts_of(counts), _weights())[0]})
    return out


def certificate_alerts(plants=None, limit=15):
    """The certificates running out soonest, and those run out, through the
    user's permissions."""
    from hrms_addon.hrms_addon import learning_rules

    filters = {"status": ["in", [learning_rules.DUE_SOON, learning_rules.EXPIRED]]}
    if plants is not None:
        filters["branch"] = ["in", plants or [""]]
    rows = frappe.get_list(CERTIFICATE, filters=filters, fields=["name", "employee", "employee_name", "certification",
                                                                 "branch", "expiry_date", "status"],
                           order_by="expiry_date asc", limit_page_length=limit)
    for row in rows:
        row.days_left = learning_rules.days_left(row.expiry_date, today())
    return rows


def insights_for(company, lines, plants=None):
    """The findings, from the lines and a few reads of their own."""
    from hrms_addon.hrms_addon import competency, learning, learning_delivery

    s = learning.settings()
    since = add_months(getdate(today()), -12)
    held = frappe.get_all(EVENT, filters={"docstatus": 1, "event_status": ["!=", "Cancelled"],
                                          "start_time": [">=", str(since)]},
                          fields=["name", "training_program", "custom_branch"], limit_page_length=0)
    if plants is not None:
        held = [event for event in held if event.custom_branch in plants]
    by_programme = {}
    for event in held:
        by_programme.setdefault(event.training_program or "", []).append(event.name)
    levels = learning_delivery.programme_levels(list(by_programme))
    results = {row.name: row.training_event for row in frappe.get_all(
        "Training Result", filters={"docstatus": 1, "training_event": ["in", [e.name for e in held] or [""]]},
        fields=["name", "training_event"], limit_page_length=0)}
    marks = {}
    for row in frappe.get_all("Training Result Employee", filters={"parenttype": "Training Result",
                                                                   "parent": ["in", list(results) or [""]],
                                                                   "custom_effective": ["is", "set"]},
                              fields=["parent", "custom_effective"], limit_page_length=0):
        marks.setdefault(results[row.parent], []).append(row.custom_effective)
    reviewed = {row.training_event for row in frappe.get_all(
        "Training Application Review", filters={"status": "Done", "training_event": ["in", [e.name for e in held]
                                                                                     or [""]]},
        fields=["training_event"], limit_page_length=0)}
    programmes = []
    for programme, events in by_programme.items():
        if not programme:
            continue
        judged = [mark for event in events for mark in marks.get(event, [])]
        programmes.append({"training_program": programme, "held": len(events), "assessed": len(judged),
                           "pass_rate": round(100.0 * judged.count("Effective") / len(judged), 1) if judged else None,
                           "behaviour_on": (levels.get(programme) or {"behaviour": True})["behaviour"],
                           "reviews_done": sum(1 for event in events if event in reviewed)})
    critical = frappe.get_all("Skill", filters={"custom_critical": 1}, pluck="name", limit_page_length=0) \
        if frappe.get_meta("Skill").has_field("custom_critical") else []
    covers = competency.cover_by_shift(critical) if critical else []
    if plants is not None:
        covers = [row for row in covers if row["branch"] in plants]
    budgets = frappe.get_all("Training Budget", filters={"year": getdate(today()).year,
                                                         "status": ["in", ["Near the Limit", "Over Budget"]]},
                             fields=["name", "status", "utilisation"], limit_page_length=0)
    providers = frappe.get_all("Training Provider", filters={"trend": ["<", 0]}, fields=["name", "trend", "score"],
                               limit_page_length=0)
    return rules.insights(lines, programmes, covers, budgets, providers, threshold=s["matrix_green_from"])


def my_team(own):
    """A supervisor's team: their compliance, sessions to come, gaps,
    certificates running out, sheets waiting on them and needs raised."""
    if not own:
        return {"team": []}
    team = frappe.get_all("Employee", filters={"reports_to": own.name, "status": "Active"},
                          fields=["name", "employee_name", "designation", "custom_work_section" if frappe.get_meta(
                              "Employee").has_field("custom_work_section") else "department"],
                          order_by="employee_name asc", limit_page_length=0)
    names = [row.name for row in team] or [""]
    status = {}
    for row in frappe.get_all(REQUIREMENT, filters={"employee": ["in", names], "status": ["!=", "Not Applicable"],
                                                    "requirement_type": ["!=", "Recommended"]},
                              fields=["employee", "status"], limit_page_length=0):
        status.setdefault(row.employee, {}).setdefault(row.status, 0)
        status[row.employee][row.status] += 1
    gaps = frappe.get_all("Competency Assessment", filters={"employee": ["in", names],
                                                            "status": ["in", ["Gap", "Reassessment Due",
                                                                              "Certificate Needed"]]},
                          fields=["employee", "employee_name", "skill", "level", "required_level", "status"],
                          limit_page_length=0)
    skills = frappe.get_all("Competency Assessment", filters={"employee": ["in", names], "status": ["!=", "Superseded"]},
                            fields=["employee", "skill", "level"], limit_page_length=0)
    certs = frappe.get_all(CERTIFICATE, filters={"employee": ["in", names], "status": ["in", ["Due Soon", "Expired"]]},
                           fields=["name", "employee_name", "certification", "expiry_date", "status"],
                           order_by="expiry_date asc", limit_page_length=0)
    from hrms_addon.hrms_addon import learning

    upcoming = []
    for row in team:
        for event in learning.upcoming_sessions(row.name)[:3]:
            upcoming.append(dict(event, employee_name=row.employee_name))
    waiting = frappe.get_all("Application Review Sheet", filters={"reviewer": frappe.session.user, "docstatus": 0},
                             fields=["name", "training_program", "due_on"], limit_page_length=0)
    needs = frappe.get_all(REQUIREMENT, filters={"employee": ["in", names], "requirement_type": "Recommended",
                                                 "status": ["!=", "Compliant"]},
                           fields=["employee_name", "training_program", "due_date", "status"], limit_page_length=0)
    attended = _grouped("Training Attendance", {"employee": ["in", names]}, ("status",))
    for row in team:
        mine = status.get(row.name, {})
        required = sum(mine.values())
        row.update(required=required, overdue=mine.get("Overdue", 0), due_soon=mine.get("Due Soon", 0),
                   compliance=rules.share(mine.get("Compliant", 0), required))
    return {"team": team, "gaps": gaps, "skills": skills, "certificates": certs, "upcoming": upcoming,
            "waiting": waiting, "needs": needs, "attendance": {row.status: row.n for row in attended}}


def my_learning(own):
    """The employee's own: their passport, the content given them, and the
    sessions they may register for."""
    from hrms_addon.hrms_addon import learning, learning_library

    if not own:
        return {"employee": None}
    found = learning.passport(own.name)
    found["assignments"] = learning_library.my_assignments(own.name)
    found["open_sessions"] = frappe.get_all(EVENT, filters={"docstatus": 0, "event_status": "Scheduled",
                                                            "start_time": [">=", str(today())],
                                                            "custom_branch": ["in", [own.branch, ""]] if own.branch
                                                            else ["is", "not set"]},
                                            fields=["name", "event_name", "training_program", "start_time",
                                                    "location", "custom_seats_left", "custom_capacity"],
                                            order_by="start_time asc", limit_page_length=20)
    return found


@frappe.whitelist()
def download_deck(company=None, month=None, branch=None):
    """The month as a PowerPoint deck, for the board and management."""
    frappe.has_permission(SNAPSHOT, "read", throw=True)
    from hrms_addon.hrms_addon import learning_deck

    data = centre(company, branch, month, "Company" if _roles() & set(SEE_ALL) else "Plant")
    content = learning_deck.deck(data)
    frappe.local.response.filename = "Learning %s.pptx" % data["month"][:7]
    frappe.local.response.filecontent = content
    frappe.local.response.type = "binary"
