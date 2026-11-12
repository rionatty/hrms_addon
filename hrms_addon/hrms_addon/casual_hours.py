# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Casuals' hours by the week, on the site. The rules are in
casual_hours_rules.py and casual_hours_approval.py (scripts/verify_casual_hours.py).

Luuka, 12 Nov 2026: "the team captures total number of hours worked and
overtime how can we make it easy for them". A Casual Hours Sheet is one
plant's week: each casual paid by the hour with the week's totals, filled
from a template or the team's own sheet, approved by the plant's General
Manager, then paid by the weekly payroll (weekly_pay.py).

  sheet_validate       the week and its people: the plant's casuals paid by
                       the hour, each once, on no other sheet of those days;
                       each one's rate and Overtime Type on the week's last
                       day, and what the row comes to; the approval's steps
  sheet_before_submit  only the General Manager's Approve submits it
  sheet_before_cancel  refused once a submitted weekly slip paid any of it
  new_sheet_week       the week a plant's next sheet is for
  download_template    the plant's casuals paid by the hour, to fill in
  upload_sheet         the filled template, or the team's own sheet with
                       those headings, onto a draft
  spans, unpaid, waiting, latest_to
                       what the weekly payroll reads: the weeks the sheets
                       cover, what is still to pay, and where a payroll stops
