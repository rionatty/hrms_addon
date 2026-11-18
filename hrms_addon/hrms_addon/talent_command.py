# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Talent Command page (page/talent_command) and the figures the
Talent Council pack and the HR board pack read. Everything is added up in
SQL, a GROUP BY a figure, never a query a person; the page's answer is
cached for ten minutes a review, company and plant scope. The layout rules
are in talent_command_rules.py (scripts/verify_talent_command.py).

  get_command    the page: tiles; the plants and the departments side by
                 side on the nine boxes against the guide and the review
                 before; the succession heat map (impact x probability),
                 bench strength and the successors named for several
                 roles; top talent and flight risk; the 9 x 9 movement since
                 the review before; the graduate funnel by cohort; what the
                 development plans cost. Each figure carries the list it
                 drills down to
  figures        the same, for a review, without the cache (the council
                 pack, the board pack)
  board_figures  what the HR board pack reads about talent: the risk in the
                 talent and the cover behind the critical roles
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from hrms_addon.hrms_addon import calibration_rules, succession_rules, talent_command_rules as rules
from hrms_addon.hrms_addon import talent_masters as masters

REVIEW, PLACEMENT, POSITION = "Talent Review", "Talent Placement", "Succession Position"
WHOLE_COMPANY = ("System Manager", "HR Manager", "Talent Council", "General Manager", "Executive Director")
CACHE_SECONDS = 600


def _check_access():
    from hrms_addon.hrms_addon import talent_board

    if not talent_board.can_see_boxes():
        frappe.throw(_("Talent Command is for HR, the Talent Council and the executives."), frappe.PermissionError)


def scope(user=None):
    """The plants the user sees: None for all (HR Manager, the council and
    the executives), else their Branch User Permissions, if any."""
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & set(WHOLE_COMPANY):
        return None
    branches = frappe.get_all("User Permission", filters={"user": user, "allow": "Branch"}, pluck="for_value")
    return sorted(set(branches)) or None


def latest_review(company=None):
    filters = {"status": ["!=", "Cancelled"]}
    if company:
        filters["company"] = company
    found = frappe.get_all(REVIEW, filters=filters, order_by="review_year desc, opens_on desc", pluck="name", limit=1)
    return found[0] if found else None


def review_before(review):
    if not review:
        return None
    year = frappe.db.get_value(REVIEW, review, "review_year")
    found = frappe.get_all(REVIEW, filters={"name": ["!=", review], "review_year": ["<", cint(year)],
                                            "status": ["!=", "Cancelled"]},
                           order_by="review_year desc, opens_on desc", pluck="name", limit=1)
    return found[0] if found else None


@frappe.whitelist()
def get_command(review=None, company=None, fresh=0):
    """The page's one call."""
    _check_access()
    company = company or None
    review = review or latest_review(company)
    plants = scope()
    key = rules.cache_key(plants, review, company)
    if not cint(fresh):
        cached = frappe.cache.get_value(key)
        if cached:
            return cached
    data = figures(review, company, plants)
    data["reviews"] = frappe.get_all(REVIEW, filters={"status": ["!=", "Cancelled"]},
                                     fields=["name", "title", "review_year", "status"],
                                     order_by="review_year desc, opens_on desc", limit=20)
    frappe.cache.set_value(key, data, expires_in_sec=CACHE_SECONDS)
    return data


def _where(alias, company, plants):
    parts = []
    if company:
        parts.append("%s.company = %%(company)s" % alias)
    if plants:
        parts.append("%s.branch in %%(plants)s" % alias)
    return "".join(" and " + part for part in parts)


