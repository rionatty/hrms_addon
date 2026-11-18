# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence rebuild (18 Nov 2026): one section everywhere.
The live documents keep the section text they always had; beside it, their
Work Section is filled in.

  Disciplinary Case   its case type (Disciplinary unless set) and the
                      employee's employment, Permanent or Casual
  Overtime Request    the section named, else the one most of its people are
                      in; each line the employee's section
  Daily Production Report
                      the supervisor's section
  Employee Grievance  the section of who raised it
"""

import frappe

EMPLOYEE_SECTION = "custom_work_section"


def execute():
    sections = {row.name: row for row in frappe.get_all(
        "Employee", fields=["name", EMPLOYEE_SECTION, "employment_type"], limit_page_length=0)} \
        if frappe.db.has_column("Employee", EMPLOYEE_SECTION) else {}
    _cases(sections)
    _overtime(sections)
    _production(sections)
    _grievances(sections)


def _section(sections, employee):
    row = sections.get(employee)
    return row.get(EMPLOYEE_SECTION) if row else None


def _cases(sections):
    if not frappe.db.has_column("Disciplinary Case", "case_type"):
        return
    for row in frappe.get_all("Disciplinary Case", fields=["name", "employee", "case_type", "employment",
                                                           "work_section"], limit_page_length=0):
        values = {}
        if not row.case_type:
            values["case_type"] = "Disciplinary"
        person = sections.get(row.employee)
        if person and not row.employment:
            values["employment"] = "Casual" if "casual" in (person.employment_type or "").lower() else "Permanent"
        if person and not row.work_section and person.get(EMPLOYEE_SECTION):
            values["work_section"] = person.get(EMPLOYEE_SECTION)
        if values:
            frappe.db.set_value("Disciplinary Case", row.name, values, update_modified=False)
    frappe.db.commit()


def _overtime(sections):
    if not frappe.db.has_column("Overtime Request", "work_section"):
        return
    named = {}
    for row in frappe.get_all("Work Section", fields=["name", "section_name", "branch"], limit_page_length=0):
        named[((row.section_name or "").strip().lower(), row.branch)] = row.name
    lines = {}
    for line in frappe.get_all("Overtime Request Employee", filters={"parenttype": "Overtime Request"},
                               fields=["name", "parent", "employee", "work_section"], limit_page_length=0):
        lines.setdefault(line.parent, []).append(line)
        if not line.work_section and _section(sections, line.employee):
            frappe.db.set_value("Overtime Request Employee", line.name, "work_section",
                                _section(sections, line.employee), update_modified=False)
            line.work_section = _section(sections, line.employee)
    for row in frappe.get_all("Overtime Request", filters={"work_section": ["is", "not set"]},
                              fields=["name", "section", "branch"], limit_page_length=0):
        found = named.get(((row.section or "").strip().lower(), row.branch))
        if not found:
            counts = {}
            for line in lines.get(row.name, []):
                if line.work_section:
                    counts[line.work_section] = counts.get(line.work_section, 0) + 1
            found = max(sorted(counts), key=lambda name: counts[name]) if counts else None
        if found:
            frappe.db.set_value("Overtime Request", row.name, "work_section", found, update_modified=False)
    frappe.db.commit()


def _production(sections):
    if not frappe.db.has_column("Daily Production Report", "work_section"):
        return
    for row in frappe.get_all("Daily Production Report", filters={"work_section": ["is", "not set"],
                                                                  "supervisor": ["is", "set"]},
                              fields=["name", "supervisor"], limit_page_length=0):
        section = _section(sections, row.supervisor)
        if section:
            frappe.db.set_value("Daily Production Report", row.name, "work_section", section, update_modified=False)
    frappe.db.commit()


def _grievances(sections):
    if not frappe.db.has_column("Employee Grievance", "custom_work_section"):
        return
    for row in frappe.get_all("Employee Grievance", filters={"custom_work_section": ["is", "not set"]},
                              fields=["name", "raised_by"], limit_page_length=0):
        section = _section(sections, row.raised_by)
        if section:
            frappe.db.set_value("Employee Grievance", row.name, "custom_work_section", section,
                                update_modified=False)
    frappe.db.commit()