"""

import datetime
import io

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, today

from hrms_addon.hrms_addon import casual_hours_rules as rules, output_pay, people
from hrms_addon.hrms_addon import weekly_pay_rules

DOCTYPE = "Casual Hours Sheet"
ROW = "Casual Hours Row"
DAY = "Weekly Pay Day"
OVERTIME_TYPE = "Overtime Type"
WEEKLY = "Weekly"
TITLE = "Casual Hours"


def _standard():
    return flt(output_pay.settings().get("standard_hours")) or rules.STANDARD_DAY


# ── 1. The sheet ──────────────────────────────────────
def sheet_validate(doc, method=None):
    from hrms_addon.hrms_addon import casual_hours_approval as approval

    errors = rules.sheet_errors(doc.get("from_date"), doc.get("to_date"), today())
    if not errors:
        errors = _row_errors(doc) + _overlap_errors(doc) + _verified_errors(doc)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TITLE))
    facts = _price(doc)
    _totals(doc)
    _check_step(doc, facts)
    doc.status = doc.get("workflow_state") or doc.get("status") or approval.DRAFT


def _row_errors(doc):
    """The people on the sheet: each the company's casual paid by the hour, at the sheet's plant, once, with
    figures that will do."""
    names = [row.employee for row in doc.get("rows") or [] if row.get("employee")]
    found = {row.name: row for row in frappe.get_all(
        "Employee", filters={"name": ["in", names]}, limit_page_length=0,
        fields=["name", "employee_name", "custom_pay_category", "company", "branch"])} if names else {}
    days, standard = rules.week_days(doc.from_date, doc.to_date), _standard()
    errors, seen = [], set()
    for row in doc.get("rows") or []:
        who = row.get("employee")
        if not who:
            errors.append("Row %d: choose the employee." % row.idx)
            continue
        if who in seen:
            errors.append("%s is on the sheet twice." % who)
            continue
        seen.add(who)
        person = found.get(who)
        if not person:
            errors.append("Row %d: there is no employee %s." % (row.idx, who))
            continue
        row.employee_name = person.employee_name
        if person.custom_pay_category != WEEKLY:
            errors.append("%s is not paid by the hour: their Pay Category is %s." % (
                who, person.custom_pay_category or "not set"))
        elif person.company != doc.get("company"):
            errors.append("%s is not an employee of %s." % (who, doc.get("company")))
        elif doc.get("branch") and person.branch != doc.branch:
            errors.append("%s is at %s, not %s: their plant's sheet takes them." % (
                who, person.branch or "no plant", doc.branch))
        for why in rules.row_errors({"hours": row.get("hours_worked"), "overtime": row.get("overtime_hours"),
                                     "days": row.get("days_worked")}, days, standard):
            errors.append("%s: %s." % (who, why))
    return errors


def _clashes(doc, employees):
    """{employee: the other sheet}: those of these people already on another sheet, not cancelled, that shares a
    day with this one. Each week is entered once, so it is paid once."""
    employees = [employee for employee in employees or () if employee]
    if not employees:
        return {}
    others = [sheet.name for sheet in frappe.get_all(
        DOCTYPE, filters={"docstatus": ["<", 2], "name": ["!=", doc.name or ""], "company": doc.get("company")},
        fields=["name", "from_date", "to_date"], limit_page_length=0)
        if rules.overlap(sheet.from_date, sheet.to_date, doc.get("from_date"), doc.get("to_date"))]
    if not others:
        return {}
    return {row.employee: row.parent for row in frappe.get_all(
        ROW, filters={"parenttype": DOCTYPE, "parent": ["in", others], "employee": ["in", employees]},
        fields=["parent", "employee"], limit_page_length=0)}


def _overlap_errors(doc):
    clashes = _clashes(doc, [row.employee for row in doc.get("rows") or [] if row.get("employee")])
    return ["%s is already on %s for some of these days." % (employee, sheet)
            for employee, sheet in sorted(clashes.items())]


def _verified_errors(doc):
    """A sheet's people whose days in its week a verified Attendance Verification holds: the week as verified is what
    the payroll pays, so the hours are not changed under it. The General Manager reopens it first (as
    attendance_verification.refuse_attendance asks of a day's attendance)."""
    from hrms_addon.hrms_addon import attendance_verification

    people = [row.employee for row in doc.get("rows") or [] if row.get("employee")]
    if not people or not doc.get("from_date") or not doc.get("to_date"):
        return []
    return ["%s is on %s, verified for %s: the General Manager reopens it before these hours change." % (
        ", ".join(sorted(sheet["employees"])), sheet.name, sheet.branch or doc.get("branch"))
        for sheet in attendance_verification.verified_sheets(doc.from_date, doc.to_date, doc.get("company"), people)
        if sheet["employees"]]


def _paid_already(doc):
    """["employee (slip)"] of the sheet's people some of whose days in its week a submitted slip paid another way:
    from the attendance on a weekly slip, or on a monthly slip. Sent or approved, the sheet would pay them again."""
    people = [row.employee for row in doc.get("rows") or [] if row.get("employee")]
    if not people or not doc.get("from_date") or not doc.get("to_date"):
        return []
    found = {}
    for row in frappe.get_all(DAY, filters={"employee": ["in", people], "docstatus": 1, "hours_sheet": ["is", "not set"],
                                            "attendance_date": ["between", [getdate(doc.from_date),
                                                                            getdate(doc.to_date)]]},
                              fields=["employee", "parent"], limit_page_length=0):
        found.setdefault(row.employee, row.parent)
    for row in frappe.get_all("Salary Slip", filters={"employee": ["in", people], "docstatus": 1,
                                                      "payroll_frequency": ["!=", WEEKLY],
                                                      "start_date": ["<=", getdate(doc.to_date)],
                                                      "end_date": [">=", getdate(doc.from_date)]},
                              fields=["employee", "name"], limit_page_length=0):
        found.setdefault(row.employee, row.name)
    return ["%s (%s)" % (employee, slip) for employee, slip in sorted(found.items())]


def _price(doc):
    """Each row's rate and Overtime Type on the week's last day, and what it comes to. The week's overtime is at
    the weekday rate (OT1), the type taken as a weekday's: a week's total, whatever day the week ends on, as the
    weekly slip pays it (weekly_pay.multipliers). {"unrated", "no_type"}: those the approval waits on."""
    from hrms_addon.hrms_addon import overtime, overtime_rules, weekly_pay

    employees = [row.employee for row in doc.get("rows") or [] if row.get("employee")]
    day = getdate(doc.to_date)
    standard_rate, history = weekly_pay.standard_rate(), weekly_pay.rate_history(employees, day)
    kinds = overtime._types_for() if any(flt(row.get("overtime_hours")) > 0 for row in doc.get("rows") or []) else None
    types, unrated, no_type = {}, [], []
    for row in doc.get("rows") or []:
        rate = weekly_pay_rules.rate_on(history.get(row.employee), day) or standard_rate
        if (flt(row.get("hours_worked")) or flt(row.get("overtime_hours"))) and not rate:
            unrated.append(row.employee)
        multiplier, row.overtime_type = 0.0, None
        if flt(row.get("overtime_hours")) > 0:
            name, why = overtime.type_on(row.employee, day, kinds, kind=overtime_rules.WEEKDAY)
            if name:
                row.overtime_type = name
                if name not in types:
                    types[name] = frappe.get_cached_doc(OVERTIME_TYPE, name).as_dict()
                multiplier = overtime_rules.multiplier_for(overtime_rules.WEEKDAY, types[name])
            else:
                no_type.append("%s (%s)" % (row.employee, why) if why else row.employee)
        row.rate, row.multiplier = rate, multiplier
        row.update(rules.pay(row.get("hours_worked"), row.get("overtime_hours"), rate, multiplier))
    return {"unrated": unrated, "no_type": no_type}


def _totals(doc):
    rows = doc.get("rows") or []
    doc.total_people = len([row for row in rows if flt(row.get("hours_worked")) or flt(row.get("overtime_hours"))])
    doc.total_hours = round(sum(flt(row.get("hours_worked")) for row in rows), 2)
    doc.total_overtime = round(sum(flt(row.get("overtime_hours")) for row in rows), 2)
    doc.total_pay = round(sum(flt(row.get("total_pay")) for row in rows), 2)


def _check_step(doc, facts):
    from hrms_addon.hrms_addon import casual_hours_approval as approval

    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.get("workflow_state")
    if old_state != new_state:
        errors = approval.step_errors(old_state, new_state, {
            "return_remarks": doc.get("return_remarks"), "people": doc.get("total_people"),
            "unrated": facts["unrated"], "no_type": facts["no_type"],
            "paid": _paid_already(doc) if new_state in (approval.PENDING_GM, approval.APPROVED) else []})
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_(TITLE))
        if new_state == approval.PENDING_GM:
            doc.return_remarks = None
    current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}
    for field, value in approval.compute_stamps(old_state, new_state, frappe.session.user, now_datetime(),
                                                current).items():
        doc.set(field, value)
    if old_state != new_state:
        _tell_step(doc, old_state, new_state)


