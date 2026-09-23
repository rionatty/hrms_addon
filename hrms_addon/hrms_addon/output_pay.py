# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Output pay on the site: the machines, the daily production report, and
the month's run (minutes §4.6).

The rules are in output_rules.py, without a Frappe import
(scripts/verify_output_pay.py). This reads and writes the site.

  machine_validate   each machine's own rates are sound
  report_validate    each line priced at its machine's rate, for its width
                     or piece category, on the day it was made
  report_on_submit   refused once that month's run is paid, because the
                     report would then never be counted
  run_validate       the payroll month (26th to 25th), the lines priced,
                     and what each person is paid
  get_output         the run filled from the submitted daily reports
                     (Per Meter, Per Piece) or from attendance (Hourly)
  run_on_submit      one Additional Salary per person, on top of the basic
                     salary, which the payroll run reads as it reads every
                     other Additional Salary
  run_on_cancel      those Additional Salaries cancelled with it

WHY ADDITIONAL SALARY

It is how Frappe HR puts a one-off earning on a payslip, and it is what the
advances, the loans and the overtime module already use for the same job.
The output is already what was earned, so the components are made with
"depends on payment days" off: a Per Meter operator who missed two days
has already earned less by making less, and pro-rating it would take the
two days off twice.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from hrms_addon.hrms_addon import attendance_rules, output_rules as rules

MACHINE = "Production Machine"
REPORT = "Daily Production Report"
REPORT_LINE = "Daily Production Line"
RUN = "Output Pay Run"
SETTINGS = "Output Pay Settings"
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")
# the earning each section is written to, unless Output Pay Settings says another
COMPONENTS = {rules.PER_METER: ("Per Meter Earnings", "PME"),
              rules.PER_PIECE: ("Per Piece Earnings", "PPE"),
              rules.HOURLY: ("Hourly Earnings", "HRE")}
SETTING_FIELDS = {rules.PER_METER: "per_meter_component", rules.PER_PIECE: "per_piece_component",
                  rules.HOURLY: "hourly_component"}
PRESENT = ("Present", "Half Day", "Work From Home")
HAND_LINE_FIELDS = ("employee", "machine", "width_cm", "piece_category", "shifts", "output", "target")


# ── 1. The machines ───────────────────────────────────────────────────
def machine_validate(doc, method=None):
    errors = rules.rate_errors(doc.get("section"), [_row(row) for row in doc.get("rates") or []])
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(MACHINE))


def _machines(names):
    """{machine: (section, rate rows)} for the machines a document names."""
    found = {}
    for name in set(filter(None, names)):
        if not frappe.db.exists(MACHINE, name):
            continue
        machine = frappe.get_doc(MACHINE, name)
        found[name] = (machine.get("section"), [_row(row) for row in machine.get("rates") or []])
    return found


def _pay_categories(employees):
    if not frappe.get_meta("Employee").has_field("custom_pay_category"):
        return {}
    return {name: frappe.db.get_value("Employee", name, "custom_pay_category") or "Monthly"
            for name in set(filter(None, employees))}


# ── 2. The day: the Daily Loom Production Report ──────────────────────
def report_validate(doc, method=None):
    section = doc.get("section")
    rows = doc.get("lines") or []
    machines = _machines(row.machine for row in rows)
    checked = []
    for row in rows:
        machine_section, rates = machines.get(row.machine, (None, []))
        rate = rules.rate_for(rates, doc.get("report_date"), row.get("width_cm"),
                              row.get("piece_category"), section)
        row.rate = flt(rate["rate"]) if rate else 0
        if rate and not flt(row.get("target")):
            row.target = flt(rate.get("daily_target"))
        row.unit = rules.UNITS.get(section)
        priced = rules.line(row.get("output"), row.rate, row.get("target"))
        row.amount = priced["amount"]
        row.achieved = priced["achieved"] or 0
        checked.append(dict(_row(row), rate=flt(rate["rate"]) if rate else None))
    errors = rules.report_errors(section, checked, _pay_categories(row.employee for row in rows),
                                 {name: seat[0] for name, seat in machines.items()})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(REPORT))
    doc.total_output = round(sum(flt(row.get("output")) for row in rows), 3)
    doc.total_amount = round(sum(flt(row.get("amount")) for row in rows), 2)


