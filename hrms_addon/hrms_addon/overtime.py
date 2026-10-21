# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Overtime on the site: what the day is, what it costs, and how it is paid.

The rules are in overtime_rules.py, without a Frappe import
(scripts/verify_overtime.py). This reads and writes the site.

LPL/HR/14 is raised before the work and approved on the Actions menu, as
every other request is (overtime_approval.py): Submit, Approve by the
officer who carries the section, Approve by HR.

  check_step      the step just taken is checked, signed for and told to
                  whoever holds the request next
  _cost           as HR approve it, what the overtime comes to — each
                  person's own hourly pay at their own rate — is written on
                  it
  send            the approved hours are written onto the employees'
                  Attendance rows with the Overtime Type they fall under,
                  and an Overtime Slip is drawn for the cycle: by itself
                  once the day's attendance is in (approved, send_ready),
                  or by HR from the form (send_to_payroll)

The slip is Frappe HR's own: it prices the attendance it finds, holds the
multipliers on the Overtime Type, and writes the Additional Salary the
payroll run reads. Nothing here re-prices it, and nothing here writes a
salary component. Its hour is the month's pay over Payroll Settings' Days
in a Pay Month, 26, where Frappe HR's would be over the slip's payment days
(pay_days.py); the cost here is divided by the same days.

  seed_overtime_types   the three kinds of day, at the Employment Act's
                        floor, made once and then Luuka's to amend

  raise_from_clock  overtime the clock shows, for people whose Overtime Type
                  says to raise it from the clock, becomes a request by
                  itself: the type's rules say what counts, and the
                  employee's supervisor (else the type's own requester) is
                  named on it
  waiting         for the Overtime Slip's form: the employee's requests in
                  the slip's dates that have not reached payroll, and the
                  step each waits for
  stamp_untyped   hours sent while their Overtime Type was not on the
                  site, put under it once it is
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from hrms_addon.hrms_addon import attendance, attendance_rules, overtime_approval as approval, \
    overtime_rules as rules, pay, pay_days, people

REQUEST = "Overtime Request"
TYPE = "Overtime Type"
SLIP = "Overtime Slip"


# ── 1. What sort of day it is ─────────────────────────────────────────
def day_kind(employee, day):
    """Read the day rather than ask for it: a holiday on the employee's
    own list, their weekly off, a day they are on leave, or a weekday."""
    return rules.kind_of_day({
        "on_holiday_list": _is_holiday(employee, day, weekly_off=False),
        "is_weekly_off": _is_holiday(employee, day, weekly_off=True),
        "on_leave": _on_leave(employee, day),
    })


def _holiday_list(employee):
    found = frappe.db.get_value("Employee", employee, ["holiday_list", "company"], as_dict=True)
    if not found:
        return None
    if found.holiday_list:
        return found.holiday_list
    return frappe.db.get_value("Company", found.company, "default_holiday_list")


def _is_holiday(employee, day, weekly_off):
    name = _holiday_list(employee)
    if not name:
        return False
    return bool(frappe.db.exists("Holiday", {"parent": name, "holiday_date": getdate(day),
                                             "weekly_off": 1 if weekly_off else 0}))


def _on_leave(employee, day):
    return bool(frappe.db.exists("Leave Application", {
        "employee": employee, "docstatus": 1, "status": "Approved",
        "from_date": ["<=", getdate(day)], "to_date": [">=", getdate(day)]}))


def type_for(kind, company=None):
    """The Overtime Type the day falls under. Named, not guessed: the
    types are seeded under the names in overtime_rules."""
    name = rules.type_name_for(kind)
    if frappe.db.exists(TYPE, name):
        return name
    return None


# ── 2. What it costs ──────────────────────────────────────────────────
def fill_day_and_rate(doc):
    """Called from attendance.overtime_validate: what sort of day it is, and
    on each line the Overtime Type that person falls under and its rate, so
    the form shows them before anybody signs. There is no one rate for the
    sheet: a person's type follows their own pay, and one person's rest day
    is another's working day."""
    rows = doc.get("employees") or []
    if not doc.get("overtime_date") or not rows:
        return
    first = next((row.employee for row in rows if row.employee), None)
    if not first:
        return
    kind = day_kind(first, doc.overtime_date)
    doc.day_kind = kind
    people_on_it = [row.employee for row in rows if row.employee]
    kinds = {employee: day_kind(employee, doc.overtime_date) for employee in people_on_it}
    rated = rules.priced([_plain(row) for row in rows], {}, kind, _type_row(type_for(kind, doc.get("company"))),
                         _types_for(kind, kinds.values()), _monthly_gross(people_on_it, doc.overtime_date), None,
                         kinds, _departments(people_on_it))["rows"]
    for row, found in zip(rows, rated):
        row.day_kind = found["day_kind"] if row.employee else None
        row.overtime_type = found["overtime_type"] if row.employee else None
        row.multiplier = found["multiplier"] if row.employee else 0
    return rules.eligibility_errors(rated)


