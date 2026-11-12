# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Casuals paid by the week, on the site. The rules, and what Luuka asked for,
are in weekly_pay_rules.py (scripts/verify_weekly_pay.py).

  dates_for             where a weekly payroll for these people starts and stops
  payroll_validate      Payroll Entry validate: it starts where the last one
                        stopped, whatever was sent
  PayrollEntryWeekly    Get Employees: those paid by the week with days or
                        overtime to pay, and the Per Piece casuals with piece
                        pay in its days, each given the weekly structure the
                        first time
  slip_before_validate  Salary Slip before_validate: the days it pays, their
                        hours and the rate, and the approved overtime
  SalarySlipWeekly      the structure's two lines read those, and no tax is
                        worked out or added
  slip_validate         Salary Slip validate: the days it shows
  show_on_figures       and the same days on the payroll's Employees tab
  assign_people         the weekly structure for those who have none, as Get
                        Employees gives it (piece_pay.py writes their pay first)
  rates_of              each casual's rate on a day, from their Hourly Rates
  rate_validate         an Hourly Rate: more than nothing, one a day a person

A Per Piece casual's week is Additional Salary their week's Output Pay Run
wrote (piece_pay.py, output_pay.py), which the slip reads as it reads every
other.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, strip_html, today

from hrms_addon.hrms_addon import output_pay, output_rules
from hrms_addon.hrms_addon import weekly_pay_rules as rules

PAYROLL = "Payroll Entry"
SLIP = "Salary Slip"
RUN = "Output Pay Run"
ASSIGNMENT = "Salary Structure Assignment"
STRUCTURE = "Salary Structure"
COMPONENT = "Salary Component"
COMPONENT_ACCOUNT = "Salary Component Account"
ATTENDANCE = "Attendance"
DAY = "Weekly Pay Day"
TABLE = "custom_weekly_days"
HOURS = "custom_weekly_hours"
RATE = "custom_weekly_rate"
OVERTIME_HOURS = "custom_weekly_overtime_hours"
OVERTIME_PAY = "custom_weekly_overtime"
# the earning a casual's overtime is paid under on the weekly structure, made once where the site has none
OVERTIME_COMPONENT = ("Casual Overtime", "COT")
OVERTIME_TYPE = "Overtime Type"
# a casual's rate, from a day: its own record, for HR alone (doctype/hourly_rate)
RATE_DOCTYPE = "Hourly Rate"
OVERTIME_SLIP = "Overtime Slip"
OVERTIME_DETAIL = "Overtime Details"
BASIC = "Basic"
TITLE = "Weekly Pay"
# assignments made in one go are saved this often, so a click cut short carries on where it stopped
SAVE_EVERY = 50


# ── The dates ─────────────────────────────────────────
@frappe.whitelist()
def dates_for(company=None, branch=None, department=None, designation=None, grade=None):
    """{"start", "end", "last"} for a new weekly payroll for these people."""
    frappe.has_permission(PAYROLL, "read", throw=True)
    wanted = {"company": company, "branch": branch, "department": department,
              "designation": designation, "grade": grade}
    return rules.dates(_last_executed(wanted), _latest_attendance(wanted))


def payroll_validate(doc, method=None):
    """A weekly payroll starts the day after the last one for the same people stopped."""
    if not rules.on_weekly_pay(doc):
        return
    last = _last_executed(doc, doc.name)
    if last:
        doc.start_date = rules.dates(last, None)["start"]
    errors = rules.date_errors(doc.get("start_date"), doc.get("end_date"), last)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TITLE))


def _last_executed(wanted, name=None):
    """Where the last payroll for these people stopped: the last weekly payroll, or a monthly Hourly run from before
    there were any."""
    company = wanted.get("company")
    runs = frappe.get_all(PAYROLL, filters={"company": company, "payroll_frequency": rules.WEEKLY, "docstatus": 1,
                                            "salary_slip_based_on_timesheet": 0, "name": ["!=", name or ""]},
                          fields=["end_date", *rules.FILTERS], limit_page_length=0)
    runs += [{"end_date": row.to_date, "branch": row.branch}
             for row in frappe.get_all(RUN, filters={"company": company, "section": output_rules.HOURLY, "docstatus": 1},
                                       fields=["to_date", "branch"], limit_page_length=0)]
    return rules.last_executed(runs, wanted)


