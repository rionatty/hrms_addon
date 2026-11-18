# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LMS phase 3 on the site; learning_delivery_rules.py has the rules.

  daily                  each session held: once its trainees have had time
                         to use it, a Training Application Review for each one
                         who came, on their supervisor's list; later, a
                         Training Impact Review for each KPI its programme
                         names, on the plant's HR Officer's list, its before
                         and after worked out from the Shift Reports where it
                         can be
  Application Review     scored from the supervisor's three answers; only the
                         supervisor it is for, or HR, answer it
  Impact Review          the KPI's way, its change and whether it improved;
                         "From Shift Reports" works the two periods out again
  Training Result        a trainee who did not pass is told, with their
                         supervisor and the plant's HR, to book it again
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import learning_delivery_rules as rules

REVIEW, IMPACT, EVENT = "Training Application Review", "Training Impact Review", "Training Event"
KPI_ROWS, KPI = "Training Program KPI", "Training KPI"
HR_ROLES = ("HR Manager", "HR User", "System Manager")
SEE_ALL = HR_ROLES + ("General Manager", "Executive Director", "Auditor")


def settings():
    from hrms_addon.hrms_addon import learning

    return learning.settings()


# ── Every day ─────────────────────────────────────────────────────────
def daily():
    s = settings()
    day = today()
    longest = max(int(s["application_review_days"]), int(s["impact_review_days"])) + rules.CATCH_UP_DAYS + 1
    events = frappe.get_all(EVENT, filters={"docstatus": 1, "event_status": ["!=", "Cancelled"],
                                            "end_time": ["between", [add_days(day, -longest), add_days(day, 1)]]},
                            fields=["name", "training_program", "start_time", "end_time", "custom_branch", "company"])
    levels = programme_levels({event.training_program for event in events if event.training_program})
    for event in events:
        try:
            rows = frappe.get_all("Training Event Employee", filters={"parent": event.name, "parenttype": EVENT},
                                  fields=["employee", "attendance"], order_by="idx asc")
            present = rules.reviewees({"employees": rows})
            wanted = levels.get(event.training_program) or rules.programme_levels({})
            if wanted["behaviour"] and rules.due_now(event.end_time, s["application_review_days"], day):
                _raise_reviews(event, present, day)
            if wanted["impact"] and rules.due_now(event.end_time, s["impact_review_days"], day):
                _raise_impacts(event, present, s)
        except Exception:
            frappe.log_error(title="HRMS Addon: training reviews for %s" % event.name)


def programme_levels(programmes):
    """{programme: {level: evaluated}} in one read; a programme with no level
    fields yet is evaluated at all four."""
    programmes = [name for name in programmes or () if name]
    if not programmes:
        return {}
    meta = frappe.get_meta("Training Program")
    fields = ["name"] + [field for _level, field in rules.LEVELS if meta.has_field(field)]
    return {row.name: rules.programme_levels(row) for row in frappe.get_all(
        "Training Program", filters={"name": ["in", programmes]}, fields=fields, limit_page_length=0)}


def _raise_reviews(event, present, day):
    """A review for each trainee who came, then one sheet a supervisor with
    their trainees' reviews on it, on their list once (learning_sheets)."""
    from hrms_addon.hrms_addon import learning_sheets

    by_supervisor = {}
    for employee in present:
        review = _raise_review(event, employee, day)
        if review:
            by_supervisor.setdefault(review.supervisor, []).append(review)
    for supervisor, reviews in by_supervisor.items():
        learning_sheets.review_sheet_for(event, supervisor, reviews, add_days(day, rules.REVIEW_DAYS_TO_ANSWER))
    return by_supervisor


def _raise_review(event, employee, day):
    if frappe.db.exists(REVIEW, {"training_event": event.name, "employee": employee}):
        return None
    facts = frappe.db.get_value("Employee", employee, ["employee_name", "department", "branch", "company",
                                                       "reports_to"], as_dict=True)
    if not facts or not facts.reports_to:
        return None
    reviewer = frappe.db.get_value("Employee", facts.reports_to, "user_id")
    doc = frappe.get_doc({"doctype": REVIEW, "training_event": event.name, "training_program": event.training_program,
                          "event_end": getdate(event.end_time), "employee": employee,
                          "employee_name": facts.employee_name, "department": facts.department, "branch": facts.branch,
                          "company": facts.company or event.company, "supervisor": facts.reports_to,
                          "reviewer": reviewer, "due_on": add_days(day, rules.REVIEW_DAYS_TO_ANSWER),
                          "status": rules.PENDING})
    doc.insert(ignore_permissions=True)
    return doc