def _plain(row):
    return row.as_dict() if hasattr(row, "as_dict") else dict(row)


def _type_row(name):
    if not name:
        return None
    return frappe.db.get_value(
        TYPE, name,
        ["standard_multiplier", "weekend_multiplier", "public_holiday_multiplier",
         "applicable_for_weekend", "applicable_for_public_holiday",
         "maximum_overtime_hours_allowed", "overtime_salary_component", "custom_gross_above",
         "custom_from_clock", "custom_clock_minimum", "custom_clock_step", "custom_clock_requester"], as_dict=True)


def _types_for(kind=None, kinds=()):
    """Every Overtime Type on the site with who it is for: its row, the
    employees it lists and the departments it is not paid to. A person's
    type is chosen among them (overtime_rules.person_type), so every type
    is read, whatever the day."""
    found = {name: dict(_type_row(name) or {}) for name in frappe.get_all(TYPE, pluck="name", limit_page_length=0)}
    for table, key, field in (("Overtime Type Employee", "employees", "employee"),
                              ("Overtime Type Department", "excluded_departments", "department")):
        for row in frappe.get_all(table, filters={"parenttype": TYPE}, fields=["parent", field],
                                  limit_page_length=0):
            if row.parent in found:
                found[row.parent].setdefault(key, []).append(row.get(field))
    return found


def _departments(employees):
    """{employee: their department}."""
    names = sorted(set(filter(None, employees)))
    if not names:
        return {}
    return {row.name: row.department for row in frappe.get_all(
        "Employee", filters={"name": ["in", names]}, fields=["name", "department"], limit_page_length=0)}


def _day_kinds(doc):
    """{employee: what sort of day the overtime date is for them}."""
    return {row.employee: row.get("day_kind") or day_kind(row.employee, doc.overtime_date)
            for row in doc.get("employees") or [] if row.employee}


def _monthly_gross(employees, day):
    """Each employee's monthly gross on the day, as their salary structure
    works it out: what the line on the Overtime Type is compared with."""
    return {employee: pay.monthly_gross(employee, day) for employee in employees}


def _standard_hours(employees, day):
    """Each employee's standard hours on the day: those of the shift they
    work it on (attendance.shift_on), which their hour is divided out of."""
    hours = attendance.all_shift_hours()
    return {employee: attendance.shift_hours_of(attendance.shift_on(employee, day), hours)["standard"]
            for employee in employees}


def _monthly_bases(employees):
    """Each employee's monthly base, from their Salary Structure
    Assignment. The one in force, not the newest ever written."""
    out = {}
    for employee in employees:
        found = frappe.get_all(
            "Salary Structure Assignment",
            filters={"employee": employee, "docstatus": 1,
                     "from_date": ["<=", today()]},
            fields=["base"], order_by="from_date desc", limit=1)
        out[employee] = flt(found[0].base) if found else 0.0
    return out


def check_step(doc, raising=()):
    """Called from attendance.overtime_validate, with what would stop the
    request being raised: the step the Actions menu has just taken is
    checked, signed for, and told to whoever holds the request next."""
    before = doc.get_doc_before_save()
    old = before.get(approval.STATE_FIELD) if before else None
    new = doc.get(approval.STATE_FIELD) or approval.DRAFT
    moved = old != new and not (old is None and new == approval.DRAFT)
    if moved:
        errors = approval.step_errors(old, new, {
            field: doc.get(field) for field in ("return_remarks", "authority_remarks", "cost_remarks")})
        if new == approval.REQUESTED:
            errors = list(raising) + errors
        if new == approval.COSTED and not errors:
            errors = _cost(doc, old)
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(REQUEST))
        if new != approval.DRAFT:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old, new, frappe.session.user, today(), current).items():
        doc.set(field, value)
    doc.status = new
    if moved:
        _tell(doc, old, new)


