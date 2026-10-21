# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The desk home's panels under what waits for the user (home_panels_rules.py
has the rules and says what each panel is): read here, in a call of their
own, so the greeting and what waits are never held up by them.
public/js/hrms_addon_home.js draws them.

  panels           every panel the user's roles are for and Theme Settings
                   show, with its figures
  places           the panels of a desk and where each goes, for
                   home.summary
  ensure_switches  after_migrate: a switch nobody has saved is written on,
                   so the settings form shows it on

AS THE USER MAY SEE IT

Records are read with the user's own permissions (frappe.get_list), as the
home's are: a plant's HR see their plant. A doctype the user may not read is
not asked for: its step says so, or its rows are left out. The rows of a
table are read only for records the user has read. A part that cannot be
read is logged and left out (home._or), and the rest still come.

KEPT FIVE MINUTES

The desk asks again every minute it is open, so a user's panels are kept
for five minutes (CACHE_SECONDS) and read afresh after.
"""

import frappe
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate

from hrms_addon.hrms_addon import attendance_rules, home, home_panels_rules as rules, home_rules

SETTINGS = "HRMS Addon Theme Settings"
CACHE_KEY = "hrms_addon_home_panels"
UNREADABLE = {rules.UNREADABLE: 1}


@frappe.whitelist()
def panels():
    """Every panel of the logged-in user's desk, with its figures."""
    user = frappe.session.user
    roles = frappe.get_roles(user)
    keys = rules.panels_for(roles, rules.switched_on(home._or({}, _stored)))
    if not keys:
        return {"panels": []}
    today = getdate(nowdate())
    money = rules.money_for(roles)
    kept = home._or(None, _kept, user)
    if kept and kept.get("keys") == keys and kept.get("day") == str(today) and kept.get("money") == money:
        return kept
    found = []
    for key in keys:
        panel = home._or(None, READERS[key], today, money, roles)
        if panel:
            found.append(dict(panel, key=key, title=rules.TITLES[key]))
    out = {"panels": found, "keys": keys, "day": str(today), "money": money}
    home._or(None, _keep, user, out)
    return out


def places(roles, view, today):
    """The panels of a desk and where each goes, for home.summary to send
    with the home so the page can lay them out before their figures come."""
    return rules.places(rules.panels_for(roles, rules.switched_on(home._or({}, _stored))), view, today)


def _stored():
    """What Theme Settings have saved; a switch nobody has saved is not in it."""
    if not frappe.db.exists("DocType", SETTINGS):
        return {}
    return frappe.db.get_singles_dict(SETTINGS)


def _kept(user):
    return frappe.cache.get_value(CACHE_KEY, user=user)


def _keep(user, value):
    frappe.cache.set_value(CACHE_KEY, value, user=user, expires_in_sec=rules.CACHE_SECONDS)


def ensure_switches():
    """after_migrate. Each panel's switch that nobody has saved is written
    on, as its field's default says: a Check never saved reads 0 on the
    settings form, and the next save of the settings would switch the panel
    off without anybody choosing to."""
    if not frappe.db.exists("DocType", SETTINGS):
        return
    stored = frappe.db.get_singles_dict(SETTINGS)
    for switch in rules.SWITCHES:
        if stored.get(switch) is None:
            frappe.db.set_single_value(SETTINGS, switch, 1)


def _may(doctype):
    """A doctype the site has and the user may read."""
    return bool(frappe.db.exists("DocType", doctype) and frappe.has_permission(doctype, "read"))


# ── Payroll Readiness ─────────────────────────────────────────────────
def _payroll(today, money, roles):
    """The steps of the period that ends this month."""
    start, end = attendance_rules.cycle_window(today.year, today.month)
    facts = {key: home._or(UNREADABLE, read, start, end)
             for key, read in (("clock", _clock), ("overtime", _overtime_decided), ("output", _output_runs),
                               ("advances", _advances))}
    entries = home._or(UNREADABLE, _entries, start, end)
    facts["drafted"] = facts["slips"] = entries
    facts["bank"] = home._or(UNREADABLE, _bank, entries) if entries and not entries.get(rules.UNREADABLE) else entries
    steps = rules.payroll_steps(facts, today, start, end, now_datetime())
    return {"kind": "steps", "steps": steps, "note": rules.payroll_note(steps, start, end)}