def kpi_facts(names):
    """{kpi: its unit, way, source, measure, value per unit and window} from
    HR's list (Training KPI)."""
    names = [name for name in names or () if name]
    if not names:
        return {}
    return {row.name: row for row in frappe.get_all(
        KPI, filters={"name": ["in", names]},
        fields=["name", "unit", "better", "source", "shift_measure", "value_per_unit", "window_days"],
        limit_page_length=0)}


def _raise_impacts(event, present, s):
    if not event.training_program:
        return []
    kpis = frappe.get_all(KPI_ROWS, filters={"parent": event.training_program, "parenttype": "Training Program"},
                          fields=["kpi", "kpi_name", "target", "weight", "value_per_unit"], order_by="idx asc")
    if not kpis:
        return []
    facts = kpi_facts([row.kpi for row in kpis])
    have = {(row.kpi, row.kpi_name or "") for row in frappe.get_all(
        IMPACT, filters={"training_event": event.name}, fields=["kpi", "kpi_name"])}
    sections = frappe.get_all("Employee", filters={"name": ["in", present or [""]]}, pluck="custom_work_section")
    section = rules.main_section(sections)
    made = []
    for row in kpis:
        if (row.kpi, row.kpi_name or "") in have:
            continue
        kpi = facts.get(row.kpi) or frappe._dict()
        window = cint(kpi.get("window_days")) or s["impact_window_days"]
        before_from, before_to, after_from, after_to = rules.impact_windows(event.start_time, event.end_time, window)
        doc = frappe.get_doc({"doctype": IMPACT, "training_event": event.name,
                              "training_program": event.training_program, "event_end": getdate(event.end_time),
                              "branch": event.custom_branch, "company": event.company, "work_section": section,
                              "kpi": row.kpi, "kpi_name": row.kpi_name, "better": kpi.get("better"),
                              "target": row.get("target"), "weight": row.get("weight") or 1,
                              "value_per_unit": flt(row.get("value_per_unit")) or flt(kpi.get("value_per_unit")),
                              "baseline_from": before_from, "baseline_to": before_to, "after_from": after_from,
                              "after_to": after_to, "status": rules.OPEN})
        if section and kpi.get("source") == rules.SHIFT_REPORTS and kpi.get("shift_measure"):
            _measure(doc, kpi.get("shift_measure"))
        doc.insert(ignore_permissions=True)
        made.append(doc.name)
        from hrms_addon.hrms_addon import people

        people.assign(IMPACT, doc.name, people.hr_officers(event.custom_branch),
                      _("The impact of {0} on {1}").format(event.training_program, row.kpi_name or row.kpi))
    return made


def _measure(doc, measure=None):
    """The KPI before and after, from the section's Shift Reports."""
    from hrms_addon.hrms_addon import excellence

    if measure is None:
        measure = (kpi_facts([doc.kpi]).get(doc.kpi) or {}).get("shift_measure") or rules.KPI_FROM_SHIFTS.get(doc.kpi)
    s = excellence.settings()
    values = []
    for start, end in ((doc.baseline_from, doc.baseline_to), (doc.after_from, doc.after_to)):
        rows = excellence.shift_rows(start, end, section=doc.work_section)
        totals = excellence.rules.totals(rows, s)
        values.append(rules.measure_value(measure, totals, excellence.rules.averages(totals)))
    if values[0] is not None and values[1] is not None:
        doc.baseline, doc.after, doc.measured = values[0], values[1], 1
    return values


@frappe.whitelist()
def impact_from_shift_reports(name):
    doc = frappe.get_doc(IMPACT, name)
    doc.check_permission("write")
    kpi = kpi_facts([doc.kpi]).get(doc.kpi) or {}
    if kpi.get("source") != rules.SHIFT_REPORTS or not kpi.get("shift_measure"):
        frappe.throw(_("{0} is not on the Shift Reports: type its values.").format(doc.kpi_name or doc.kpi),
                     title=_(IMPACT))
    if not doc.work_section:
        frappe.throw(_("Pick the section to measure."), title=_(IMPACT))
    before, after = _measure(doc)
    if before is None or after is None:
        frappe.throw(_("{0} has no Shift Reports in the {1} period.").format(
            doc.work_section, _("before") if before is None else _("after")), title=_(IMPACT))
    doc.save()
    return {"baseline": doc.baseline, "after": doc.after}


