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
KPI_ROWS = "Training Program KPI"
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
    for event in events:
        try:
            rows = frappe.get_all("Training Event Employee", filters={"parent": event.name, "parenttype": EVENT},
                                  fields=["employee", "attendance"], order_by="idx asc")
            present = rules.reviewees({"employees": rows})
            if rules.due_now(event.end_time, s["application_review_days"], day):
                for employee in present:
                    _raise_review(event, employee, day)
            if rules.due_now(event.end_time, s["impact_review_days"], day):
                _raise_impacts(event, present, s)
        except Exception:
            frappe.log_error(title="HRMS Addon: training reviews for %s" % event.name)


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
    if reviewer:
        from hrms_addon.hrms_addon import people

        people.assign(REVIEW, doc.name, [reviewer],
                      _("How {0} has applied {1}").format(facts.employee_name,
                                                         event.training_program or event.name), date=doc.due_on)
    return doc.name


def _raise_impacts(event, present, s):
    if not event.training_program:
        return []
    kpis = frappe.get_all(KPI_ROWS, filters={"parent": event.training_program, "parenttype": "Training Program"},
                          fields=["kpi", "kpi_name", "better"], order_by="idx asc")
    if not kpis:
        return []
    have = {(row.kpi, row.kpi_name or "") for row in frappe.get_all(
        IMPACT, filters={"training_event": event.name}, fields=["kpi", "kpi_name"])}
    sections = frappe.get_all("Employee", filters={"name": ["in", present or [""]]}, pluck="custom_work_section")
    section = rules.main_section(sections)
    before_from, before_to, after_from, after_to = rules.impact_windows(event.start_time, event.end_time,
                                                                        s["impact_window_days"])
    made = []
    for row in kpis:
        if (row.kpi, row.kpi_name or "") in have:
            continue
        doc = frappe.get_doc({"doctype": IMPACT, "training_event": event.name,
                              "training_program": event.training_program, "event_end": getdate(event.end_time),
                              "branch": event.custom_branch, "company": event.company, "work_section": section,
                              "kpi": row.kpi, "kpi_name": row.kpi_name, "better": row.better,
                              "baseline_from": before_from, "baseline_to": before_to, "after_from": after_from,
                              "after_to": after_to, "status": rules.OPEN})
        if section and row.kpi in rules.KPI_FROM_SHIFTS:
            _measure(doc)
        doc.insert(ignore_permissions=True)
        made.append(doc.name)
        from hrms_addon.hrms_addon import people

        people.assign(IMPACT, doc.name, people.hr_officers(event.custom_branch),
                      _("The impact of {0} on {1}").format(event.training_program, row.kpi_name or row.kpi))
    return made


def _measure(doc):
    """The KPI before and after, from the section's Shift Reports."""
    from hrms_addon.hrms_addon import excellence

    s = excellence.settings()
    values = []
    for start, end in ((doc.baseline_from, doc.baseline_to), (doc.after_from, doc.after_to)):
        rows = excellence.shift_rows(start, end, section=doc.work_section)
        totals = excellence.rules.totals(rows, s)
        values.append(rules.kpi_from_totals(doc.kpi, totals, excellence.rules.averages(totals)))
    if values[0] is not None and values[1] is not None:
        doc.baseline, doc.after, doc.measured = values[0], values[1], 1
    return values


@frappe.whitelist()
def impact_from_shift_reports(name):
    doc = frappe.get_doc(IMPACT, name)
    doc.check_permission("write")
    if doc.kpi not in rules.KPI_FROM_SHIFTS:
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
    if doc.kpi in rules.KPI_BETTER:
        doc.better = rules.KPI_BETTER[doc.kpi]
    if doc.kpi != rules.OTHER:
        doc.kpi_name = None
    for message in rules.impact_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(IMPACT))
    if cint(doc.get("measured")) or flt(doc.get("baseline")) or flt(doc.get("after")):
        change, percent, result = rules.impact_result(doc.better, flt(doc.baseline), flt(doc.after))
        doc.change, doc.change_percent, doc.result = change or 0, percent or 0, result
        doc.measured, doc.status = 1, rules.MEASURED
        if not doc.get("measured_by"):
            doc.measured_by = frappe.session.user
    else:
        doc.change, doc.change_percent, doc.result, doc.status, doc.measured = 0, 0, "", rules.OPEN, 0


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