def _clock(start, end):
    """The BioTime clock's last good read and error, and the period's punches it could not place."""
    if not _may("BioTime Server"):
        return None
    server = frappe.db.get_singles_dict("BioTime Server")
    unplaced = 0
    if _may("Attendance Device Log"):
        unplaced = len(frappe.get_list("Attendance Device Log", filters={
            "status": ["in", list(rules.UNPLACED_PUNCHES)], "punch_time": ["between", [str(start), "%s 23:59:59" % end]]},
            pluck="name", limit_page_length=0))
    return {"enabled": cint(server.get("enabled")), "last_success": server.get("last_success"),
            "error": server.get("last_error"), "unplaced": unplaced}


def _overtime_decided(start, end):
    """The period's overtime requests by where they stand, and its Overtime Slips still in draft."""
    if not _may("Overtime Request"):
        return None
    live = [row for row in frappe.get_list("Overtime Request", filters={
        "overtime_date": ["between", [start, end]], "docstatus": ["<", 2]}, fields=["status"], limit_page_length=0)
        if row.status not in ("Rejected", "Cancelled")]
    slips = 0
    if _may("Overtime Slip"):
        slips = len(frappe.get_list("Overtime Slip", filters={"start_date": start, "end_date": end, "docstatus": 0},
                                    pluck="name", limit_page_length=0))
    return {"total": len(live), "waiting": sum(1 for row in live if row.status in rules.OVERTIME_WAITING),
            "approved": sum(1 for row in live if row.status == rules.OVERTIME_APPROVED), "slips": slips}


def _output_runs(start, end):
    """Each plant and section that is paid by its output this month: from the people paid that way, the
    period's reports and the month's runs; which runs are submitted; and a report left out of a paid run."""
    if not _may("Output Pay Run"):
        return None

    def label(branch, section):
        return "%s %s" % (branch or rules.UNPLACED, section)

    runs = frappe.get_list("Output Pay Run", filters={
        "year": end.year, "month": rules.MONTHS[end.month - 1], "docstatus": ["<", 2]},
        fields=["branch", "section", "docstatus"], limit_page_length=0)
    reports = []
    if _may("Daily Production Report"):
        reports = frappe.get_list("Daily Production Report", filters={
            "docstatus": 1, "report_date": ["between", [start, end]]},
            fields=["branch", "section", "output_pay_run"], limit_page_length=0)
    paid_by_output = []
    if _may("Employee"):
        paid_by_output = frappe.get_list("Employee", filters={
            "status": "Active", "custom_pay_category": ["in", list(rules.OUTPUT_SECTIONS)]},
            fields=["branch", "custom_pay_category"], limit_page_length=0)
    paid = {label(row.branch, row.section) for row in runs if row.docstatus == 1}
    needed = {label(row.branch, row.section) for row in runs} | {label(row.branch, row.section) for row in reports} \
        | {label(row.branch, row.custom_pay_category) for row in paid_by_output}
    loose = sum(1 for row in reports if not row.output_pay_run and label(row.branch, row.section) in paid)
    return {"needed": sorted(needed), "paid": sorted(paid), "unpaid_reports": loose}


def _advances(start, end):
    """The month's salary advance run, and the period's recoveries not yet on the payroll."""
    if not _may("Salary Advance Processing"):
        return None
    runs = frappe.get_list("Salary Advance Processing", filters={
        "year": end.year, "month": rules.MONTHS[end.month - 1], "docstatus": ["<", 2]},
        fields=["docstatus", "journal_entry"], limit_page_length=0)
    run = None
    if runs:
        submitted = [row for row in runs if row.docstatus == 1]
        if not submitted:
            run = "draft"
        else:
            # paid once Finance submit the bank entry the run drafted: its state, read from the run's own entry
            entries = [row.journal_entry for row in submitted if row.journal_entry]
            paid = bool(entries) and all(cint(frappe.db.get_value("Journal Entry", entry, "docstatus")) == 1
                                         for entry in entries)
            run = "paid" if paid else "submitted"
    return {"run": run, "unposted": _unposted(start, end)}