def report_on_submit(doc, method=None):
    """A report for a month whose run is already paid would never be
    counted: somebody's shift would go unpaid with nothing to say so."""
    paid = _paid_run(doc.get("branch"), doc.get("section"), doc.get("report_date"))
    if paid:
        frappe.throw(_("{0} has already paid {1} for this month. Cancel and amend it to include this "
                       "report, or the shift is never paid.").format(paid, doc.get("branch")),
                     title=_(REPORT))


def report_on_cancel(doc, method=None):
    if doc.get("output_pay_run") and frappe.db.get_value(RUN, doc.output_pay_run, "docstatus") == 1:
        frappe.throw(_("This report was paid in {0}. Cancel that run first, or the pay would stand "
                       "with nothing behind it.").format(doc.output_pay_run), title=_(REPORT))


def _paid_run(branch, section, day):
    year, month = attendance_rules.cycle_of(getdate(day))
    return frappe.db.get_value(RUN, {"branch": branch, "section": section, "year": year,
                                     "month": MONTHS[month - 1], "docstatus": 1}, "name")


# ── 3. The month: the Per Meter Template ──────────────────────────────
def run_validate(doc, method=None):
    _set_period(doc)
    _one_run_a_month(doc)
    if doc.get("section") in rules.OUTPUT_SECTIONS:
        _price_lines(doc)
        _employees_from_lines(doc)
    else:
        _price_hours(doc)
    # a draft is somewhere to gather the month; only paying it has to be right
    if doc.docstatus == 1:
        errors = rules.run_errors(doc.get("section"), [_row(row) for row in doc.get("employees") or []],
                                  {row.employee: row.get("rate") for row in doc.get("employees") or []})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(RUN))
    doc.total_employees = len(doc.get("employees") or [])
    doc.total_amount = round(sum(flt(row.get("amount")) for row in doc.get("employees") or []), 2)


def _set_period(doc):
    if doc.get("month") not in MONTHS or not cint(doc.get("year")):
        frappe.throw(_("Say the payroll month and year."), title=_(RUN))
    start, end = attendance_rules.cycle_window(cint(doc.year), MONTHS.index(doc.month) + 1)
    doc.from_date, doc.to_date = start, end


def _one_run_a_month(doc):
    other = frappe.db.get_value(RUN, {"branch": doc.get("branch"), "section": doc.get("section"),
                                      "year": cint(doc.get("year")), "month": doc.get("month"),
                                      "docstatus": ["!=", 2], "name": ["!=", doc.name or ""]}, "name")
    if other:
        frappe.throw(_("{0} is already the {1} {2} run for {3}: one month is paid once.").format(
            other, doc.month, doc.year, doc.branch), title=_(RUN))