def _cost(doc, standing):
    """HR's approval: what the overtime comes to is worked out and written
    on the request as it is approved, each person's own hourly pay at their
    own rate. Returns what stops it; `standing` is the state it leaves."""
    rows = [_plain(row) for row in doc.get("employees") or []]
    people_on_it = [row.get("employee") for row in rows if row.get("employee")]
    kind = doc.get("day_kind") or (day_kind(people_on_it[0], doc.overtime_date) if people_on_it else rules.WEEKDAY)
    kinds = _day_kinds(doc)
    types = _types_for(kind, kinds.values())
    costed = rules.priced(rows, _monthly_bases(people_on_it), kind, _type_row(type_for(kind, doc.get("company"))), types,
                          _monthly_gross(people_on_it, doc.overtime_date),
                          _standard_hours(people_on_it, doc.overtime_date), kinds, _departments(people_on_it),
                          days=pay_days.days_in_month())
    errors = rules.cost_check_errors({
        "status": standing, "rows": costed["rows"], "unpriced": costed["unpriced"],
        "not_eligible": rules.eligibility_errors(costed["rows"])})
    if errors:
        return errors
    for row, priced_row in zip(doc.get("employees") or [], costed["rows"]):
        row.update({"hourly_rate": priced_row["hourly_rate"], "multiplier": priced_row["multiplier"],
                    "amount": priced_row["amount"], "day_kind": priced_row["day_kind"],
                    "overtime_type": priced_row["overtime_type"]})
    # the ceiling is a person's day on their own type, not the sheet's hours together
    over = [row.get("employee_name") or row.get("employee") for row in costed["rows"] if rules.over_the_cap(
        row.get("hours"), (types.get(row.get("overtime_type")) or {}).get("maximum_overtime_hours_allowed"))]
    doc.day_kind = kind
    doc.total_cost = costed["total"]
    doc.over_the_cap = 1 if over else 0
    if over:
        frappe.msgprint(_("Over the day's ceiling on their Overtime Type: {0}. It may still be paid, but say so in "
                          "the HR remarks.").format(", ".join(over)), indicator="orange")
    return []


def _holders(doc, state):
    """Who holds the request at a state: the officer who carries the section
    while it waits to be authorised, HR while it waits to be costed."""
    if state == approval.REQUESTED:
        return people.people_for("Production Manager", doc.get("branch"), doc.get("department")) \
            or people.people_for("Head of Department", doc.get("branch"), doc.get("department"))
    if state == approval.AUTHORISED:
        return people.hr_officers(doc.get("branch"), doc.get("department"))
    return []


def _tell(doc, old, new):
    """Whoever holds the request next is told and given it, whoever held it
    is let off, and a request returned or refused is told to whoever asked."""
    held = list(_holders(doc, old) or [])
    if held and doc.name:
        people.withdraw(doc.doctype, doc.name, held)
    day = frappe.utils.format_date(doc.overtime_date)
    users = list(_holders(doc, new) or [])
    if new == approval.REQUESTED:
        message = _("Overtime for {0} on {1}: {2} employee(s), {3} hours.").format(
            doc.get("section") or doc.get("department") or "", day, len(doc.get("employees") or []), doc.total_hours)
    elif new == approval.AUTHORISED:
        message = _("Overtime authorised for {0}: {1} permanent and {2} casual coupon(s) to issue, and the cost to "
                    "approve.").format(day, doc.coupons_permanent, doc.coupons_casual)
    elif new in (approval.REJECTED, approval.DRAFT) and old in approval.PENDING_STATES:
        asked = frappe.db.get_value("Employee", doc.get("requested_by"), "user_id") if doc.get("requested_by") else None
        why = doc.get("return_remarks") if new == approval.DRAFT else doc.get(approval.REMARK_FIELDS[old][0])
        if asked:
            people.notify([asked], doc.doctype, doc.name,
                          (_("Overtime for {0} was returned: {1}") if new == approval.DRAFT
                           else _("Overtime for {0} was refused: {1}")).format(day, why or ""))
        return
    else:
        return
    if users and doc.name:
        people.notify(users, doc.doctype, doc.name, message)
        people.assign(doc.doctype, doc.name, users, message, date=doc.overtime_date)
        _let_act(doc, users)


def _let_act(doc, users):
    """Whoever is given the request can act on it. Approving saves it and
    refusing submits it, which the role of the one asked may not carry on a
    site, and Frappe shares an assigned document read-only."""
    from frappe.share import add_docshare

    for user in sorted({user for user in users or [] if user}):
        if not frappe.has_permission(doc.doctype, "submit", doc.name, user=user):
            add_docshare(doc.doctype, doc.name, user, read=1, write=1, submit=1,
                         flags={"ignore_share_permission": True})


