# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Per Piece casuals, paid by the week (Luuka, 10 Nov 2026: "casual is
divided into two, one that is paid per piece and the one they are paid by
the number of working hours"). The weekly payroll pays both kinds
(weekly_pay.py); this is the Per Piece side.

  upload_pieces      Luuka's weekly workbook (PET packaging, piece_sheet.py)
                     uploaded on a weekly Payroll Entry: every week that ends
                     in its dates is checked (output_rules.take_pieces) and
                     made one Per Piece report, replacing the last upload of
                     that week
  report_validate    a Per Piece report's arrears: Per Piece casuals, each
                     more than nothing; no Looms OT
  report_on_submit   each person's week written as Additional Salary dated
                     the report's day, which the weekly payslip reads as it
                     reads every other: one for each salary component the
                     categories are paid under, and one for the arrears.
                     Refused once a weekly slip that pays that day is
                     submitted, as the pay would never be counted
  report_on_cancel   those Additional Salaries cancelled and deleted, unless
                     a submitted slip paid them
  waiting            who has piece pay dated in a payroll's days, for its
                     Get Employees

The monthly Output Pay Run no longer pays Per Piece (output_pay.run_validate),
so a week is never paid twice.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from hrms_addon.hrms_addon import advance_runs, output_pay, output_rules as rules, piece_sheet, weekly_pay
from hrms_addon.hrms_addon import weekly_pay_rules

REPORT = output_pay.REPORT
REPORT_LINE = output_pay.REPORT_LINE
REPORT_OT = output_pay.REPORT_OT
ADDITIONAL = "Additional Salary"
TITLE = "Per Piece Sheet"
# the earning a casual's arrears are paid under, made once where the site has none
ARREARS = ("Arrears", "ARR")


# ── The workbook in ───────────────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def upload_pieces(payroll_entry, file_url):
    """The weekly workbook on a draft weekly payroll. Returns what was taken,
    and what was not and why."""
    doc = frappe.get_doc("Payroll Entry", payroll_entry)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft payroll takes the sheet."), title=_(TITLE))
    if not weekly_pay_rules.on_weekly_pay(doc) or not doc.get("start_date") or not doc.get("end_date"):
        frappe.throw(_("The Per Piece sheet is for a weekly payroll with its Start and End Dates."), title=_(TITLE))
    start, end = getdate(doc.start_date), getdate(doc.end_date)
    try:
        found = piece_sheet.read(output_pay._file_bytes(file_url), wanted=lambda first, last: start <= last <= end)
    except ValueError as error:
        frappe.throw(_(str(error)), title=_(TITLE))
    people = _people()
    by_employee = {person["employee"]: person for person in people}
    names = {person["employee"]: person["employee_name"] for person in people}
    sizes = output_pay._sizes(section=rules.PER_PIECE)
    taken = rules.take_pieces(found["weeks"], people, {name for name, seat in sizes.items() if seat["enabled"]},
                              {name: seat["rates"] for name, seat in sizes.items()}, (start, end), doc.get("branch"),
                              found.get("unread"))
    problems = _keep_reported_weeks(doc, taken, names)
    problems += _drop_paid_weeks(taken, names)
    plantless = {employee for employee in _people_in(taken) if not (by_employee[employee].get("branch") or doc.get("branch"))}
    problems += _drop(taken, {employee: None for employee in plantless}, names, _("they have no plant"))
    problems += _drop_not_employed(taken, names, start)
    failed = weekly_pay.assign_people(_people_in(taken), doc.company, start)
    problems += _drop(taken, failed, names, _("they have no salary assignment: {0}"))
    _replace_uploads(doc, [week["end"] for week in taken["weeks"]])
    made = _make_reports(doc, taken, by_employee)
    work, owed = taken["work"].values(), taken["arrears"].values()
    notes = list(taken["notes"])
    if found.get("skipped"):
        notes.append(_("{0} other weekly sheet(s) end outside {1} to {2}: the payroll of the week each ends in "
                       "takes it.").format(found["skipped"], start.strftime("%d-%b-%Y"), end.strftime("%d-%b-%Y")))
    return {
        "reports": made, "weeks": len({day for _employee, day, _size in taken["work"]}
                                      | {day for _employee, day in taken["arrears"]}),
        "people": len(_people_in(taken)),
        "bags": round(sum(bags for bags, _price, _where in work), 3),
        "amount": round(sum(rules.line_total(bags, price) for bags, price, _where in work), 2),
        "arrears": round(sum(amount for amount, _where in owed), 2),
        "problems": taken["problems"] + problems, "notes": notes,
    }


