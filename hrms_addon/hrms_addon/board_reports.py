# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The board pack's drill-down reports: what each figure of the Board
Dashboard and the deck is made of, record by record or cut by cut.

  Board Head Count        opening, hires, exits, transfers, conversions and
                          closing by plant, department, section, gender, age,
                          tenure or population (a GROUP BY over HR Employee
                          Month)
  Board Leavers           each exit with its reason, type and years of service
  Board Hires             each hire with what it was for and its requisition
  Board Incidents         each incident with its severity, hazard and days lost
  Board Pay by Component  the wage bill by component, population, plant or
                          section against a year before (a GROUP BY over HR
                          Pay Fact)
  Board Data Quality      the records that keep the figures from adding up

The lists read through the user's permissions; the cuts are counts and sums,
held to the plants a user is held to.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate

from hrms_addon.hrms_addon import board_facts, board_facts_rules as rules

CUT_OF = {label: field for field, label in rules.CUTS.items()}
PAY_CUTS = {"Component Group": "component_group", "Salary Component": "salary_component", "Population": "population",
            "Plant": "branch", "Section": "work_section"}


def _filters(filters):
    filters = frappe._dict(filters or {})
    if not filters.get("company"):
        filters.company = frappe.defaults.get_user_default("Company")
    filters.from_date = getdate(filters.get("from_date") or rules.month_start(getdate()))
    filters.to_date = getdate(filters.get("to_date") or rules.month_end(getdate()))
    held = frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Branch"},
                          pluck="for_value")
    if held:
        if filters.get("branch") and filters.branch not in held:
            frappe.throw(_("You are not permitted to see {0}.").format(filters.branch), frappe.PermissionError)
        filters.branches = held
    return filters


def _plants_sql(filters, column="`branch`"):
    if filters.get("branch"):
        return " AND %s = %%(branch)s" % column
    if filters.get("branches"):
        return " AND %s IN %%(branches)s" % column
    return ""