def approved(doc):
    """Overtime Request on_submit. HR's approval submits it: where its day
    has come, the hours go to payroll at once if the attendance is in, and
    what stops them is said; a day still to come is left to the daily job.
    A refused request is submitted too, as a record, and nothing follows."""
    if doc.get(approval.STATE_FIELD) != approval.COSTED:
        return None
    if getdate(doc.overtime_date) > getdate(today()):
        return None
    found = send(doc, quiet=True)
    if found.get("errors"):
        frappe.msgprint(_("Approved. Not with payroll yet:<br>{0}").format("<br>".join(found["errors"])),
                        indicator="orange", title=_(REQUEST))
    return found


# ── 3. How it is paid ─────────────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def send_to_payroll(name):
    """The Send to Payroll button, for HR: now, and saying what stops it."""
    doc = frappe.get_doc(REQUEST, name)
    doc.check_permission("submit")
    return send(doc)


def send_ready():
    """Daily: the approved requests whose day has passed go to payroll as
    their attendance comes in. One the attendance still stops is left as it
    is, for HR to see why from its form. Returns those sent."""
    sent = []
    for name in frappe.get_all(REQUEST, filters={"docstatus": 1, "status": approval.COSTED,
                                                 "overtime_date": ["<", getdate(today())]},
                               pluck="name", order_by="overtime_date asc", limit_page_length=0):
        try:
            if not send(frappe.get_doc(REQUEST, name), quiet=True).get("errors"):
                sent.append(name)
        except Exception:
            frappe.log_error(title="HRMS Addon: sending overtime %s to payroll" % name)
    return sent


CLOCK_DAYS_BACK = 3


def raise_from_clock(day=None):
    """Daily. Not every hour of overtime is asked for beforehand: where a
    person's Overtime Type says to raise it from the clock, the overtime
    their attendance shows on a day becomes a request by itself, waiting
    for the authorising officer as one raised by hand does.

    The type carries the rules: the least that counts, the step it is
    counted in, its ceiling for a day. The request names the employee's own
    supervisor, else the requester the type gives; somebody with neither is
    left out and said in the Error Log. Somebody already on a request for
    that day is left to it, so a second run raises nothing twice.

    `day`: the day to read; none reads the last few, as the clock's
    attendance comes in. Returns the requests raised."""
    if day is None:
        raised = []
        for back in range(CLOCK_DAYS_BACK, 0, -1):
            raised += raise_from_clock(add_days(today(), -back))
        return raised
    day = getdate(day)
    types = _types_for()
    if not any(cint((row or {}).get("custom_from_clock")) for row in types.values()):
        return []
    marked = frappe.get_all("Attendance", filters={
        "attendance_date": day, "docstatus": 1, "status": rules.PAID_ON, "in_time": ["is", "set"],
        "out_time": ["is", "set"]}, fields=["name", "employee", "employee_name", "working_hours"], limit_page_length=0)
    asked = _on_a_request(day)
    marked = [row for row in marked if row.employee not in asked]
    if not marked:
        return []
    names = [row.employee for row in marked]
    seats = {row.name: row for row in frappe.get_all(
        "Employee", filters={"name": ["in", names]},
        fields=["name", "reports_to", "branch", "department", "company"], limit_page_length=0)}
    grosses, standards = _monthly_gross(names, day), _standard_hours(names, day)
    lines, nobody = [], []
    for row in marked:
        seat = seats.get(row.employee) or frappe._dict()
        kind = day_kind(row.employee, day)
        named = rules.person_type(kind, grosses.get(row.employee), types, row.employee, seat.get("department"))[0]
        theirs = types.get(named) if named else None
        if not theirs or not cint(theirs.get("custom_from_clock")):
            continue
        worked = rules.worked_overtime(kind, row.working_hours,
                                       standards.get(row.employee) or attendance_rules.STANDARD_HOURS)
        hours = rules.clock_hours(worked, theirs.get("custom_clock_minimum"), theirs.get("custom_clock_step"),
                                  theirs.get("maximum_overtime_hours_allowed"))
        if hours <= 0:
            continue
        requester = seat.get("reports_to") or theirs.get("custom_clock_requester")
        if not requester:
            nobody.append(row.employee_name or row.employee)
            continue
        lines.append({"employee": row.employee, "employee_name": row.employee_name, "hours": hours,
                      "requester": requester, "branch": seat.get("branch"), "department": seat.get("department"),
                      "company": seat.get("company")})
    if nobody:
        frappe.log_error(title="HRMS Addon: overtime by the clock with nobody to request it",
                         message="%s: %s" % (day, ", ".join(sorted(nobody))))
    raised = []
    for sheet in rules.clock_sheets(lines):
        doc = frappe.get_doc({
            "doctype": REQUEST, "overtime_date": day, "requested_by": sheet["requester"], "requested_on": today(),
            "branch": sheet["branch"], "department": sheet["department"], "section": sheet["department"],
            "company": sheet["company"], "from_clock": 1,
            "reason": _("Worked past the shift, by the clock."), "employees": sheet["employees"]})
        doc.flags.ignore_permissions = True
        doc.insert()
        # raised: it waits for the authorising officer, as one raised by hand does
        doc.set(approval.STATE_FIELD, approval.REQUESTED)
        doc.flags.ignore_permissions = True
        doc.save()
        raised.append(doc.name)
    return raised