def _people():
    """Every employee, by what the workbook finds them by (the name, or the
    Employee Number where a sheet has an Employee Id column), with their pay
    category and plant."""
    fields = ["name", "employee_name", "employee_number", "branch"]
    has_category = frappe.get_meta("Employee").has_field("custom_pay_category")
    if has_category:
        fields.append("custom_pay_category")
    return [{"employee": row.name, "employee_name": row.employee_name, "employee_number": row.employee_number,
             "branch": row.branch,
             "category": (row.get("custom_pay_category") if has_category else None) or rules.REGULAR}
            for row in frappe.get_all("Employee", fields=fields, limit_page_length=0)]


def _people_in(taken):
    return sorted({employee for employee, _day, _size in taken["work"]} | {employee for employee, _day in taken["arrears"]})


def _drop(taken, held, names, why):
    """Takes each person in `held` ({employee: what to say, or None}) out of
    what the sheet gave, and says so."""
    problems = []
    for employee in sorted(held):
        keys = [key for key in taken["work"] if key[0] == employee]
        owed = [key for key in taken["arrears"] if key[0] == employee]
        if not keys and not owed:
            continue
        worth = sum(rules.line_total(*taken["work"][key][:2]) for key in keys) + \
            sum(taken["arrears"][key][0] for key in owed)
        for key in keys:
            del taken["work"][key]
        for key in owed:
            del taken["arrears"][key]
        problems.append(_("{0}'s pay on the sheet, {1}, is left out: {2}.").format(
            names.get(employee) or employee, "{:,.0f}".format(worth), why.format(held[employee] or "")))
    return problems


def _keep_reported_weeks(doc, taken, names):
    """A person's week already on another submitted Per Piece report stays
    there: a supervisor's daily report on any day of the week, or another
    plant's upload (this payroll's last upload is about to be replaced). The
    sheet's pay for that person and week is taken out and said, so nothing is
    paid twice."""
    weeks = {getdate(week["end"]): getdate(week["start"]) for week in taken["weeks"]}
    people = _people_in(taken)
    if not weeks or not people:
        return []
    reports = {row.name: getdate(row.report_date) for row in frappe.get_all(REPORT, filters={
        "docstatus": 1, "section": rules.PER_PIECE, "report_date": ["between", [min(weeks.values()), max(weeks)]]},
        fields=["name", "report_date", "source", "branch"], limit_page_length=0)
        if not ((row.source or rules.ENTERED) == rules.UPLOADED and (not doc.get("branch") or row.branch == doc.branch))}
    if not reports:
        return []
    held = {}
    for doctype in (REPORT_LINE, REPORT_OT):
        for row in frappe.get_all(doctype, filters={"parenttype": REPORT, "parent": ["in", list(reports)],
                                                    "employee": ["in", people]},
                                  fields=["parent", "employee"], limit_page_length=0):
            for last, first in weeks.items():
                if first <= reports[row.parent] <= last:
                    held.setdefault((row.employee, last), set()).add(row.parent)
    problems = []
    for (employee, last), holders in sorted(held.items(), key=lambda item: (item[0][1], str(item[0][0]))):
        keys = [key for key in taken["work"] if key[0] == employee and key[1] == last]
        worth = sum(rules.line_total(*taken["work"][key][:2]) for key in keys)
        for key in keys:
            del taken["work"][key]
        taken["arrears"].pop((employee, last), None)
        listed = ", ".join(sorted(holders)[:5]) + ("…" if len(holders) > 5 else "")
        problems.append(_("{0}'s week to {1} is on submitted daily reports ({2}), which stand, so the sheet's pay "
                          "for it, {3}, is left out. If the reports are wrong, cancel them and upload again.").format(
            names.get(employee) or employee, last.strftime("%d-%b-%Y"), listed, "{:,.0f}".format(worth)))
    return problems


def _employment(employees):
    return {row.name: row for row in frappe.get_all("Employee", filters={"name": ["in", list(employees)]},
                                                    fields=["name", "status", "date_of_joining", "relieving_date"],
                                                    limit_page_length=0)} if employees else {}


