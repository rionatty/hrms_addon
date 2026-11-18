# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Learning, Training & Certification on the site (Luuka's LMS, phases 1
and 2). The rules are in learning_rules.py, without a Frappe import
(scripts/verify_learning.py).

  Training Rule                  who must do which training, or hold which
                                 certificate; saving one brings everyone it
                                 applies to up to date in the background
  Employee Training Requirement  made and kept by refresh_employee: one per
                                 employee and rule, its status worked out
                                 from the sessions they attended (Frappe HR's
                                 Training Event and Training Result) and the
                                 certificates they hold. HR, heads of
                                 department and supervisors may recommend more
  Employee Certification         the register; a training that gives a
                                 certificate makes it, unchecked, for those
                                 who passed
  daily                          everything brought up to date; each
                                 certificate's expiry chased rung by rung, and
                                 training falling due or overdue told
  weekly                         each plant's HR told how much is done
  passport                       the Learning Passport's figures

An employee moved, promoted or regraded is brought up to date the same way
(employee_on_update): the rules decide afresh what they need.
"""

import datetime
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now, today

from hrms_addon.hrms_addon import learning_rules as rules, people
from hrms_addon.hrms_addon import training_rules

SETTINGS = "Learning Settings"
CATEGORY = "Training Category"
CERTIFICATION = "Certification"
CERTIFICATE = "Employee Certification"
RULE = "Training Rule"
REQUIREMENT = "Employee Training Requirement"
PROGRAMME = "Training Program"
EVENT = "Training Event"
RESULT = "Training Result"
EVENT_CANCELLED = "Cancelled"
# learning content an employee completed counts as doing its training
# (learning_library.py): its assignments are named LCA-...
CONTENT_ASSIGNMENT, CONTENT_PREFIX = "Learning Content Assignment", "LCA-"
CONTENT_DONE = ("Completed", "Passed")
# who sees anyone's passport (narrowed by their own permissions on the Employee)
HR_ROLES = ("System Manager", "HR Manager")
LOOK_ROLES = ("HR User", "General Manager", "Executive Director", "Head of Department", "Supervisor")
HEAD_ROLE, GM_ROLE = "Head of Department", "General Manager"
# the Employee fields a rule reads: a change to one of them is, to the rules,
# a move, a promotion or a new grade
WATCHED = ("company", "branch", "department", "designation", "grade", "employment_type", "status",
           "date_of_joining", "custom_operates_machinery", "custom_work_section")
# a change to one of these is a transfer or a promotion, which sets off the
# refreshers that ask for it
MOVES = ("branch", "department", "designation", "grade", "custom_work_section")
CHILD_TABLES = (("branches", "Training Rule Branch", "branch"),
                ("departments", "Training Rule Department", "department"),
                ("designations", "Training Rule Designation", "designation"),
                ("grades", "Training Rule Grade", "grade"),
                ("employment_types", "Training Rule Employment Type", "employment_type"))
# what a requirement's record holds, as refresh_employee writes it
KEPT = ("employee_name", "requirement_type", "training_program", "certification", "training_category",
        "due_date", "completed_on", "valid_until", "status", "company", "branch", "department",
        "designation", "training_rule", "required_since", "evidence_type", "evidence", "last_result",
        "work_section", "booking_status", "booked_event", "booked_for", "requisition", "triggered_on")
CHUNK = rules.CHUNK
# a requisition still asking for its training
REQUISITION_DONE = ("Closed", "Cancelled")
# the composite indexes the learning records are looked up by (add_indexes),
# and the pairs that may be there once only
INDEXES = {
    REQUIREMENT: (("status", "due_date"), ("branch", "department")),
    "Competency Assessment": (("employee", "skill"),),
    "Training Application Review": (("training_event", "employee"), ("reviewer", "status")),
    "Training Attendance": (("training_event", "session_date"), ("branch", "session_date")),
    "Learning Content Assignment": (("employee", "status"), ("branch", "work_section")),
}
UNIQUE = {
    REQUIREMENT: ("employee", "training_rule"),
    "Training Attendance": ("training_event", "employee", "session_date"),
    "Learning Content Assignment": ("learning_content", "employee"),
}


# ── Settings ──────────────────────────────────────────────────────────
def settings():
    """The Learning Settings, with the defaults for whatever is empty."""
    stored = frappe.get_cached_doc(SETTINGS)
    values = {key: stored.get(key) for key in rules.DEFAULTS}
    values["tiers"] = [row.as_dict() for row in stored.get("alert_tiers") or []]
    s = rules.settings_from(values)
    for key in ("notify_due_soon", "notify_overdue", "weekly_digest"):
        value = stored.get(key)
        s[key] = 1 if value is None else cint(value)
    return s


def settings_validate(doc):
    errors = rules.settings_errors(dict(doc.as_dict(), tiers_rows=[row.as_dict() for row in doc.alert_tiers]))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SETTINGS))


def setup_on_migrate():
    """The blueprint's categories and the alert ladder, made once and then
    HR's to change."""
    try:
        for index, (name, mandatory) in enumerate(rules.CATEGORIES, 1):
            if not frappe.db.exists(CATEGORY, name):
                frappe.get_doc({"doctype": CATEGORY, "category_name": name, "mandatory": mandatory,
                                "matrix_order": index}).insert(ignore_permissions=True)
        doc = frappe.get_single(SETTINGS)
        if not doc.get("alert_tiers"):
            for days, who in rules.DEFAULT_TIERS:
                doc.append("alert_tiers", dict({"days_before": days}, **{audience: 1 for audience in who}))
            for key, value in rules.DEFAULTS.items():
                if doc.get(key) in (None, ""):
                    doc.set(key, value)
            for key in ("notify_due_soon", "notify_overdue", "weekly_digest"):
                if doc.get(key) is None:
                    doc.set(key, 1)
            doc.flags.ignore_permissions = True
            doc.save()
    except Exception:
        frappe.log_error(title="HRMS Addon: setting up Learning")


# ── The catalogue ─────────────────────────────────────────────────────
def certification_validate(doc):
    doc.certification_name = (doc.certification_name or "").strip()
    if cint(doc.get("validity_months")) < 0:
        frappe.throw(_("Valid For cannot be less than nought months."), title=_(CERTIFICATION))


# ── The rule ──────────────────────────────────────────────────────────
def rule_validate(doc):
    errors = rules.rule_errors(doc.as_dict())
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(RULE))
    if doc.requirement_type == rules.CERTIFICATION:
        doc.training_program = None
        doc.repeat = rules.ONCE
    else:
        doc.certification = None
    if not doc.get("trigger"):
        doc.trigger_reach, doc.absence_days = None, 0
    elif not doc.get("trigger_reach"):
        doc.trigger_reach = rules.THE_EMPLOYEE
    if not doc.get("applies_from"):
        doc.applies_from = today()


def rule_on_update(doc):
    """Everyone the rule applies to (and anyone it no longer does), brought
    up to date in the background."""
    frappe.enqueue("hrms_addon.hrms_addon.learning.refresh_rule", queue="long", timeout=3600,
                   enqueue_after_commit=True, rule=doc.name)


def rule_on_trash(doc):
    """A rule deleted takes what it asked for with it: those records are the
    rule's, not anybody's work."""
    frappe.db.delete(REQUIREMENT, {"training_rule": doc.name})