def _on_a_request(day):
    """The employees a request already asks overtime for on the day, in
    whatever stage but refused or cancelled."""
    requests = frappe.get_all(REQUEST, filters={
        "overtime_date": day, "docstatus": ["<", 2], "status": ["not in", [approval.REJECTED, approval.CANCELLED]]},
        pluck="name", limit_page_length=0)
    if not requests:
        return set()
    return set(frappe.get_all("Overtime Request Employee", filters={"parenttype": REQUEST, "parent": ["in", requests]},
                              pluck="employee", limit_page_length=0))


def send(doc, quiet=False):
    """Test cases 2, 4 and 5: the hours are written onto the employees' own
    Attendance rows under the Overtime Type the day falls under, and Frappe
    HR's Overtime Slip is drawn for the cycle. The slip prices them and
    writes the Additional Salary payroll reads — none of that is done here.

    The hours paid are those authorised, up to what the clock shows
    (overtime_rules.payable_hours): on a day the clock measured, nobody is
    paid for overtime it says they did not work. A day it did not measure,
    marked by hand, is paid as authorised. Somebody the attendance reads
    absent stops the sheet.

    The slip reads only an attendance that carries an Overtime Type. One
    that is not on the site is made here as the migrate would have made
    it, and where it cannot be the sheet is stopped: hours written without
    a type would read Sent to Payroll and never be paid.

    What stops it is thrown, or with `quiet` handed back as {"errors"}:
    nothing is written either way."""
    def stopped(messages):
        if quiet:
            return {"errors": list(messages)}
        frappe.throw("<br>".join(messages), title=_("Payroll"))

    kinds = _day_kinds(doc)
    rows = []
    for row in doc.get("employees") or []:
        found = frappe.db.get_value("Attendance", {
            "employee": row.employee, "attendance_date": getdate(doc.overtime_date), "docstatus": 1},
            ["name", "status", "in_time", "out_time", "working_hours"], as_dict=True)
        if found and row.attendance != found.name:
            row.db_set("attendance", found.name, update_modified=False)
        rows.append(dict(row.as_dict(), attendance=found.name if found else None, marked=found,
                         status=found.status if found else None,
                         absent=bool(found) and found.status == "Absent",
                         clocked_in=bool(found) and bool(found.in_time)))
    errors = rules.payroll_errors({"status": doc.get("status"), "rows": rows})
    if errors:
        return stopped([_(message) for message in errors])
    kind = doc.get("day_kind") or rules.WEEKDAY
    grosses = _monthly_gross([row["employee"] for row in rows], doc.overtime_date)
    standards = _standard_hours([row["employee"] for row in rows], doc.overtime_date)

    def planned():
        """What goes onto each attendance. Read again once a missing type
        has been made: the types set who falls under which."""
        types = _types_for(kind, kinds.values())
        out = []
        for row in rows:
            theirs = kinds.get(row["employee"]) or kind
            named, why = rules.person_type(theirs, grosses.get(row["employee"]), types, row["employee"],
                                           departments.get(row["employee"]))
            if why:
                closed.append(_("{0} is not eligible for this overtime: {1}").format(
                    row.get("employee_name") or row["employee"], _(why)))
            standard = standards.get(row["employee"]) or attendance_rules.STANDARD_HOURS
            found = row["marked"]
            # the clock measured the day when it has both ends of it
            worked = rules.worked_overtime(theirs, found.working_hours, standard) \
                if (found.in_time and found.out_time) else None
            paid = rules.payable_hours(row.get("hours"), worked)
            out.append((theirs, worked, paid, rules.attendance_update(row, theirs, standard, hours=paid, named=named)))
        return out

    departments = _departments([row["employee"] for row in rows])
    closed = []
    plans = planned()
    if closed:
        return stopped(closed)
    if _missing_types(plans):
        seed_overtime_types()
        plans = planned()
    missing = _missing_types(plans)
    if missing:
        return stopped([_(rules.missing_type_error(missing))])
    marked, short = 0, []
    for row, line, (theirs, worked, paid, values) in zip(rows, doc.get("employees") or [], plans):
        frappe.db.set_value("Attendance", row["attendance"], values, update_modified=False)
        # a number column takes no empty value: a day the clock did not measure reads 0, and says so
        line.db_set({"day_kind": theirs, "worked_hours": flt(worked), "clocked": 0 if worked is None else 1,
                     "payable_hours": paid}, update_modified=False)
        if paid < flt(row.get("hours")):
            short.append(_("{0}: {1} of {2} hours").format(row.get("employee_name") or row["employee"], paid,
                                                           flt(row.get("hours"))))
        marked += 1
    slips = _draw_slips(doc)
    doc.db_set({"status": approval.SENT, approval.STATE_FIELD: approval.SENT, "sent_to_payroll_on": today()},
               update_modified=False)
    if short:
        frappe.msgprint(_("Paid by the clock, which shows less than was authorised:<br>{0}").format(
            "<br>".join(short)), indicator="orange", title=_("Overtime"))
    officers = people.people_for("Payroll Officer", doc.get("branch"), doc.get("department")) \
        or people.hr_officers(doc.get("branch"), doc.get("department"))
    if officers:
        people.notify(list(officers), doc.doctype, doc.name,
                      _("Overtime of {0} for {1} is checked and ready for payroll.").format(
                          frappe.utils.fmt_money(doc.get("total_cost") or 0),
                          frappe.utils.format_date(doc.overtime_date)))
    return {"attendance_marked": marked, "slips": slips, "paid_less": short}