def _employee_filters(wanted):
    filters = {"company": wanted.get("company"), "custom_pay_category": ["in", list(rules.CATEGORIES)]}
    for field in rules.FILTERS:
        if wanted.get(field):
            filters[field] = wanted.get(field)
    return filters


def _latest_attendance(wanted):
    """The last day before today with attendance of those paid by the week."""
    people = frappe.get_all("Employee", filters=_employee_filters(wanted), pluck="name", limit_page_length=0)
    if not people:
        return None
    return frappe.db.get_value(ATTENDANCE, {"employee": ["in", people], "docstatus": 1, "status": ["in", rules.WORKED],
                                            "attendance_date": ["<", today()]},
                               "attendance_date", order_by="attendance_date desc")


# ── The days ──────────────────────────────────────────
def days_to_pay(employees, start, end, company):
    """{employee: the days still to pay them, up to the payroll's End}, read for them all at once."""
    employees = list(employees or ())
    if not employees or not end:
        return {}
    first = frappe.db.get_value(PAYROLL, {"company": company, "payroll_frequency": rules.WEEKLY, "docstatus": 1,
                                          "salary_slip_based_on_timesheet": 0},
                                "start_date", order_by="start_date asc")
    since = rules.earliest(first, start) or end
    between = ["between", [since, end]]
    attendance, paid, covered = {}, {}, {}
    for row in frappe.get_all(ATTENDANCE, filters={"employee": ["in", employees], "docstatus": 1,
                                                   "status": ["in", rules.WORKED], "attendance_date": between},
                              fields=["employee", "attendance_date", "status", "working_hours"],
                              limit_page_length=0):
        attendance.setdefault(row.employee, []).append(row)
    for row in frappe.get_all(DAY, filters={"employee": ["in", employees], "docstatus": 1, "attendance_date": between},
                              fields=["employee", "attendance_date"], limit_page_length=0):
        paid.setdefault(row.employee, []).append(row.attendance_date)
    for row in frappe.get_all(SLIP, filters={"employee": ["in", employees], "docstatus": 1,
                                             "payroll_frequency": ["!=", rules.WEEKLY], "end_date": [">=", since]},
                              fields=["employee", "start_date", "end_date"], limit_page_length=0):
        covered.setdefault(row.employee, []).append((row.start_date, row.end_date))
    standard = flt(output_pay.settings().get("standard_hours")) or output_rules.STANDARD_HOURS
    return {employee: rules.to_pay(attendance.get(employee), paid.get(employee), covered.get(employee), standard)
            for employee in employees}


def overtime_due(employees, start, end, company):
    """{employee: the approved overtime still to pay them, up to the payroll's End}, read for them all at once
    (rules.overtime_to_pay). The hours are those the overtime module wrote on the attendance when the request was
    approved; those a weekly slip or an Overtime Slip has paid are not paid again."""
    employees = list(employees or ())
    if not employees or not end:
        return {}
    first = frappe.db.get_value(PAYROLL, {"company": company, "payroll_frequency": rules.WEEKLY, "docstatus": 1,
                                          "salary_slip_based_on_timesheet": 0},
                                "start_date", order_by="start_date asc")
    since = rules.earliest(first, start) or end
    between = ["between", [since, end]]
    attendance, paid = {}, {}
    for row in frappe.get_all(ATTENDANCE, filters={"employee": ["in", employees], "docstatus": 1,
                                                   "attendance_date": between, "actual_overtime_duration": [">", 0],
                                                   "overtime_type": ["is", "set"]},
                              fields=["name", "employee", "attendance_date", "status", "actual_overtime_duration",
                                      "overtime_type"], limit_page_length=0):
        attendance.setdefault(row.employee, []).append(row)
    days = {row.name: (row.employee, row.attendance_date) for rows in attendance.values() for row in rows}
    # hours paid on a submitted Overtime Slip, as everyone else's are, before the casual was paid by the week
    for row in frappe.get_all(OVERTIME_DETAIL, filters={"parenttype": OVERTIME_SLIP, "docstatus": 1,
                                                       "reference_document": ["in", list(days)]},
                              fields=["reference_document", "overtime_duration"], limit_page_length=0) if days else []:
        employee, day = days[row.reference_document]
        theirs = paid.setdefault(employee, {})
        theirs[day] = flt(theirs.get(day)) + flt(row.overtime_duration)
    for row in frappe.get_all(DAY, filters={"employee": ["in", employees], "docstatus": 1, "attendance_date": between,
                                            "overtime_hours": [">", 0]},
                              fields=["employee", "attendance_date", "overtime_hours"], limit_page_length=0):
        theirs = paid.setdefault(row.employee, {})
        theirs[row.attendance_date] = flt(theirs.get(row.attendance_date)) + flt(row.overtime_hours)
    return {employee: rules.overtime_to_pay(attendance.get(employee), paid.get(employee)) for employee in employees}