# ── The requirement somebody recommends ───────────────────────────────
def requirement_validate(doc):
    """A rule's requirement is the rule's: only a recommendation is made
    and changed by hand (TNA step 4: HR, heads of department and supervisors
    add training beyond the rules)."""
    if doc.get("training_rule"):
        if doc.is_new():
            frappe.throw(_("A rule's requirement is made by its rule."), title=_(REQUIREMENT))
        return
    doc.requirement_type = rules.RECOMMENDED
    doc.certification = None
    if not doc.get("training_program"):
        frappe.throw(_("Pick the training recommended."), title=_(REQUIREMENT))
    employee = frappe.db.get_value("Employee", doc.employee,
                                   ["employee_name", "status", "company", "branch", "department", "designation"],
                                   as_dict=True)
    if not employee:
        frappe.throw(_("Pick the employee."), title=_(REQUIREMENT))
    if employee.status != rules.ACTIVE and doc.is_new():
        frappe.throw(_("{0} is not an active employee.").format(employee.employee_name), title=_(REQUIREMENT))
    for field in ("employee_name", "company", "branch", "department", "designation"):
        doc.set(field, employee.get(field))
    doc.training_category = _programme_category(doc.training_program)
    if doc.is_new():
        doc.recommended_by = frappe.session.user
        doc.required_since = today()
        if frappe.db.exists(REQUIREMENT, {"employee": doc.employee, "training_program": doc.training_program,
                                          "requirement_type": rules.RECOMMENDED,
                                          "status": ["not in", [rules.COMPLIANT, rules.NOT_APPLICABLE]]}):
            frappe.throw(_("{0} already has {1} recommended and not yet done.").format(
                employee.employee_name, doc.training_program), title=_(REQUIREMENT))
    done, results = _completions([doc.employee])
    state = rules.programme_state(doc.get("due_date"), 0, done.get(doc.employee, {}).get(doc.training_program))
    _fill(doc, state, results.get(doc.employee, {}).get(doc.training_program))
    doc.status = rules.status_on(dict(doc.as_dict(), status=None), getdate(today()), settings())


def _fill(doc, state, last_result):
    doc.completed_on, doc.valid_until = state["completed_on"], state["valid_until"]
    doc.evidence_type = _proof_type(state["evidence"]) if state["evidence"] else None
    doc.evidence = state["evidence"]
    doc.last_result = last_result


# ── The certificate ───────────────────────────────────────────────────
def certificate_validate(doc):
    day = getdate(today())
    if not doc.get("expiry_date") and doc.get("certification"):
        months = frappe.db.get_value(CERTIFICATION, doc.certification, "validity_months")
        doc.expiry_date = rules.expiry_for(doc.issue_date, months)
    errors = rules.certificate_errors(doc.as_dict(), day)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(CERTIFICATE))
    _refuse_twice(doc)
    _stamp_verification(doc)
    if doc.is_new():
        # entered already run out: HR know, nobody is chased about it
        if doc.expiry_date and getdate(doc.expiry_date) < day:
            doc.alerts_sent = "0"
    elif doc.has_value_changed("expiry_date"):
        # a new expiry is chased afresh
        doc.alerts_sent = None
    doc.status = rules.certificate_status(doc.as_dict(), day, settings())


def _refuse_twice(doc):
    same = {"employee": doc.employee, "certification": doc.certification, "name": ["!=", doc.name or ""]}
    if doc.get("certificate_no"):
        twice = frappe.db.get_value(CERTIFICATE, dict(same, certificate_no=doc.certificate_no), "name")
        if twice:
            frappe.throw(_("{0} already has {1} number {2}: {3}.").format(
                doc.get("employee_name") or doc.employee, doc.certification, doc.certificate_no, twice),
                title=_(CERTIFICATE))
    twice = frappe.db.get_value(CERTIFICATE, dict(same, issue_date=doc.issue_date), "name")
    if twice:
        frappe.throw(_("{0} already has {1} issued on {2}: {3}.").format(
            doc.get("employee_name") or doc.employee, doc.certification,
            frappe.utils.format_date(doc.issue_date), twice), title=_(CERTIFICATE))


def _stamp_verification(doc):
    """Only HR check a certificate; whoever did, and when, is kept."""
    status = doc.get("verification_status") or rules.UNVERIFIED
    before = doc.get_doc_before_save()
    was = (before.get("verification_status") if before else None) or rules.UNVERIFIED
    if status == was:
        return
    if not set(frappe.get_roles()) & set(HR_ROLES + ("HR User",)):
        frappe.throw(_("Only HR check a certificate."), frappe.PermissionError)
    if status == rules.UNVERIFIED:
        doc.verified_by = doc.verified_on = None
    else:
        doc.verified_by, doc.verified_on = frappe.session.user, today()


def certificate_on_update(doc):
    """A newer certificate renews the older ones of the same kind; revoked
    or refused by HR, it lets them stand again. The employee's requirements
    are brought up to date."""
    if cint(doc.get("revoked")) or doc.get("verification_status") == rules.REJECTED:
        _release(doc.name)
    else:
        mine = _key(doc)
        for older in frappe.get_all(CERTIFICATE, filters={"employee": doc.employee,
                                                          "certification": doc.certification,
                                                          "name": ["!=", doc.name], "revoked": 0,
                                                          "renewed_by": ["is", "not set"]},
                                    fields=["name", "issue_date", "expiry_date"]):
            if _key(older) < mine:
                frappe.db.set_value(CERTIFICATE, older.name, {"renewed_by": doc.name, "status": rules.RENEWED},
                                    update_modified=False)
    refresh_later([doc.employee])


def certificate_on_trash(doc):
    """The certificates it renewed stand again, and nothing points at it."""
    _release(doc.name)
    _let_go(doc.name)
    refresh_later([doc.employee])


def _release(name):
    """The certificates this one renewed stand again, each with its own status."""
    s, day = settings(), getdate(today())
    for older in frappe.get_all(CERTIFICATE, filters={"renewed_by": name}, fields=["name", "expiry_date", "revoked"]):
        frappe.db.set_value(CERTIFICATE, older.name, {
            "renewed_by": None, "status": rules.certificate_status(dict(older, renewed_by=None), day, s)},
            update_modified=False)


def _key(row):
    return (getdate(row.get("expiry_date")) if row.get("expiry_date") else datetime.date.max,
            getdate(row.get("issue_date")))


def _let_go(name):
    """Requirements naming a record as their proof let go of it, so that it
    can be cancelled or deleted."""
    for requirement in frappe.get_all(REQUIREMENT, filters={"evidence": name}, pluck="name"):
        frappe.db.set_value(REQUIREMENT, requirement, {"evidence": None, "evidence_type": None},
                            update_modified=False)


# ── What changes the picture ──────────────────────────────────────────
def employee_on_update(doc, method=None):
    """A new employee, or one moved, promoted, regraded or gone: the rules
    decide afresh what they need, and a move sets off the refreshers that
    ask for one."""
    before = doc.get_doc_before_save()
    if before and not any(str(before.get(field) or "") != str(doc.get(field) or "") for field in WATCHED):
        return
    if before and doc.get("status") == rules.ACTIVE and any(
            str(before.get(field) or "") != str(doc.get(field) or "") for field in MOVES):
        frappe.enqueue("hrms_addon.hrms_addon.learning.trigger", queue="short", enqueue_after_commit=True,
                       kind=rules.MOVED, employees=[doc.name], day=today(),
                       note=_("Moved to {0}").format(", ".join(str(doc.get(field)) for field in MOVES
                                                               if doc.get(field) and str(before.get(field) or "")
                                                               != str(doc.get(field) or ""))))
    refresh_later([doc.name])


def event_changed(doc, method=None):
    """A session held, changed or cancelled: what its people have done."""
    if method == "on_cancel":
        _let_go(doc.name)
    sync_certificates(doc.name)
    refresh_later([row.employee for row in doc.get("employees") or []])


def event_on_trash(doc, method=None):
    _let_go(doc.name)


def result_changed(doc, method=None):
    """Marks given or taken back: who passed."""
    if doc.get("training_event"):
        sync_certificates(doc.training_event)
    refresh_later([row.employee for row in doc.get("employees") or []])


def refresh_later(employees):
    employees = sorted({employee for employee in employees or () if employee})
    if employees:
        frappe.enqueue("hrms_addon.hrms_addon.learning.refresh_employees",
                       queue="short" if len(employees) <= 20 else "long", timeout=3600,
                       enqueue_after_commit=True, employees=employees)