def _drop_not_employed(taken, names, start):
    """A person's week they were not employed for, or anyone Inactive, is taken out and said
    (rules.piece_pay_day): Frappe HR would refuse the pay, and with it the whole upload. One who left
    during the week stays, and is paid on their last day (report_on_submit)."""
    found = _employment(_people_in(taken))
    firsts = {getdate(week["end"]): max(getdate(week["start"]), getdate(start)) for week in taken["weeks"]}
    weeks = {(employee, day) for employee, day, _size in taken["work"]} | set(taken["arrears"])
    problems = []
    for employee, day in sorted(weeks, key=lambda key: (key[1], str(key[0]))):
        person = found.get(employee) or {}
        _paid_on, why = rules.piece_pay_day(firsts.get(day), day, person.get("date_of_joining"),
                                            person.get("relieving_date"), person.get("status"))
        if not why:
            continue
        keys = [key for key in taken["work"] if key[0] == employee and key[1] == day]
        worth = sum(rules.line_total(*taken["work"][key][:2]) for key in keys) + \
            (taken["arrears"].get((employee, day)) or (0.0,))[0]
        for key in keys:
            del taken["work"][key]
        taken["arrears"].pop((employee, day), None)
        problems.append(_("{0}'s week to {1} on the sheet, {2}, is left out: {3}.").format(
            names.get(employee) or employee, day.strftime("%d-%b-%Y"), "{:,.0f}".format(worth), why))
    return problems


def _drop_paid_weeks(taken, names):
    """A person's week that a submitted weekly slip already covers is taken
    out and said: its Additional Salary would never be counted. Their other
    weeks stand."""
    weeks = {(employee, day) for employee, day, _size in taken["work"]} | set(taken["arrears"])
    paid = _paying_slips(weeks)
    problems = []
    for (employee, day), slip in sorted(paid.items(), key=lambda item: (item[0][1], str(item[0][0]))):
        keys = [key for key in taken["work"] if key[0] == employee and key[1] == day]
        worth = sum(rules.line_total(*taken["work"][key][:2]) for key in keys) + \
            (taken["arrears"].get((employee, day)) or (0.0,))[0]
        for key in keys:
            del taken["work"][key]
        taken["arrears"].pop((employee, day), None)
        problems.append(_("{0}'s week to {1} on the sheet, {2}, is left out: {3} has already paid that week.").format(
            names.get(employee) or employee, day.strftime("%d-%b-%Y"), "{:,.0f}".format(worth), slip))
    return problems


def _paying_slips(weeks):
    """{(employee, day): the submitted weekly salary slip whose days hold it}, for these (employee, day), read at
    once."""
    weeks = {(employee, getdate(day)) for employee, day in weeks or ()}
    if not weeks:
        return {}
    days = [day for _employee, day in weeks]
    found = {}
    for row in frappe.get_all("Salary Slip", filters={
            "employee": ["in", sorted({employee for employee, _day in weeks})], "docstatus": 1,
            "payroll_frequency": weekly_pay_rules.WEEKLY, "start_date": ["<=", max(days)],
            "end_date": [">=", min(days)]},
            fields=["name", "employee", "start_date", "end_date"], order_by="start_date asc", limit_page_length=0):
        for employee, day in weeks:
            if employee == row.employee and getdate(row.start_date) <= day <= getdate(row.end_date):
                found.setdefault((employee, day), row.name)
    return found


def _replace_uploads(doc, days):
    """The last upload of the weeks the sheet gives goes, its pay with it
    (report_on_cancel): found by the week's last day and the plant, not by the
    payroll, so a payroll deleted and made again still replaces what it
    uploaded. A week the sheet does not give keeps its upload."""
    days = sorted({getdate(day) for day in days or ()})
    if not days:
        return
    filters = {"source": rules.UPLOADED, "section": rules.PER_PIECE, "report_date": ["in", days]}
    if doc.get("branch"):
        filters["branch"] = doc.branch
    for name in frappe.get_all(REPORT, filters=filters, pluck="name", limit_page_length=0):
        report = frappe.get_doc(REPORT, name)
        report.flags.ignore_permissions = True
        if report.docstatus == 1:
            report.cancel()
        frappe.delete_doc(REPORT, name, ignore_permissions=True, force=True)