def multipliers(employee, rows):
    """{date: the multiplier for that day's overtime}: its Overtime Type's, for the sort of day it is for the
    person (overtime.day_kind), as the overtime module costs a request. Read for one slip's days only."""
    from hrms_addon.hrms_addon import overtime, overtime_rules

    types = {name: frappe.get_cached_doc(OVERTIME_TYPE, name).as_dict()
             for name in {row["overtime_type"] for row in rows or []} if frappe.db.exists(OVERTIME_TYPE, name)}
    return {row["attendance_date"]: overtime_rules.multiplier_for(overtime.day_kind(employee, row["attendance_date"]),
                                                                  types.get(row["overtime_type"]))
            for row in rows or []}


def rate_history(employees, until=None):
    """{employee: [{"rate", "from_date"}]}: their Hourly Rates from on or before `until`, read for them all at
    once."""
    employees = [employee for employee in employees or () if employee]
    if not employees:
        return {}
    filters = {"employee": ["in", employees]}
    if until:
        filters["from_date"] = ["<=", getdate(until)]
    found = {}
    for row in frappe.get_all(RATE_DOCTYPE, filters=filters, fields=["employee", "rate", "from_date"],
                              order_by="from_date asc", limit_page_length=0):
        found.setdefault(row.employee, []).append({"rate": row.rate, "from_date": row.from_date})
    return found


def standard_rate():
    """Output Pay Settings' Standard Hourly Rate, for a casual with no rate of their own."""
    return flt(output_pay.settings().get("standard_hourly_rate"))


def rates_of(employees, on=None):
    """{employee: their hourly rate in force on `on`, today where none is given}: their own Hourly Rate, else
    Output Pay Settings' standard one."""
    employees = [employee for employee in employees or () if employee]
    day = getdate(on or today())
    standard, history = standard_rate(), rate_history(employees, day)
    return {employee: rules.rate_on(history.get(employee), day) or standard for employee in employees}


def rate_validate(doc, method=None):
    """An Hourly Rate: more than nothing, from a day, and one a day for each person (rules.rate_errors)."""
    clash = frappe.db.get_value(RATE_DOCTYPE, {"employee": doc.get("employee"), "from_date": doc.get("from_date"),
                                               "name": ["!=", doc.name or ""]}, "name") if doc.get("employee") else None
    errors = rules.rate_errors(doc.get("rate"), doc.get("from_date"), clash)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(RATE_DOCTYPE))


def show_on_figures(doc, figures):
    """A weekly payroll's Employees tab shows the days its slips will (slip_figures.expected), and the hours (Luuka,
    12 Nov 2026: "add hours worked on the weekly payroll"): a Per Piece casual's pay is their bags, and none of their
    days or hours is paid."""
    hourly = set(frappe.get_all("Employee", filters={"name": ["in", list(figures)], "custom_pay_category": rules.WEEKLY},
                                pluck="name", limit_page_length=0)) if figures else set()
    days = days_to_pay([employee for employee in figures if employee in hourly], doc.get("start_date"),
                       doc.get("end_date"), doc.get("company"))
    period = date_diff(doc.get("end_date"), doc.get("start_date")) + 1
    for employee, row in figures.items():
        row["custom_working_days"] = period
        row["custom_paid_days"] = len(days.get(employee) or [])
        row["custom_hours_worked"] = round(sum(flt(day.get("hours")) for day in days.get(employee) or []), 2)