def _price_lines(doc):
    """Lines from the daily reports keep what each shift earned, at the
    rate on its day. A line entered by hand is priced at the machine's
    rate on the last day of the month."""
    section = doc.get("section")
    machines = _machines(row.machine for row in doc.get("lines") or [])
    categories = _pay_categories(row.employee for row in doc.get("lines") or [])
    errors = []
    for number, row in enumerate(doc.get("lines") or [], 1):
        machine_section, rates = machines.get(row.machine, (None, []))
        if machine_section and machine_section != section:
            errors.append(_("Line {0}: {1} is a {2} machine.").format(number, row.machine, machine_section))
        if row.employee in categories and categories[row.employee] != section:
            errors.append(_("Line {0}: {1} is paid {2}, not {3}.").format(
                number, row.employee, categories[row.employee], section))
        if not cint(row.get("from_reports")):
            rate = rules.rate_for(rates, doc.to_date, row.get("width_cm"), row.get("piece_category"), section)
            if not rate:
                errors.append(_("Line {0}: {1} has no rate for that width or category on {2}.").format(
                    number, row.machine, frappe.utils.format_date(doc.to_date)))
                continue
            row.amount = rules.line(row.get("output"), rate["rate"])["amount"]
            if not flt(row.get("target")) and flt(rate.get("daily_target")):
                row.target = flt(rate["daily_target"]) * max(cint(row.get("shifts")), 1)
            row.shifts = cint(row.get("shifts")) or 0
        row.achieved = rules.line(row.get("output"), 0, row.get("target"))["achieved"] or 0
    if errors:
        frappe.throw("<br>".join(errors), title=_(RUN))


def _employees_from_lines(doc):
    """What each person is paid: their lines added up. An Additional Salary
    already written stays linked, so a re-save never forgets it."""
    written = {row.employee: row.get("additional_salary") for row in doc.get("employees") or []}
    doc.set("employees", [])
    for seat in rules.per_employee([_row(row) for row in doc.get("lines") or []]):
        doc.append("employees", {"employee": seat["employee"], "shifts": seat["shifts"],
                                 "output": seat["output"], "amount": seat["amount"],
                                 "additional_salary": written.get(seat["employee"])})


def _price_hours(doc):
    s = settings()
    rates = _hourly_rates([row.employee for row in doc.get("employees") or []], s)
    for row in doc.get("employees") or []:
        row.rate = rates.get(row.employee) or 0
        row.amount = round(flt(row.get("hours")) * flt(row.rate), 2)


def _hourly_rates(employees, s):
    own = {}
    if frappe.get_meta("Employee").has_field("custom_hourly_rate"):
        own = {name: flt(frappe.db.get_value("Employee", name, "custom_hourly_rate")) for name in employees}
    return {name: own.get(name) or flt(s.get("standard_hourly_rate")) for name in employees}


@frappe.whitelist(methods=["POST"])
def get_output(run):
    """Fill the run: the daily reports' lines, per person per machine per
    width or category (Per Meter, Per Piece); or each hourly casual's
    standard hours from their attendance (Hourly). Lines entered by hand
    are kept."""
    doc = frappe.get_doc(RUN, run)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft run can be filled."), title=_(RUN))
    _set_period(doc)
    if doc.section in rules.OUTPUT_SECTIONS:
        reports = frappe.get_all(REPORT, filters={
            "docstatus": 1, "branch": doc.branch, "section": doc.section,
            "report_date": ["between", [doc.from_date, doc.to_date]]}, pluck="name", limit_page_length=0)
        rows = frappe.get_all(REPORT_LINE, filters={"parenttype": REPORT, "parent": ["in", reports or [""]]},
                              fields=["employee", "machine", "width_cm", "piece_category", "output",
                                      "amount", "target"], limit_page_length=0) if reports else []
        # a line typed in by hand is kept as it was typed: only its own
        # fields, so it goes back in as a new row rather than an old one
        kept = [{field: row.get(field) for field in HAND_LINE_FIELDS}
                for row in doc.get("lines") or [] if not cint(row.get("from_reports"))]
        doc.set("lines", [])
        for seat in rules.merge_lines(rows):
            doc.append("lines", dict(seat, from_reports=1))
        for row in kept:
            doc.append("lines", row)
    else:
        _fill_hours(doc)
    doc.save()
    return {"lines": len(doc.get("lines") or []), "employees": len(doc.get("employees") or [])}


