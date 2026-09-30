# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Output pay on the site: the sizes, the daily production report, the
month's run, and Luuka's Per Meter sheet out and back (minutes §4.6).

The rules are in output_rules.py and the sheet in output_sheet.py, neither
with a Frappe import (scripts/verify_output_pay.py). This reads and writes
the site.

  size_validate      a size's Work Units are sound; the one in force today
                     shows on it
  report_validate    each line priced at its size's Work Unit on the day it
                     was made, the Looms OT checked, and a person's day
                     taken from one place: the daily reports or the sheet
  report_on_submit   refused once that month's run is paid, because the
                     report would then never be counted
  run_validate       the payroll month (26th to 25th), the lines priced,
                     and what each person is paid: their work and Looms OT
  get_output         the run filled from the submitted daily reports, the
                     sheet's among them (Per Meter, Per Piece), or from
                     attendance (Hourly)
  download_sheet     the month in Luuka's own layout, with what the system
                     has, to fill in
  upload_sheet       the sheet read back and checked: one report a day,
                     replacing the last upload's, and the run filled again
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

import datetime

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import attendance_rules, output_rules as rules, output_sheet as sheet

SIZE = "Output Rate"
SIZE_RATE = "Output Rate Change"
REPORT = "Daily Production Report"
REPORT_LINE = "Daily Production Line"
REPORT_OT = "Daily Production Overtime"
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
HAND_LINE_FIELDS = ("employee", "size", "shifts", "output")
HAND_OT_FIELDS = ("employee", "amount")


# ── 1. The sizes ──────────────────────────────────────────────────────
def size_validate(doc, method=None):
    rows = [_row(row) for row in doc.get("rates") or []]
    errors = rules.size_errors(doc.get("section"), doc.get("size"), rows)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SIZE))
    doc.work_unit = rules.work_unit_on(rows, today()) or 0


def _sizes(names=None, section=None):
    """{size: {"section", "enabled", "order", "rates"}}, in the sheet's
    order: the sizes named, or every size of a section."""
    filters = {}
    if names is not None:
        filters["name"] = ["in", sorted(filter(None, names)) or [""]]
    if section:
        filters["section"] = section
    found = frappe.get_all(SIZE, filters=filters, fields=["name", "section", "enabled", "sheet_order"],
                           limit_page_length=0)
    # a size given no place on the sheet goes after those that have one
    found.sort(key=lambda row: (cint(row.sheet_order) <= 0, cint(row.sheet_order), row.name))
    rates = {}
    for row in frappe.get_all(SIZE_RATE, filters={"parenttype": SIZE, "parent": ["in", [s.name for s in found] or [""]]},
                              fields=["parent", "work_unit", "valid_from"], limit_page_length=0):
        rates.setdefault(row.parent, []).append({"work_unit": row.work_unit, "valid_from": row.valid_from})
    return {row.name: {"section": row.section, "enabled": cint(row.enabled), "order": cint(row.sheet_order),
                       "rates": rates.get(row.name, [])} for row in found}


def _pay_categories(employees):
    """{employee: pay category} in one query."""
    names = sorted(set(filter(None, employees)))
    if not names or not frappe.get_meta("Employee").has_field("custom_pay_category"):
        return {}
    return {row.name: row.custom_pay_category or "Monthly"
            for row in frappe.get_all("Employee", filters={"name": ["in", names]},
                                      fields=["name", "custom_pay_category"], limit_page_length=0)}