def _tell_step(doc, old_state, new_state):
    """The plant's General Manager is told of a week to approve; whoever prepared it, of a return; the plant's HR
    and Payroll Officers, of a week the payroll may pay."""
    from hrms_addon.hrms_addon import casual_hours_approval as approval

    branch = doc.get("branch")
    week = "%s to %s" % (rules.shown(doc.from_date), rules.shown(doc.to_date))
    if new_state == approval.PENDING_GM:
        users = [user for user in people.people_for(approval.GM, branch) if user != frappe.session.user]
        message = _("Casual hours of {0}, {1}: {2} people, {3} hours and {4} overtime hours to approve.").format(
            branch, week, doc.get("total_people"), doc.get("total_hours"), doc.get("total_overtime"))
        if users:
            people.notify(users, doc.doctype, doc.name, message)
            people.assign(doc.doctype, doc.name, users, message)
        return
    if old_state == approval.PENDING_GM:
        people.withdraw(doc.doctype, doc.name, people.people_for(approval.GM, branch))
    if new_state == approval.DRAFT and old_state == approval.PENDING_GM:
        users = [user for user in [doc.get("owner")] + list(people.hr_officers(branch)) if user]
        users = [user for user in dict.fromkeys(users) if user != frappe.session.user]
        if users:
            people.notify(users, doc.doctype, doc.name, _("Casual hours of {0}, {1}, returned: {2}").format(
                branch, week, doc.get("return_remarks") or ""))
    elif new_state == approval.APPROVED:
        users = set(people.hr_officers(branch)) | set(people.people_for(approval.PAYROLL_OFFICER, branch))
        users.discard(frappe.session.user)
        if users:
            people.notify(sorted(users), doc.doctype, doc.name, _(
                "Casual hours of {0}, {1}, approved: the weekly payroll pays them.").format(branch, week))