# ── The Salary Slip ───────────────────────────────────
def slip_before_validate(doc, method=None):
    """The days a slip pays, worked out each time it is saved or submitted, so that it pays what is unpaid then."""
    if not rules.on_weekly_pay(doc) or not doc.get("employee") or not doc.get("end_date"):
        return
    if frappe.db.get_value("Employee", doc.employee, "custom_pay_category") != rules.WEEKLY:
        return
    doc.flags.weekly_pay = True
    days = days_to_pay([doc.employee], doc.get("start_date"), doc.get("end_date"), doc.get("company")).get(doc.employee)
    overtime = overtime_due([doc.employee], doc.get("start_date"), doc.get("end_date"),
                            doc.get("company")).get(doc.employee) or []
    # each day at the rate in force that day: a raise from a day leaves the days before it at the old rate
    standard, history = standard_rate(), rate_history([doc.employee], doc.get("end_date")).get(doc.employee)
    table = rules.days_table(days, overtime)
    rates = rules.day_rates([row["attendance_date"] for row in table], history, standard)
    missing = rules.unrated(table, rates)
    if missing:
        frappe.throw(_("{0} has hours but no hourly rate on {1}: give them an Hourly Rate from that day, or set the "
                       "Standard Hourly Rate on Output Pay Settings.").format(doc.employee, rules.shown(missing[0])),
                     title=_(TITLE))
    doc.set(TABLE, [dict(row, employee=doc.employee, rate=rates.get(row["attendance_date"])) for row in table])
    doc.set(HOURS, rules.total_hours(days))
    doc.set(RATE, rules.rate_on(history, doc.get("end_date")) or standard)
    doc.set(OVERTIME_HOURS, round(sum(flt(row["hours"]) for row in overtime), 2))
    doc.set(OVERTIME_PAY, rules.overtime_amount(overtime, rates, multipliers(doc.employee, overtime)))


def slip_validate(doc, method=None):
    """After Frappe HR has counted the days: the days of the period, and those this slip pays the hours of."""
    if doc.flags.get("weekly_pay"):
        doc.custom_days_in_period = date_diff(doc.end_date, doc.start_date) + 1
        doc.custom_days_paid = rules.days_paid(doc.get(TABLE))


class SalarySlipWeekly:
    def get_data_for_eval(self):
        data, default_data = super().get_data_for_eval()
        pay = rules.week_pay(self.get(TABLE), self.get(HOURS), self.get(RATE))
        overtime = flt(self.get(OVERTIME_PAY))
        data[rules.PAY], data[rules.OVERTIME] = pay, overtime
        default_data[rules.PAY], default_data[rules.OVERTIME] = pay, overtime
        return data, default_data

    def add_tax_components(self):
        """Nothing for tax on weekly pay. With no tax line on a structure, Frappe HR adds the Salary Component
        master's own, and with it asks for an Income Tax Slab; here it is left as it leaves a slip with no tax."""
        if not rules.on_weekly_pay(self):
            return super().add_tax_components()
        self.other_deduction_components = []
        self._component_based_variable_tax = {}


class SalaryStructureAssignmentWeekly:
    def _get_component_eval_context(self):
        """An assignment works its lines out for a whole month with no slip: nothing has been worked yet."""
        data = super()._get_component_eval_context()
        data[rules.PAY] = 0
        data[rules.OVERTIME] = 0
        return data


# ── Get Employees ─────────────────────────────────────
class PayrollEntryWeekly:
    @frappe.whitelist()
    def fill_employee_details(self):
        if not rules.on_weekly_pay(self):
            return _leave_out_casuals(self, super().fill_employee_details())
        _tell_not_assigned(assign_missing(self))
        unmarked = super().fill_employee_details()
        _keep_those_to_pay(self)
        if not unmarked:
            return unmarked
        kept = {row.employee for row in self.employees}
        return [row for row in unmarked if row["employee"] in kept]