# ── A training that gives a certificate ───────────────────────────────
def sync_certificates(training_event):
    """Each person who passed a session whose training gives a certificate
    holds it, unchecked, from the session's last day. One who no longer
    passed (the session cancelled, a result entered) loses the one it made,
    unless HR have checked it already."""
    event = frappe.db.get_value(EVENT, training_event, ["name", "docstatus", "event_status", "training_program",
                                                        "start_time", "end_time", "supplier"], as_dict=True)
    if not event:
        return
    certification = _gives(event.training_program)
    made = {row.employee: row for row in frappe.get_all(CERTIFICATE, filters={"training_event": event.name},
                                                         fields=["name", "employee", "verification_status"])}
    passed = set()
    if certification and event.docstatus == 1 and event.event_status != EVENT_CANCELLED:
        passed = set(_passed(event.name))
    issued = getdate(event.end_time or event.start_time) if (event.end_time or event.start_time) else None
    cost = flt(frappe.db.get_value(PROGRAMME, event.training_program, "custom_cost_per_person")) \
        if event.training_program and _has(PROGRAMME, "custom_cost_per_person") else 0
    for employee in sorted(passed - set(made)):
        try:
            frappe.get_doc({"doctype": CERTIFICATE, "employee": employee, "certification": certification,
                            "issue_date": issued, "training_event": event.name, "provider": event.supplier,
                            "cost": cost, "verification_status": rules.UNVERIFIED,
                            "remarks": _("Given by the training {0}.").format(event.name)}).insert(
                ignore_permissions=True)
        except frappe.ValidationError:
            # already holds it from that day, or the session is dated ahead: HR enter it themselves
            frappe.clear_last_message()
    for employee, row in made.items():
        if employee not in passed and row.verification_status == rules.UNVERIFIED:
            frappe.delete_doc(CERTIFICATE, row.name, ignore_permissions=True, force=True)


def _gives(programme):
    if not programme or not _has(PROGRAMME, "custom_certification"):
        return None
    return frappe.db.get_value(PROGRAMME, programme, "custom_certification")


def _passed(training_event):
    """Those marked Present whose marks, where any are entered, did not
    find the training ineffective for them."""
    present = frappe.get_all("Training Event Employee",
                             filters={"parenttype": EVENT, "parent": training_event,
                                      "attendance": training_rules.PRESENT},
                             pluck="employee")
    failed = {key[1] for key, result in _results([training_event], present).items()
              if result.get("custom_effective") == training_rules.NOT_EFFECTIVE}
    return [employee for employee in present if employee not in failed]


# ── The engine ────────────────────────────────────────────────────────
def refresh_rule(rule):
    """Everyone the rule asks something of, and everyone it asked before."""
    rules_by_name = _rules([rule], enabled_only=False)
    if not rules_by_name:
        return {"added": 0, "changed": 0}
    employees = set(frappe.get_all("Employee", filters={"status": rules.ACTIVE}, pluck="name"))
    employees |= set(frappe.get_all(REQUIREMENT, filters={"training_rule": rule}, pluck="employee", distinct=True))
    return _refresh_many(sorted(employees), rules_by_name, only_rule=rule)


def refresh_employees(employees):
    return _refresh_many(sorted({employee for employee in employees or () if employee}), _rules())


def refresh_all():
    """Everyone active, and anyone gone who still has something required."""
    employees = set(frappe.get_all("Employee", filters={"status": rules.ACTIVE}, pluck="name"))
    employees |= set(frappe.get_all(REQUIREMENT, filters={"status": ["!=", rules.NOT_APPLICABLE]},
                                    pluck="employee", distinct=True))
    return _refresh_many(sorted(employees), _rules())


def _refresh_many(employees, rules_by_name, only_rule=None):
    """A hundred employees at a time, each part read in a handful of queries
    and committed before the next, so a refresh of the whole company neither
    holds a long transaction nor asks the database once per person."""
    s, day = settings(), getdate(today())
    added = changed = 0
    for part in rules.chunks(employees, CHUNK):
        found = _refresh_chunk(part, rules_by_name, s, day, only_rule)
        added, changed = added + found["added"], changed + found["changed"]
        frappe.db.commit()
    return {"added": added, "changed": changed}


def refresh_employee(employee, rules_by_name=None, s=None, day=None, only_rule=None):
    """One employee brought up to date: {"added", "changed"}."""
    rules_by_name = _rules() if rules_by_name is None else rules_by_name
    return _refresh_chunk([employee], rules_by_name, s or settings(), day or getdate(today()), only_rule)


def _refresh_chunk(employees, rules_by_name, s, day, only_rule=None):
    """Bring a part of the staff's requirements up to date. Returns
    {"added", "changed"}.

    Everything the part needs is read once for all of it: who they are, what
    they hold now, what they attended and passed, the sessions they are
    booked on, their certificates and the requisitions still open for them.
    Every rule that applies to an employee has its requirement, worked out
    from that; one that no longer applies (they moved, were promoted, left;
    the rule was disabled) is kept as Not Applicable. A recommendation is
    worked out the same way, its due date the one given.
    """
    facts = _employees(employees)
    filters = {"employee": ["in", list(employees)]}
    if only_rule:
        filters["training_rule"] = only_rule
    rows = frappe.get_all(REQUIREMENT, filters=filters, fields=["name", "employee"] + list(KEPT),
                          limit_page_length=0)
    mine = {}
    for row in rows:
        mine.setdefault(row.employee, []).append(row)
    done, results, booked = _participation(employees, day)
    held = _certificates(employees)
    requested = _open_requisitions([row.requisition for row in rows if row.get("requisition")])
    renewals = _renewal_programmes([rule.get("certification") for rule in rules_by_name.values()
                                    if rule.get("certification")])
    added = changed = 0
    for employee in employees:
        person = facts.get(employee)
        if not person:
            continue
        theirs = mine.get(employee, [])
        by_rule = {row.training_rule: row for row in theirs if row.training_rule}
        context = {"done": done.get(employee, {}), "results": results.get(employee, {}),
                   "held": held.get(employee, {}), "booked": booked.get(employee, {}), "requested": requested,
                   "renewals": renewals}
        for name, rule in rules_by_name.items():
            if only_rule and name != only_rule:
                continue
            row = by_rule.get(name)
            values = _wanted(rule, person, row, context, s, day)
            if values:
                if row:
                    changed += _write(row, values)
                else:
                    _insert(values)
                    added += 1
            elif row and row.status != rules.NOT_APPLICABLE:
                changed += _write(row, _employee_values(person, {"status": rules.NOT_APPLICABLE,
                                                                 "booking_status": None, "booked_event": None,
                                                                 "booked_for": None}))
        if not only_rule:
            for row in theirs:
                if row.training_rule and row.training_rule not in rules_by_name \
                        and row.status != rules.NOT_APPLICABLE:
                    changed += _write(row, {"status": rules.NOT_APPLICABLE})
                elif not row.training_rule:
                    changed += _write(row, _recommended(row, person, context, s, day))
    return {"added": added, "changed": changed}