def sheet_before_submit(doc, method=None):
    """Only the General Manager's Approve submits a sheet: a plain submit would pay a week nobody approved."""
    from hrms_addon.hrms_addon import casual_hours_approval as approval

    if doc.get("workflow_state") != approval.APPROVED:
        frappe.throw(_("The plant's General Manager approves the week: send it to them."), title=_(TITLE))


def sheet_before_cancel(doc, method=None):
    """A week a submitted weekly slip has paid stays: its slips are cancelled first. So does one a verified Attendance
    Verification holds: the General Manager reopens it first."""
    held = _verified_errors(doc)
    if held:
        frappe.throw("<br>".join(_(message) for message in held), title=_(TITLE))
    slips = sorted({row.parent for row in frappe.get_all(DAY, filters={"hours_sheet": doc.name, "docstatus": 1},
                                                        fields=["parent"], limit_page_length=0)})
    if slips:
        frappe.throw(_("Weekly slips have paid this week: {0}. Cancel them first.").format(", ".join(slips)),
                     title=_(TITLE))


def sheet_on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled", update_modified=False)


# ── 2. The week, the template, the upload ─────────────
@frappe.whitelist()
def new_sheet_week(company=None, branch=None):
    """{"from_date", "to_date"} for a plant's next sheet: the week after its last one."""
    frappe.has_permission(DOCTYPE, "read", throw=True)
    filters = {"docstatus": ["<", 2]}
    if company:
        filters["company"] = company
    if branch:
        filters["branch"] = branch
    last = frappe.db.get_value(DOCTYPE, filters, "to_date", order_by="to_date desc")
    start, end = rules.default_week(last, today())
    return {"from_date": str(start) if start else None, "to_date": str(end) if end else None}


def _plant_casuals(company, branch, start=None):
    """The plant's casuals paid by the hour on its sheet's week: not Inactive, and not gone before it starts."""
    filters = {"company": company, "custom_pay_category": WEEKLY, "status": ["!=", "Inactive"]}
    if branch:
        filters["branch"] = branch
    return [row for row in frappe.get_all("Employee", filters=filters, order_by="employee_name asc",
                                          fields=["name", "employee_name", "relieving_date"], limit_page_length=0)
            if weekly_pay_rules.still_here(row.relieving_date, start)]


@frappe.whitelist()
def download_template(sheet):
    """The sheet's week as a template: every one of the plant's casuals paid by the hour, by PAYROLL NO, with the
    week's hours, overtime hours and (if known) days worked to fill in."""
    from frappe.utils.xlsxutils import make_xlsx

    doc = frappe.get_doc(DOCTYPE, sheet)
    doc.check_permission("read")
    data = [list(rules.TEMPLATE_HEADS)] + [[row.name, row.employee_name, None, None, None]
                                           for row in _plant_casuals(doc.company, doc.get("branch"), doc.from_date)]
    content = make_xlsx(data, "Hours")
    frappe.response["filename"] = "Casual hours %s %s to %s.xlsx" % (
        doc.get("branch") or doc.company, rules.shown(doc.from_date), rules.shown(doc.to_date))
    frappe.response["filecontent"] = content.getvalue()
    frappe.response["type"] = "binary"


def _tables(content):
    """[(title, rows)]: each worksheet's values, row by row, the one the file was saved on first (rules.read_book)."""
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheets = list(book.worksheets)
        active = book.active if book.active in sheets else None
        if active is not None:
            sheets = [active] + [sheet for sheet in sheets if sheet is not active]
        return [(sheet.title, [list(row) for row in sheet.iter_rows(values_only=True)]) for sheet in sheets]
    finally:
        book.close()


def _key(value):
    return "".join(str(value or "").replace("_x000D_", " ").split()).upper()