# ── 2. The day: the Daily Production Report ───────────────────────────
def report_validate(doc, method=None):
    section = doc.get("section")
    rows = doc.get("lines") or []
    sizes = _sizes({row.get("size") for row in rows})
    checked = []
    for row in rows:
        size = sizes.get(row.get("size")) or {}
        unit = rules.work_unit_on(size.get("rates"), doc.get("report_date")) if size.get("enabled") else None
        row.rate = flt(unit) if unit is not None else 0
        row.unit = rules.UNITS.get(section)
        row.amount = rules.line_total(row.get("output"), row.rate)
        checked.append(dict(_row(row), rate=unit))
    overtime = [_row(row) for row in doc.get("looms_ot") or []]
    categories = _pay_categories([row.get("employee") for row in checked + overtime])
    in_use = {name: seat["section"] for name, seat in sizes.items() if seat["enabled"]}
    errors = rules.report_errors(section, checked, overtime, categories, in_use)
    errors += rules.day_clashes(checked, overtime, doc.get("source") or rules.ENTERED, doc.get("shift"),
                                _others(doc, [row.get("employee") for row in checked + overtime]))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(REPORT))
    doc.total_output = round(sum(flt(row.get("output")) for row in rows), 3)
    doc.total_amount = round(sum(flt(row.get("amount")) for row in rows), 2)
    doc.total_overtime = round(sum(flt(row.get("amount")) for row in overtime), 2)


def _others(doc, people):
    """The same people's lines and Looms OT on the other submitted reports
    of this section and day, for rules.day_clashes."""
    people = sorted(set(filter(None, people)))
    if not people or not doc.get("report_date"):
        return []
    reports = {row.name: row for row in frappe.get_all(REPORT, filters={
        "docstatus": 1, "section": doc.get("section"), "report_date": doc.get("report_date"),
        "name": ["!=", doc.name or ""]}, fields=["name", "source", "shift"], limit_page_length=0)}
    if not reports:
        return []
    others = []
    for doctype, fields in ((REPORT_LINE, ["parent", "employee", "size"]), (REPORT_OT, ["parent", "employee"])):
        for row in frappe.get_all(doctype, filters={"parenttype": REPORT, "parent": ["in", list(reports)],
                                                    "employee": ["in", people]}, fields=fields, limit_page_length=0):
            report = reports[row.parent]
            others.append({"report": row.parent, "source": report.source or rules.ENTERED, "shift": report.shift,
                           "employee": row.employee, "size": row.get("size")})
    return others


def report_on_submit(doc, method=None):
    """A report for a month whose run is already paid would never be
    counted: somebody's day would go unpaid with nothing to say so."""
    paid = _paid_run(doc.get("branch"), doc.get("section"), doc.get("report_date"))
    if paid:
        frappe.throw(_("{0} has already paid {1} for this month. Cancel and amend it to include this "
                       "report, or the day is never paid.").format(paid, doc.get("branch")), title=_(REPORT))


def report_on_cancel(doc, method=None):
    if doc.get("output_pay_run") and frappe.db.get_value(RUN, doc.output_pay_run, "docstatus") == 1:
        frappe.throw(_("This report was paid in {0}. Cancel that run first, or the pay would stand "
                       "with nothing behind it.").format(doc.output_pay_run), title=_(REPORT))


def _paid_run(branch, section, day):
    year, month = attendance_rules.cycle_of(getdate(day))
    return frappe.db.get_value(RUN, {"branch": branch, "section": section, "year": year,
                                     "month": MONTHS[month - 1], "docstatus": 1}, "name")