def _wanted(rule, facts, row, context, s, day):
    """The record the rule asks for, or None where it asks nothing of them."""
    if not (cint(rule.get("enabled")) and rules.in_scope(rule, facts)):
        return None
    if rules.triggered(rule):
        # asked only once an event set it off, and afresh each time: what was
        # done before the event does not count
        on = row.get("triggered_on") if row else None
        if not on or (row.status == rules.NOT_APPLICABLE and not row.get("retriggered")):
            return None
        since, first, after = getdate(on), rules.trigger_due(rule, on), on
    else:
        # required since they came under the rule; afresh if it had stopped applying
        since = row.required_since if row and row.status != rules.NOT_APPLICABLE and row.required_since else day
        first, after = rules.first_due(rule, facts, since), None
    if first is None:
        return None
    if rule["requirement_type"] == rules.CERTIFICATION:
        state = rules.certificate_state(first, context["held"].get(rule["certification"]), s["only_verified"])
        proof, last = CERTIFICATE, None
        programme = context["renewals"].get(rule["certification"])
    else:
        state = rules.programme_state(first, rules.repeat_months(rule), context["done"].get(rule["training_program"]),
                                      since=after)
        proof, last = _proof_type(state["evidence"]), context["results"].get(rule["training_program"])
        programme = rule["training_program"]
    values = _employee_values(facts, {
        "employee": facts.name, "requirement_type": rule["requirement_type"],
        "training_program": rule.get("training_program"), "certification": rule.get("certification"),
        "training_category": rule.get("category"), "due_date": state["due_date"],
        "completed_on": state["completed_on"], "valid_until": state["valid_until"],
        "training_rule": rule["name"], "required_since": since,
        "evidence_type": proof if state["evidence"] else None, "evidence": state["evidence"], "last_result": last,
    })
    values["status"] = rules.status_on(values, day, s)
    values.update(_booking(values, row, programme, context, day))
    return values


def _proof_type(evidence):
    """A session's name, or a learning content assignment's (LCA-...)."""
    return CONTENT_ASSIGNMENT if str(evidence or "").startswith(CONTENT_PREFIX) else EVENT


def _booking(values, row, programme, context, day):
    """Booked on a session still to be held, or Requested while a requisition
    for it is open; nothing once it is done and counting."""
    if values.get("status") == rules.COMPLIANT:
        return {"booking_status": None, "booked_event": None, "booked_for": None}
    sessions = context["booked"].get(programme) if programme else None
    open_request = bool(row and row.get("requisition") and row.get("requisition") in context["requested"])
    status, event, on = rules.booking_of(sessions, open_request, day)
    return {"booking_status": status, "booked_event": event, "booked_for": on}


def _recommended(row, facts, context, s, day):
    if facts.status != rules.ACTIVE:
        return {"status": rules.NOT_APPLICABLE}
    state = rules.programme_state(row.due_date, 0, context["done"].get(row.training_program))
    values = _employee_values(facts, {
        "completed_on": state["completed_on"], "valid_until": state["valid_until"],
        "evidence_type": _proof_type(state["evidence"]) if state["evidence"] else None,
        "evidence": state["evidence"], "last_result": context["results"].get(row.training_program)})
    values["status"] = rules.status_on(dict(row, **values, status=None), day, s)
    values.update(_booking(values, row, row.training_program, context, day))
    return values


def _employee_values(facts, values):
    values.update({"employee_name": facts.employee_name, "company": facts.company, "branch": facts.branch,
                   "department": facts.department, "designation": facts.designation,
                   "work_section": facts.get("work_section")})
    return values


def _write(row, values):
    changed = {field: value for field, value in values.items() if field != "employee"
               and str(row.get(field) if row.get(field) is not None else "")
               != str(value if value is not None else "")}
    if changed:
        frappe.db.set_value(REQUIREMENT, row.name, changed, update_modified=False)
        row.update(changed)
    return 1 if changed else 0


def _insert(values):
    """A rule's requirement, written as it is: nothing about it is typed in.
    An employee holds one per rule (the table's unique key): where another
    job wrote it first, that one is brought up to date instead."""
    doc = frappe.new_doc(REQUIREMENT)
    doc.update(values)
    doc.flags.ignore_permissions = True
    doc.set_new_name()
    doc.owner = doc.modified_by = frappe.session.user
    doc.creation = doc.modified = now()
    try:
        doc.db_insert()
    except Exception as error:
        twice = tuple(getattr(frappe, name) for name in ("UniqueValidationError", "DuplicateEntryError")
                      if hasattr(frappe, name))
        if not (twice and isinstance(error, twice)):
            raise
        frappe.clear_last_message()
        found = frappe.db.get_value(REQUIREMENT, {"employee": values.get("employee"),
                                                  "training_rule": values.get("training_rule")},
                                    ["name"] + list(KEPT), as_dict=True)
        if not found:
            raise
        _write(found, values)
        return found.name
    return doc.name


def add_indexes(doctype=None):
    """on_doctype_update and the lms_indexes patch: the composite indexes the
    learning records are looked up by, and the pairs held once only. A
    speed-up and a guard; a table that will not take one (old duplicates,
    say) is logged and holds nothing else up."""
    for name in ([doctype] if doctype else sorted(set(INDEXES) | set(UNIQUE))):
        if not frappe.db.table_exists(name):
            continue
        for fields in INDEXES.get(name, ()):
            try:
                frappe.db.add_index(name, list(fields))
            except Exception:
                frappe.log_error(title="Learning: index on %s %s" % (name, ", ".join(fields)))
        if UNIQUE.get(name):
            try:
                frappe.db.add_unique(name, list(UNIQUE[name]), constraint_name="unique_" + "_".join(UNIQUE[name]))
            except Exception:
                frappe.log_error(title="Learning: unique key on %s" % name)


# ── What the engine reads ─────────────────────────────────────────────
def _rules(names=None, enabled_only=True):
    """{name: rule} with its lists and its training's category."""
    filters = {"enabled": 1} if enabled_only else {}
    if names:
        filters["name"] = ["in", list(names)]
    found = {row.name: dict(row) for row in frappe.get_all(
        RULE, filters=filters,
        fields=["name", "enabled", "requirement_type", "training_program", "certification", "due_within_days",
                "repeat", "applies_from", "company", "operators_only", "trigger", "trigger_reach",
                "absence_days"], limit_page_length=0)}
    if not found:
        return {}
    for table, child, field in CHILD_TABLES:
        for rule in found.values():
            rule[table] = []
        for row in frappe.get_all(child, filters={"parenttype": RULE, "parent": ["in", list(found)]},
                                  fields=["parent", field], limit_page_length=0):
            found[row.parent][table].append(row.get(field))
    for rule in found.values():
        rule["category"] = (_certification_category(rule["certification"])
                            if rule["requirement_type"] == rules.CERTIFICATION
                            else _programme_category(rule["training_program"]))
    return found


def _programme_category(programme):
    if not programme or not _has(PROGRAMME, "custom_training_category"):
        return None
    return frappe.db.get_value(PROGRAMME, programme, "custom_training_category")


def _certification_category(certification):
    return frappe.db.get_value(CERTIFICATION, certification, "training_category") if certification else None


EMPLOYEE_FIELDS = ["name", "employee_name", "status", "company", "branch", "department", "designation", "grade",
                   "employment_type", "date_of_joining", "reports_to", "user_id"]


def _employee_fields():
    fields = list(EMPLOYEE_FIELDS)
    for field in ("custom_operates_machinery", "custom_work_section", "cell_number"):
        if _has("Employee", field):
            fields.append(field)
    return fields


def _facts(row):
    row.operates_machinery = row.get("custom_operates_machinery")
    row.work_section = row.get("custom_work_section")
    return row


def _employee(employee):
    facts = frappe.db.get_value("Employee", employee, _employee_fields(), as_dict=True)
    return _facts(facts) if facts else facts


def _employees(names):
    """{employee: what the rules read of them}, in one read."""
    names = [name for name in names or () if name]
    if not names:
        return {}
    return {row.name: _facts(row) for row in frappe.get_all("Employee", filters={"name": ["in", names]},
                                                            fields=_employee_fields(), limit_page_length=0)}


def _completions(employees):
    """({employee: {training: [(day, proof)]}}, {employee: {training: last result}}): the sessions
    each attended and passed, and how the last one went."""
    done, last, _booked = _participation(employees)
    return done, last


