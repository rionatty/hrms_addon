# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LMS phase 4 on the site; competency_rules.py has the rules.

  Competency Assessment  takes the employee's job title, plant, department
                         and section, the level the skill needs of them, the
                         day it is due again and where they stand. The newest
                         for an employee and a skill is the one that counts;
                         the others are Superseded, and come back if it goes
  daily                  each assessment that counts is brought up to date: a
                         reassessment falling due goes on the supervisor's
                         list once, a certificate run out shows
  coverage_for           what the HR Excellence scorecard reads: the share at
                         the level needed, all skills and critical ones
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import competency_rules as rules

ASSESSMENT, SKILL, CERTIFICATE = "Competency Assessment", "Skill", "Employee Certification"
FIELDS = ["name", "employee", "employee_name", "skill", "level", "required_level", "assessed_on", "next_due",
          "status", "critical", "branch", "department", "work_section", "designation", "assessed_by", "creation"]


def settings():
    from hrms_addon.hrms_addon import learning

    s = learning.settings()
    return {key: int(s.get(key) or default) for key, default in rules.DEFAULTS.items()}


def _role_levels(skill):
    return {row.parent: row.custom_required_level for row in frappe.get_all(
        "Designation Skill", filters={"skill": skill, "parenttype": "Designation"},
        fields=["parent", "custom_required_level"]) if row.custom_required_level}


def _has_certificate(employee, certification):
    from hrms_addon.hrms_addon import learning_rules

    return bool(frappe.get_all(CERTIFICATE, filters={"employee": employee, "certification": certification,
                                                     "status": ["in", [learning_rules.VALID, learning_rules.DUE_SOON]]},
                               pluck="name", limit=1))


def _status(row, skill, day):
    certification = skill.get("custom_certification")
    return rules.status_of(row.get("level"), rules.level_of(row.get("required_level")) or rules.DEFAULT_REQUIRED,
                           row.get("next_due"), day, bool(certification),
                           _has_certificate(row.get("employee"), certification) if certification else True)


def assessment_validate(doc):
    for message in rules.assessment_errors(doc.as_dict(), today()):
        frappe.throw(_(message), title=_(ASSESSMENT))
    facts = frappe.db.get_value("Employee", doc.employee, ["employee_name", "designation", "branch", "department",
                                                           "company", "custom_work_section"], as_dict=True) or {}
    for field, key in (("employee_name", "employee_name"), ("designation", "designation"), ("branch", "branch"),
                       ("department", "department"), ("company", "company"), ("work_section", "custom_work_section")):
        doc.set(field, facts.get(key))
    if doc.get("assessed_by"):
        doc.assessed_by_name = frappe.db.get_value("Employee", doc.assessed_by, "employee_name")
    skill = frappe.get_cached_doc(SKILL, doc.skill)
    needed = rules.required_level(skill.as_dict(), _role_levels(doc.skill), doc.designation)
    doc.required_level = rules.level_name(needed)
    doc.gap = max(0, needed - (rules.level_of(doc.level) or 0))
    doc.critical = 1 if skill.get("custom_critical") else 0
    doc.next_due = rules.next_due(doc.assessed_on, skill.get("custom_reassess_months"))
    if doc.get("status") != rules.SUPERSEDED or doc.is_new():
        doc.status = _status(doc.as_dict(), skill, today())


def assessment_on_update(doc):
    _settle(doc.employee, doc.skill)


def assessment_on_trash(doc):
    _settle(doc.employee, doc.skill, leaving=doc.name)


def _settle(employee, skill, leaving=None):
    """The newest assessment counts, the rest are Superseded."""
    rows = [row for row in frappe.get_all(ASSESSMENT, filters={"employee": employee, "skill": skill},
                                          fields=FIELDS) if row.name != leaving]
    counting = rules.current(rows).get((employee, skill))
    if not counting:
        return None
    for row in rows:
        if row.name != counting.name and row.status != rules.SUPERSEDED:
            frappe.db.set_value(ASSESSMENT, row.name, "status", rules.SUPERSEDED, update_modified=False)
    if counting.status == rules.SUPERSEDED:
        status = _status(counting, frappe.get_cached_doc(SKILL, skill).as_dict(), today())
        frappe.db.set_value(ASSESSMENT, counting.name, "status", status, update_modified=False)
    return counting.name


def daily():
    """Where each counting assessment stands today; a reassessment newly due
    goes on the employee's supervisor's list."""
    from hrms_addon.hrms_addon import people

    day = today()
    skills = {}
    for row in frappe.get_all(ASSESSMENT, filters={"status": ["!=", rules.SUPERSEDED]}, fields=FIELDS):
        if row.skill not in skills:
            skills[row.skill] = frappe.get_cached_doc(SKILL, row.skill).as_dict()
        status = _status(row, skills[row.skill], day)
        if status == row.status:
            continue
        frappe.db.set_value(ASSESSMENT, row.name, "status", status, update_modified=False)
        if status == rules.REASSESS:
            supervisor = frappe.db.get_value("Employee", row.employee, "reports_to")
            user = frappe.db.get_value("Employee", supervisor, "user_id") if supervisor else None
            if user:
                people.assign(ASSESSMENT, row.name, [user],
                              _("Reassess {0} in {1}").format(row.employee_name, row.skill))


# ── What the reports and the scorecard read ───────────────────────────
def counting_rows(filters):
    """The assessments that count, through the user's permissions."""
    conditions = {"status": ["!=", rules.SUPERSEDED]}
    for field in ("company", "branch", "work_section", "skill"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    return frappe.get_list(ASSESSMENT, filters=conditions, fields=FIELDS, limit_page_length=0)


def skills_in(filters):
    """The skills assessed in a plant and section: those with a type, for the
    section or plant asked, or for every plant."""
    found = []
    for row in frappe.get_all(SKILL, filters={"custom_skill_type": ["is", "set"]},
                              fields=["name", "custom_skill_type", "custom_branch", "custom_work_section",
                                      "custom_critical", "custom_required_level", "custom_certification"],
                              order_by="name asc"):
        if filters.get("skill_type") and row.custom_skill_type != filters.get("skill_type"):
            continue
        if filters.get("work_section") and row.custom_work_section not in (filters.get("work_section"), None, ""):
            continue
        if filters.get("branch") and row.custom_branch not in (filters.get("branch"), None, ""):
            continue
        found.append(row)
    return found


def coverage_for(people):
    """((competent, assessed) in every skill, the same in critical skills) for
    these employees' counting assessments."""
    if not people:
        return (0, 0), (0, 0)
    rows = frappe.get_all(ASSESSMENT, filters={"employee": ["in", people], "status": ["!=", rules.SUPERSEDED]},
                          fields=["status", "critical"])
    return rules.coverage(rows), rules.coverage([row for row in rows if row.critical])