def take_back(doc):
    """A cancelled request's hours come off the attendance they were written
    onto, and off any Overtime Slip still in draft, so nothing pays them.
    Where a submitted slip already has, the cancel is refused: that slip is
    cancelled first. Returns the attendance cleared."""
    names = [row.attendance for row in doc.get("employees") or []
             if row.get("attendance") and flt(row.get("payable_hours")) > 0]
    if not names or not doc.get("sent_to_payroll_on"):
        return []
    slips = sorted({line.parent for line in frappe.get_all(
        "Overtime Details", filters={"parenttype": SLIP, "reference_document": ["in", names]}, fields=["parent"],
        limit_page_length=0)})
    stands = {slip: cint(frappe.db.get_value(SLIP, slip, "docstatus")) for slip in slips}
    paid = [slip for slip in slips if stands[slip] == 1]
    if paid:
        frappe.throw(_("These hours are paid on {0}. Cancel that Overtime Slip first.").format(", ".join(paid)),
                     title=_("Overtime Request"))
    for name in slips:
        if stands[name] != 0:
            continue
        slip = frappe.get_doc(SLIP, name)
        kept = [line for line in slip.get("overtime_details") or [] if line.reference_document not in names]
        slip.set("overtime_details", kept)
        slip.total_overtime_duration = sum(flt(line.overtime_duration) for line in kept)
        slip.flags.ignore_permissions = True
        slip.save()
    for name in names:
        frappe.db.set_value("Attendance", name, {"overtime_type": None, "actual_overtime_duration": 0},
                            update_modified=False)
    return names


def _missing_types(plans):
    """The Overtime Types the hours would go under that are not on the site."""
    return sorted({values["overtime_type"] for _theirs, _worked, _paid, values in plans
                   if not frappe.db.exists(TYPE, values["overtime_type"])})


