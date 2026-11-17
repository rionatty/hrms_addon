# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack on the site (Luuka's quarterly HR Board Report). The
rules are in board_pack_rules.py (scripts/verify_board_pack.py); the deck and
the workbook are made by board_deck.py.

  Board Report Settings   the monthly attrition target and the wage bill's
                          component groups, seeded from the components' names
  Board Finance Figures   a quarter's revenue, output and staff cost by plant
                          and month, typed by Finance (decided 17 Nov 2026)
  HR Monthly Snapshot     a month's figures by plant: built from the site on
                          the 1st for the month just ended, rebuilt on demand
                          until locked, or imported for the months before the
                          system, which the board compares with
  HR Board Report         the quarter's figures from three months' snapshots,
                          the month before and the same quarter a year before;
                          HR's own words beside them; the deck and the
                          workbook made from both
"""

import datetime
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now, today

from hrms_addon.hrms_addon import board_pack_rules as rules

SETTINGS = "Board Report Settings"
FINANCE = "Board Finance Figures"
FINANCE_LINE = "Board Finance Line"
SNAPSHOT = "HR Monthly Snapshot"
REPORT = "HR Board Report"
FIELDS = rules.COUNTS + rules.AMOUNTS


# ── Settings ──────────────────────────────────────────────────────────
def settings():
    try:
        stored = frappe.get_cached_doc(SETTINGS)
    except Exception:
        return {"target": 5.0, "groups": {}}
    return {"target": flt(stored.get("attrition_target")) or 5.0,
            "groups": {row.salary_component: row.component_group for row in stored.get("component_groups") or []}}


def settings_validate(doc):
    seen = set()
    for row in doc.get("component_groups") or []:
        if row.salary_component in seen:
            frappe.throw(_("{0} is listed twice.").format(row.salary_component), title=_(SETTINGS))
        seen.add(row.salary_component)


def setup_on_migrate():
    """The earnings' groups from their names, once; then HR's."""
    try:
        doc = frappe.get_single(SETTINGS)
        if doc.get("component_groups"):
            return
        for name in frappe.get_all("Salary Component", filters={"type": "Earning"}, pluck="name", order_by="name asc"):
            group = rules.component_group(name)
            if group != "Other":
                doc.append("component_groups", {"salary_component": name, "component_group": group})
        if not doc.get("attrition_target"):
            doc.attrition_target = 5
        doc.flags.ignore_permissions = True
        doc.save()
    except Exception:
        frappe.log_error(title="HRMS Addon: setting up the board pack")


# ── What Finance type ─────────────────────────────────────────────────
def finance_autoname(doc):
    doc.name = "%s %s %s" % (doc.year, doc.quarter, doc.company)


def finance_validate(doc):
    months = {datetime.date(year, month, 1) for year, month in rules.quarter_months(doc.year, doc.quarter)}
    seen = set()
    for row in doc.get("lines") or []:
        row.month_start = getdate(row.month_start).replace(day=1) if row.month_start else None
        if row.month_start not in months:
            frappe.throw(_("Row {0}: {1} is not a month of {2} {3}.").format(
                row.idx, frappe.utils.format_date(row.month_start), doc.quarter, doc.year), title=_(FINANCE))
        if (row.branch, row.month_start) in seen:
            frappe.throw(_("Row {0}: {1} is in twice for that month.").format(row.idx, row.branch), title=_(FINANCE))
        seen.add((row.branch, row.month_start))


@frappe.whitelist(methods=["POST"])
def add_finance_lines(name):
    """A line for each plant with people, for each month of the quarter.
    Returns how many were added."""
    doc = frappe.get_doc(FINANCE, name)
    doc.check_permission("write")
    have = {(row.branch, getdate(row.month_start)) for row in doc.get("lines") or []}
    added = 0
    for plant in _plants(doc.company):
        for year, month in rules.quarter_months(doc.year, doc.quarter):
            first = datetime.date(year, month, 1)
            if (plant, first) not in have:
                doc.append("lines", {"branch": plant, "month_start": first})
                added += 1
    doc.save()
    return added


def _plants(company):
    return sorted(plant for plant in frappe.get_all(
        "Employee", filters={"company": company, "status": "Active", "branch": ["is", "set"]}, pluck="branch",
        distinct=True) if plant)


# ── A month's snapshot ────────────────────────────────────────────────
def snapshot_autoname(doc):
    first = getdate(doc.month_start).replace(day=1)
    doc.name = "%s %s" % (doc.company, first.strftime("%Y-%m"))


def snapshot_validate(doc):
    doc.month_start = getdate(doc.month_start).replace(day=1)
    if doc.is_new() and doc.get("source") != "Imported" and not doc.get("plants"):
        _fill(doc)
    _total(doc)


def _fill(doc):
    figures = build_snapshot(doc.company, doc.month_start)
    doc.set("plants", [dict(figures[plant], branch=plant or None) for plant in sorted(figures)])
    doc.built_on = now()


def _total(doc):
    rows = doc.get("plants") or []
    doc.total_closing = sum(cint(row.closing) for row in rows)
    doc.total_hires = sum(cint(row.hires) for row in rows)
    doc.total_exits = sum(cint(row.exits) for row in rows)
    doc.total_wage_bill = sum(flt(row.wage_bill) for row in rows)


@frappe.whitelist(methods=["POST"])
def rebuild_snapshot(name):
    """The month built from the site again, unless it is locked or imported."""
    doc = frappe.get_doc(SNAPSHOT, name)
    doc.check_permission("write")
    if cint(doc.locked) or doc.get("source") == "Imported":
        frappe.throw(_("{0} is locked or imported: it stands as it is.").format(doc.name), title=_(SNAPSHOT))
    _fill(doc)
    doc.save()
    return doc.total_closing


def monthly():
    """On the 1st: the month just ended, for each company with people."""
    first = getdate(today()).replace(day=1)
    month = (first - datetime.timedelta(days=1)).replace(day=1)
    for company in frappe.get_all("Employee", filters={"status": "Active"}, pluck="company", distinct=True):
        if not company:
            continue
        try:
            take_snapshot(company, month)
        except Exception:
            frappe.log_error(title="HRMS Addon: the month's HR snapshot")
    frappe.db.commit()


def take_snapshot(company, month):
    """The month's snapshot made, or built again where it may be."""
    name = frappe.db.get_value(SNAPSHOT, {"company": company, "month_start": getdate(month).replace(day=1)}, "name")
    if not name:
        doc = frappe.get_doc({"doctype": SNAPSHOT, "company": company, "month_start": month, "source": "System"})
        doc.flags.ignore_permissions = True
        doc.insert()
        return doc.name
    doc = frappe.get_doc(SNAPSHOT, name)
    if not cint(doc.locked) and doc.get("source") != "Imported":
        _fill(doc)
        doc.flags.ignore_permissions = True
        doc.save()
    return name