def _unposted(start, end):
    """The period's advance recoveries with no Additional Salary yet, on submitted advances."""
    count = 0
    for parent, table in (("Employee Advance", "Advance Recovery"), ("Leave Advance", "Leave Advance Recovery")):
        if not _may(parent) or not frappe.db.exists("DocType", table):
            continue
        rows = frappe.get_all(table, filters={"parenttype": parent, "payroll_date": ["between", [start, end]],
                                              "additional_salary": ["is", "not set"]},
                              fields=["parent"], limit_page_length=0)
        if not rows:
            continue
        live = set(frappe.get_list(parent, filters={"name": ["in", sorted({row.parent for row in rows})],
                                                    "docstatus": 1}, pluck="name", limit_page_length=0))
        count += sum(1 for row in rows if row.parent in live)
    return count


def _entries(start, end):
    """The period's Payroll Entries."""
    if not _may("Payroll Entry"):
        return None
    return {"entries": [{"name": row.name, "docstatus": row.docstatus, "status": row.status,
                         "slips_submitted": cint(row.salary_slips_submitted)}
                        for row in frappe.get_list("Payroll Entry", filters={
                            "start_date": start, "end_date": end, "docstatus": ["<", 2]},
                            fields=["name", "docstatus", "status", "salary_slips_submitted"], limit_page_length=0)]}


def _bank(found):
    """Which of the Payroll Entries have a submitted bank entry made from them."""
    entries = found.get("entries") or []
    if not entries:
        return {"entries": [], "paid": 0}
    if not _may("Journal Entry"):
        return None
    paid = {row.reference_name for row in frappe.get_all("Journal Entry Account", filters={
        "reference_type": "Payroll Entry", "reference_name": ["in", [entry["name"] for entry in entries]],
        "docstatus": 1}, fields=["reference_name"], limit_page_length=0)}
    return {"entries": entries, "paid": len(paid)}


# ── Plants at a Glance ────────────────────────────────────────────────
def _plants(today, money, roles):
    """Each plant's people today, and its approved overtime this period."""
    if not _may("Employee"):
        return None
    people = frappe.get_list("Employee", filters={"status": "Active"}, fields=["name", "branch"],
                             limit_page_length=0)
    clocked, marked, on_leave, seen = home._marks([row.name for row in people] or [""], today)
    where = home_rules.where_today([row.name for row in people], clocked, marked, on_leave)
    start = attendance_rules.cycle_window(*attendance_rules.cycle_of(today))[0]
    overtime = rules.overtime_hours(home._or([], _overtime_lines, start, today))
    clocks, punched = home._or(({}, set()), _clocks, today)
    rows = rules.plants(people, where, overtime, clocks, punched,
                        known=bool(seen.get("clock") or seen.get("attendance")))
    return {"kind": "plants", "rows": rows, "note": rules.plants_note(rows)}


def _overtime_lines(start, end):
    """The approved overtime of these days, a line for each person, marked where it is on the attendance."""
    if not _may("Overtime Request"):
        return []
    requests = {row.name: row.status for row in frappe.get_list("Overtime Request", filters={
        "overtime_date": ["between", [start, end]], "docstatus": 1, "status": ["in", list(rules.OVERTIME_COUNTED)]},
        fields=["name", "status"], limit_page_length=0)}
    if not requests:
        return []
    return [dict(line, sent=requests.get(line.parent) == "Sent to Payroll") for line in frappe.get_all(
        "Overtime Request Employee", filters={"parenttype": "Overtime Request", "parent": ["in", sorted(requests)]},
        fields=["parent", "employee", "hours", "payable_hours", "amount"], limit_page_length=0)]


def _clocks(today):
    """How many clocks stand at each plant, and which plants' clocks have sent a punch today."""
    if not _may("Attendance Device"):
        return {}, set()
    devices = {row.name: row.branch for row in frappe.get_list("Attendance Device", filters={"enabled": 1},
                                                                fields=["name", "branch"], limit_page_length=0)}
    clocks = {}
    for branch in devices.values():
        if branch:
            clocks[branch] = clocks.get(branch, 0) + 1
    punched = set()
    if devices and _may("Attendance Device Log"):
        for device in frappe.get_list("Attendance Device Log", filters={
                "punch_time": [">=", str(today)], "device": ["in", sorted(devices)]},
                pluck="device", distinct=True, limit_page_length=0):
            if devices.get(device):
                punched.add(devices[device])
    return clocks, punched