def _lookup(company):
    """The company's employees, by their ID as written and without its spaces, and by Employee Number."""
    found = {}
    for row in frappe.get_all("Employee", filters={"company": company}, limit_page_length=0,
                              fields=["name", "employee_name", "employee_number", "custom_pay_category", "branch"]):
        for key in (row.name, _key(row.name), _key(row.employee_number)):
            if key and key not in found:
                found[key] = row
    return found


@frappe.whitelist(methods=["POST"])
def upload_sheet(sheet, file_url):
    """The filled template, or the team's own sheet with PAYROLL NO and HOURS WORKED headings, onto a draft sheet:
    its rows replaced by the file's. Returns what was taken, and what was not and why."""
    from hrms_addon.hrms_addon import casual_hours_approval as approval

    doc = frappe.get_doc(DOCTYPE, sheet)
    doc.check_permission("write")
    if doc.docstatus != 0 or (doc.get("workflow_state") or approval.DRAFT) != approval.DRAFT:
        frappe.throw(_("Only a draft sheet takes an upload: return it to Draft first."), title=_(TITLE))
    try:
        found = rules.read_book(_tables(output_pay._file_bytes(file_url)))
    except ValueError as error:
        frappe.throw(_(str(error)), title=_(TITLE))
    except Exception:  # noqa: BLE001 — not a workbook openpyxl can read
        frappe.throw(_("The file could not be read: upload the template, saved as .xlsx."), title=_(TITLE))
    lookup = _lookup(doc.company)
    days, standard = rules.week_days(doc.from_date, doc.to_date), _standard()
    taken, problems, seen = [], list(found["problems"]), set()
    for row in found["rows"]:
        person = lookup.get(row["employee"]) or lookup.get(_key(row["employee"]))
        line = "Row %d, %s" % (row["line"], row["employee"])
        if not person:
            problems.append(_("{0}: no such employee of {1}.").format(line, doc.company))
        elif person.custom_pay_category != WEEKLY:
            problems.append(_("{0}: not paid by the hour (Pay Category {1}).").format(
                line, person.custom_pay_category or "not set"))
        elif doc.get("branch") and person.branch != doc.branch:
            problems.append(_("{0}: at {1}, not {2}; their plant's sheet takes them.").format(
                line, person.branch or "no plant", doc.branch))
        elif person.name in seen:
            problems.append(_("{0}: on the file twice; the first row is taken.").format(line))
        else:
            why = rules.row_errors(row, days, standard)
            if why:
                problems.append("%s: %s." % (line, "; ".join(why)))
            else:
                seen.add(person.name)
                taken.append({"employee": person.name, "employee_name": person.employee_name,
                              "hours_worked": row["hours"], "overtime_hours": row["overtime"],
                              "days_worked": row["days"]})
    clashes = _clashes(doc, [row["employee"] for row in taken])
    for row in [row for row in taken if row["employee"] in clashes]:
        problems.append(_("{0}: already on {1} for some of these days.").format(row["employee"], clashes[row["employee"]]))
        taken.remove(row)
    doc.set("rows", taken)
    doc.uploaded_sheet = file_url
    doc.save()
    missing = len([row for row in _plant_casuals(doc.company, doc.get("branch"), doc.from_date)
                   if row.name not in seen])
    return {"people": len(taken), "hours": round(sum(flt(row["hours_worked"]) for row in taken), 2),
            "overtime": round(sum(flt(row["overtime_hours"]) for row in taken), 2),
            "problems": problems, "missing": missing}