def build_snapshot(company, month):
    """{plant: figures} for the month, from the site."""
    first, last = rules.month_bounds(getdate(month).year, getdate(month).month)
    return rules.snapshot(_people(company, first, last), _slips(company, first, last), _incidents(company, first, last),
                          _finance(company, first), first, last, settings()["groups"])


def _people(company, first, last):
    meta = frappe.get_meta("Employee")
    fields = ["name", "branch", "gender", "date_of_joining", "relieving_date"]
    fields += [field for field in ("custom_pay_category", "job_applicant") if meta.has_field(field)]
    people = [row for row in frappe.get_all("Employee", filters={"company": company, "date_of_joining": ["<=", last]},
                                            fields=fields, limit_page_length=0)
              if not row.relieving_date or getdate(row.relieving_date) >= add_days(first, -1)]
    leavers = [row.name for row in people if row.relieving_date and first <= getdate(row.relieving_date) <= last]
    regrettable = set()
    if leavers and frappe.get_meta("Employee Separation").has_field("custom_regrettable"):
        regrettable = set(frappe.get_all("Employee Separation", filters={"docstatus": ["!=", 2], "custom_regrettable": 1,
                                                                          "employee": ["in", leavers]}, pluck="employee"))
    reasons = _hire_reasons([row for row in people if row.date_of_joining
                             and first <= getdate(row.date_of_joining) <= last and row.get("job_applicant")])
    return [{"name": row.name, "branch": row.branch, "gender": row.gender, "pay_category": row.get("custom_pay_category"),
             "date_of_joining": row.date_of_joining, "relieving_date": row.relieving_date,
             "regrettable": 1 if row.name in regrettable else 0, "hire_reason": reasons.get(row.name)}
            for row in people]


def _hire_reasons(hires):
    """{employee: the reason of the requisition they were hired against}:
    applicant, then opening, then requisition."""
    if not hires:
        return {}
    openings = dict(frappe.get_all("Job Applicant", filters={"name": ["in", [row.job_applicant for row in hires]]},
                                   fields=["name", "job_title"], as_list=True))
    requisitions = dict(frappe.get_all("Job Opening", filters={"name": ["in", [value for value in openings.values() if value]]},
                                       fields=["name", "job_requisition"], as_list=True)) if openings else {}
    meta = frappe.get_meta("Job Requisition")
    reasons = dict(frappe.get_all("Job Requisition", filters={"name": ["in", [value for value in requisitions.values()
                                                                               if value]]},
                                  fields=["name", "custom_reason_type"], as_list=True)) \
        if requisitions and meta.has_field("custom_reason_type") else {}
    return {row.name: reasons.get(requisitions.get(openings.get(row.job_applicant))) for row in hires}