# ── Output and Labour Cost ────────────────────────────────────────────
def _output(today, money, roles):
    """Each plant's output and overtime so far this period, against the same days of the last."""
    start = attendance_rules.cycle_window(*attendance_rules.cycle_of(today))[0]
    before_start, before_end = rules.same_days_before(start, today)
    lines_now = home._or([], _overtime_lines, start, today)
    lines_before = home._or([], _overtime_lines, before_start, before_end)
    branches = home._or({}, _branches, sorted({line["employee"] for line in lines_now + lines_before}))
    rows = rules.output_rows(rules.output_figures(home._or([], _reports, start, today)),
                             rules.output_figures(home._or([], _reports, before_start, before_end)),
                             rules.overtime_figures(lines_now, branches), rules.overtime_figures(lines_before, branches),
                             money)
    for row in rows:
        row["route"] = ["List", "Daily Production Report"]
        row["filters"] = {"branch": row["plant"], "docstatus": 1, "report_date": ["between", [str(start), str(today)]]}
    return {"kind": "output", "rows": rows, "money": 1 if money else 0, "currency": home._or("", _currency) or "",
            "note": rules.output_note(start, today)}


def _reports(start, end):
    """The submitted Daily Production Reports of these days."""
    if not _may("Daily Production Report"):
        return []
    return frappe.get_list("Daily Production Report", filters={"docstatus": 1, "report_date": ["between", [start, end]]},
                           fields=["branch", "section", "total_output", "total_amount"], limit_page_length=0)


def _branches(employees):
    """{employee: their plant}."""
    if not employees or not _may("Employee"):
        return {}
    return {row.name: row.branch for row in frappe.get_list("Employee", filters={"name": ["in", employees]},
                                                             fields=["name", "branch"], limit_page_length=0)}


def _currency():
    """The currency of the user's company."""
    company = frappe.defaults.get_user_default("Company")
    return frappe.get_cached_value("Company", company, "default_currency") if company else ""


# ── Workforce Movement ────────────────────────────────────────────────
def _movement(today, money, roles):
    """Joiners and leavers by month, the year's leavers, and the headcount by status."""
    from hrms_addon.hrms_addon import employee_status

    if not _may("Employee"):
        return None
    people = frappe.get_list("Employee", fields=["name", "status", "custom_employee_status", "date_of_joining",
                                                 "relieving_date", "creation"], limit_page_length=0)
    out = rules.movement(people, home._or({}, employee_status.counts), today)
    return dict(out, kind="movement", note=rules.movement_note(out))


# ── Deadlines ─────────────────────────────────────────────────────────
def _deadlines(today, money, roles):
    """What comes due, from each of the processes that set a date."""
    found = []
    for read in (_probations, _contracts, _clearances, _settlements, _suspensions, _documents):
        found += home._or([], read, today)
    listed = rules.deadlines(found, today)
    return {"kind": "list", "rows": listed["rows"], "note": listed["note"]}


def _probations(today):
    if not _may("Employee"):
        return []
    start, end = rules.window(today, rules.PROBATION_AHEAD)
    return [{"kind": "probation", "day": row.custom_probation_end_date, "who": row.employee_name or row.name,
             "doctype": "Employee", "docname": row.name}
            for row in frappe.get_list("Employee", filters={
                "status": "Active", "custom_probation_end_date": ["between", [start, end]]},
                fields=["name", "employee_name", "custom_probation_end_date", "custom_probation_status"],
                limit_page_length=0) if rules.probation_open(row)]


def _contracts(today):
    if not _may("Employee Contract"):
        return []
    start, end = rules.window(today, rules.CONTRACT_AHEAD)
    return [{"kind": "contract", "day": row.end_date, "who": row.employee_name or row.employee,
             "doctype": "Employee Contract", "docname": row.name}
            for row in frappe.get_list("Employee Contract", filters={
                "docstatus": 1, "status": ["in", list(rules.CONTRACT_UNDECIDED)], "end_date": ["between", [start, end]]},
                fields=["name", "employee", "employee_name", "end_date"], limit_page_length=0)]