# ── 3. What the weekly payroll reads ──────────────────
def _approved_rows(employees, until=None):
    """These people's rows on approved sheets: [{"sheet", "from_date", "to_date", "employee", "hours",
    "overtime", "days", "overtime_type"}], of weeks ending on or before `until` where it is given."""
    employees = [employee for employee in dict.fromkeys(employees or ()) if employee]
    if not employees:
        return []
    rows = frappe.get_all(ROW, filters={"parenttype": DOCTYPE, "docstatus": 1, "employee": ["in", employees]},
                          fields=["parent", "employee", "hours_worked", "overtime_hours", "days_worked",
                                  "overtime_type"], limit_page_length=0)
    if not rows:
        return []
    sheets = {row.name: row for row in frappe.get_all(
        DOCTYPE, filters={"name": ["in", list({row.parent for row in rows})], "docstatus": 1},
        fields=["name", "from_date", "to_date"], limit_page_length=0)}
    last = getdate(until) if until else None
    out = []
    for row in rows:
        sheet = sheets.get(row.parent)
        if not sheet or (last and getdate(sheet.to_date) > last):
            continue
        out.append({"sheet": sheet.name, "from_date": sheet.from_date, "to_date": sheet.to_date,
                    "employee": row.employee, "hours": row.hours_worked, "overtime": row.overtime_hours,
                    "days": row.days_worked, "overtime_type": row.overtime_type})
    return out


def spans(employees):
    """{employee: [(from, to)]}: the weeks approved sheets cover for each person they list, whose days the attendance
    no longer pays (weekly_pay.days_to_pay, overtime_due). A casual a sheet leaves out is paid from the attendance,
    and the Attendance Verification shows them so (for_verification)."""
    out = {}
    for row in _approved_rows(employees):
        out.setdefault(row["employee"], []).append((row["from_date"], row["to_date"]))
    return out


def unpaid(employees, end):
    """{employee: [row]}: what approved sheets still owe each, of weeks ending on or before `end`, that no
    submitted weekly slip has paid (rules.slip_rows)."""
    employees = [employee for employee in dict.fromkeys(employees or ()) if employee]
    rows = _approved_rows(employees, until=end)
    if not rows:
        return {}
    paid = {}
    for day in frappe.get_all(DAY, filters={"docstatus": 1, "employee": ["in", employees], "hours_sheet": ["is", "set"]},
                              fields=["employee", "hours_sheet"], limit_page_length=0):
        paid.setdefault(day.employee, set()).add(day.hours_sheet)
    out = {}
    for employee in employees:
        found = rules.slip_rows([row for row in rows if row["employee"] == employee], paid.get(employee), end)
        if found:
            out[employee] = found
    return out


def waiting(employees, end):
    """Those of these people an approved sheet still owes, for a weekly payroll's Get Employees."""
    return set(unpaid(employees, end))


def for_verification(employees, first, last, branch=None):
    """What a weekly Attendance Verification takes from the Casual Hours Sheets over its days, as the weekly payroll
    pays them (attendance_verification._read; Luuka, 12 Nov 2026: "attendance verification is not accurate ... i have
    uploaded casual hours but it pull different data also it doesnt show the overtime hours"; "for casuals the
    attendance verification should be from casual hours sheet"):

      {"people": {employee: {"covered": {date}, "counted": {date}, "hours", "overtime", "days"}},
       "sheets": {name: {"from_date", "to_date", "state", "people"}}, "plant_days": {date}}

    plant_days: the verification's days the sheets of its plant (branch) give, not cancelled. Over a week they give
    every day of, the sheets feed its casuals paid by the hour: one they do not list is not on it (Luuka, 12 Nov 2026:
    "this is for casuals only casual hour sheet is the one tha feed the attendance verifacition sheet").

    covered: the days within the verification's that a sheet not cancelled gives the person; they are the sheet's,
    not the attendance's. counted: those of them whose days worked are the attendance's to count, as their sheet
    leaves its Days Worked blank. The totals, the days worked a sheet gives among them, count on the verification
    that holds the sheet's last day, as the payroll dates the week, so no day is counted on two. Every sheet not
    cancelled counts, so what was uploaded shows at once; one not yet approved stops the verification
    (attendance_verification_rules.hours_sheet_issue)."""
    employees = [employee for employee in dict.fromkeys(employees or ()) if employee]
    first, last = (getdate(first) if first else None), (getdate(last) if last else None)
    if not first or not last:
        return {"people": {}, "sheets": {}, "plant_days": set()}
    sheets = {row.name: row for row in frappe.get_all(
        DOCTYPE, filters={"docstatus": ["<", 2], "from_date": ["<=", last], "to_date": [">=", first]},
        fields=["name", "branch", "from_date", "to_date", "docstatus", "workflow_state"], limit_page_length=0)}
    plant_days = set()
    for sheet in sheets.values():
        if branch and sheet.get("branch") == branch:
            plant_days |= rules.days_within(sheet.from_date, sheet.to_date, first, last)
    if not employees:
        return {"people": {}, "sheets": {}, "plant_days": plant_days}
    people, used = {}, {}
    if sheets:
        for row in frappe.get_all(ROW, filters={"parenttype": DOCTYPE, "parent": ["in", list(sheets)],
                                                "employee": ["in", employees]},
                                  fields=["parent", "employee", "hours_worked", "overtime_hours", "days_worked"],
                                  limit_page_length=0):
            sheet = sheets[row.parent]
            mine = people.setdefault(row.employee, {"covered": set(), "counted": set(), "hours": 0.0, "overtime": 0.0,
                                                    "days": 0.0})
            days = rules.days_within(sheet.from_date, sheet.to_date, first, last)
            mine["covered"] |= days
            if not flt(row.days_worked):
                mine["counted"] |= days
            used.setdefault(sheet.name, set()).add(row.employee)
            if first <= getdate(sheet.to_date) <= last:
                mine["hours"] = round(mine["hours"] + flt(row.hours_worked), 2)
                mine["overtime"] = round(mine["overtime"] + flt(row.overtime_hours), 2)
                mine["days"] = round(mine["days"] + flt(row.days_worked), 2)
    return {"people": people,
            "sheets": {name: {"from_date": sheets[name].from_date, "to_date": sheets[name].to_date,
                              "state": sheets[name].get("workflow_state") or ("Approved" if sheets[name].docstatus == 1
                                                                             else "Draft"),
                              "people": len(who)}
                       for name, who in used.items()},
            "plant_days": plant_days}