# ── Board Head Count ──────────────────────────────────────────────────
def head_count(filters):
    filters = _filters(filters)
    by = CUT_OF.get(filters.get("group_by") or "Plant", "branch")
    rows = board_facts.cut_figures(filters.company, filters.from_date, filters.to_date, by,
                                   branch=filters.get("branch"), population=filters.get("population"),
                                   branches=filters.get("branches"))
    data = []
    for row in rows:
        average = (row["opening"] + row["closing"]) / 2.0
        data.append(dict(row, cut=row["cut"] or (rules.NO_PLANT if by == "branch" else _("Not Set")),
                         change=row["closing"] - row["opening"],
                         turnover=round(100.0 * row["exits"] / average, 1) if average else None,
                         training_per_head=round(row["training_hours"] / row["closing"], 2) if row["closing"] else None,
                         absence_rate=round(100.0 * row["days_absent"] / row["attendance_days"], 1)
                         if row["attendance_days"] else None))
    columns = [
        {"fieldname": "cut", "label": _(filters.get("group_by") or "Plant"), "fieldtype": "Data", "width": 180},
        {"fieldname": "opening", "label": _("Opening"), "fieldtype": "Int", "width": 90},
        {"fieldname": "hires", "label": _("Hires"), "fieldtype": "Int", "width": 80},
        {"fieldname": "exits", "label": _("Exits"), "fieldtype": "Int", "width": 80},
        {"fieldname": "transferred", "label": _("Transferred"), "fieldtype": "Int", "width": 100},
        {"fieldname": "converted", "label": _("Converted"), "fieldtype": "Int", "width": 95},
        {"fieldname": "closing", "label": _("Closing"), "fieldtype": "Int", "width": 90},
        {"fieldname": "change", "label": _("Change"), "fieldtype": "Int", "width": 85},
        {"fieldname": "turnover", "label": _("Turnover %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "regrettable", "label": _("Regrettable"), "fieldtype": "Int", "width": 100},
        {"fieldname": "training_per_head", "label": _("Training Hours per Head"), "fieldtype": "Float", "width": 160},
        {"fieldname": "absence_rate", "label": _("Absence %"), "fieldtype": "Percent", "width": 95},
    ]
    chart = {"data": {"labels": [row["cut"] for row in data[:12]],
                      "datasets": [{"name": _("Closing"), "values": [row["closing"] for row in data[:12]]}]},
             "type": "bar"} if data else None
    return columns, data, None, chart


# ── Board Leavers and Board Hires ─────────────────────────────────────
def _movements(filters, kind, extra=None):
    conditions = {"company": filters.company, "movement_type": kind,
                  "effective_date": ["between", [filters.from_date, filters.to_date]]}
    if filters.get("branch"):
        conditions["branch"] = filters.branch
    for field in ("population", "exit_type", "hire_reason"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    if cint(filters.get("regrettable")):
        conditions["regrettable"] = 1
    conditions.update(extra or {})
    return frappe.get_list("HR Movement", filters=conditions, limit_page_length=0, order_by="effective_date asc",
                           fields=["employee", "employee_name", "effective_date", "branch", "department",
                                   "designation", "population", "exit_reason", "exit_type", "regrettable",
                                   "tenure_years", "tenure_band", "hire_reason", "job_requisition", "heads"])


def leavers(filters):
    filters = _filters(filters)
    data = _movements(filters, rules.EXIT)
    columns = [
        {"fieldname": "effective_date", "label": _("Last Day"), "fieldtype": "Date", "width": 100},
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 150},
        {"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link", "options": "Designation",
         "width": 150},
        {"fieldname": "population", "label": _("Population"), "fieldtype": "Data", "width": 100},
        {"fieldname": "exit_reason", "label": _("Reason"), "fieldtype": "Data", "width": 130},
        {"fieldname": "exit_type", "label": _("Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "regrettable", "label": _("Regrettable"), "fieldtype": "Check", "width": 95},
        {"fieldname": "tenure_years", "label": _("Years of Service"), "fieldtype": "Float", "width": 120},
        {"fieldname": "tenure_band", "label": _("Tenure Band"), "fieldtype": "Data", "width": 110},
    ]
    heads = sum(cint(row.heads) or 1 for row in data)
    voluntary = sum(cint(row.heads) or 1 for row in data if row.exit_type == rules.VOLUNTARY)
    served = [flt(row.tenure_years) for row in data if row.tenure_years]
    summary = [
        {"value": heads, "label": _("Leavers"), "datatype": "Int", "indicator": "Blue"},
        {"value": round(100.0 * voluntary / heads, 1) if heads else 0, "label": _("Voluntary %"),
         "datatype": "Percent", "indicator": "Orange"},
        {"value": sum(1 for row in data if row.regrettable), "label": _("Regrettable"), "datatype": "Int",
         "indicator": "Red"},
        {"value": round(sum(served) / len(served), 1) if served else 0, "label": _("Average Years of Service"),
         "datatype": "Float", "indicator": "Grey"},
    ]
    reasons = {}
    for row in data:
        reasons[row.exit_reason or _("Not Given")] = reasons.get(row.exit_reason or _("Not Given"), 0) + (cint(row.heads) or 1)
    chart = {"data": {"labels": list(reasons), "datasets": [{"name": _("Leavers"), "values": list(reasons.values())}]},
             "type": "bar"} if reasons else None
    return columns, data, None, chart, summary


def hires(filters):
    filters = _filters(filters)
    data = _movements(filters, rules.HIRE)
    columns = [
        {"fieldname": "effective_date", "label": _("Joined"), "fieldtype": "Date", "width": 100},
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 150},
        {"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link", "options": "Designation",
         "width": 150},
        {"fieldname": "population", "label": _("Population"), "fieldtype": "Data", "width": 100},
        {"fieldname": "hire_reason", "label": _("Hire Reason"), "fieldtype": "Data", "width": 120},
        {"fieldname": "job_requisition", "label": _("Job Requisition"), "fieldtype": "Link",
         "options": "Job Requisition", "width": 150},
    ]
    counts = {reason: sum(cint(row.heads) or 1 for row in data if (row.hire_reason or rules.UNCLASSIFIED) == reason)
              for reason in rules.HIRE_REASONS}
    summary = [{"value": sum(counts.values()), "label": _("Hires"), "datatype": "Int", "indicator": "Blue"}] + [
        {"value": counts[reason], "label": _(reason), "datatype": "Int",
         "indicator": "Grey" if reason == rules.UNCLASSIFIED else "Green"} for reason in rules.HIRE_REASONS]
    return columns, data, None, None, summary


# ── Board Incidents ───────────────────────────────────────────────────
def incidents(filters):
    filters = _filters(filters)
    if frappe.has_permission("Safety Incident", "read"):
        conditions = {"company": filters.company, "docstatus": ["<", 2],
                      "incident_on": ["between", ["%s 00:00:00" % filters.from_date, "%s 23:59:59" % filters.to_date]]}
        if filters.get("branch"):
            conditions["branch"] = filters.branch
        if filters.get("severity"):
            conditions["severity"] = filters.severity
        data = frappe.get_list("Safety Incident", filters=conditions, limit_page_length=0, order_by="incident_on asc",
                               fields=["name", "incident_on", "employee", "employee_name", "branch", "department",
                                       "severity", "hazard", "off_site", "sick_days", "capa_status", "capa_due"])
        columns = [
            {"fieldname": "name", "label": _("Incident"), "fieldtype": "Link", "options": "Safety Incident",
             "width": 150},
            {"fieldname": "incident_on", "label": _("When"), "fieldtype": "Datetime", "width": 150},
            {"fieldname": "employee_name", "label": _("Employee"), "fieldtype": "Data", "width": 160},
            {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
            {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
             "width": 140},
            {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 130},
            {"fieldname": "hazard", "label": _("Hazard"), "fieldtype": "Data", "width": 160},
            {"fieldname": "off_site", "label": _("Off Site"), "fieldtype": "Check", "width": 80},
            {"fieldname": "sick_days", "label": _("Sick Days"), "fieldtype": "Int", "width": 90},
            {"fieldname": "capa_status", "label": _("Corrective Action"), "fieldtype": "Data", "width": 130},
            {"fieldname": "capa_due", "label": _("Action Due"), "fieldtype": "Date", "width": 100},
        ]
        counted = [row for row in data if row.severity != rules.NEAR_MISS]
        summary = [{"value": len(counted), "label": _("Incidents"), "datatype": "Int", "indicator": "Red"},
                   {"value": len(data) - len(counted), "label": _("Near Misses"), "datatype": "Int",
                    "indicator": "Orange"},
                   {"value": sum(1 for row in data if row.severity in rules.LOST_TIME_SEVERITIES),
                    "label": _("Lost Time"), "datatype": "Int", "indicator": "Red"}]
        return columns, data, None, None, summary
    # those who may not open the incidents see them counted
    values = {"company": filters.company, "first": rules.month_start(filters.from_date),
              "last": rules.month_start(filters.to_date), "branch": filters.get("branch"),
              "branches": tuple(filters.get("branches") or ()), "severity": filters.get("severity")}
    data = frappe.db.sql(
        """SELECT `branch`, `department`, `severity`, `hazard`, `off_site`, SUM(`incidents`) AS incidents,
            SUM(`days_lost`) AS days_lost
        FROM `tabHR Safety Fact`
        WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s{plants}{severity}
        GROUP BY `branch`, `department`, `severity`, `hazard`, `off_site`""".format(
            plants=_plants_sql(filters), severity=" AND `severity` = %(severity)s" if filters.get("severity") else ""),
        values, as_dict=True)
    columns = [
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 150},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 130},
        {"fieldname": "hazard", "label": _("Hazard"), "fieldtype": "Data", "width": 160},
        {"fieldname": "off_site", "label": _("Off Site"), "fieldtype": "Check", "width": 80},
        {"fieldname": "incidents", "label": _("Incidents"), "fieldtype": "Int", "width": 90},
        {"fieldname": "days_lost", "label": _("Days Lost"), "fieldtype": "Float", "width": 90},
    ]
    return columns, data


# ── Board Pay by Component ────────────────────────────────────────────
def pay(filters):
    filters = _filters(filters)
    by = PAY_CUTS.get(filters.get("group_by") or "Component Group", "component_group")
    first, last = rules.month_start(filters.from_date), rules.month_start(filters.to_date)
    values = {"company": filters.company, "branch": filters.get("branch"),
              "branches": tuple(filters.get("branches") or ()), "population": filters.get("population")}
    extra = _plants_sql(filters) + (" AND `population` = %(population)s" if filters.get("population") else "")

    def totals(start, end):
        return {row.cut: row for row in frappe.db.sql(
            """SELECT COALESCE(`{by}`, '') AS cut, SUM(`amount`) AS amount, SUM(`heads`) AS heads
            FROM `tabHR Pay Fact`
            WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s{extra}
            GROUP BY COALESCE(`{by}`, '')""".format(by=by, extra=extra),
            dict(values, first=start, last=end), as_dict=True)}

    now = totals(first, last)
    before = totals(rules.month_start(add_months(first, -12)), rules.month_start(add_months(last, -12)))
    whole = sum(flt(row.amount) for row in now.values())
    data = []
    for cut in sorted(set(now) | set(before), key=lambda key: -flt((now.get(key) or {}).get("amount"))):
        amount, old = flt((now.get(cut) or {}).get("amount")), flt((before.get(cut) or {}).get("amount"))
        data.append({"cut": cut or (_("Gross over earnings") if by == "salary_component" else rules.NO_PLANT
                                    if by == "branch" else _("Not Set")),
                     "amount": amount, "share": round(100.0 * amount / whole, 1) if whole else None,
                     "heads": cint((now.get(cut) or {}).get("heads")), "last_year": old or None,
                     "change": round(100.0 * (amount - old) / old, 1) if old else None})
    columns = [
        {"fieldname": "cut", "label": _(filters.get("group_by") or "Component Group"), "fieldtype": "Data",
         "width": 200},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "share", "label": _("Share %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "heads", "label": _("Heads Paid"), "fieldtype": "Int", "width": 100},
        {"fieldname": "last_year", "label": _("A Year Before"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "change", "label": _("Change %"), "fieldtype": "Percent", "width": 95},
    ]
    return columns, data


# ── Board Data Quality ────────────────────────────────────────────────
CHECK_LABELS = dict(rules.DATA_CHECKS)


def data_quality(filters):
    filters = _filters(filters)
    wanted = [filters.check] if filters.get("check") in CHECK_LABELS else list(CHECK_LABELS)
    data = []
    if "blank_branch" in wanted:
        for row in frappe.get_list("Employee", filters={"company": filters.company, "status": "Active",
                                                        "branch": ["is", "not set"]},
                                   fields=["name", "employee_name", "department", "date_of_joining"],
                                   limit_page_length=0):
            data.append({"check": CHECK_LABELS["blank_branch"], "document_type": "Employee", "document": row.name,
                         "title": row.employee_name, "detail": row.department, "date": row.date_of_joining})
    if "left_without_date" in wanted:
        for row in frappe.get_list("Employee", filters={"company": filters.company, "status": "Left",
                                                        "relieving_date": ["is", "not set"]},
                                   fields=["name", "employee_name", "branch", "department"], limit_page_length=0):
            data.append({"check": CHECK_LABELS["left_without_date"], "document_type": "Employee", "document": row.name,
                         "title": row.employee_name, "detail": row.branch or row.department, "date": None})
    if "hires_without_requisition" in wanted:
        for row in frappe.get_list("HR Movement", filters={
                "company": filters.company, "movement_type": rules.HIRE, "employee": ["is", "set"],
                "effective_date": ["between", [filters.from_date, filters.to_date]],
                "hire_reason": ["in", ["", rules.UNCLASSIFIED]]},
                fields=["employee", "employee_name", "branch", "effective_date"], limit_page_length=0):
            data.append({"check": CHECK_LABELS["hires_without_requisition"], "document_type": "Employee",
                         "document": row.employee, "title": row.employee_name, "detail": row.branch,
                         "date": row.effective_date})
    if "slips_without_branch" in wanted:
        for row in frappe.get_list("Salary Slip", filters={"company": filters.company, "docstatus": 1,
                                                           "end_date": ["between", [filters.from_date, filters.to_date]],
                                                           "branch": ["is", "not set"]},
                                   fields=["name", "employee_name", "department", "end_date"], limit_page_length=0):
            data.append({"check": CHECK_LABELS["slips_without_branch"], "document_type": "Salary Slip",
                         "document": row.name, "title": row.employee_name, "detail": row.department,
                         "date": row.end_date})
    columns = [
        {"fieldname": "check", "label": _("Check"), "fieldtype": "Data", "width": 230},
        {"fieldname": "document_type", "label": _("Document Type"), "fieldtype": "Link", "options": "DocType",
         "width": 120},
        {"fieldname": "document", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "document_type",
         "width": 170},
        {"fieldname": "title", "label": _("Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "detail", "label": _("Plant or Department"), "fieldtype": "Data", "width": 160},
        {"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
    ]
    return columns, data