# ── 3. The month ──────────────────────────────────────────────────────
def run_validate(doc, method=None):
    _set_period(doc)
    _one_run_a_month(doc)
    if doc.get("section") in rules.OUTPUT_SECTIONS:
        _price_lines(doc)
        _check_overtime(doc)
        _employees_from_lines(doc)
    else:
        doc.set("overtime", [])
        _price_hours(doc)
    # a draft is somewhere to gather the month; only paying it has to be right
    if doc.docstatus == 1:
        errors = rules.run_errors(doc.get("section"), [_row(row) for row in doc.get("employees") or []],
                                  {row.employee: row.get("rate") for row in doc.get("employees") or []})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(RUN))
    doc.total_employees = len(doc.get("employees") or [])
    doc.total_amount = round(sum(flt(row.get("amount")) for row in doc.get("employees") or []), 2)
    doc.total_overtime = round(sum(flt(row.get("amount")) for row in doc.get("overtime") or []), 2)


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
    """A line from the daily reports is taken as they recorded it, each day
    at its own Work Unit and checked when its report was submitted, so a
    size taken out of use or a person moved to another pay category since
    does not unpay work already done. A line typed in here is checked, and
    priced at its size's Work Unit on the last day of the month."""
    section = doc.get("section")
    word = rules.SIZE_WORD.get(section, "size")
    typed = [(number, row) for number, row in enumerate(doc.get("lines") or [], 1)
             if not cint(row.get("from_reports"))]
    sizes = _sizes({row.get("size") for _number, row in typed})
    categories = _pay_categories(row.get("employee") for _number, row in typed)
    errors = []
    for number, row in typed:
        size = sizes.get(row.get("size"))
        if not row.get("size"):
            errors.append(_("Line {0}: say which {1}.").format(number, word))
            continue
        if not size or not size["enabled"]:
            errors.append(_("Line {0}: {1} is not a {2} in use.").format(number, row.size, word))
            continue
        if size["section"] != section:
            errors.append(_("Line {0}: {1} is a {2} {3}.").format(
                number, row.size, size["section"], rules.SIZE_WORD.get(size["section"], "size")))
            continue
        if row.employee in categories and categories[row.employee] != section:
            errors.append(_("Line {0}: {1} is paid {2}, not {3}.").format(
                number, row.employee, categories[row.employee], section))
        if flt(row.get("output")) < 0:
            errors.append(_("Line {0}: Work Done cannot be less than nothing.").format(number))
        unit = rules.work_unit_on(size["rates"], doc.to_date)
        if unit is None:
            errors.append(_("Line {0}: {1} has no Work Unit on {2}.").format(
                number, row.size, frappe.utils.format_date(doc.to_date)))
            continue
        row.rate = unit
        row.amount = rules.line_total(row.get("output"), unit)
        row.shifts = cint(row.get("shifts")) or 0
    if errors:
        frappe.throw("<br>".join(errors), title=_(RUN))


def _check_overtime(doc):
    """Looms OT typed in here is checked; the rows from the daily reports
    were checked on them."""
    typed = [_row(row) for row in doc.get("overtime") or [] if not cint(row.get("from_reports"))]
    errors = rules.overtime_errors(doc.get("section"), typed,
                                   _pay_categories(row.get("employee") for row in typed), where="run")
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(RUN))


def _employees_from_lines(doc):
    """What each person is paid: their lines and their Looms OT. An
    Additional Salary already written stays linked, so a re-save never
    forgets it."""
    written = {row.employee: row.get("additional_salary") for row in doc.get("employees") or []}
    overtime = rules.overtime_by_employee([_row(row) for row in doc.get("overtime") or []])
    doc.set("employees", [])
    for seat in rules.per_employee([_row(row) for row in doc.get("lines") or []], overtime):
        doc.append("employees", dict(seat, additional_salary=written.get(seat["employee"])))


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
    """Fill the run: the daily reports' lines, per person per size, and
    their Looms OT (Per Meter, Per Piece); or each hourly casual's standard
    hours from their attendance (Hourly). Lines and Looms OT entered by
    hand are kept."""
    doc = frappe.get_doc(RUN, run)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft run can be filled."), title=_(RUN))
    _fill(doc)
    doc.save()
    return {"lines": len(doc.get("lines") or []), "employees": len(doc.get("employees") or [])}