def _fill_hours(doc):
    s = settings()
    standard = flt(s.get("standard_hours")) or rules.STANDARD_HOURS
    people = frappe.get_all("Employee", filters={"branch": doc.branch, "status": ["in", ("Active", "Left")],
                                                 "custom_pay_category": rules.HOURLY},
                            fields=["name", "relieving_date"], limit_page_length=0)
    people = [row.name for row in people
              if not row.relieving_date or getdate(row.relieving_date) >= getdate(doc.from_date)]
    days = {}
    for row in frappe.get_all("Attendance", filters={
            "employee": ["in", people or [""]], "docstatus": 1, "status": ["in", PRESENT],
            "attendance_date": ["between", [doc.from_date, doc.to_date]]},
            fields=["employee", "working_hours"], limit_page_length=0) if people else []:
        days.setdefault(row.employee, []).append(flt(row.working_hours))
    rates = _hourly_rates(people, s)
    doc.set("employees", [])
    for name in people:
        if name not in days:
            continue
        month = rules.hourly_pay(days[name], rates.get(name), standard)
        doc.append("employees", {"employee": name, "shifts": month["days"], "hours": month["hours"],
                                 "overtime_hours": month["overtime"], "rate": rates.get(name),
                                 "amount": month["amount"]})


# ── 4. Paying it ──────────────────────────────────────────────────────
def run_on_submit(doc, method=None):
    component = _component(doc.section)
    currency = frappe.get_cached_value("Company", doc.company, "default_currency") or "UGX"
    for row in doc.get("employees") or []:
        if flt(row.amount) <= 0 or row.get("additional_salary"):
            continue
        earning = frappe.get_doc({
            "doctype": "Additional Salary", "employee": row.employee, "company": doc.company,
            "salary_component": component, "amount": flt(row.amount), "payroll_date": doc.to_date,
            "currency": currency, "overwrite_salary_structure_amount": 0,
            "ref_doctype": RUN, "ref_docname": doc.name,
        })
        earning.flags.ignore_permissions = True
        earning.insert()
        earning.submit()
        row.db_set("additional_salary", earning.name, update_modified=False)
    if doc.section in rules.OUTPUT_SECTIONS:
        for name in frappe.get_all(REPORT, filters={
                "docstatus": 1, "branch": doc.branch, "section": doc.section,
                "report_date": ["between", [doc.from_date, doc.to_date]]}, pluck="name", limit_page_length=0):
            frappe.db.set_value(REPORT, name, "output_pay_run", doc.name, update_modified=False)


def run_on_cancel(doc, method=None):
    for row in doc.get("employees") or []:
        name = row.get("additional_salary")
        if name and frappe.db.exists("Additional Salary", name):
            earning = frappe.get_doc("Additional Salary", name)
            if earning.docstatus == 1:
                earning.flags.ignore_permissions = True
                earning.cancel()
    for name in frappe.get_all(REPORT, filters={"output_pay_run": doc.name}, pluck="name",
                               limit_page_length=0):
        frappe.db.set_value(REPORT, name, "output_pay_run", None, update_modified=False)


def _component(section):
    """The earning a section is written to: Output Pay Settings' choice, or
    ours, made once — an Earning, taxable, and not pro-rated by payment days."""
    chosen = settings().get(SETTING_FIELDS[section])
    if chosen and frappe.db.exists("Salary Component", chosen):
        return chosen
    name, abbr = COMPONENTS[section]
    if not frappe.db.exists("Salary Component", name):
        component = frappe.get_doc({
            "doctype": "Salary Component", "name": name, "salary_component": name,
            "salary_component_abbr": abbr,
            "type": "Earning", "depends_on_payment_days": 0, "is_tax_applicable": 1,
            "description": "%s pay from the Output Pay Run." % section})
        component.flags.ignore_permissions = True
        component.insert()
    return name


def settings():
    try:
        return frappe.get_single(SETTINGS)
    except Exception:  # noqa: BLE001 — a fresh site with nothing saved yet
        return frappe._dict()


def _row(row):
    return row.as_dict() if hasattr(row, "as_dict") else dict(row)
