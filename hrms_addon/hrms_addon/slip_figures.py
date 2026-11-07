# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a payroll's slips will show, before they are made, for each row of its
Employees tab (rules: slip_figures_rules.py; scripts/verify_slip_figures.py).

  expected   {employee: the figures for their row}, for those named

Read for the whole payroll at once: a query for each kind of record, whatever
the number of people, and nothing asked again for each of them. It runs each
time the form opens or is saved, until the slips are made.
"""

import unicodedata

import frappe
from frappe.utils import cint, date_diff, getdate, today

from hrms_addon.hrms_addon import pay_days, pay_days_rules, payslip_rules, weekly_pay_rules
from hrms_addon.hrms_addon import slip_figures_rules as rules

SETTINGS = "Payroll Settings"
ASSIGNMENT = "Salary Structure Assignment"
STRUCTURE = "Salary Structure"
COMPONENT = "Salary Component"
ADDITIONAL = "Additional Salary"
EARNING = "Earning"
BASIC = "Basic"
LINE_FIELDS = ["parent", "salary_component", "abbr", "amount", "amount_based_on_formula", "formula", "condition",
               "depends_on_payment_days", "statistical_component", "do_not_include_in_total"]
COMPONENT_FLAGS = ["depends_on_payment_days", "statistical_component", "do_not_include_in_total"]


def expected(doc, employees):
    """{employee: the figures for their row of the Employees table}, worked out as their slip will work them out.
    Nothing for a cancelled payroll, one not yet dated or worked out from timesheets, or a site whose Payroll Settings
    do not go by attendance: the slips will have to say."""
    wanted = set(employees or ())
    if (not wanted or cint(doc.get("docstatus")) == 2 or cint(doc.get("salary_slip_based_on_timesheet"))
            or not doc.get("start_date") or not doc.get("end_date")):
        return {}
    settings = frappe.db.get_singles_dict(SETTINGS)
    if settings.get("payroll_based_on") != rules.ATTENDANCE:
        return {}

    from hrms.payroll.utils import SALARY_SLIP_EVAL_DEFAULTS, get_component_abbr_map

    start, end = getdate(doc.get("start_date")), getdate(doc.get("end_date"))
    period = date_diff(end, start) + 1
    lines = _structure_lines(doc.get("payroll_frequency"))
    read = {name for rows in lines.values() for line in rows
            for name in rules.names_in(line.formula) | rules.names_in(line.condition)}
    assignments = _assignments(end, lines, read)
    people = _people(doc.get("company"), read)
    holidays = _holidays(doc.get("company"), wanted, start, end)
    attendance = _attendance(start, end)
    leave_types = _leave_types()
    unmarked_absent = settings.get("consider_unmarked_attendance_as") == rules.ABSENT
    marked = _marked(start, end) if unmarked_absent else {}
    components = _components()
    additional = _additional(start, end, components)
    rounded = {name for name, row in components.items() if cint(row.round_to_the_nearest_integer)}
    days = pay_days.days_in_month() if pay_days.on_luuka_month(doc) else 0
    shown_choice = pay_days.days_shown()

    # what a formula may read, as Frappe HR seeds it for a whole month with nothing taken off
    shared = {**get_component_abbr_map(), **SALARY_SLIP_EVAL_DEFAULTS, "start_date": start, "end_date": end,
              "payment_days": period, "total_working_days": period, "leave_without_pay": 0, "absent_days": 0,
              "unmarked_days": 0, weekly_pay_rules.PAY: 0}

    evaluate = _evaluator()
    figures = {}
    for employee in wanted:
        person = people.get(employee) or {}
        count = rules.days_of(start, end, person.get("date_of_joining"), person.get("relieving_date"),
                              holidays.get(employee), attendance.get(employee), settings, leave_types,
                              marked.get(employee))
        facts = {"on_payroll": count["on_payroll"], "counted_from": count["counted_from"], "paid": count["paid"],
                 "without_pay": count["without_pay"]}
        output_paid = pay_days_rules.is_output_paid(person.get(pay_days.CATEGORY_FIELD))
        month = pay_days_rules.slip_days(days, output_paid=output_paid, **facts) if days else None
        working, paid = month or (count["working"], count["paid"])
        shown = pay_days_rules.shown_days(shown_choice, period, (working, paid), facts, output_paid) if month \
            else (count["working"], count["paid"])
        assignment = assignments.get(employee)
        structure = []
        if assignment:
            structure = rules.month_lines(lines.get(assignment.salary_structure),
                                          {**shared, **assignment, **person}, evaluate)
        rows = rules.earning_rows(structure, additional.get(employee))
        figures[employee] = {
            "custom_working_days": shown[0],
            "custom_paid_days": shown[1],
            "custom_absent_days": 0 if output_paid and month else count["absent"],
            "custom_absent_amount": payslip_rules.absent_amount(rules.paid_rows(rows, paid, working, rounded)),
            "custom_basic_salary": sum(pay_days_rules.full_amount(row) for row in rows
                                       if row["salary_component"] == BASIC),
        }
    if weekly_pay_rules.on_weekly_pay(doc):
        from hrms_addon.hrms_addon import weekly_pay

        weekly_pay.show_on_figures(doc, figures)
    return figures


def _evaluator():
    """evaluate(code, data), as Frappe HR evaluates a formula. Its _safe_eval checks a formula and compiles it each time
    it runs it, which for 2,000 people would be most of the time this takes. So a formula goes through it once, and once
    it has passed runs compiled, on the same globals."""
    from hrms.payroll.utils import COMPONENT_EVAL_GLOBALS, _safe_eval

    scope = COMPONENT_EVAL_GLOBALS.copy()
    scope.update({"__builtins__": {}, "int": int, "float": float, "long": int, "round": round})
    passed = {}

    def evaluate(code, data):
        compiled = passed.get(code)
        if compiled:
            return eval(compiled, scope, data)  # nosemgrep: a formula _safe_eval has passed
        result = _safe_eval(code, COMPONENT_EVAL_GLOBALS.copy(), data)
        passed[code] = compile(unicodedata.normalize("NFKC", code), "<formula>", "eval")
        return result

    return evaluate


def _structure_lines(frequency):
    """{structure: its earning lines in order}, for the active structures a payroll of this frequency runs on."""
    filters = {"docstatus": 1, "is_active": "Yes"}
    if frequency:
        filters["payroll_frequency"] = frequency
    structures = frappe.get_all(STRUCTURE, filters=filters, pluck="name", limit_page_length=0)
    if not structures:
        return {}
    from hrms.payroll.utils import sanitize_expression

    lines = {structure: [] for structure in structures}
    for line in frappe.get_all("Salary Detail", filters={"parenttype": STRUCTURE, "parentfield": "earnings",
                                                         "parent": ["in", structures]},
                               fields=LINE_FIELDS, order_by="idx asc", limit_page_length=0):
        line.condition, line.formula = sanitize_expression(line.condition), sanitize_expression(line.formula)
        lines[line.parent].append(line)
    return lines


def _fields_read(doctype, read, *fields):
    """The fields to read of a record: those named, and those of the rest a formula reads."""
    meta = frappe.get_meta(doctype)
    return [*fields, *sorted(name for name in read if name not in fields and meta.has_field(name))]


def _assignments(end, lines, read):
    """{employee: their assignment on the period's last day}: the latest by then, on a structure of this payroll's."""
    assignments = {}
    for row in frappe.get_all(ASSIGNMENT, filters={"docstatus": 1, "from_date": ["<=", end]},
                              fields=_fields_read(ASSIGNMENT, read, "employee", "salary_structure", "base", "variable"),
                              order_by="from_date asc", limit_page_length=0):
        if row.salary_structure in lines:
            assignments[row.employee] = row
    return assignments


def _people(company, read):
    """{employee: when they joined and left, their pay category, and whatever else a formula reads of them}."""
    fields = ["name", "date_of_joining", "relieving_date"]
    if frappe.get_meta("Employee").has_field(pay_days.CATEGORY_FIELD):
        fields.append(pay_days.CATEGORY_FIELD)
    return {row.name: row for row in frappe.get_all(
        "Employee", filters={"company": company}, limit_page_length=0,
        fields=_fields_read("Employee", read, *fields))}


def _holidays(company, employees, start, end):
    """{employee: the dates of the period on their holiday list}. Frappe HR finds a list as of today: their own
    assignment, else the company's."""
    latest = {}
    for row in frappe.get_all("Holiday List Assignment", filters={"docstatus": 1, "from_date": ["<=", today()]},
                              fields=["assigned_to", "holiday_list"], order_by="from_date asc", limit_page_length=0):
        latest[row.assigned_to] = row.holiday_list
    if not latest:
        return {}
    dates = {}
    for row in frappe.get_all("Holiday", filters={"parent": ["in", sorted(set(latest.values()))],
                                                  "holiday_date": ["between", [start, end]]},
                              fields=["parent", "holiday_date"], limit_page_length=0):
        dates.setdefault(row.parent, set()).add(row.holiday_date)
    return {employee: dates.get(latest.get(employee) or latest.get(company)) for employee in employees}


def _attendance(start, end):
    """{employee: their submitted attendance of the period that takes days off}. Most days are days at work: they
    are not read."""
    rows = {}
    for row in frappe.get_all("Attendance", filters={"docstatus": 1, "status": ["in", list(rules.TAKES_DAYS)],
                                                     "attendance_date": ["between", [start, end]]},
                              fields=["employee", "attendance_date", "status", "leave_type", "half_day_status"],
                              limit_page_length=0):
        rows.setdefault(row.employee, []).append(row)
    return rows


def _marked(start, end):
    """{employee: the dates of all their submitted attendance of the period}, as plain rows, there being a lot of it."""
    dates = {}
    for employee, day in frappe.get_all("Attendance", filters={"docstatus": 1, "attendance_date": ["between", [start, end]]},
                                        fields=["employee", "attendance_date"], as_list=True, limit_page_length=0):
        dates.setdefault(employee, []).append(day)
    return dates


def _leave_types():
    """{name: row} of the leave types without pay or part paid, as Frappe HR's slip reads them."""
    return {row.name: row for row in frappe.get_all(
        "Leave Type", or_filters={"is_ppl": 1, "is_lwp": 1}, limit_page_length=0,
        fields=["name", "is_lwp", "is_ppl", "fraction_of_daily_salary_per_leave", "include_holiday"])}


def _components():
    """{name: row} of the earning components, with what an Additional Salary row takes from them."""
    return {row.name: row for row in frappe.get_all(
        COMPONENT, filters={"type": EARNING}, limit_page_length=0,
        fields=["name", "round_to_the_nearest_integer", *COMPONENT_FLAGS])}


def _additional(start, end, components):
    """{employee: their Additional Salary earnings of the period that the figures need}: the Basic, and what follows
    the days. Overtime and the like do neither, and at 2,000 people there is a lot of it to leave unread."""
    needed = [name for name, row in components.items()
              if name == BASIC or (cint(row.depends_on_payment_days) and not cint(row.statistical_component)
                                   and not cint(row.do_not_include_in_total))]
    if not needed:
        return {}
    common = {"docstatus": 1, "type": EARNING, "disabled": 0, "salary_component": ["in", needed]}
    fields = ["employee", "salary_component", "amount", "overwrite_salary_structure_amount"]
    rows = {}
    for dates in ({"is_recurring": 1, "from_date": ["<=", end], "to_date": [">=", end]},
                  {"is_recurring": 0, "payroll_date": ["between", [start, end]]}):
        for row in frappe.get_all(ADDITIONAL, filters={**common, **dates}, fields=fields, limit_page_length=0):
            component = components[row.salary_component]
            row.update({flag: component.get(flag) for flag in COMPONENT_FLAGS})
            rows.setdefault(row.employee, []).append(row)
    return rows