def _make_reports(doc, taken, people):
    """One submitted report for each week and plant, from the sheet: the sheet
    is the week's record already. Their submit writes the pay."""
    groups = {}
    for (employee, day, size), (bags, _price, _where) in sorted(taken["work"].items(), key=lambda item: (item[0][1], item[1][2])):
        branch = people[employee].get("branch") or doc.get("branch")
        groups.setdefault((day, branch), {"lines": [], "arrears": []})["lines"].append(
            {"employee": employee, "size": size, "output": bags})
    for (employee, day), (amount, _where) in sorted(taken["arrears"].items(), key=lambda item: (item[0][1], item[1][1])):
        branch = people[employee].get("branch") or doc.get("branch")
        groups.setdefault((day, branch), {"lines": [], "arrears": []})["arrears"].append(
            {"employee": employee, "amount": amount})
    made = []
    for (day, branch), found in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1] or "")):
        report = frappe.get_doc({
            "doctype": REPORT, "report_date": day, "shift": rules.SHIFTS[0], "section": rules.PER_PIECE,
            "branch": branch, "company": doc.company, "source": rules.UPLOADED,
            "lines": found["lines"], "arrears": found["arrears"],
            "remarks": _("Uploaded on {0}.").format(doc.name),
        })
        report.flags.ignore_permissions = True
        # a week whose only pay at this plant is arrears has no lines, which the form asks for
        report.flags.ignore_mandatory = not found["lines"]
        report.docstatus = 1
        report.insert()
        made.append(report.name)
    return made


# ── A Per Piece report ────────────────────────────────────────────────
def report_validate(doc, method=None):
    """A Per Piece report's arrears are a Per Piece casual's, each more than
    nothing, once a person; a Per Piece report has no Looms OT."""
    if doc.get("section") != rules.PER_PIECE:
        if doc.get("arrears"):
            frappe.throw(_("Arrears go on a Per Piece report."), title=_(REPORT))
        return
    if doc.get("looms_ot"):
        frappe.throw(_("A Per Piece report has no Looms OT: put what is owed under Arrears."), title=_(REPORT))
    rows = doc.get("arrears") or []
    categories = output_pay._pay_categories([row.get("employee") for row in rows])
    seen, errors = set(), []
    for row in rows:
        if not row.get("employee"):
            errors.append(_("Arrears row {0}: whose arrears?").format(row.idx))
        elif row.employee in seen:
            errors.append(_("Arrears row {0}: {1} is already on the arrears.").format(row.idx, row.employee))
        elif categories.get(row.employee) != rules.PER_PIECE:
            errors.append(_("Arrears row {0}: {1} is not paid Per Piece.").format(row.idx, row.employee))
        if flt(row.get("amount")) <= 0:
            errors.append(_("Arrears row {0}: the amount must be more than nothing.").format(row.idx))
        seen.add(row.get("employee"))
    if errors:
        frappe.throw("<br>".join(errors), title=_(REPORT))
    doc.total_arrears = round(sum(flt(row.get("amount")) for row in rows), 2)


def report_on_submit(doc, method=None):
    """Each person's pay on the report written as Additional Salary dated its
    day: the weekly slip whose days hold it pays it."""
    if doc.get("section") != rules.PER_PIECE:
        return
    amounts = _amounts(doc)
    people = sorted({employee for employee, _component in amounts})
    paid = _paying_slips((employee, doc.report_date) for employee in people)
    for (employee, day), slip in sorted(paid.items()):
        frappe.throw(_("{0} has already paid {1}'s week of {2}: the pay would never be counted. Date the "
                       "report in a week not yet paid, or cancel that slip first.").format(
            slip, employee, day.strftime("%d-%b-%Y")), title=_(REPORT))
    failed = weekly_pay.assign_people(people, doc.company, getdate(doc.report_date))
    if failed:
        frappe.throw(_("No salary assignment for: {0}.").format(
            "; ".join("%s: %s" % (employee, why) for employee, why in sorted(failed.items()))), title=_(REPORT))
    # posting the payroll needs an account for each earning: Basic's, where it has none (weekly_pay._give_account)
    for component in sorted({component for _employee, component in amounts}):
        weekly_pay._give_account(component, doc.company)
    currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    # an uploaded week is paid to the last day of one who left during it, as Frappe HR takes no pay dated after
    days = {}
    if doc.get("source") == rules.UPLOADED:
        found = _employment(people)
        days = {employee: rules.piece_pay_day(None, doc.report_date, None,
                                              (found.get(employee) or {}).get("relieving_date"))[0]
                for employee in people}
    for (employee, component), amount in sorted(amounts.items()):
        if amount <= 0:
            continue
        earning = frappe.get_doc({
            "doctype": ADDITIONAL, "employee": employee, "company": doc.company, "salary_component": component,
            "amount": amount, "payroll_date": days.get(employee) or doc.report_date, "currency": currency,
            "overwrite_salary_structure_amount": 0, "ref_doctype": REPORT, "ref_docname": doc.name,
        })
        earning.flags.ignore_permissions = True
        earning.insert()
        earning.submit()