def _keep_those_to_pay(doc):
    """Only those with something to pay: the casuals by the hour with days or approved overtime to pay, and anyone
    with pay as Additional Salary in the payroll's days: a Per Piece casual's piece pay, anyone's arrears
    (piece_pay.waiting). One with hours and no rate is left out and named: their days wait for the next payroll."""
    from hrms_addon.hrms_addon import piece_pay

    names = [row.employee for row in doc.get("employees") or []]
    categories = {row.name: row.custom_pay_category for row in frappe.get_all(
        "Employee", filters={"name": ["in", names]}, fields=["name", "custom_pay_category"],
        limit_page_length=0)} if names else {}
    weekly = [name for name in names if categories.get(name) == rules.WEEKLY]
    pieces = [name for name in names if categories.get(name) == rules.PER_PIECE]
    days = days_to_pay(weekly, doc.get("start_date"), doc.get("end_date"), doc.get("company"))
    due = overtime_due(weekly, doc.get("start_date"), doc.get("end_date"), doc.get("company"))
    standard, history = standard_rate(), rate_history(weekly, doc.get("end_date"))
    no_rate = []
    for name in weekly:
        table = rules.days_table(days.get(name), due.get(name))
        if rules.unrated(table, rules.day_rates([row["attendance_date"] for row in table], history.get(name), standard)):
            no_rate.append(name)
    keep = {name for name in weekly if (days.get(name) or due.get(name)) and name not in no_rate}
    keep |= piece_pay.waiting(pieces, doc.get("start_date"), doc.get("end_date"))
    # arrears and anything else owed a casual by the hour, entered as Additional Salary (Luuka, 11 Nov 2026)
    keep |= piece_pay.waiting([name for name in weekly if name not in no_rate], doc.get("start_date"),
                              doc.get("end_date"))
    doc.set("employees", [row for row in doc.get("employees") if row.employee in keep])
    doc.number_of_employees = len(doc.employees)
    if no_rate:
        frappe.msgprint(_("Left out, no hourly rate: {0}. Give them an Hourly Rate, or set the Standard Hourly Rate "
                          "on Output Pay Settings.").format(", ".join(no_rate)), title=_(TITLE), indicator="orange")
    if not doc.employees:
        frappe.throw(_("Nobody has attendance, piece work or Additional Salary to pay up to {0}.").format(
            rules.shown(doc.get("end_date"))), title=_(TITLE))


def _leave_out_casuals(doc, unmarked):
    """A monthly payroll that reaches into weekly pay leaves out the casuals paid by the week (rules.weekly_began):
    the weekly payroll pays their days and their piece work, which a monthly slip would pay again."""
    began = frappe.db.get_value(PAYROLL, {"company": doc.get("company"), "payroll_frequency": rules.WEEKLY,
                                          "docstatus": ["<", 2], "salary_slip_based_on_timesheet": 0},
                                "start_date", order_by="start_date asc")
    names = [row.employee for row in doc.get("employees") or []]
    if not names or not rules.weekly_began(began, doc.get("end_date")):
        return unmarked
    casuals = set(frappe.get_all("Employee", filters={"name": ["in", names],
                                                     "custom_pay_category": ["in", list(rules.CATEGORIES)]},
                                 pluck="name", limit_page_length=0))
    if not casuals:
        return unmarked
    doc.set("employees", [row for row in doc.get("employees") if row.employee not in casuals])
    doc.number_of_employees = len(doc.employees)
    if not doc.employees:
        frappe.throw(_("Everyone found is a casual paid by the week: their weekly payroll pays them."), title=_(TITLE))
    frappe.msgprint(_("Left out, paid by the week: {0} casual(s).").format(len(casuals)), title=_(TITLE),
                    indicator="orange")
    return [row for row in unmarked if row["employee"] not in casuals] if unmarked else unmarked


def _tell_not_assigned(failed):
    if failed:
        said = "<br>".join("%s: %s" % (name, why) for name, why in sorted(failed.items()))
        frappe.msgprint(_("Left out, no salary assignment:") + "<br>" + said, title=_(TITLE), indicator="orange")