def _participation(employees, day=None):
    """What a part of the staff did and will do, from one read of the
    sessions they are on:
      done    {employee: {training: [(day, proof)]}}: the sessions they
              attended and passed, and the learning content they completed
      last    {employee: {training: how the last session went}}
      booked  {employee: {training: [(day, session)]}}: the sessions still to
              be held (a draft, not cancelled) they are on"""
    done, last, booked = {}, {}, {}
    employees = list(employees or ())
    if not employees:
        return done, last, booked
    rows = frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "employee": ["in", employees]},
                          fields=["parent", "employee", "attendance"], limit_page_length=0)
    events = {row.name: row for row in frappe.get_all(
        EVENT, filters={"name": ["in", list({row.parent for row in rows}) or [""]],
                        "event_status": ["!=", EVENT_CANCELLED], "docstatus": ["<", 2]},
        fields=["name", "training_program", "start_time", "end_time", "docstatus"],
        limit_page_length=0)} if rows else {}
    held = [name for name, event in events.items() if event.docstatus == 1]
    results = _results(held, employees)
    attempts = {}
    for row in rows:
        event = events.get(row.parent)
        if not event or not event.training_program:
            continue
        when = getdate(event.end_time or event.start_time) if (event.end_time or event.start_time) else None
        if event.docstatus == 0:
            booked.setdefault(row.employee, {}).setdefault(event.training_program, []).append(
                (getdate(event.start_time) if event.start_time else when, event.name))
            continue
        if row.attendance != training_rules.PRESENT:
            continue
        result = results.get((event.name, row.employee), {})
        failed = result.get("custom_effective") == training_rules.NOT_EFFECTIVE
        attempts.setdefault((row.employee, event.training_program), []).append((when, event.name, result, failed))
        if not failed and when:
            done.setdefault(row.employee, {}).setdefault(event.training_program, []).append((when, event.name))
    for (employee, programme), tries in attempts.items():
        when, _event, result, failed = max(tries, key=lambda attempt: str(attempt[0]))
        last.setdefault(employee, {})[programme] = _result_text(when, result, failed)
    for employee, programmes in _content_done(employees).items():
        for programme, proofs in programmes.items():
            done.setdefault(employee, {}).setdefault(programme, []).extend(proofs)
    return done, last, booked


def _content_done(employees):
    """{employee: {training: [(day, assignment)]}}: learning content linked to
    a training that each completed (and acknowledged, where it asks for that)
    or whose quiz they passed (learning_library.py)."""
    out = {}
    for row in frappe.get_all(CONTENT_ASSIGNMENT, filters={"employee": ["in", list(employees)],
                                                           "training_program": ["is", "set"],
                                                           "status": ["in", list(CONTENT_DONE)]},
                              fields=["name", "employee", "training_program", "completed_on"], limit_page_length=0):
        if row.completed_on:
            out.setdefault(row.employee, {}).setdefault(row.training_program, []).append(
                (getdate(row.completed_on), row.name))
    return out


def _open_requisitions(names):
    """The requisitions among these still asking for their training."""
    names = list({name for name in names or () if name})
    if not names:
        return set()
    return set(frappe.get_all("Training Requisition", filters={"name": ["in", names], "docstatus": ["<", 2],
                                                               "status": ["not in", list(REQUISITION_DONE)]},
                              pluck="name"))


def _renewal_programmes(certifications):
    """{certification: the training that renews it}: the one it names, else
    a training that gives it."""
    certifications = list({name for name in certifications or () if name})
    if not certifications:
        return {}
    found = {row.name: row.renewal_program for row in frappe.get_all(
        CERTIFICATION, filters={"name": ["in", certifications]}, fields=["name", "renewal_program"],
        limit_page_length=0) if row.renewal_program}
    if _has(PROGRAMME, "custom_certification") and len(found) < len(certifications):
        for row in frappe.get_all(PROGRAMME, filters={"custom_certification": ["in", certifications]},
                                  fields=["name", "custom_certification"], order_by="name asc",
                                  limit_page_length=0):
            found.setdefault(row.custom_certification, row.name)
    return found
def _result_text(day, result, failed):
    when = frappe.utils.format_date(day) if day else ""
    if _marked(result):
        return _("{0}, {1} marks, {2}").format(
            result.get("custom_effective") or (_("Not Effective") if failed else _("Effective")),
            "%g" % flt(result.get("custom_marks")), when)
    return _("Attended {0}").format(when)


def _marked(result):
    """Marks were given: the result says whether the training was effective
    only then (training_rules.effectiveness). The marks column itself reads
    nought where nobody typed any."""
    return bool(result and result.get("custom_effective"))


def assessment_averages(employees, day=None):
    """{employee: their average marks over the last year's results}."""
    day = day or getdate(today())
    rows = [row for row in frappe.get_all(
        "Training Result Employee", filters={"parenttype": RESULT, "employee": ["in", list(employees or [])]},
        fields=["parent", "employee", "custom_marks", "custom_effective"], limit_page_length=0)
        if _marked(row)] if employees else []
    if not rows:
        return {}
    sessions = {row.name: row.training_event for row in frappe.get_all(
        RESULT, filters={"name": ["in", list({row.parent for row in rows})], "docstatus": 1},
        fields=["name", "training_event"], limit_page_length=0)}
    held = {row.name: getdate(row.end_time or row.start_time) for row in frappe.get_all(
        EVENT, filters={"name": ["in", list(set(sessions.values()) or {""})]},
        fields=["name", "start_time", "end_time"], limit_page_length=0) if row.end_time or row.start_time}
    marks = {}
    for row in rows:
        when = held.get(sessions.get(row.parent))
        if when and (day - when).days <= 365:
            marks.setdefault(row.employee, []).append(flt(row.custom_marks))
    return {employee: round(sum(values) / len(values), 1) for employee, values in marks.items()}


def _results(events, employees):
    """{(session, employee): its submitted result row}."""
    if not events or not employees:
        return {}
    submitted = {row.name: row.training_event for row in frappe.get_all(
        RESULT, filters={"training_event": ["in", list(events)], "docstatus": 1},
        fields=["name", "training_event"], limit_page_length=0)}
    if not submitted:
        return {}
    out = {}
    for row in frappe.get_all("Training Result Employee",
                              filters={"parenttype": RESULT, "parent": ["in", list(submitted)],
                                       "employee": ["in", list(employees)]},
                              fields=["parent", "employee", "hours", "custom_marks", "custom_effective"],
                              limit_page_length=0):
        out[(submitted[row.parent], row.employee)] = row
    return out


def _certificates(employees):
    """{employee: {certification: [certificates]}}."""
    out = {}
    for row in frappe.get_all(CERTIFICATE, filters={"employee": ["in", list(employees)]},
                              fields=["name", "employee", "certification", "issue_date", "expiry_date", "status",
                                      "verification_status", "revoked", "renewed_by"],
                              limit_page_length=0):
        out.setdefault(row.employee, {}).setdefault(row.certification, []).append(row)
    return out


def _has(doctype, fieldname):
    return frappe.get_meta(doctype).has_field(fieldname)


# ── Every day ─────────────────────────────────────────────────────────
def daily():
    """Everything brought up to date (whatever a job missed), each
    certificate's expiry chased, and training falling due or overdue told:
    each person told gets one digest for the day, whatever it lists."""
    refresh_all()
    s, day = settings(), getdate(today())
    digest = Digest()
    chase_certificates(s, day, digest)
    chase_requirements(s, day, digest)
    digest.send()
    frappe.db.commit()


class Digest:
    """What each person is told today, gathered from every chase and sent as
    one notice each: never one per employee or per certificate. Those with
    no user of their own are sent an SMS where the settings ask for it
    (learning_loop.message_employees)."""

    def __init__(self):
        self.items, self.texts = {}, {}

    def add(self, user, item, doctype, name):
        if user:
            self.items.setdefault(user, []).append(dict(item, doctype=doctype, name=name))

    def text(self, employee, line):
        """A line for an employee who has no user to be told through."""
        if employee:
            self.texts.setdefault(employee, []).append(line)

    def send(self):
        from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

        for user, items in sorted(self.items.items()):
            overdue, soon = rules.digest_counts(items)
            subject = _("Learning: {0} overdue, {1} due soon.").format(overdue, soon) if overdue or soon \
                else _("Learning: {0} to look at.").format(len(items))
            body = "<br>".join(frappe.utils.escape_html(line) for line in rules.digest_lines(items))
            notice = {"type": people.alert_type(), "subject": subject, "email_content": body}
            if len(items) == 1:
                notice.update(document_type=items[0]["doctype"], document_name=items[0]["name"])
            else:
                notice["link"] = "/app/learning-command-centre"
            enqueue_create_notification([user], notice)
        if self.texts:
            from hrms_addon.hrms_addon import learning_loop

            learning_loop.message_employees(self.texts)
        sent = len(self.items)
        self.items, self.texts = {}, {}
        return sent