def _amounts(doc):
    """{(employee, salary component): amount}: each category under the
    component its Output Rate names, else the Per Piece earning; the arrears
    under Arrears. A component cut by payment days is refused: a casual's
    pieces are what they made, and a week with few days marked would pay
    less."""
    sizes = {row.size for row in doc.get("lines") or [] if row.get("size")}
    named = {row.name: row.salary_component for row in frappe.get_all(
        "Output Rate", filters={"name": ["in", list(sizes) or [""]]}, fields=["name", "salary_component"],
        limit_page_length=0)}
    amounts = {}
    for row in doc.get("lines") or []:
        component = named.get(row.size) or output_pay._component(rules.PER_PIECE)
        key = (row.employee, component)
        amounts[key] = round(amounts.get(key, 0.0) + flt(row.get("amount")), 2)
    if doc.get("arrears"):
        arrears = _arrears_component()
        for row in doc.arrears:
            key = (row.employee, arrears)
            amounts[key] = round(amounts.get(key, 0.0) + flt(row.get("amount")), 2)
    for component in {component for _employee, component in amounts}:
        if frappe.db.get_value("Salary Component", component, "depends_on_payment_days"):
            frappe.throw(_("{0} is cut by payment days: untick Depends on Payment Days on it, as a casual's pieces "
                           "and arrears are what they are owed.").format(component), title=_(REPORT))
    return amounts


def _arrears_component():
    """The earning a casual's arrears are paid under: the site's Arrears, made
    once where it has none: an Earning, not pro-rated by payment days."""
    name, abbr = ARREARS
    if not frappe.db.exists("Salary Component", name):
        component = frappe.get_doc({
            "doctype": "Salary Component", "name": name, "salary_component": name, "salary_component_abbr": abbr,
            "type": "Earning", "depends_on_payment_days": 0, "is_tax_applicable": 1,
            "description": "What is owed from an earlier week or month."})
        component.flags.ignore_permissions = True
        component.insert()
    return name


def report_on_cancel(doc, method=None):
    """The report's pay goes with it, unless a submitted slip has paid it:
    that slip is named and nothing is cancelled."""
    if doc.get("section") != rules.PER_PIECE:
        return
    paid = advance_runs.recovered_on(REPORT, [doc.name])
    if paid:
        frappe.throw(_("{0}'s pay is on Salary Slip {1}, which is submitted. Cancel the salary slip first.").format(
            doc.name, paid[1] if isinstance(paid, (list, tuple)) else paid), title=_(REPORT))
    for name in frappe.get_all(ADDITIONAL, filters={"ref_doctype": REPORT, "ref_docname": doc.name,
                                                    "docstatus": ["<", 2]}, pluck="name", limit_page_length=0):
        earning = frappe.get_doc(ADDITIONAL, name)
        earning.flags.ignore_permissions = True
        if earning.docstatus == 1:
            earning.cancel()
        frappe.delete_doc(ADDITIONAL, name, ignore_permissions=True, force=True)


# ── The payroll ───────────────────────────────────────────────────────
def waiting(employees, start, end):
    """Those of these Per Piece casuals with piece pay dated in a payroll's
    days and not yet on a submitted slip."""
    employees = list(employees or ())
    if not employees or not start or not end:
        return set()
    owed = frappe.get_all(ADDITIONAL, filters={"employee": ["in", employees], "docstatus": 1, "ref_doctype": REPORT,
                                               "payroll_date": ["between", [getdate(start), getdate(end)]]},
                          fields=["name", "employee"], limit_page_length=0)
    if not owed:
        return set()
    paid = set(frappe.get_all("Salary Detail", filters={"parenttype": "Salary Slip", "docstatus": 1,
                                                        "additional_salary": ["in", [row.name for row in owed]]},
                              pluck="additional_salary", limit_page_length=0))
    return {row.employee for row in owed if row.name not in paid}
