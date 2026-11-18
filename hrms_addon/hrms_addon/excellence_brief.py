# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR Partner Brief (Manufacturing Excellence, 18 Nov 2026): the week for
the Monday production meeting, for a plant or the company, as the workbook's
HR Partner Brief sheet has it.

  1  the business case in money and people
  2  where the money went: the three sections that lost the most
  3  the five supervisors to coach, with the agreed HR action
  4  accountability: interventions open, overdue, raised
  5  the talking points, written from the figures
  6  the sections where workforce signals occur together
  7  the nine questions for the Plant Manager review, answered

Built every Monday for each plant for the week just ended and e-mailed to
the plant's General Manager and Production Manager and to HR, one e-mail a
person with each brief of the plants they serve. HR adds its own notes; it
can be built again, and sent again, from the form. board_slide gives the
board pack its Manufacturing Excellence slide.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from hrms_addon.hrms_addon import excellence_rules as rules, excellence_summary as summary

BRIEF = "HR Partner Brief"
PRINT = "HR Partner Brief"
COACH, SHOWN = 5, 3


def brief_autoname(doc):
    # Frappe names a document before validating it: the week is written alike first
    _week(doc)
    doc.name = "%s %s" % (doc.week, doc.branch or _("All Plants"))


def _week(doc):
    """The week written as 2026-W44, with its first and last day."""
    week = (doc.week or "").strip().upper().replace(" ", "")
    try:
        year, number = week.split("-W")
        start, end = rules.period_bounds(rules.WEEK, int(year), int(number))
    except ValueError:
        frappe.throw(_("Write the week as 2026-W44."), title=_(BRIEF))
    doc.week = "%s-W%02d" % (year, int(number))
    doc.week_start, doc.week_end = start, end


def brief_validate(doc):
    _week(doc)
    if not doc.get("company"):
        doc.company = (frappe.defaults.get_user_default("Company")
                       or frappe.db.get_single_value("Global Defaults", "default_company"))


@frappe.whitelist()
def build(name):
    doc = frappe.get_doc(BRIEF, name)
    doc.check_permission("write")
    fill(doc)
    doc.save()
    return doc.name


def fill(doc):
    """Every figure of the brief from the week's summaries."""
    brief_validate(doc)
    start, end, branch, company = getdate(doc.week_start), getdate(doc.week_end), doc.get("branch"), doc.company
    facts, s = summary.period_facts(start, end, company, branch)
    card = rules.pillars(facts, s)
    t = facts["totals"]
    filters = summary.scope_filters(start, end, company, branch)
    scored = rules.section_scores(summary.section_totals(filters), s)
    plant = rules.plant_score([row["score"] for row in scored])
    over = sum(1 for row in scored if (row["totals"]["waste_cap"]
                                       and row["totals"]["waste_value"] >= row["totals"]["waste_cap"])
               or (row["totals"]["complaint_cap"] and row["totals"]["complaint_value"]
                   >= row["totals"]["complaint_cap"]))
    doc.waste_value, doc.complaint_value, doc.money_lost = t["waste_value"], t["complaint_value"], t["money_lost"]
    doc.over_limit, doc.not_wearing = over, cint(t["not_wearing"])
    doc.absent = max(0, cint(t["staff_planned"]) - cint(t["staff_on_shift"]))
    doc.hours_lost, doc.safety_incidents = t["hours_lost"], cint(t["safety_incidents"])
    doc.plant_score, doc.plant_status = plant or 0, rules.rag(plant, s)
    doc.verdict = rules.verdict(scored)
    doc.set("top_sections", [])
    for row in sorted(scored, key=lambda row: -row["totals"]["money_lost"])[:SHOWN]:
        doc.append("top_sections", {"work_section": row["section"], "waste_value": row["totals"]["waste_value"],
                                    "complaint_value": row["totals"]["complaint_value"], "score": row["score"],
                                    "status": row["status"], "weakest_area": row["weakest_label"]})
    supervisors, _s = summary.supervisor_rows(start, end, company, branch)
    lowest = sorted((row for row in supervisors if row["score"] is not None), key=lambda row: row["score"])[:COACH]
    doc.set("supervisors", [])
    for row in lowest:
        doc.append("supervisors", {"supervisor": row["supervisor"], "supervisor_name": row["supervisor_name"],
                                   "work_section": row["section"], "shift": row["shift"], "score": row["score"],
                                   "weakest_area": row["weakest"], "action": row["next_step"],
                                   "people_index": row["index"], "focus": row["focus"]})
    doc.open_interventions = facts.get("interventions_open") or 0
    doc.overdue_interventions = facts.get("interventions_overdue") or 0
    doc.raised_interventions = facts.get("interventions_raised") or 0
    heat, _s = summary.section_rows(start, end, company, branch, week=doc.week)
    signals = [row for row in heat if row["count"] >= 2][:SHOWN + 2]
    doc.set("signals", [])
    for row in signals:
        doc.append("signals", {"work_section": row["section"], "signals": row["count"], "alert": row["alert"],
                               "intervention": row["intervention"]})
    downtime = rules.downtime_breakdown(summary.downtime(start, end, company, branch))
    figures = _figures(doc, facts, card, t, s, lowest, downtime, signals, start, end, company, branch)
    doc.talking_points = "\n".join(rules.talking_points(figures))
    doc.set("questions", [])
    for question, answer in rules.nine_questions(figures):
        doc.append("questions", {"question": question, "answer": answer})
    doc.built_on = now_datetime()
    return figures