def assign_missing(doc):
    """Each person paid by the week on these filters with no assignment on the company's weekly structure gets one,
    so nobody sets them up by hand. {employee: why not}, for those it could not be done for."""
    structure = structure_for(doc.get("company"))
    filters = dict(_employee_filters(doc), status=["!=", "Inactive"])
    people = [row for row in frappe.get_all("Employee", filters=filters, limit_page_length=0,
                                            fields=["name", "date_of_joining", "relieving_date"])
              if rules.still_here(row.relieving_date, doc.get("start_date"))]
    return _assign_all(people, structure, doc)


# the Additional Salary Frappe HR leaves whole whatever its component (salary_slip.update_component_row)
WHOLE = ("Arrear", "Payroll Correction", "Employee Benefit Claim")


def additional_validate(doc, method=None):
    """A casual's Additional Salary: their arrears and anything else owed beside the pieces and the hours (Luuka,
    11 Nov 2026: "arrears and additional salary should be done on the additional salary"). Frappe HR cuts it by the
    days paid where its component is cut by payment days, and a Per Piece casual is paid no days, so it would come to
    nothing; a casual by the hour's would come to a part. Such a component is refused, saying what to do."""
    if not doc.get("employee") or not doc.get("salary_component") or doc.get("ref_doctype") in WHOLE:
        return
    category = frappe.db.get_value("Employee", doc.employee, "custom_pay_category")
    if category not in (rules.WEEKLY, rules.PER_PIECE):
        return
    if frappe.db.get_value("Salary Component", doc.salary_component, "depends_on_payment_days"):
        frappe.throw(_("{0} is cut by the days paid, and {1} is a casual paid by the week, so it would come to less "
                       "than is owed. Untick Depends on Payment Days on {0}, or use a component that is not cut, such "
                       "as Arrears.").format(doc.salary_component, doc.employee), title=_("Additional Salary"))


def assign_people(employees, company, start):
    """The weekly structure for those of these employees with no assignment on it, as Get Employees gives it, so
    their piece pay can be written before the payroll's Get Employees (piece_pay.py). {employee: why not}."""
    employees = sorted(set(employees or ()))
    if not employees:
        return {}
    structure = structure_for(company)
    people = frappe.get_all("Employee", filters={"name": ["in", employees]}, limit_page_length=0,
                            fields=["name", "date_of_joining", "relieving_date"])
    return _assign_all(people, structure, {"company": company, "start_date": start})


def _assign_all(people, structure, payroll):
    """Each of these people with no assignment on the structure gets one. {employee: why not}."""
    if not people:
        return {}
    have, taken = set(), {}
    for row in frappe.get_all(ASSIGNMENT, filters={"employee": ["in", [row.name for row in people]], "docstatus": 1},
                              fields=["employee", "salary_structure", "from_date"], limit_page_length=0):
        taken.setdefault(row.employee, []).append(row.from_date)
        if row.salary_structure == structure:
            have.add(row.employee)
    currency = frappe.get_cached_value("Company", payroll.get("company"), "default_currency")
    failed = {}
    made = 0
    for person in people:
        if person.name in have:
            continue
        reason = _assign(person, structure, payroll, currency, taken.get(person.name))
        if reason:
            failed[person.name] = reason
            continue
        made += 1
        if not made % SAVE_EVERY:
            frappe.db.commit()  # nosemgrep: a click cut short by the server's time limit carries on from here
    return failed


def _assign(person, structure, payroll, currency, taken):
    """One person's assignment, or why not: one who cannot have one does not stop the rest."""
    day = rules.assignment_from(person.date_of_joining, payroll.get("start_date"), taken)
    if not day:
        return _("they already have an assignment from that day")
    frappe.db.savepoint("weekly_assignment")
    try:
        assignment = frappe.get_doc({"doctype": ASSIGNMENT, "employee": person.name, "salary_structure": structure,
                                     "from_date": day, "company": payroll.get("company"), "currency": currency})
        assignment.flags.ignore_permissions = True
        assignment.insert()
        assignment.submit()
    except Exception as error:  # noqa: BLE001 — said to whoever clicked, with the others made
        frappe.db.rollback(save_point="weekly_assignment")
        frappe.clear_last_message()
        return strip_html(str(error)) or error.__class__.__name__
    return None