def _fill(doc):
    _set_period(doc)
    if doc.section not in rules.OUTPUT_SECTIONS:
        _fill_hours(doc)
        return
    reports = _month_reports(doc)
    lines = frappe.get_all(REPORT_LINE, filters={"parenttype": REPORT, "parent": ["in", reports or [""]]},
                           fields=["employee", "size", "output", "amount"], limit_page_length=0) if reports else []
    extra = frappe.get_all(REPORT_OT, filters={"parenttype": REPORT, "parent": ["in", reports or [""]]},
                           fields=["employee", "amount"], limit_page_length=0) if reports else []
    # what was typed in by hand is kept as it was typed: only its own
    # fields, so it goes back in as a new row rather than an old one
    kept = [{field: row.get(field) for field in HAND_LINE_FIELDS}
            for row in doc.get("lines") or [] if not cint(row.get("from_reports"))]
    kept_ot = [{field: row.get(field) for field in HAND_OT_FIELDS}
               for row in doc.get("overtime") or [] if not cint(row.get("from_reports"))]
    doc.set("lines", [])
    for seat in rules.merge_lines(lines):
        doc.append("lines", dict(seat, from_reports=1))
    for row in kept:
        doc.append("lines", row)
    doc.set("overtime", [])
    for employee, amount in rules.overtime_by_employee(extra).items():
        doc.append("overtime", {"employee": employee, "amount": amount, "from_reports": 1})
    for row in kept_ot:
        doc.append("overtime", row)


def _month_reports(doc):
    return frappe.get_all(REPORT, filters={
        "docstatus": 1, "branch": doc.branch, "section": doc.section,
        "report_date": ["between", [doc.from_date, doc.to_date]]}, pluck="name", limit_page_length=0)


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


# ── 4. Luuka's Per Meter sheet, out and back ──────────────────────────
@frappe.whitelist()
def download_sheet(run):
    """The month in Luuka's own layout: every Per Meter person of the
    plant, every day, every size in use, with the Work Units and whatever
    the system already has, to fill in and upload again."""
    doc = frappe.get_doc(RUN, run)
    doc.check_permission("read")
    if doc.get("section") != rules.PER_METER:
        frappe.throw(_("The sheet is for a Per Meter run."), title=_(RUN))
    _set_period(doc)
    dates = _days(doc.from_date, doc.to_date)
    sizes = []
    for name, seat in _sizes(section=rules.PER_METER).items():
        units = {day: rules.work_unit_on(seat["rates"], day) for day in dates}
        # a size with no Work Unit on any day of the month cannot be paid in it
        if seat["enabled"] and any(unit is not None for unit in units.values()):
            sizes.append({"size": name, "rates": units})
    if not sizes:
        frappe.throw(_("No size has a Work Unit in this month. Set up the sizes first."), title=_(RUN))
    work, overtime = _month_work(doc)
    people = _sheet_people(doc, {employee for employee, _day, _size in work} | {employee for employee, _day in overtime})
    content = sheet.build({
        "title": "%s %s" % (doc.month.upper(), doc.year),
        "tag": {"run": doc.name, "branch": doc.branch, "from": doc.from_date, "to": doc.to_date},
        "employees": people, "dates": dates, "sizes": sizes, "work": work, "overtime": overtime,
    })
    frappe.response["filename"] = "PER METER %s %s %s.xlsx" % (doc.month.upper(), doc.year, doc.branch)
    frappe.response["filecontent"] = content
    frappe.response["type"] = "binary"


def _days(start, end):
    start, end = getdate(start), getdate(end)
    return [start + datetime.timedelta(days=n) for n in range((end - start).days + 1)]


def _month_work(doc):
    """{(employee, day, size): metres} and {(employee, day): Looms OT} on
    the month's submitted reports, both shifts of a day together."""
    reports = {row.name: getdate(row.report_date) for row in frappe.get_all(REPORT, filters={
        "docstatus": 1, "branch": doc.branch, "section": rules.PER_METER,
        "report_date": ["between", [doc.from_date, doc.to_date]]}, fields=["name", "report_date"],
        limit_page_length=0)}
    work, overtime = {}, {}
    if not reports:
        return work, overtime
    for row in frappe.get_all(REPORT_LINE, filters={"parenttype": REPORT, "parent": ["in", list(reports)]},
                              fields=["parent", "employee", "size", "output"], limit_page_length=0):
        key = (row.employee, reports[row.parent], row.size)
        work[key] = round(work.get(key, 0) + flt(row.output), 3)
    for row in frappe.get_all(REPORT_OT, filters={"parenttype": REPORT, "parent": ["in", list(reports)]},
                              fields=["parent", "employee", "amount"], limit_page_length=0):
        key = (row.employee, reports[row.parent])
        overtime[key] = round(overtime.get(key, 0) + flt(row.amount), 2)
    return work, overtime