def _clearances(today):
    if not _may("Employee Separation"):
        return []
    start, end = rules.window(today, rules.CLEARANCE_AHEAD)
    exits = frappe.get_list("Employee Separation", filters={
        "docstatus": 1, "custom_relieving_date": ["between", [start, end]]},
        fields=["name", "employee", "employee_name", "custom_relieving_date", "custom_clearance"], limit_page_length=0)
    forms = sorted({row.custom_clearance for row in exits if row.custom_clearance})
    cleared = set()
    if forms and _may("Clearance Form"):
        cleared = set(frappe.get_list("Clearance Form", filters={"name": ["in", forms], "docstatus": 1},
                                      pluck="name", limit_page_length=0))
    return [{"kind": "clearance", "day": row.custom_relieving_date, "who": row.employee_name or row.employee,
             "doctype": "Clearance Form" if row.custom_clearance else "Employee Separation",
             "docname": row.custom_clearance or row.name}
            for row in exits if not (row.custom_clearance and row.custom_clearance in cleared)]


def _settlements(today):
    if not _may("Full and Final Statement"):
        return []
    start, end = rules.window(today, rules.SETTLEMENT_AHEAD)
    waiting = frappe.get_list("Full and Final Statement", filters={
        "docstatus": 0, "custom_settlement_status": rules.SETTLEMENT_WAITING},
        fields=["name", "employee", "employee_name", "custom_payroll_date"], limit_page_length=0)
    scheduled = frappe.get_list("Full and Final Statement", filters={
        "docstatus": 1, "status": ["!=", "Paid"], "custom_payroll_date": ["between", [start, end]]},
        fields=["name", "employee", "employee_name", "custom_payroll_date", "custom_additional_salary"],
        limit_page_length=0)
    salaries = sorted({row.custom_additional_salary for row in scheduled if row.custom_additional_salary})
    # paid by a submitted salary slip that took its Additional Salary: Frappe HR marks it Paid only from a bank entry
    taken = set(frappe.get_all("Salary Detail", filters={
        "parenttype": "Salary Slip", "docstatus": 1, "additional_salary": ["in", salaries]},
        pluck="additional_salary", limit_page_length=0)) if salaries else set()
    return [{"kind": "settlement", "day": row.custom_payroll_date or today, "who": row.employee_name or row.employee,
             "doctype": "Full and Final Statement", "docname": row.name}
            for row in waiting + [row for row in scheduled if row.custom_additional_salary not in taken]]


def _suspensions(today):
    if not _may("Employee Suspension"):
        return []
    start, end = rules.window(today, rules.SUSPENSION_AHEAD, back=0)
    return [{"kind": "suspension", "day": row.report_back_on, "who": row.employee_name or row.employee,
             "doctype": "Employee Suspension", "docname": row.name}
            for row in frappe.get_list("Employee Suspension", filters={
                "docstatus": 1, "status": ["in", list(rules.SUSPENSION_RUNNING)],
                "report_back_on": ["between", [start, end]]},
                fields=["name", "employee", "employee_name", "report_back_on"], limit_page_length=0)]


def _documents(today):
    if not _may("Employee") or not frappe.db.exists("DocType", "Employee Document"):
        return []
    start, end = rules.window(today, rules.DOCUMENT_AHEAD, back=rules.DOCUMENT_BACK)
    people = {row.name: row.employee_name or row.name for row in frappe.get_list(
        "Employee", filters={"status": "Active"}, fields=["name", "employee_name"], limit_page_length=0)}
    if not people:
        return []
    return [{"kind": "document", "day": row.expires_on, "who": people.get(row.parent), "what": row.document_type,
             "doctype": "Employee", "docname": row.parent}
            for row in frappe.get_all("Employee Document", filters={
                "parenttype": "Employee", "parent": ["in", sorted(people)], "expires_on": ["between", [start, end]]},
                fields=["parent", "document_type", "expires_on"], limit_page_length=0)]