@frappe.whitelist()
def waiting(employee=None, start_date=None, end_date=None):
    """For the Overtime Slip's form. Frappe HR's slip reads the attendance,
    and overtime is written there only when its request is sent to payroll,
    so a slip made while a request is still on its way finds nothing. Those
    requests are named here with the step each waits for. Only what the
    user may read."""
    if not (employee and start_date and end_date) or not frappe.has_permission(REQUEST, "read"):
        return []
    hours = {row.parent: row.hours for row in frappe.get_all(
        "Overtime Request Employee", filters={"employee": employee, "parenttype": REQUEST},
        fields=["parent", "hours"], limit_page_length=0)}
    if not hours:
        return []
    found = frappe.get_list(REQUEST, filters={
        "name": ["in", sorted(hours)], "docstatus": ["<", 2],
        "overtime_date": ["between", [getdate(start_date), getdate(end_date)]]},
        fields=["name", "overtime_date", "status"], limit_page_length=0)
    return rules.waiting([{"name": row.name, "overtime_date": row.overtime_date, "status": row.status,
                           "hours": hours.get(row.name)} for row in found])


def stamp_untyped():
    """after_migrate. Hours sent to payroll while their Overtime Type was
    not on the site were written onto the attendance without one, where
    Frappe HR's Overtime Slip never finds them. Once the type is there they
    are put under it. Only an attendance a request sent to payroll wrote
    on, and never one that has a type. Returns the attendance stamped."""
    untyped = frappe.get_all("Attendance", filters={
        "docstatus": 1, "status": rules.PAID_ON, "actual_overtime_duration": [">", 0],
        "overtime_type": ["is", "not set"]}, fields=["name", "employee", "attendance_date"], limit_page_length=0)
    types, stamped = None, []
    for found in untyped:
        sheet = frappe.get_all("Overtime Request Employee", filters={"attendance": found.name, "parenttype": REQUEST},
                               fields=["parent", "day_kind"], limit=1)
        request = frappe.db.get_value(REQUEST, sheet[0].parent, ["status", "day_kind"], as_dict=True) if sheet else None
        if not request or request.status != "Sent to Payroll":
            continue
        if types is None:
            types = _types_for()
        name = rules.person_type(sheet[0].day_kind or request.day_kind or rules.WEEKDAY,
                                 pay.monthly_gross(found.employee, found.attendance_date), types, found.employee,
                                 _departments([found.employee]).get(found.employee))[0]
        if name and frappe.db.exists(TYPE, name):
            frappe.db.set_value("Attendance", found.name, "overtime_type", name, update_modified=False)
            stamped.append(found.name)
    if stamped:
        print("HRMS Addon: %d attendance record(s) with overtime sent to payroll now carry their Overtime Type."
              % len(stamped))
    return stamped


def _draw_slips(doc):
    """One Overtime Slip per employee per attendance cycle. An open slip
    that already covers the day is left alone — it will pick the hours up
    on its own, because it reads the attendance, not this request."""
    start, end = attendance_rules.cycle_window(*attendance_rules.cycle_of(doc.overtime_date))
    window = rules.slip_window(start, end)
    made = []
    for row in doc.get("employees") or []:
        existing = frappe.db.get_value(SLIP, {
            "employee": row.employee, "docstatus": ["<", 2],
            "start_date": ["<=", getdate(doc.overtime_date)],
            "end_date": [">=", getdate(doc.overtime_date)]}, "name")
        if existing:
            made.append(existing)
            continue
        try:
            slip = frappe.get_doc({
                "doctype": SLIP, "employee": row.employee, "company": doc.get("company"),
                "department": doc.get("department"), "posting_date": today(),
                "start_date": window["start_date"], "end_date": window["end_date"]})
            slip.flags.ignore_permissions = True
            slip.flags.ignore_mandatory = True
            slip.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: overtime slip for an authorised request")
            continue
        made.append(slip.name)
    return made


# ── 4. The three kinds of day, as masters ─────────────────────────────
def seed_overtime_types():
    """The Employment Act's floor, made once. An hour is worked out of the
    earnings the salary structures work out from the base (Frappe HR asks
    for them on an Overtime Type), and each type pays through the company's
    own overtime earning for its rate. Luuka amend them after; this never
    writes over a type that is already there."""
    kinds = [kind for kind in (rules.WEEKDAY, rules.REST_DAY, rules.PUBLIC_HOLIDAY)
             if not frappe.db.exists(TYPE, rules.type_name_for(kind))]
    higher = not frappe.db.exists(TYPE, rules.HIGHER_EARNERS)
    if not kinds and not higher:
        return
    hourly = _hourly_components()
    if not hourly:
        message = ("HRMS Addon: the overtime types are not made yet. No submitted salary structure works "
                   "an earning out from the base for an hour of overtime to be priced from.")
        frappe.log_error(title=message)
        print(message)
        return
    earnings = frappe.get_all("Salary Component", filters={"type": "Earning"},
                              fields=["name", "salary_component_abbr"])
    weekday_component = rules.component_for_rate(rules.ACT_MULTIPLIERS[rules.WEEKDAY], earnings)
    for kind in kinds:
        _make_type(rules.type_name_for(kind),
                   rules.component_for_rate(rules.ACT_MULTIPLIERS[kind], earnings) or _overtime_component(),
                   hourly, rules.ACT_MULTIPLIERS[kind])
    # a weekday for those whose gross is above the line pays 1x (§4.12)
    if higher:
        _make_type(rules.HIGHER_EARNERS,
                   rules.component_for_rate(rules.HIGHER_EARNER_MULTIPLIER, earnings) or weekday_component
                   or _overtime_component(),
                   hourly, rules.HIGHER_EARNER_MULTIPLIER, gross_above=rules.GROSS_THRESHOLD)