def chase_certificates(s=None, day=None, digest=None):
    """Each certificate's status as it stands today; the alert of the rung it
    has reached, sent once, to the people that rung names. The days left are
    worked out when the certificate is read, never written each day. The
    first alert asks for the renewal (learning_loop.renewal_requisitions)."""
    s, day = s or settings(), day or getdate(today())
    own = digest is None
    digest = Digest() if own else digest
    due = []
    for cert in frappe.get_all(CERTIFICATE, filters={"status": ["not in", [rules.RENEWED, rules.REVOKED]]},
                               fields=["name", "employee", "employee_name", "certification", "certificate_no",
                                       "expiry_date", "status", "verification_status", "revoked", "renewed_by",
                                       "alerts_sent", "renewal_requisition"], limit_page_length=0):
        status = rules.certificate_status(cert, day, s)
        if status != cert.status:
            frappe.db.set_value(CERTIFICATE, cert.name, "status", status, update_modified=False)
        if status in (rules.RENEWED, rules.REVOKED) or cert.verification_status == rules.REJECTED:
            continue
        left = rules.days_left(cert.expiry_date, day)
        rung = rules.tier_due(left, s["tiers"], rules.sent_list(cert.alerts_sent))
        if rung is not None:
            due.append((cert, left, rung))
    staff = _staff({cert.employee for cert, _left, _rung in due})
    cache, renew = {}, []
    for cert, left, rung in due:
        employee = staff.get(cert.employee)
        if employee and employee.status == rules.ACTIVE:
            item = {"status": rules.EXPIRED if left < 0 else rules.DUE_SOON, "due_date": cert.expiry_date,
                    "line": _expiry_text(cert, left)}
            audiences = rules.audiences_for(s["tiers"], rung)
            for user in audience_users(audiences, employee, cache):
                digest.add(user, item, CERTIFICATE, cert.name)
            if rules.EMPLOYEE in audiences and not employee.user_id:
                digest.text(employee.name, item["line"])
            if not rules.sent_list(cert.alerts_sent) and not cert.renewal_requisition:
                renew.append(cert)
        frappe.db.set_value(CERTIFICATE, cert.name, "alerts_sent", rules.with_sent(cert.alerts_sent, rung),
                            update_modified=False)
    if renew and cint(s.get("renewal_requisition")):
        from hrms_addon.hrms_addon import learning_loop

        learning_loop.renewal_requisitions([cert.name for cert in renew])
    if own:
        digest.send()
    return due


def _expiry_text(cert, left):
    what = _("{0}'s {1} certificate").format(cert.employee_name or cert.employee, cert.certification)
    if cert.certificate_no:
        what += " ({0})".format(cert.certificate_no)
    on = frappe.utils.format_date(cert.expiry_date)
    if left > 0:
        return _("{0} runs out in {1} day(s), on {2}.").format(what, left, on)
    if left == 0:
        return _("{0} runs out today.").format(what)
    return _("{0} ran out {1} day(s) ago, on {2}.").format(what, -left, on)


def audience_users(audiences, employee, cache=None):
    """The users each rung of the ladder names, for this employee. `cache`
    keeps who holds a role in a plant and department for the rest of a run."""
    cache = {} if cache is None else cache

    def holding(role, branch, department=None):
        key = (role, branch, department)
        if key not in cache:
            cache[key] = (people.hr_officers(branch, department) if role == "HR"
                          else people.people_for(role, branch, department))
        return cache[key]

    users = []
    if rules.EMPLOYEE in audiences:
        users.append(employee.user_id)
    if rules.SUPERVISOR in audiences:
        users.append(_supervisor_user(employee))
    if rules.HEAD in audiences:
        users += holding(HEAD_ROLE, employee.branch, employee.department)
    if rules.HR in audiences:
        users += holding("HR", employee.branch, employee.department)
    if rules.MANAGEMENT in audiences:
        users += holding(GM_ROLE, employee.branch)
    return [user for user in dict.fromkeys(users) if user]


def _supervisor_user(employee):
    if "supervisor_user" in employee:
        return employee.supervisor_user
    return frappe.db.get_value("Employee", employee.reports_to, "user_id") if employee.get("reports_to") else None


def _staff(names):
    """{employee: their facts and their supervisor's user}, in two reads."""
    staff = _employees(names)
    bosses = {person.reports_to for person in staff.values() if person.get("reports_to")}
    users = dict(frappe.get_all("Employee", filters={"name": ["in", list(bosses)]}, fields=["name", "user_id"],
                                as_list=True, limit_page_length=0)) if bosses else {}
    for person in staff.values():
        person.supervisor_user = users.get(person.get("reports_to"))
    return staff


def chase_requirements(s=None, day=None, digest=None):
    """Training falling due told to the employee and their supervisor, and
    overdue to them and the head of department, once per due date: each
    person told gets it in their digest for the day, every employee they
    are told about in it."""
    s, day = s or settings(), day or getdate(today())
    if not (s.get("notify_due_soon") or s.get("notify_overdue")):
        return []
    own = digest is None
    digest = Digest() if own else digest
    news = []
    for row in frappe.get_all(REQUIREMENT, filters={"status": ["in", [rules.DUE_SOON, rules.OVERDUE]]},
                              fields=["name", "employee", "status", "due_date", "valid_until", "training_program",
                                      "certification", "alerts_sent", "booking_status", "booked_for"],
                              limit_page_length=0):
        wanted = s.get("notify_overdue") if row.status == rules.OVERDUE else s.get("notify_due_soon")
        mark = "%s %s" % (row.status, row.due_date or "")
        sent = [part for part in (row.alerts_sent or "").split(";") if part]
        if not wanted or mark in sent:
            continue
        news.append(row)
        # only this due date's marks are kept: the next round is told afresh
        kept = [part for part in sent if part.endswith(" %s" % (row.due_date or ""))]
        frappe.db.set_value(REQUIREMENT, row.name, "alerts_sent", ";".join(kept + [mark]), update_modified=False)
    staff = _staff({row.employee for row in news})
    cache = {}
    for row in news:
        employee = staff.get(row.employee)
        if not employee or employee.status != rules.ACTIVE:
            continue
        status = row.status
        audiences = [rules.EMPLOYEE, rules.SUPERVISOR] + ([rules.HEAD] if status == rules.OVERDUE else [])
        item = {"status": status, "due_date": row.due_date, "line": _requirement_text(row, employee)}
        for user in audience_users(audiences, employee, cache):
            digest.add(user, item, REQUIREMENT, row.name)
        if not employee.user_id:
            digest.text(employee.name, item["line"])
    if own:
        digest.send()
    return news


def _requirement_text(row, employee):
    what = row.training_program or row.certification
    on = frappe.utils.format_date(row.due_date)
    text = (_("{0}: {1}, overdue since {2}.") if row.status == rules.OVERDUE
            else _("{0}: {1}, due {2}.")).format(employee.employee_name, what, on)
    if row.booking_status == rules.BOOKED and row.booked_for:
        text += " " + _("Booked for {0}.").format(frappe.utils.format_date(row.booked_for))
    return text