def _slips(company, first, last):
    """The month's submitted slips: gross in the company's currency, and the
    earnings that count, by component."""
    currency = frappe.get_cached_value("Company", company, "default_currency")
    slips = frappe.get_all("Salary Slip", filters={"company": company, "docstatus": 1,
                                                   "end_date": ["between", [first, last]]},
                           fields=["name", "employee", "branch", "base_gross_pay", "gross_pay", "currency",
                                   "exchange_rate"], limit_page_length=0)
    if not slips:
        return []
    rate = {slip.name: flt(slip.exchange_rate) or 1.0 for slip in slips}
    parts = {}
    for start in range(0, len(slips), 500):
        names = [slip.name for slip in slips[start:start + 500]]
        for row in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Slip", "parentfield": "earnings",
                                                             "parent": ["in", names], "statistical_component": 0,
                                                             "do_not_include_in_total": 0},
                                  fields=["parent", "salary_component", "amount"], limit_page_length=0):
            mine = parts.setdefault(row.parent, {})
            mine[row.salary_component] = mine.get(row.salary_component, 0.0) + flt(row.amount) * rate[row.parent]
    return [{"branch": slip.branch, "employee": slip.employee,
             "gross": flt(slip.base_gross_pay) or flt(slip.gross_pay) * rate[slip.name],
             "foreign": bool(slip.currency and currency and slip.currency != currency),
             "components": parts.get(slip.name, {})} for slip in slips]


def _incidents(company, first, last):
    meta = frappe.get_meta("Safety Incident")
    fields = ["branch"] + (["severity"] if meta.has_field("severity") else [])
    return frappe.get_all("Safety Incident", filters={"company": company, "docstatus": ["!=", 2],
                                                      "incident_on": ["between", ["%s 00:00:00" % first,
                                                                                  "%s 23:59:59" % last]]},
                          fields=fields, limit_page_length=0)


def _finance(company, first):
    docs = frappe.get_all(FINANCE, filters={"company": company}, pluck="name")
    out = {}
    if docs:
        for row in frappe.get_all(FINANCE_LINE, filters={"parenttype": FINANCE, "parent": ["in", docs],
                                                         "month_start": first},
                                  fields=["branch", "revenue", "output_kg", "staff_cost"], limit_page_length=0):
            mine = out.setdefault(row.branch, {"revenue": 0.0, "output_kg": 0.0, "staff_cost": 0.0})
            for field in ("revenue", "output_kg", "staff_cost"):
                mine[field] += flt(row.get(field))
    return out


# ── The quarter's report ──────────────────────────────────────────────
def report_validate(doc):
    if not doc.get("title"):
        doc.title = _("HR Board Report {0}").format(rules.label(doc.year, doc.quarter))
    if doc.is_new():
        if not doc.get("ratings"):
            doc.set("ratings", rules.default_ratings())
        if not doc.get("metrics"):
            doc.set("metrics", rules.default_metrics())
    doc.status = {0: "Draft", 1: "Approved", 2: "Cancelled"}[cint(doc.docstatus)]


def report_on_submit(doc):
    doc.db_set("status", "Approved", update_modified=False)


def report_on_cancel(doc):
    doc.db_set("status", "Cancelled", update_modified=False)


def _snapshot(company, year, month):
    name = frappe.db.get_value(SNAPSHOT, {"company": company, "month_start": datetime.date(year, month, 1)}, "name")
    if not name:
        return None
    return {row.branch or "": {field: row.get(field) for field in FIELDS}
            for row in frappe.get_all("HR Snapshot Plant", filters={"parenttype": SNAPSHOT, "parent": name},
                                      fields=["branch"] + list(FIELDS), limit_page_length=0)}