def _hourly_components():
    """The earnings the active salary structures work out from the base."""
    structures = set(frappe.get_all("Salary Structure", filters={"docstatus": 1, "is_active": "Yes"},
                                    pluck="name"))
    found = []
    for row in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure", "parentfield": "earnings"},
                              fields=["parent", "salary_component", "formula", "amount_based_on_formula",
                                      "statistical_component", "do_not_include_in_total"], order_by="idx asc"):
        if row.parent in structures and rules.works_from_base(row) and row.salary_component not in found:
            found.append(row.salary_component)
    return found


def _make_type(name, component, hourly, standard, gross_above=None):
    values = {
        "doctype": TYPE, "__newname": name, "overtime_salary_component": component,
        "overtime_calculation_method": "Salary Component Based",
        "applicable_salary_component": [{"salary_component": earning} for earning in hourly],
        "standard_multiplier": standard,
        "applicable_for_weekend": 1, "weekend_multiplier": rules.ACT_MULTIPLIERS[rules.REST_DAY],
        "applicable_for_public_holiday": 1,
        "public_holiday_multiplier": rules.ACT_MULTIPLIERS[rules.PUBLIC_HOLIDAY],
    }
    if gross_above:
        values["custom_gross_above"] = gross_above
    try:
        doc = frappe.get_doc(values)
        doc.flags.ignore_permissions = True
        doc.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: making the %s overtime type" % name)
        print("HRMS Addon: the %s overtime type could not be made. See the Error Log." % name)


def _overtime_component():
    """An Overtime Type cannot be saved without the salary component it
    pays through, so the component is made once if Luuka have none. It is
    an earning and nothing more: how it is taxed and where it posts is
    theirs to set."""
    for name in ("Overtime", "Overtime Allowance"):
        if frappe.db.exists("Salary Component", name):
            return name
    try:
        doc = frappe.get_doc({
            "doctype": "Salary Component", "salary_component": "Overtime",
            "salary_component_abbr": "OT", "type": "Earning",
            "description": "Overtime, paid through the Overtime Slip."})
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert()
    except Exception:
        frappe.log_error(title="HRMS Addon: the overtime salary component")
        return None
    return doc.name


def warn_below_the_act():
    """after_migrate: a multiplier somebody has edited under the statutory
    floor is said out loud on the deploy rather than found in a payslip."""
    for kind in (rules.WEEKDAY, rules.REST_DAY, rules.PUBLIC_HOLIDAY):
        name = rules.type_name_for(kind)
        row = _type_row(name) if frappe.db.exists(TYPE, name) else None
        if not row:
            continue
        multiplier = rules.multiplier_for(kind, row)
        if rules.below_the_act(kind, multiplier):
            message = ("HRMS Addon: %s pays %sx on a %s, under the Employment Act's %sx"
                       % (name, multiplier, kind.lower(), rules.ACT_MULTIPLIERS[kind]))
            frappe.log_error(title=message)
            print(message)


def fill_gross_line():
    """The higher earners' type made before it carried its line gets the
    minutes' UGX 500,000. A line HR have set is theirs."""
    if frappe.db.exists(TYPE, rules.HIGHER_EARNERS) and \
            not flt(frappe.db.get_value(TYPE, rules.HIGHER_EARNERS, "custom_gross_above")):
        frappe.db.set_value(TYPE, rules.HIGHER_EARNERS, "custom_gross_above", rules.GROSS_THRESHOLD,
                            update_modified=False)


def setup_on_migrate():
    seed_overtime_types()
    fill_gross_line()
    stamp_untyped()
    warn_below_the_act()
