# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Casuals paid by the week, on the site. The rules, and what Luuka asked for,
are in weekly_pay_rules.py (scripts/verify_weekly_pay.py).

  dates_for             where a weekly payroll for these people starts and stops
  payroll_validate      Payroll Entry validate: it starts where the last one
                        stopped, whatever was sent
  PayrollEntryWeekly    Get Employees: those paid by the week with days to pay,
                        each given the weekly structure the first time
  slip_before_validate  Salary Slip before_validate: the days it pays, their
                        hours and the rate
  SalarySlipWeekly      the structure's one line reads those, and no tax is
                        worked out or added
  slip_validate         Salary Slip validate: the days it shows
  show_on_figures       and the same days on the payroll's Employees tab
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, strip_html, today

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
    filters = {"company": wanted.get("company"), "custom_pay_category": rules.WEEKLY}
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


def rates_of(employees):
    """{employee: their hourly rate}: their own, else Output Pay Settings' standard one."""
    standard = flt(output_pay.settings().get("standard_hourly_rate"))
    return {row.name: flt(row.custom_hourly_rate) or standard
            for row in frappe.get_all("Employee", filters={"name": ["in", list(employees or ())]},
                                      fields=["name", "custom_hourly_rate"], limit_page_length=0)}


def show_on_figures(doc, figures):
    """A weekly payroll's Employees tab shows the days its slips will (slip_figures.expected)."""
    days = days_to_pay(figures, doc.get("start_date"), doc.get("end_date"), doc.get("company"))
    period = date_diff(doc.get("end_date"), doc.get("start_date")) + 1
    for employee, row in figures.items():
        row["custom_working_days"] = period
        row["custom_paid_days"] = len(days.get(employee) or [])


# ── The Salary Slip ───────────────────────────────────
def slip_before_validate(doc, method=None):
    """The days a slip pays, worked out each time it is saved or submitted, so that it pays what is unpaid then."""
    if not rules.on_weekly_pay(doc) or not doc.get("employee") or not doc.get("end_date"):
        return
    if frappe.db.get_value("Employee", doc.employee, "custom_pay_category") != rules.WEEKLY:
        return
    doc.flags.weekly_pay = True
    days = days_to_pay([doc.employee], doc.get("start_date"), doc.get("end_date"), doc.get("company")).get(doc.employee)
    hours, rate = rules.total_hours(days), rates_of([doc.employee]).get(doc.employee)
    if hours and not rate:
        frappe.throw(_("{0} has hours but no hourly rate: set one on the employee or the Standard Hourly Rate on "
                       "Output Pay Settings.").format(doc.employee), title=_(TITLE))
    doc.set(TABLE, [dict(day, employee=doc.employee) for day in days or []])
    doc.set(HOURS, hours)
    doc.set(RATE, rate)


def slip_validate(doc, method=None):
    """After Frappe HR has counted the days: the days of the period, and those this slip pays."""
    if doc.flags.get("weekly_pay"):
        doc.custom_days_in_period = date_diff(doc.end_date, doc.start_date) + 1
        doc.custom_days_paid = len(doc.get(TABLE) or [])


class SalarySlipWeekly:
    def get_data_for_eval(self):
        data, default_data = super().get_data_for_eval()
        pay = rules.amount(self.get(HOURS), self.get(RATE))
        data[rules.PAY] = pay
        default_data[rules.PAY] = pay
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
        return data


# ── Get Employees ─────────────────────────────────────
class PayrollEntryWeekly:
    @frappe.whitelist()
    def fill_employee_details(self):
        if not rules.on_weekly_pay(self):
            return super().fill_employee_details()
        _tell_not_assigned(assign_missing(self))
        unmarked = super().fill_employee_details()
        _keep_those_to_pay(self)
        if not unmarked:
            return unmarked
        kept = {row.employee for row in self.employees}
        return [row for row in unmarked if row["employee"] in kept]


def _keep_those_to_pay(doc):
    """Only those paid by the week with days to pay. One with hours and no rate is left out and named: their days
    wait for the next payroll."""
    names = [row.employee for row in doc.get("employees") or []]
    weekly = frappe.get_all("Employee", filters={"name": ["in", names], "custom_pay_category": rules.WEEKLY},
                            pluck="name", limit_page_length=0) if names else []
    days = days_to_pay(weekly, doc.get("start_date"), doc.get("end_date"), doc.get("company"))
    rates = rates_of(weekly)
    no_rate = sorted(name for name in weekly if rules.total_hours(days.get(name)) and not rates.get(name))
    doc.set("employees", [row for row in doc.get("employees") if days.get(row.employee) and row.employee not in no_rate])
    doc.number_of_employees = len(doc.employees)
    if no_rate:
        frappe.msgprint(_("Left out, no hourly rate: {0}. Set one on the employee or the Standard Hourly Rate on "
                          "Output Pay Settings.").format(", ".join(no_rate)), title=_(TITLE), indicator="orange")
    if not doc.employees:
        frappe.throw(_("Nobody has attendance to pay up to {0}.").format(rules.shown(doc.get("end_date"))),
                     title=_(TITLE))


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
    if not people:
        return {}
    have, taken = set(), {}
    for row in frappe.get_all(ASSIGNMENT, filters={"employee": ["in", [row.name for row in people]], "docstatus": 1},
                              fields=["employee", "salary_structure", "from_date"], limit_page_length=0):
        taken.setdefault(row.employee, []).append(row.from_date)
        if row.salary_structure == structure:
            have.add(row.employee)
    currency = frappe.get_cached_value("Company", doc.get("company"), "default_currency")
    failed = {}
    made = 0
    for person in people:
        if person.name in have:
            continue
        reason = _assign(person, structure, doc, currency, taken.get(person.name))
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
    """The company's weekly structure, made the first time: one line, the week's hours at the rate, and no PAYE, NSSF
    or LST. Its earning takes an account too, as posting the payroll needs one."""
    name = rules.structure_name(frappe.get_cached_value("Company", company, "abbr"))
    component = output_pay._component(output_rules.HOURLY)
    _give_account(component, company)
    if frappe.db.get_value(STRUCTURE, name, "docstatus") == 1:
        return name
    if cint(frappe.db.get_value(COMPONENT, component, "depends_on_payment_days")):
        frappe.throw(_("{0} is cut by payment days: untick Depends on Payment Days on it, as a casual's hours are "
                       "already what they worked.").format(component), title=_(TITLE))
    structure = frappe.get_doc({
        "doctype": STRUCTURE, "name": name, "company": company, "is_active": "Yes",
        "payroll_frequency": rules.WEEKLY, "salary_slip_based_on_timesheet": 0,
        "currency": frappe.get_cached_value("Company", company, "default_currency"),
        "earnings": [{"salary_component": component, "amount_based_on_formula": 1, "formula": rules.PAY}]})
    structure.flags.ignore_permissions = True
    structure.insert()
    structure.submit()
    return name


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