# ── Recruitment Pipeline ──────────────────────────────────────────────
def _recruitment(today, money, roles):
    """From requisitions to offers, the openings open longest, and this week's interviews."""
    if not _may("Job Opening"):
        return None
    openings = frappe.get_list("Job Opening", filters={"status": "Open"}, fields=["name", "job_title", "posted_on"],
                               limit_page_length=0)
    open_names = [row.name for row in openings] or [""]
    facts = {"openings": openings, "requisitions": 0, "applicants": 0, "shortlisted": 0, "interviewed": 0,
             "offered": 0, "filled": [], "interviews": []}
    if _may("Job Requisition"):
        facts["requisitions"] = len(frappe.get_list("Job Requisition", filters={"status": "Pending"}, pluck="name",
                                                    limit_page_length=0))
        since = add_days(today, -rules.FILLED_WITHIN)
        facts["filled"] = [rules.days_to_fill(row.posting_date, row.completed_on) for row in frappe.get_list(
            "Job Requisition", filters={"status": "Filled", "completed_on": [">=", since]},
            fields=["posting_date", "completed_on"], limit_page_length=0)]
    names = {}
    if _may("Job Applicant"):
        applicants = frappe.get_list("Job Applicant", filters={"job_title": ["in", open_names]},
                                     fields=["name", "status"], limit_page_length=0)
        facts["applicants"] = sum(1 for row in applicants if row.status in rules.APPLYING)
        facts["shortlisted"] = sum(1 for row in applicants if row.status == rules.SHORTLISTED)
    if _may("Interview"):
        facts["interviewed"] = len(frappe.get_list("Interview", filters={
            "job_opening": ["in", open_names], "status": ["in", list(rules.INTERVIEWED)], "docstatus": ["<", 2]},
            pluck="name", limit_page_length=0))
        monday, sunday = rules.week_of(today)
        week = frappe.get_list("Interview", filters={
            "scheduled_on": ["between", [monday, sunday]], "status": ["in", list(rules.INTERVIEW_COMING)],
            "docstatus": ["<", 2]}, fields=["name", "job_applicant", "scheduled_on", "job_opening"], limit_page_length=0)
        if week and _may("Job Applicant"):
            names = {row.name: row.applicant_name for row in frappe.get_list("Job Applicant", filters={
                "name": ["in", sorted({row.job_applicant for row in week if row.job_applicant})]},
                fields=["name", "applicant_name"], limit_page_length=0)}
        facts["interviews"] = [dict(row, applicant_name=names.get(row.job_applicant)) for row in week]
    if _may("Job Offer"):
        facts["offered"] = len(frappe.get_list("Job Offer", filters={"status": rules.OFFER_LIVE, "docstatus": ["<", 2]},
                                               pluck="name", limit_page_length=0))
    return dict(rules.pipeline(facts, today), kind="pipeline", note=rules.pipeline_note(facts))


# ── Data Health ───────────────────────────────────────────────────────
def _data_health(today, money, roles):
    """What the active employees' records are missing for payroll and the clock."""
    if not _may("Employee"):
        return None
    bank_known = bool(set(roles or ()) & set(rules.BANK_ROLES))
    fields = ["name", "employee_name", "attendance_device_id", "custom_automatic_attendance", "custom_nssf_no",
              "custom_tin", "custom_nin", "date_of_birth", "date_of_joining"]
    if bank_known:
        fields += ["salary_mode", "bank_ac_no"]
    people = frappe.get_list("Employee", filters={"status": "Active"}, fields=fields, limit_page_length=0)
    assigned = None
    if _may("Salary Structure Assignment"):
        assigned = set(frappe.get_list("Salary Structure Assignment", filters={
            "docstatus": 1, "from_date": ["<=", today]}, pluck="employee", limit_page_length=0))
    rows = rules.data_health(people, assigned, today, bank_known)
    return {"kind": "health", "rows": rows, "note": "%s active records" % format(len(people), ",")}


READERS = {rules.PAYROLL: _payroll, rules.PLANTS: _plants, rules.OUTPUT: _output, rules.MOVEMENT: _movement,
           rules.DEADLINES: _deadlines, rules.RECRUITMENT: _recruitment, rules.DATA_HEALTH: _data_health}