def quarter_figures(company, year, quarter):
    """The quarter's tables, and what is missing from them."""
    months = rules.quarter_months(year, quarter)
    taken = [_snapshot(company, y, m) for y, m in months]
    missing = [rules.MONTH_NAMES[m - 1] + " " + str(y) for (y, m), snap in zip(months, taken) if snap is None]
    first_year, first_month = months[0]
    before_month = (first_year - 1, 12) if first_month == 1 else (first_year, first_month - 1)
    before = _snapshot(company, *before_month)
    last_year = [_snapshot(company, y - 1, m) for y, m in months]
    last_year = last_year if all(snap is not None for snap in last_year) else []
    prior_year, prior_quarter = rules.quarter_before(year, quarter)
    previous = [_snapshot(company, y, m) for y, m in rules.quarter_months(prior_year, prior_quarter)]
    previous = previous if all(snap is not None for snap in previous) else []
    plants = sorted({plant for snap in taken if snap for plant in snap if plant})
    figures = rules.quarter([snap or {} for snap in taken], before, last_year, plants, settings()["target"], previous)
    end_month = months[-1][1]
    opens, closes = rules.month_bounds(*months[0])[0], rules.month_bounds(*months[-1])[1]
    series = {}
    for year_shown in (int(year) - 1, int(year)):
        series[str(year_shown)] = [round(sum(flt(f.get("overtime")) + flt(f.get("special_overtime"))
                                             for f in (_snapshot(company, year_shown, month) or {}).values()), 2)
                                   for month in range(1, end_month + 1)]
    figures.update({"label": rules.label(year, quarter), "year": int(year), "quarter": quarter,
                    "missing": missing, "before_missing": before is None, "last_year_missing": not last_year,
                    "overtime_series": series, "overtime_months": [rules.MONTH_NAMES[m - 1][:3]
                                                                   for m in range(1, end_month + 1)],
                    "regrettable": _regrettable(company, opens, closes),
                    "training_held": _training_held(company, opens, closes)})
    return figures


def _regrettable(company, first, last):
    """The regrettable losses of the quarter: who, what and where."""
    if not frappe.get_meta("Employee Separation").has_field("custom_regrettable"):
        return []
    leavers = frappe.get_all("Employee Separation", filters={"company": company, "docstatus": ["!=", 2],
                                                             "custom_regrettable": 1},
                             fields=["employee", "employee_name", "designation", "custom_branch"], limit_page_length=0)
    out = []
    for row in leavers:
        relieved = frappe.db.get_value("Employee", row.employee, "relieving_date")
        if relieved and first <= getdate(relieved) <= last:
            out.append({"name": row.employee_name or row.employee, "designation": row.designation,
                        "plant": row.custom_branch})
    return out


def _training_held(company, first, last):
    """The sessions held in the quarter, with how many attended."""
    events = frappe.get_all("Training Event", filters={"company": company, "docstatus": 1,
                                                       "event_status": ["!=", "Cancelled"],
                                                       "start_time": ["between", ["%s 00:00:00" % first,
                                                                                  "%s 23:59:59" % last]]},
                            fields=["name", "event_name", "training_program", "start_time"], order_by="start_time asc",
                            limit_page_length=0)
    out = []
    for event in events:
        present = frappe.db.count("Training Event Employee", {"parenttype": "Training Event", "parent": event.name,
                                                               "attendance": "Present"})
        out.append({"event": event.event_name or event.name, "programme": event.training_program,
                    "day": str(getdate(event.start_time)), "attended": present})
    return out


@frappe.whitelist(methods=["POST"])
def get_figures(name):
    """The quarter's figures taken into the report, and the regrettable
    losses written into its note where HR have written nothing yet."""
    doc = frappe.get_doc(REPORT, name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("The report is approved: its figures stand."), title=_(REPORT))
    figures = quarter_figures(doc.company, doc.year, doc.quarter)
    doc.figures_json = json.dumps(figures, default=str)
    doc.built_on = now()
    if not (doc.get("regrettable_note") or "").strip() and figures["regrettable"]:
        doc.regrettable_note = "; ".join("%s (%s)" % (row["name"], ", ".join(
            value for value in (row.get("designation"), row.get("plant")) if value)) for row in figures["regrettable"])
    doc.save()
    return {"missing": figures["missing"], "last_year_missing": figures["last_year_missing"]}


def figures_of(doc):
    try:
        return json.loads(doc.get("figures_json") or "{}")
    except ValueError:
        return {}


@frappe.whitelist()
def download_deck(name):
    """The board pack as a PowerPoint deck."""
    doc = frappe.get_doc(REPORT, name)
    doc.check_permission("read")
    from hrms_addon.hrms_addon import board_deck

    content = board_deck.deck(doc, figures_of(doc))
    frappe.local.response.filename = "%s.pptx" % (doc.title or doc.name)
    frappe.local.response.filecontent = content
    frappe.local.response.type = "binary"


@frappe.whitelist()
def download_workbook(name):
    """The board pack's tables as an Excel workbook."""
    doc = frappe.get_doc(REPORT, name)
    doc.check_permission("read")
    from hrms_addon.hrms_addon import board_deck

    content = board_deck.workbook(doc, figures_of(doc))
    frappe.local.response.filename = "%s.xlsx" % (doc.title or doc.name)
    frappe.local.response.filecontent = content
    frappe.local.response.type = "binary"