def _sheet_people(doc, with_work):
    """The plant's Per Meter people who worked any day of the month, by
    name, and anyone else the month's reports already have."""
    found = frappe.get_all("Employee", filters={"custom_pay_category": rules.PER_METER},
                           fields=["name", "employee_name", "employee_number", "branch", "status",
                                   "date_of_joining", "relieving_date"], order_by="employee_name asc",
                           limit_page_length=0)
    people = []
    for row in found:
        on_roll = row.branch == doc.branch and row.status in ("Active", "Left") \
            and (not row.date_of_joining or getdate(row.date_of_joining) <= getdate(doc.to_date)) \
            and (not row.relieving_date or getdate(row.relieving_date) >= getdate(doc.from_date))
        if on_roll or row.name in with_work:
            people.append({"employee": row.name, "name": row.employee_name or row.name,
                           "id": row.employee_number or row.name})
    return people


@frappe.whitelist(methods=["POST"])
def upload_sheet(run, file_url):
    """The filled sheet back in. Each line is checked (output_rules.take_sheet);
    what passes becomes one report a day, replacing the last upload's, and
    the run is filled again. A day already on another submitted report (a
    supervisor's, or another plant's sheet) stays there. Returns what was
    taken, and what was not and why."""
    doc = frappe.get_doc(RUN, run)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft run takes a sheet."), title=_(RUN))
    if doc.get("section") != rules.PER_METER:
        frappe.throw(_("The sheet is for a Per Meter run."), title=_(RUN))
    _set_period(doc)
    try:
        found = sheet.read(_file_bytes(file_url))
    except ValueError as error:
        frappe.throw(_(str(error)), title=_(RUN))
    tag = found.get("tag") or {}
    if tag.get("from") and (tag.get("from") != str(doc.from_date) or tag.get("branch") != doc.branch):
        frappe.throw(_("This sheet was made for {0}, {1} to {2}: download this month's.").format(
            tag.get("branch"), tag.get("from"), tag.get("to")), title=_(RUN))
    ids, categories, names = _employee_ids()
    sizes = _sizes(section=rules.PER_METER)
    taken = rules.take_sheet(found["lines"], ids, categories,
                             {rules.size_key(name): name for name, seat in sizes.items() if seat["enabled"]},
                             {name: seat["rates"] for name, seat in sizes.items()},
                             (doc.from_date, doc.to_date), names)
    kept_back = _keep_entered_days(doc, taken, {name for name, seat in sizes.items() if seat["enabled"]}, names)
    days = rules.sheet_days(taken["work"], taken["overtime"])
    _replace_upload(doc, days)
    doc.uploaded_sheet = file_url
    _fill(doc)
    doc.save()
    work = taken["work"].values()
    return {
        "days": len(days), "people": len({employee for employee, _day, _size in taken["work"]}
                                         | {employee for employee, _day in taken["overtime"]}),
        "metres": round(sum(done for done, _unit, _row in work), 3),
        "amount": round(sum(rules.line_total(done, unit) for done, unit, _row in work), 2),
        "looms_ot": round(sum(amount for amount, _row in taken["overtime"].values()), 2),
        "problems": taken["problems"] + kept_back, "notes": taken["notes"],
    }


def _employee_ids():
    """{id: employee} by name and by Employee Number, {employee: pay
    category} and {employee: name}, for every employee."""
    fields = ["name", "employee_number", "employee_name"]
    has_category = frappe.get_meta("Employee").has_field("custom_pay_category")
    if has_category:
        fields.append("custom_pay_category")
    ids, categories, names = {}, {}, {}
    rows = frappe.get_all("Employee", fields=fields, limit_page_length=0)
    for row in rows:
        ids.setdefault(rules.employee_key(row.name), row.name)
    for row in rows:
        if row.get("employee_number"):
            ids.setdefault(rules.employee_key(row.employee_number), row.name)
        categories[row.name] = (row.get("custom_pay_category") if has_category else None) or "Monthly"
        names[row.name] = row.employee_name
    return ids, categories, names