def plants_with_sheets(branches, first, last):
    """Those of these plants with a sheet not cancelled over any of the days: their casuals by the hour are on the
    sheet, or not paid from the clock unseen (attendance_verification.payroll_problems)."""
    branches = sorted({branch for branch in branches or () if branch})
    if not branches or not first or not last:
        return set()
    return set(frappe.get_all(DOCTYPE, filters={"branch": ["in", branches], "docstatus": ["<", 2],
                                                "from_date": ["<=", getdate(last)], "to_date": [">=", getdate(first)]},
                              pluck="branch", limit_page_length=0))


def plant_week(company, branch, first, yesterday):
    """(from, to) of the plant's sheet a new weekly Attendance Verification follows, so the two cover the same days,
    or None: the plant's earliest sheet not cancelled that ends on or after `first` and by yesterday. A sheet that
    starts later leaves the days before it to a verification of their own."""
    if not company or not branch or not first or not yesterday:
        return None
    found = frappe.get_all(DOCTYPE, filters={"company": company, "branch": branch, "docstatus": ["<", 2],
                                             "to_date": [">=", getdate(first)]},
                           fields=["from_date", "to_date"], order_by="from_date asc", limit=1)
    if not found or getdate(found[0].to_date) > getdate(yesterday):
        return None
    start = getdate(found[0].from_date)
    if start > getdate(first):
        return getdate(first), start - datetime.timedelta(days=1)
    return getdate(first), getdate(found[0].to_date)


def latest_to(wanted):
    """The last day an approved sheet for these people ends before today: where a weekly payroll stops when the
    hours come by the sheet rather than the attendance."""
    filters = {"company": wanted.get("company"), "docstatus": 1, "to_date": ["<", today()]}
    if wanted.get("branch"):
        filters["branch"] = wanted.get("branch")
    return frappe.db.get_value(DOCTYPE, filters, "to_date", order_by="to_date desc")


# ── 4. Wiring ─────────────────────────────────────────
def setup_workflows_on_migrate():
    """after_migrate: the sheet's approval."""
    from hrms_addon.hrms_addon import casual_hours_approval, workflows

    workflows.setup_on_migrate(casual_hours_approval, "Casual Hours Sheet workflow")