def figures(review, company=None, plants=None):
    """Everything the page shows for a review, added up in SQL."""
    before = review_before(review)
    watched = masters.watched_risks() or ["-"]
    values = {"review": review or "", "before": before or "", "company": company, "plants": list(plants or []),
              "watched": list(watched)}
    where = _where("p", company, plants)
    grid = masters.grid()
    names = {cell["box"]: cell["name"] for cell in grid["boxes"].values()}
    colours = {cell["box"]: cell["colour"] for cell in grid["boxes"].values()}
    guide = masters.guide()

    def grouped(field, which):
        return frappe.db.sql("""
            select p.{field} as grp, p.box, count(*) as n from `tabTalent Placement` p
            where p.talent_review = %({which})s and p.docstatus < 2 and p.box between 1 and 9 {where}
            group by p.{field}, p.box""".format(field=field, which=which, where=where), values, as_dict=True)

    counts = frappe.db.sql("""
        select count(*) as total,
               sum(case when p.box between 1 and 9 then 1 else 0 end) as placed,
               sum(case when p.top_talent = 1 and p.box between 1 and 9 then 1 else 0 end) as top,
               sum(case when p.top_talent = 1 and p.flight_risk in %(watched)s then 1 else 0 end) as at_risk,
               sum(case when p.top_talent = 1 and p.flight_risk in %(watched)s and not exists (
                   select 1 from `tabRetention Action` r where r.parent = p.name and r.parenttype = 'Talent Placement'
                   and r.status not in ('Done', 'Dropped')) then 1 else 0 end) as unprotected,
               sum(case when p.raters_disagree = 1 then 1 else 0 end) as disagree
        from `tabTalent Placement` p
        where p.talent_review = %(review)s and p.docstatus < 2 {where}""".format(where=where), values,
                           as_dict=True)[0]
    states = frappe.db.sql("""
        select coalesce(p.workflow_state, 'Draft') as state, count(*) as n from `tabTalent Placement` p
        where p.talent_review = %(review)s and p.docstatus < 2 {where}
        group by p.workflow_state""".format(where=where), values, as_dict=True)
    person = """p.name, p.employee, p.employee_name, p.designation, p.branch, p.department, p.box, p.box_name,
                p.performance_score, p.potential_score, p.flight_risk, p.impact_of_loss"""
    top = frappe.db.sql("""
        select {person} from `tabTalent Placement` p
        where p.talent_review = %(review)s and p.docstatus < 2 and p.top_talent = 1 {where}
        order by p.box desc, p.performance_score desc limit 25""".format(person=person, where=where), values,
                        as_dict=True)
    risk = frappe.db.sql("""
        select {person}, (select count(*) from `tabRetention Action` r where r.parent = p.name
                          and r.parenttype = 'Talent Placement' and r.status not in ('Done', 'Dropped')) as actions
        from `tabTalent Placement` p
        where p.talent_review = %(review)s and p.docstatus < 2 and p.top_talent = 1 and p.flight_risk in %(watched)s
        {where}
        order by case p.flight_risk when 'High' then 0 else 1 end, p.box desc limit 25""".format(
        person=person, where=where), values, as_dict=True)
    retention_open = frappe.db.sql("""
        select count(*) from `tabRetention Action` r join `tabTalent Placement` p on p.name = r.parent
        where r.parenttype = 'Talent Placement' and p.talent_review = %(review)s and p.docstatus < 2
          and r.status not in ('Done', 'Dropped') {where}""".format(where=where), values)[0][0]
    roles = frappe.db.sql("""
        select p.name, p.designation, p.branch, p.department, p.incumbent_name, p.impact_score, p.loss_probability,
               p.role_risk, p.risk_level, p.coverage, p.ready_now, p.successors, p.single_person_role
        from `tabSuccession Position` p where p.docstatus < 2 {where}
        order by p.role_risk desc""".format(where=where), values, as_dict=True)
    heat = succession_rules.heat_map([{"name": row.name, "probability": flt(row.loss_probability) / 100.0,
                                       "impact": row.impact_score} for row in roles])
    bench = succession_rules.bench_index([{"ready_now": row.ready_now, "successors": row.successors} for row in roles])
    from hrms_addon.hrms_addon import graduates, succession_risk

    overlap = succession_risk.overlap(company, plants)
    funnel = graduates.funnel(company)
    pairs = frappe.db.sql("""
        select prev.box as was, cur.box as now_box, count(*) as n from `tabTalent Placement` cur
        left join `tabTalent Placement` prev on prev.employee = cur.employee and prev.talent_review = %(before)s
             and prev.docstatus < 2 and prev.box between 1 and 9
        where cur.talent_review = %(review)s and cur.docstatus < 2 and cur.box between 1 and 9 {where}
        group by prev.box, cur.box""".format(where=_where("cur", company, plants)), values, as_dict=True) \
        if before else []
    gone = frappe.db.sql("""
        select prev.box as was, count(*) as n from `tabTalent Placement` prev
        left join `tabTalent Placement` cur on cur.employee = prev.employee and cur.talent_review = %(review)s
             and cur.docstatus < 2 and cur.box between 1 and 9
        where prev.talent_review = %(before)s and prev.docstatus < 2 and prev.box between 1 and 9
          and cur.name is null {where}
        group by prev.box""".format(where=_where("prev", company, plants)), values, as_dict=True) if before else []
    matrix = calibration_rules.matrix([])
    for row in pairs:
        matrix[cint(row.was)][cint(row.now_box)] += cint(row.n)
    for row in gone:
        matrix[cint(row.was)][0] += cint(row.n)
    invested = frappe.db.sql("""
        select sum(p.approved_investment) as approved, sum(p.actual_investment) as actual, count(*) as plans
        from `tabTalent Program` p where p.docstatus < 2 and p.talent_review = %(review)s {where}""".format(
        where=where), values, as_dict=True)[0]
    trainees = sum(row["total"] for row in funnel)
    confirmed = sum(row["stages"]["Confirmed"] for row in funnel)
    facts = {"placed": counts.placed, "eligible": counts.total, "top": counts.top, "at_risk": counts.at_risk,
             "unprotected": counts.unprotected, "retention_open": retention_open, "bench": bench,
             "high_risk_roles": len([row for row in roles if row.risk_level == "High"]), "overlap": len(overlap),
             "trainees": trainees, "confirmed": confirmed, "heat": heat, "review": review,
             "investment_approved": invested.approved, "investment_actual": invested.actual}
    return {
        "review": frappe.db.get_value(REVIEW, review, ["name", "title", "review_year", "status"], as_dict=True)
        if review else None,
        "before": before, "company": company, "plants": plants, "facts": facts,
        "kpis": rules.kpis(facts), "states": {row.state: cint(row.n) for row in states},
        "disagree": cint(counts.disagree),
        "by_plant": rules.side_by_side(grouped("branch", "review"), grouped("branch", "before") if before else [],
                                       guide),
        "by_department": rules.side_by_side(grouped("department", "review"),
                                            grouped("department", "before") if before else [], guide),
        "names": names, "colours": colours, "guide": guide,
        "top": top, "risk": risk, "roles": roles[:25], "heat": heat, "bench": bench, "overlap": overlap[:25],
        "matrix": rules.matrix_rows(matrix, names), "movement": calibration_rules.matrix_summary(matrix),
        "funnel": funnel, "investment": {"approved": flt(invested.approved), "actual": flt(invested.actual),
                                         "plans": cint(invested.plans)},
    }


def board_figures(company=None, review=None):
    """What the HR board pack reads about talent, for the company's latest
    review (board_pack.py): the risk in the talent and the cover behind the
    critical roles (talent_command_rules.board_figures)."""
    review = review or latest_review(company)
    if not review:
        return rules.board_figures({})
    return rules.board_figures(figures(review, company)["facts"])