# ── What sets a refresher off ─────────────────────────────────────────
def trigger(kind, employees, day=None, note=None, days_away=None):
    """An event that sets refreshers off (an incident, a move, a long
    absence, a process change, new equipment...): each enabled rule set off
    by `kind` asks again of everyone it reaches, due so many days from the
    event, whatever they did before it. days_away: {employee: days} for a
    long absence, each rule asking only of those away its number of days or
    more. Returns the employees asked."""
    day = getdate(day or today())
    wanted = {name: rule for name, rule in _rules().items() if rule.get("trigger") == kind}
    about = _employees(employees)
    if not wanted or not about:
        return []
    s, asked = settings(), []
    sections = {person.work_section for person in about.values() if person.get("work_section")}
    departments = {person.department for person in about.values() if person.get("department")}
    members = {}
    if any(rule.get("trigger_reach") == rules.THEIR_SECTION for rule in wanted.values()) and sections \
            and _has("Employee", "custom_work_section"):
        for row in frappe.get_all("Employee", filters={"status": rules.ACTIVE, "custom_work_section": ["in", list(sections)]},
                                  fields=["name", "custom_work_section"], limit_page_length=0):
            members.setdefault(("section", row.custom_work_section), set()).add(row.name)
    if any(rule.get("trigger_reach") == rules.THEIR_DEPARTMENT for rule in wanted.values()) and departments:
        for row in frappe.get_all("Employee", filters={"status": rules.ACTIVE, "department": ["in", list(departments)]},
                                  fields=["name", "department"], limit_page_length=0):
            members.setdefault(("department", row.department), set()).add(row.name)
    for name, rule in wanted.items():
        reach = rule.get("trigger_reach") or rules.THE_EMPLOYEE
        targets = set()
        for person in about.values():
            if days_away is not None and flt(days_away.get(person.name)) < cint(rule.get("absence_days")):
                continue
            if reach == rules.THEIR_SECTION and person.get("work_section"):
                targets |= members.get(("section", person.work_section), set())
            elif reach == rules.THEIR_DEPARTMENT and person.get("department"):
                targets |= members.get(("department", person.department), set())
            else:
                targets.add(person.name)
        for part in rules.chunks(sorted(targets), CHUNK):
            facts = _employees(part)
            have = {row.employee: row for row in frappe.get_all(
                REQUIREMENT, filters={"training_rule": name, "employee": ["in", part]},
                fields=["name", "employee", "triggered_on"] + [field for field in KEPT if field != "triggered_on"],
                limit_page_length=0)}
            for employee in part:
                person = facts.get(employee)
                if not person or not rules.in_scope(rule, person):
                    continue
                row = have.get(employee)
                stamp = {"triggered_on": day, "trigger_note": (note or kind)[:140], "required_since": day,
                         "status": rules.PENDING}
                if row:
                    if row.triggered_on and getdate(row.triggered_on) == day and row.status != rules.NOT_APPLICABLE:
                        continue
                    _write(row, stamp)
                else:
                    _insert(_employee_values(person, dict(stamp, employee=employee,
                                                          requirement_type=rule["requirement_type"],
                                                          training_program=rule.get("training_program"),
                                                          training_category=rule.get("category"),
                                                          training_rule=name,
                                                          due_date=rules.trigger_due(rule, day))))
                asked.append(employee)
            _refresh_chunk(part, {name: rule}, s, getdate(today()), only_rule=name)
            frappe.db.commit()
    return sorted(set(asked))


# ── Every week ────────────────────────────────────────────────────────
def _grouped(doctype, filters, by):
    """[{by..., "n"}]: how many records there are of each kind, counted by
    the database (GROUP BY), not one by one here."""
    from hrms_addon.hrms_addon import queries

    return frappe.get_all(doctype, filters=filters, fields=list(by) + [queries.aggregate("COUNT", "*", "n")],
                          group_by=", ".join(by), limit_page_length=0)


def compliance_counts(filters, by, day=None):
    """{key: {"required", "done", "overdue", "due_soon"}} of what the rules
    ask, counted by the database for each value of `by` (a tuple of fields):
    done is what was done and still counts on the day."""
    day = getdate(day or today())
    base = dict(filters or {}, status=["!=", rules.NOT_APPLICABLE], requirement_type=["!=", rules.RECOMMENDED])
    out = {}

    def add(rows, field):
        for row in rows:
            key = tuple(row.get(name) or "" for name in by)
            out.setdefault(key, {"required": 0, "done": 0, "overdue": 0, "due_soon": 0})[field] += int(row.n or 0)

    add(_grouped(REQUIREMENT, base, by), "required")
    add(_grouped(REQUIREMENT, dict(base, completed_on=["is", "set"], valid_until=["is", "not set"]), by), "done")
    add(_grouped(REQUIREMENT, dict(base, completed_on=["is", "set"], valid_until=[">=", str(day)]), by), "done")
    for status, field in ((rules.OVERDUE, "overdue"), (rules.DUE_SOON, "due_soon")):
        add(_grouped(REQUIREMENT, dict(base, status=status), by), field)
    return out


def weekly():
    """Each plant's HR told how much of what the rules ask is done, and the
    departments furthest behind (the blueprint's low branch compliance)."""
    s, day = settings(), getdate(today())
    if not s.get("weekly_digest"):
        return
    plants = {}
    for (branch, department), counts in compliance_counts({}, ("branch", "department"), day).items():
        plants.setdefault(branch, {})[department] = counts
    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

    for branch, departments in sorted(plants.items()):
        done = sum(counts["done"] for counts in departments.values())
        required = sum(counts["required"] for counts in departments.values())
        overdue = sum(counts["overdue"] for counts in departments.values())
        behind = sorted((rules.percent(counts["done"], counts["required"]), department)
                        for department, counts in departments.items() if department)
        behind = [(value, department) for value, department in behind
                  if value is not None and value < rules._num(s["matrix_green_from"])][:3]
        subject = _("Training at {0}: {1}% of what is required is done, {2} overdue.").format(
            branch or _("no plant"), "%g" % (rules.percent(done, required) or 0), overdue)
        if behind:
            subject += " " + _("Furthest behind: {0}.").format(
                ", ".join("%s %g%%" % (department, value) for value, department in behind))
        users = people.hr_officers(branch) if branch else [holder["user"] for holder in people.holders("HR Manager")]
        if users:
            enqueue_create_notification(users, {
                "type": people.alert_type(), "subject": subject, "email_content": subject,
                "link": "/app/query-report/Training%20Matrix" + ("?branch=" + quote(branch) if branch else "")})