def _figures(doc, facts, card, t, s, lowest, downtime, signals, start, end, company, branch):
    a = card["averages"]
    coach = lowest[0] if lowest else None
    orders = 0
    try:
        from hrms_addon.hrms_addon.report.order_feasibility import order_feasibility

        orders = sum(1 for row in order_feasibility.order_rows({"company": company, "branch": branch})
                     if row.get("feasibility") == rules.NOT_FEASIBLE)
    except Exception:
        orders = 0
    supervisors_needing = sum(1 for row in summary.supervisor_rows(start, end, company, branch)[0]
                              if row["index"] is not None and row["index"] < s["amber_from"])
    skills = facts.get("competency") or (0, 0)
    return {
        "plant_score": doc.plant_score if doc.verdict and t["shifts"] else None, "plant_status": doc.plant_status,
        "verdict": doc.verdict, "money_lost": t["money_lost"], "over_limit": doc.over_limit, "ppe": a["ppe"],
        "not_wearing": t["not_wearing"], "absent": doc.absent, "attendance": a["attendance"],
        "incidents": t["safety_incidents"], "hours_lost": t["hours_lost"],
        "top_reason": downtime[0]["reason"] if downtime else None,
        "coach": {"supervisor": coach["supervisor"], "supervisor_name": coach["supervisor_name"],
                  "section": coach["section"], "shift": coach["shift"], "weakest": coach["weakest"]} if coach else None,
        "labour": t["labour_cost"], "ot_cost": t["ot_cost"], "ot_share": a["ot_share"], "not_feasible": orders,
        "cases": facts.get("cases") or 0, "case_cost": facts.get("case_cost") or 0,
        "legal_flags": facts.get("legal_flags") or 0, "open_grievances": facts.get("open_grievances") or 0,
        "headcount": facts.get("headcount"), "establishment": facts.get("establishment"),
        "deployment": a["deployment"], "below_band": t["below_band"], "competent": card["competent"],
        "critical": card["critical"], "gaps": max(0, skills[1] - skills[0]),
        "supervision": card["supervision"]["index"], "need_coaching": supervisors_needing,
        "unauthorised": a["unauthorised"], "absence_cost": t["absence_cost"],
        "budget_variance": a["budget_variance"],
        "signals": [(row["section"], row["alert"]) for row in signals], "repeats": facts.get("repeats") or 0,
        "near_misses": t["near_misses"], "raised": facts.get("interventions_raised") or 0,
        "open_interventions": facts.get("interventions_open") or 0,
        "overdue": facts.get("interventions_overdue") or 0, "improved": facts.get("interventions_improved") or 0,
        "savings": facts.get("savings") or 0,
    }


# ── Monday ────────────────────────────────────────────────────────────
def monday(day=None):
    """Last week's brief for each plant built, and sent: one e-mail a person
    with the briefs of the plants they serve."""
    from hrms_addon.hrms_addon import excellence

    s = excellence.settings()
    monday_ = rules.week_start(day or today())
    week = rules.week_label(add_days(monday_, -7))
    built = []
    for branch, company in _plants():
        name = "%s %s" % (week, branch)
        doc = frappe.get_doc(BRIEF, name) if frappe.db.exists(BRIEF, name) else frappe.get_doc(
            {"doctype": BRIEF, "week": week, "branch": branch, "company": company})
        try:
            fill(doc)
            doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)
            frappe.db.commit()
            built.append(doc)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="HR Partner Brief %s" % name)
    if cint(s.get("send_brief")) and built:
        send_all(built)