def _keep_entered_days(doc, taken, shown, names=None):
    """A day already on another submitted report stays there: a
    supervisor's, or another plant's sheet (this plant's last upload is
    about to be replaced). The downloaded sheet shows it, so it comes back
    unchanged and nothing is said; a day changed on the sheet is left out,
    and said (rules.keep_reported_days). A report with no source was
    entered: it was made before sheets came in."""
    reports = {row.name: getdate(row.report_date) for row in frappe.get_all(REPORT, filters={
        "docstatus": 1, "section": rules.PER_METER, "report_date": ["between", [doc.from_date, doc.to_date]]},
        fields=["name", "report_date", "source", "branch"], limit_page_length=0)
        if not ((row.source or rules.ENTERED) == rules.UPLOADED and row.branch == doc.branch)}
    work, overtime = {}, {}
    if reports:
        for row in frappe.get_all(REPORT_LINE, filters={"parenttype": REPORT, "parent": ["in", list(reports)]},
                                  fields=["parent", "employee", "size", "output"], limit_page_length=0):
            day = work.setdefault((row.employee, reports[row.parent]), {})
            day[row.size] = round(flt(day.get(row.size)) + flt(row.output), 3)
        for row in frappe.get_all(REPORT_OT, filters={"parenttype": REPORT, "parent": ["in", list(reports)]},
                                  fields=["parent", "employee", "amount"], limit_page_length=0):
            key = (row.employee, reports[row.parent])
            overtime[key] = round(flt(overtime.get(key)) + flt(row.amount), 2)
    changed = rules.keep_reported_days(taken, work, overtime, shown)
    if not changed:
        return []
    names = names or {}
    listed = ", ".join("%s on %s" % (names.get(employee) or employee, day.strftime("%d-%b-%Y"))
                       for employee, day in changed[:8])
    return [_("{0} day(s) on the sheet differ from submitted daily reports, which stand: {1}{2}.")
            .format(len(changed), listed, "…" if len(changed) > 8 else "")]


def _replace_upload(doc, days):
    """The month's last upload goes, and one report a day is made from
    this sheet, submitted: the sheet is the month's record already. The
    last upload is found by the month and plant, not by the run, so a run
    cancelled and amended still replaces what it uploaded."""
    for name in frappe.get_all(REPORT, filters={
            "source": rules.UPLOADED, "section": rules.PER_METER, "branch": doc.branch,
            "report_date": ["between", [doc.from_date, doc.to_date]]}, pluck="name", limit_page_length=0):
        report = frappe.get_doc(REPORT, name)
        report.flags.ignore_permissions = True
        if report.docstatus == 1:
            report.cancel()
        frappe.delete_doc(REPORT, name, ignore_permissions=True, force=True)
    for day, found in days.items():
        report = frappe.get_doc({
            "doctype": REPORT, "report_date": day, "shift": rules.SHIFTS[0], "section": rules.PER_METER,
            "branch": doc.branch, "company": doc.company, "source": rules.UPLOADED, "sheet_run": doc.name,
            "lines": [{"employee": row["employee"], "size": row["size"], "output": row["output"]}
                      for row in found["lines"]],
            "looms_ot": found["overtime"],
        })
        report.flags.ignore_permissions = True
        report.docstatus = 1
        report.insert()


def _file_bytes(file_url):
    """A file's content as it is kept on the site."""
    if frappe.db.exists("File", {"file_url": file_url}):
        path = frappe.get_doc("File", {"file_url": file_url}).get_full_path()
    else:
        path = frappe.get_site_path("public", str(file_url).lstrip("/"))
    with open(path, "rb") as handle:
        return handle.read()


# ── 5. Paying it ──────────────────────────────────────────────────────
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
        for name in _month_reports(doc):
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
    ours, made once: an Earning, taxable, and not pro-rated by payment days."""
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