# ── Level 3 ───────────────────────────────────────────────────────────
def review_validate(doc):
    for message in rules.review_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(REVIEW))
    if doc.supervisor and not doc.get("reviewer"):
        doc.reviewer = frappe.db.get_value("Employee", doc.supervisor, "user_id")
    if doc.supervisor:
        doc.supervisor_name = frappe.db.get_value("Employee", doc.supervisor, "employee_name")
    score = rules.review_score(doc.as_dict())
    if score is None:
        doc.score, doc.status, doc.reviewed_on = 0, rules.PENDING, None
    else:
        doc.score, doc.status = score, rules.DONE
        doc.reviewed_on = doc.get("reviewed_on") or today()


def review_query(user=None):
    """A supervisor lists the reviews that are theirs to give; HR and
    management all of them."""
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & set(SEE_ALL):
        return ""
    return "`tab{0}`.`reviewer` = {1}".format(REVIEW, frappe.db.escape(user))


def review_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & set(HR_ROLES):
        return True
    if set(frappe.get_roles(user)) & set(SEE_ALL):
        return ptype in (None, "read", "print", "email", "report", "export")
    return doc.get("reviewer") == user


# ── Level 4 ───────────────────────────────────────────────────────────
def impact_validate(doc):
    """The KPI's way and worth from HR's list; the change, whether it improved
    and reached the target, and what it is worth, worked out, never typed."""
    kpi = kpi_facts([doc.kpi]).get(doc.kpi) if doc.get("kpi") else None
    if kpi:
        doc.better = kpi.better or doc.get("better")
        doc.kpi_name = None
        if not flt(doc.get("value_per_unit")):
            doc.value_per_unit = flt(kpi.value_per_unit)
    for message in rules.impact_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(IMPACT))
    if cint(doc.get("measured")) or flt(doc.get("baseline")) or flt(doc.get("after")):
        change, percent, result = rules.impact_result(doc.better, flt(doc.baseline), flt(doc.after))
        doc.change, doc.change_percent, doc.result = change or 0, percent or 0, result
        doc.measured, doc.status = 1, rules.MEASURED
        doc.benefit = rules.benefit(change, doc.better, doc.get("value_per_unit"))
        doc.target_met = rules.target_met(flt(doc.after), doc.get("target"), doc.better) or 0
        if not doc.get("measured_by"):
            doc.measured_by = frappe.session.user
    else:
        doc.change, doc.change_percent, doc.result, doc.status, doc.measured = 0, 0, "", rules.OPEN, 0
        doc.benefit, doc.target_met = 0, 0


def programme_validate(doc, method=None):
    """A new toolbox talk is evaluated at levels 1 and 2 only; HR may turn any
    level on or off for a programme."""
    if doc.is_new() and doc.get("custom_delivery_mode") == rules.TOOLBOX:
        if frappe.get_meta("Training Program").has_field("custom_level_behaviour"):
            doc.custom_level_behaviour, doc.custom_level_impact = 0, 0
    for row in doc.get("custom_kpis") or []:
        if not flt(row.get("weight")):
            row.weight = 1


# ── Level 2 ───────────────────────────────────────────────────────────
def result_failed(doc, method=None):
    """Those who did not pass are told, with their supervisor and HR."""
    from hrms_addon.hrms_addon import people, training_rules

    before = doc.get_doc_before_save() if method == "on_update_after_submit" else None
    failed = rules.newly_failed([row.as_dict() for row in doc.get("employees") or []],
                                [row.as_dict() for row in before.get("employees") or []] if before else [],
                                training_rules.NOT_EFFECTIVE)
    programme = frappe.db.get_value(EVENT, doc.training_event, "training_program") if doc.get("training_event") \
        else None
    for employee in failed:
        facts = frappe.db.get_value("Employee", employee, ["employee_name", "user_id", "reports_to", "branch",
                                                           "department"], as_dict=True)
        if not facts:
            continue
        users = [facts.user_id] if facts.user_id else []
        if facts.reports_to:
            users.append(frappe.db.get_value("Employee", facts.reports_to, "user_id"))
        users += people.hr_officers(facts.branch, facts.department)
        users = list(dict.fromkeys(user for user in users if user))
        if users:
            people.notify(users, "Training Result", doc.name,
                          _("{0} did not pass {1}: book the training again").format(
                              facts.employee_name, programme or doc.training_event))
    return failed