def structure_for(company):
    """The company's weekly structure, made the first time: two lines, the week's hours at the rate and the approved
    overtime, and no PAYE, NSSF or LST. A structure made before overtime was paid by the week has the overtime line
    added (_add_overtime_line). Each earning takes an account too, as posting the payroll needs one."""
    name = rules.structure_name(frappe.get_cached_value("Company", company, "abbr"))
    component = output_pay._component(output_rules.HOURLY)
    overtime = _overtime_component()
    for earning in (component, overtime):
        _give_account(earning, company)
    if frappe.db.get_value(STRUCTURE, name, "docstatus") == 1:
        _add_overtime_line(name, overtime)
        return name
    for earning in (component, overtime):
        if cint(frappe.db.get_value(COMPONENT, earning, "depends_on_payment_days")):
            frappe.throw(_("{0} is cut by payment days: untick Depends on Payment Days on it, as a casual's hours "
                           "are already what they worked.").format(earning), title=_(TITLE))
    structure = frappe.get_doc({
        "doctype": STRUCTURE, "name": name, "company": company, "is_active": "Yes",
        "payroll_frequency": rules.WEEKLY, "salary_slip_based_on_timesheet": 0,
        "currency": frappe.get_cached_value("Company", company, "default_currency"),
        "earnings": [{"salary_component": component, "amount_based_on_formula": 1, "formula": rules.PAY},
                     {"salary_component": overtime, "amount_based_on_formula": 1, "formula": rules.OVERTIME}]})
    structure.flags.ignore_permissions = True
    structure.insert()
    structure.submit()
    return name


def _overtime_component():
    """The earning a casual's overtime is paid under: made once where the site has none, an Earning, not pro-rated by
    payment days (the hours are what was approved), and gone from a slip where it is nothing."""
    name, abbr = OVERTIME_COMPONENT
    if not frappe.db.exists(COMPONENT, name):
        component = frappe.get_doc({
            "doctype": COMPONENT, "name": name, "salary_component": name, "salary_component_abbr": abbr,
            "type": "Earning", "depends_on_payment_days": 0, "is_tax_applicable": 1, "remove_if_zero_valued": 1,
            "description": "A casual's approved overtime, paid by the week at their own hourly rate."})
        component.flags.ignore_permissions = True
        component.insert()
    return name


# what a structure's line takes from its component (Salary Detail's fetch_from)
FETCHED = ("statistical_component", "is_tax_applicable", "is_flexible_benefit", "variable_based_on_taxable_salary",
           "depends_on_payment_days", "do_not_include_in_total", "exempted_from_income_tax",
           "do_not_include_in_accounts", "accrual_component")


def _add_overtime_line(name, component):
    """A weekly structure made before overtime was paid by the week gets its overtime line, written as the desk
    writes one; a structure that has it is left as it is."""
    if frappe.db.exists("Salary Detail", {"parenttype": STRUCTURE, "parent": name, "parentfield": "earnings",
                                          "formula": rules.OVERTIME}):
        return
    flags = frappe.db.get_value(COMPONENT, component, ["salary_component_abbr"] + list(FETCHED), as_dict=True) or {}
    structure = frappe.get_doc(STRUCTURE, name)
    row = structure.append("earnings", dict({field: flags.get(field) for field in FETCHED}, salary_component=component,
                                            abbr=flags.get("salary_component_abbr"), amount_based_on_formula=1,
                                            formula=rules.OVERTIME))
    row.docstatus = structure.docstatus
    row.db_insert()
    frappe.clear_document_cache(STRUCTURE, name)


def _give_account(component, company):
    if frappe.db.exists(COMPONENT_ACCOUNT, {"parent": component, "parenttype": COMPONENT, "company": company}):
        return
    rows = frappe.get_all(COMPONENT_ACCOUNT, filters={"parenttype": COMPONENT, "company": company},
                          fields=["parent", "account"], limit_page_length=0)
    earnings = set(frappe.get_all(COMPONENT, filters={"type": "Earning"}, pluck="name", limit_page_length=0))
    account = rules.account_to_copy(rows, earnings, BASIC)
    if account:
        doc = frappe.get_doc(COMPONENT, component)
        doc.append("accounts", {"company": company, "account": account})
        doc.flags.ignore_permissions = True
        doc.save()