def _plants():
    rows = frappe.get_all(summary.SECTION, filters={"is_active": 1}, fields=["branch", "company"], limit_page_length=0)
    return sorted({(row.branch, row.company) for row in rows if row.branch})


def recipients(branch):
    """The plant's General Manager and Production Manager, and its HR."""
    from hrms_addon.hrms_addon import people

    users = []
    for role in ("General Manager", "Production Manager"):
        users += people.people_for(role, branch)
    users += people.hr_officers(branch)
    users += [holder["user"] for holder in people.holders("HR Manager")]
    return list(dict.fromkeys(user for user in users if user))


def send_all(briefs):
    by_user = {}
    for doc in briefs:
        for user in recipients(doc.branch):
            by_user.setdefault(user, []).append(doc)
    for user, docs in by_user.items():
        _mail(user, docs)
    for doc in briefs:
        doc.db_set({"status": "Sent", "sent_on": now_datetime()}, update_modified=False)
    frappe.db.commit()


@frappe.whitelist()
def send(name):
    from hrms_addon.hrms_addon import people

    doc = frappe.get_doc(BRIEF, name)
    doc.check_permission("write")
    users = recipients(doc.branch) if doc.branch else [holder["user"] for holder in people.holders("HR Manager")]
    if not users:
        frappe.throw(_("Nobody holds the General Manager, Production Manager or HR roles for {0}.").format(
            doc.branch or _("the company")), title=_(BRIEF))
    for user in users:
        _mail(user, [doc])
    doc.db_set({"status": "Sent", "sent_on": now_datetime()})
    return users


def _mail(user, docs):
    email = frappe.db.get_value("User", user, "email") or user
    parts = []
    for doc in docs:
        try:
            parts.append(frappe.get_print(BRIEF, doc.name, print_format=PRINT))
        except Exception:
            parts.append("<p>%s</p>" % "<br>".join(frappe.utils.escape_html(line)
                                                  for line in (doc.talking_points or "").splitlines()))
    subject = _("HR Partner Brief {0}: {1}").format(docs[0].week, ", ".join(doc.branch or _("All Plants")
                                                                             for doc in docs))
    frappe.sendmail(recipients=[email], subject=subject, message="<hr>".join(parts),
                    reference_doctype=BRIEF, reference_name=docs[0].name)


# ── For the board pack ────────────────────────────────────────────────
def board_slide(company, start, end, branch=None):
    """The Manufacturing Excellence slide of the HR board pack: each plant's
    score and what moved it, the HR Excellence score and its red flags."""
    start, end = getdate(start), getdate(end)
    facts, s = summary.period_facts(start, end, company, branch)
    card = rules.pillars(facts, s)
    filters = summary.scope_filters(start, end, company, branch)
    plants = {}
    for (plant, section, _unit), totals in summary.grouped(filters, ("branch", "work_section", "unit")).items():
        plants.setdefault(plant, {})[section] = totals
    rows = []
    for plant, sections in sorted(plants.items()):
        scored = rules.section_scores(sections, s)
        t = rules.add_totals(*sections.values())
        a = rules.averages(t, s)
        score = rules.plant_score([row["score"] for row in scored])
        rows.append({"plant": plant, "score": score, "status": rules.rag(score, s), "money_lost": t["money_lost"],
                     "attendance": a["attendance"], "ppe": a["ppe"], "ot_share": a["ot_share"],
                     "incidents": int(t["safety_incidents"]), "verdict": rules.verdict(scored)})
    return {"title": _("Manufacturing Excellence"), "start": str(start), "end": str(end),
            "hr_score": card["composite"], "hr_status": card["status"], "red_flags": card["red_flags"],
            "pillars": [{"label": row["label"], "score": row["score"], "status": row["status"]}
                        for row in card["pillars"]],
            "plants": rows,
            "lines": [_("{0}: {1} ({2}). {3}").format(row["plant"], rules._plain(row["score"]) or _("no data"),
                                                      row["status"], row["verdict"]) for row in rows]}