# ── The Learning Passport ─────────────────────────────────────────────
@frappe.whitelist()
def passport(employee=None):
    """One employee's learning on a page: who they are, their light and
    score, what is required of them, their certificates, their skills, the
    sessions they attended and are booked on, how their supervisor saw them
    apply it, what it cost, their CPD and the learning content given them.
    Their own; their team's for a supervisor; whoever the user may read for
    HR and managers."""
    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        if not employee:
            return {"employee": None}
    facts = _employee(employee)
    if not facts:
        frappe.throw(_("No employee {0}.").format(employee), frappe.DoesNotExistError)
    if not can_see(facts):
        frappe.throw(_("Not permitted to see {0}'s passport.").format(facts.employee_name), frappe.PermissionError)
    s, day = settings(), getdate(today())
    requirements = frappe.get_all(REQUIREMENT, filters={"employee": employee},
                                  fields=["name"] + list(KEPT) + ["reason", "trigger_note"], order_by="due_date asc",
                                  limit_page_length=0)
    certificates = frappe.get_all(CERTIFICATE, filters={"employee": employee},
                                  fields=["name", "certification", "certificate_no", "issuing_body", "issue_date",
                                          "expiry_date", "status", "verification_status", "attachment", "cost"],
                                  order_by="expiry_date asc", limit_page_length=0)
    for cert in certificates:
        cert.days_to_expiry = rules.days_left(cert.expiry_date, day)
    history = _history(employee)
    year = [row for row in history if row["day"] and getdate(row["day"]).year == day.year]
    marked = [flt(row["marks"]) for row in history if row["marks"] is not None
              and row["day"] and (day - getdate(row["day"])).days <= 365]
    assessment = round(sum(marked) / len(marked), 1) if marked else None
    skills = _skills(employee)
    from hrms_addon.hrms_addon import competency_rules

    competency = competency_rules.score_of(skills)
    figures = rules.summary(requirements, day, s, assessment=assessment, competency=competency)
    supervisor = frappe.db.get_value("Employee", facts.reports_to, "employee_name") if facts.reports_to else None
    extra = frappe.db.get_value("Employee", employee, ["image", "employee_number"], as_dict=True) or {}
    costs = _costs(employee, history, certificates, day)
    return {
        "employee": {"name": facts.name, "employee_name": facts.employee_name, "company": facts.company,
                     "branch": facts.branch, "department": facts.department, "designation": facts.designation,
                     "grade": facts.grade, "employment_type": facts.employment_type,
                     "work_section": facts.get("work_section"),
                     "date_of_joining": facts.date_of_joining, "supervisor": supervisor, "status": facts.status,
                     "image": extra.get("image"), "employee_number": extra.get("employee_number"),
                     "own": facts.get("user_id") == frappe.session.user},
        "figures": dict(figures, assessment=assessment, competency=competency,
                        hours=round(sum(row["hours"] for row in year), 1), sessions=len(year), year=day.year,
                        cost=costs["total"], cpd_hours=_cpd_hours(employee, day)),
        "requirements": requirements, "certificates": certificates, "history": history[:50],
        "skills": skills, "reviews": _reviews(employee), "upcoming": upcoming_sessions(employee, day),
        "costs": costs, "cpd": _cpd(employee), "content": _content(employee),
        "is_hr": bool(set(frappe.get_roles()) & set(HR_ROLES + ("HR User",))),
        "today": str(day),
    }


def _skills(employee):
    """The skill assessments that count for them, the critical first."""
    return frappe.get_all("Competency Assessment", filters={"employee": employee, "status": ["!=", "Superseded"]},
                          fields=["name", "skill", "level", "required_level", "gap", "status", "critical",
                                  "assessed_on", "next_due"],
                          order_by="critical desc, skill asc", limit_page_length=0)


def _reviews(employee):
    """How their supervisor saw them apply each training (level 3)."""
    return frappe.get_all("Training Application Review", filters={"employee": employee},
                          fields=["name", "training_program", "training_event", "status", "score", "applied",
                                  "behaviour", "competency", "due_on", "reviewed_on"],
                          order_by="event_end desc", limit_page_length=20)


def upcoming_sessions(employee, day=None):
    """The sessions still to be held they are on or waiting for: when,
    where, and whether they are invited, registered or on the waiting list."""
    day = getdate(day or today())
    names = frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "employee": employee},
                           pluck="parent", limit_page_length=0)
    waiting = []
    if _has(EVENT, "custom_waitlist"):
        waiting = frappe.get_all("Training Event Waitlist", filters={"parenttype": EVENT, "employee": employee,
                                                                     "status": "Waiting"},
                                 pluck="parent", limit_page_length=0)
    if not names and not waiting:
        return []
    fields = ["name", "event_name", "training_program", "start_time", "end_time", "location"]
    fields += [field for field in ("custom_venue",) if _has(EVENT, field)]
    events = frappe.get_all(EVENT, filters={"name": ["in", list(set(names) | set(waiting))], "docstatus": 0,
                                            "event_status": ["!=", EVENT_CANCELLED],
                                            "end_time": [">=", str(day) + " 00:00:00"]},
                            fields=fields, order_by="start_time asc", limit_page_length=20)
    marked = {}
    for row in frappe.get_all("Training Attendance", filters={"employee": employee,
                                                              "training_event": ["in", [e.name for e in events] or [""]]},
                              fields=["training_event", "status"], limit_page_length=0):
        marked.setdefault(row.training_event, row.status)
    for event in events:
        event.venue = event.get("custom_venue") or event.location
        event.place = "Waiting List" if event.name in waiting and event.name not in names \
            else marked.get(event.name) or "Invited"
    return events


def _costs(employee, history, certificates, day):
    """What their learning cost this year: their share of each session they
    attended, and the certificates issued to them."""
    held = [row["event"] for row in history if row["day"] and getdate(row["day"]).year == day.year]
    sessions = 0.0
    if held and _has(EVENT, "custom_cost_per_trainee"):
        sessions = sum(flt(value) for value in frappe.get_all(EVENT, filters={"name": ["in", held]},
                                                              pluck="custom_cost_per_trainee"))
    certs = sum(flt(cert.get("cost")) for cert in certificates
                if cert.get("issue_date") and getdate(cert.issue_date).year == day.year)
    return {"sessions": round(sessions, 2), "certificates": round(certs, 2), "total": round(sessions + certs, 2),
            "year": day.year}


def _cpd(employee):
    return frappe.get_all("CPD Log", filters={"employee": employee, "docstatus": ["<", 2]},
                          fields=["name", "activity", "activity_type", "certification", "activity_date", "hours",
                                  "points", "status"], order_by="activity_date desc", limit_page_length=20)


def _cpd_hours(employee, day):
    first = "%d-01-01" % day.year
    return round(sum(flt(value) for value in frappe.get_all(
        "CPD Log", filters={"employee": employee, "docstatus": 1, "status": ["!=", "Rejected"],
                            "activity_date": [">=", first]}, pluck="hours")), 1)


def _content(employee):
    return frappe.get_all(CONTENT_ASSIGNMENT, filters={"employee": employee, "status": ["!=", "Withdrawn"]},
                          fields=["name", "learning_content", "content_title", "content_type", "version", "status",
                                  "due_date", "score", "attempts", "acknowledged_on", "completed_on"],
                          order_by="due_date asc", limit_page_length=50)


def can_see(facts):
    """Their own; their direct reports'; and for HR and managers whoever
    their own permissions on the Employee let them read."""
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles & set(HR_ROLES):
        return True
    if facts.get("user_id") and facts.user_id == user:
        return True
    if facts.get("reports_to") and frappe.db.get_value("Employee", facts.reports_to, "user_id") == user:
        return True
    if roles & set(LOOK_ROLES):
        return bool(frappe.has_permission("Employee", "read", doc=facts.name, user=user))
    return False


def _history(employee):
    """The sessions they attended, latest first: the day, the training, the
    hours and their marks."""
    present = frappe.get_all("Training Event Employee",
                             filters={"parenttype": EVENT, "employee": employee,
                                      "attendance": training_rules.PRESENT},
                             pluck="parent", limit_page_length=0)
    if not present:
        return []
    events = frappe.get_all(EVENT, filters={"name": ["in", present], "docstatus": 1,
                                            "event_status": ["!=", EVENT_CANCELLED]},
                            fields=["name", "event_name", "training_program", "start_time", "end_time"],
                            limit_page_length=0)
    results = _results([event.name for event in events], [employee])
    hours = {}
    if _has(PROGRAMME, "custom_duration_hours"):
        programmes = list({event.training_program for event in events if event.training_program})
        if programmes:
            hours = dict(frappe.get_all(PROGRAMME, filters={"name": ["in", programmes]},
                                        fields=["name", "custom_duration_hours"], as_list=True))
    out = []
    for event in events:
        result = results.get((event.name, employee), {})
        out.append({
            "event": event.name, "event_name": event.event_name, "training_program": event.training_program,
            "day": str(getdate(event.end_time or event.start_time)) if (event.end_time or event.start_time) else None,
            "hours": rules.event_hours(event.start_time, event.end_time, hours.get(event.training_program),
                                       result.get("hours")),
            "marks": flt(result.get("custom_marks")) if _marked(result) else None,
            "effective": result.get("custom_effective"),
        })
    return sorted(out, key=lambda row: row["day"] or "", reverse=True)
