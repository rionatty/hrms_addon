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
from frappe.utils import flt, getdate, today

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


def _status(row, skill, day, held=None):
    """Where the assessment stands today. held: the (employee, certification)
    pairs with a valid certificate, read once for a whole run (_valid_pairs);
    without it the one certificate is looked up."""
    certification = skill.get("custom_certification")
    if not certification:
        has = True
    elif held is not None:
        has = (row.get("employee"), certification) in held
    else:
        has = _has_certificate(row.get("employee"), certification)
    return rules.status_of(row.get("level"), rules.level_of(row.get("required_level")) or rules.DEFAULT_REQUIRED,
                           row.get("next_due"), day, bool(certification), has)


def _valid_pairs(employees, certifications):
    """{(employee, certification)} of the certificates valid now, in one read."""
    from hrms_addon.hrms_addon import learning_rules

    employees, certifications = list(employees or ()), list(certifications or ())
    if not employees or not certifications:
        return set()
    return {(row.employee, row.certification) for row in frappe.get_all(
        CERTIFICATE, filters={"employee": ["in", employees], "certification": ["in", certifications],
                              "status": ["in", [learning_rules.VALID, learning_rules.DUE_SOON]]},
        fields=["employee", "certification"], limit_page_length=0)}


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
    # the role's profile first (job title and section, else job title), then
    # the job title's skills, then the skill's own level
    profile = rules.profile_for(profiles([doc.designation]), doc.designation, doc.work_section)
    level, critical = rules.profile_level(profile, doc.skill)
    needed = level or rules.required_level(skill.as_dict(), _role_levels(doc.skill), doc.designation)
    doc.required_level = rules.level_name(needed)
    doc.gap = max(0, needed - (rules.level_of(doc.level) or 0))
    doc.critical = critical if critical is not None else (1 if skill.get("custom_critical") else 0)
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
    """Where each counting assessment stands today, every certificate read
    once for the whole run; the reassessments newly due go to each section's
    supervisors on one Skills Assessment Sheet (learning_sheets)."""
    day = today()
    rows = frappe.get_all(ASSESSMENT, filters={"status": ["!=", rules.SUPERSEDED]}, fields=FIELDS,
                          limit_page_length=0)
    skills = {name: frappe.get_cached_doc(SKILL, name).as_dict() for name in {row.skill for row in rows}}
    held = _valid_pairs({row.employee for row in rows},
                        {skill.get("custom_certification") for skill in skills.values() if skill.get("custom_certification")})
    due = []
    for row in rows:
        status = _status(row, skills[row.skill], day, held)
        if status == row.status:
            continue
        frappe.db.set_value(ASSESSMENT, row.name, "status", status, update_modified=False)
        if status == rules.REASSESS:
            due.append(row)
    if due:
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.reassessment_sheets(due)
    return due


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


def scores_for(employees):
    """{employee: their competency score} from the assessments that count,
    read once for all of them."""
    rows = {}
    if employees:
        for row in frappe.get_all(ASSESSMENT, filters={"employee": ["in", list(employees)],
                                                       "status": ["!=", rules.SUPERSEDED]},
                                  fields=["employee", "level", "required_level", "status"], limit_page_length=0):
            rows.setdefault(row.employee, []).append(row)
    return {employee: rules.score_of(mine) for employee, mine in rows.items()}


def coverage_for(people):
    """((competent, assessed) in every skill, the same in critical skills) for
    these employees' counting assessments."""
    if not people:
        return (0, 0), (0, 0)
    rows = frappe.get_all(ASSESSMENT, filters={"employee": ["in", people], "status": ["!=", rules.SUPERSEDED]},
                          fields=["status", "critical"])
    return rules.coverage(rows), rules.coverage([row for row in rows if row.critical])


# ── One framework: role profiles, the skills bank, cover by shift ─────
PROFILE, PROFILE_ROW = "Role Competency Profile", "Role Competency Profile Skill"
MACHINE = "Skill Machine"


def profiles(designations):
    """The role profiles of these job titles, each with its skills, in two reads."""
    designations = [name for name in designations or () if name]
    if not designations:
        return []
    found = {row.name: dict(row, skills=[]) for row in frappe.get_all(
        PROFILE, filters={"designation": ["in", designations]}, fields=["name", "designation", "work_section"],
        limit_page_length=0)}
    for row in frappe.get_all(PROFILE_ROW, filters={"parenttype": PROFILE, "parent": ["in", list(found) or [""]]},
                              fields=["parent", "skill", "required_level", "critical", "weight"], limit_page_length=0):
        found[row.parent]["skills"].append(row)
    return list(found.values())


def profile_validate(doc):
    """One profile a job title and section; each skill once."""
    if doc.get("work_section"):
        doc.branch = frappe.db.get_value("Work Section", doc.work_section, "branch")
    same = {"designation": doc.designation, "work_section": doc.get("work_section") or ["is", "not set"]}
    if not doc.is_new():
        same["name"] = ["!=", doc.name]
    twin = frappe.db.get_value(PROFILE, same, "name")
    if twin:
        frappe.throw(_("{0} already has a profile for this section: {1}.").format(doc.designation, twin),
                     title=_(PROFILE))
    seen = set()
    for row in doc.get("skills") or []:
        if row.skill in seen:
            frappe.throw(_("{0} is listed twice.").format(row.skill), title=_(PROFILE))
        seen.add(row.skill)
        if not row.get("required_level"):
            row.required_level = rules.level_name(rules.DEFAULT_REQUIRED)
        if not flt(row.get("weight")):
            row.weight = 1


def profile_autoname(doc):
    doc.name = " - ".join(part for part in (doc.designation, doc.get("work_section")) if part)


def skill_validate(doc, method=None):
    """A skill's category from its older type where none is set; its five
    levels described where nothing is written."""
    if frappe.get_meta(SKILL).has_field("custom_competency_category") and not doc.get("custom_competency_category") \
            and doc.get("custom_skill_type") in rules.TYPE_CATEGORY:
        doc.custom_competency_category = rules.TYPE_CATEGORY[doc.custom_skill_type]
    if frappe.get_meta(SKILL).has_field("custom_level_descriptors") and doc.get("custom_skill_type") \
            and not doc.get("custom_level_descriptors"):
        for level, text in rules.DEFAULT_DESCRIPTORS:
            doc.append("custom_level_descriptors", {"level": rules.level_name(level), "descriptor": text})


def _counting(employees, skills=None):
    """{employee: {skill: level}} of the assessments that count."""
    filters = {"employee": ["in", list(employees) or [""]], "status": ["!=", rules.SUPERSEDED]}
    if skills:
        filters["skill"] = ["in", list(skills)]
    out = {}
    for row in frappe.get_all(ASSESSMENT, filters=filters, fields=["employee", "skill", "level"], limit_page_length=0):
        out.setdefault(row.employee, {})[row.skill] = row.level
    return out


def fit_for(employees, designation, work_section=None):
    """{employee: role_fit} for a job title (and section): how well each fits
    its profile, the gaps, the missing and the critical gaps. For talent:
    successors and moves are weighed against it."""
    profile = rules.profile_for(profiles([designation]), designation, work_section)
    held = _counting(employees, [row.skill for row in (profile or {}).get("skills") or []] or None)
    return {employee: rules.role_fit(held.get(employee, {}), profile) for employee in employees or ()}


@frappe.whitelist()
def employee_fit(employee, designation, work_section=None):
    """How one employee fits a role, for the forms that ask."""
    frappe.has_permission("Employee", "read", employee, throw=True)
    return fit_for([employee], designation, work_section).get(employee)


def today_shifts(employees, day=None):
    """{employee: the shift they work today}: their Shift Assignment, else
    their default shift."""
    day = str(getdate(day or today()))
    employees = list(employees or ())
    if not employees:
        return {}
    found = {row.employee: row.shift_type for row in frappe.get_all(
        "Shift Assignment", filters={"employee": ["in", employees], "docstatus": 1, "status": "Active",
                                     "start_date": ["<=", day]},
        or_filters=[["end_date", ">=", day], ["end_date", "is", "not set"]],
        fields=["employee", "shift_type"], limit_page_length=0)}
    if len(found) < len(employees) and frappe.get_meta("Employee").has_field("default_shift"):
        for row in frappe.get_all("Employee", filters={"name": ["in", [e for e in employees if e not in found]]},
                                  fields=["name", "default_shift"], limit_page_length=0):
            if row.default_shift:
                found[row.name] = row.default_shift
    return found


def on_leave(employees, day=None):
    day = str(getdate(day or today()))
    return set(frappe.get_all("Leave Application", filters={"employee": ["in", list(employees) or [""]],
                                                            "docstatus": 1, "status": "Approved",
                                                            "from_date": ["<=", day], "to_date": [">=", day]},
                              pluck="employee", limit_page_length=0))


def skills_matching(text):
    """The skills a search names: by name, or by a machine they run."""
    text = (text or "").strip()
    if not text:
        return []
    names = set(frappe.get_all(SKILL, filters={"name": ["like", "%" + text + "%"]}, pluck="name", limit_page_length=0))
    if frappe.db.table_exists(MACHINE):
        names |= set(frappe.get_all(MACHINE, filters={"parenttype": SKILL, "machine": ["like", "%" + text + "%"]},
                                    pluck="parent", limit_page_length=0))
    return sorted(names)


@frappe.whitelist()
def skills_bank(skill=None, text=None, min_level=3, branch=None, work_section=None, shift=None):
    """Who holds a skill (or the skills a word names, a machine among them)
    at a level or above, where they work, the shift they are on today,
    whether they are on leave, and the cover each plant has on each shift.
    Through the user's own permissions on the assessments."""
    skills = [skill] if skill else skills_matching(text)
    if not skills:
        return {"skills": [], "holders": [], "cover": []}
    filters = {"skill": ["in", skills], "status": ["!=", rules.SUPERSEDED],
               "level": ["in", rules.level_names_from(min_level)]}
    for field, value in (("branch", branch), ("work_section", work_section)):
        if value:
            filters[field] = value
    rows = frappe.get_list(ASSESSMENT, filters=filters,
                           fields=["employee", "employee_name", "skill", "level", "status", "branch", "work_section",
                                   "designation", "assessed_on", "next_due"],
                           order_by="level desc, employee_name asc", limit_page_length=0)
    people = {row.employee for row in rows}
    active = set(frappe.get_all("Employee", filters={"name": ["in", list(people) or [""]], "status": "Active"},
                                pluck="name", limit_page_length=0))
    shifts = today_shifts(active)
    away = on_leave(active)
    holders = []
    for row in rows:
        if row.employee not in active:
            continue
        row.shift = shifts.get(row.employee)
        row.on_leave = row.employee in away
        if shift and row.shift != shift:
            continue
        holders.append(row)
    return {"skills": skills, "holders": holders[:500], "count": len(holders),
            "cover": cover_by_shift(skills, branch, holders=[row for row in holders if row.status == rules.COMPETENT])}


def cover_by_shift(skills, branch=None, holders=None):
    """Each skill's cover in each plant on each of today's shifts: the
    competent people on each shift against those needed (the skill's own
    number, else the settings', never more than its section's crew)."""
    s = settings()
    facts = {row.name: row for row in frappe.get_all(
        SKILL, filters={"name": ["in", list(skills) or [""]]},
        fields=["name", "custom_work_section", "custom_critical"] + (
            ["custom_cover_per_shift"] if frappe.get_meta(SKILL).has_field("custom_cover_per_shift") else []),
        limit_page_length=0)}
    crews = dict(frappe.get_all("Work Section", filters={"name": ["in", list({f.custom_work_section for f in
                                                                              facts.values()
                                                                              if f.custom_work_section}) or [""]]},
                                fields=["name", "crew_per_shift"], as_list=True, limit_page_length=0))
    if holders is None:
        filters = {"skill": ["in", list(skills) or [""]], "status": rules.COMPETENT}
        if branch:
            filters["branch"] = branch
        holders = frappe.get_all(ASSESSMENT, filters=filters, fields=["employee", "skill", "branch"],
                                 limit_page_length=0)
        shifts = today_shifts({row.employee for row in holders})
        for row in holders:
            row.shift = shifts.get(row.employee)
    plants = {}
    for row in holders:
        plants.setdefault((row.skill, row.branch or ""), {}).setdefault(row.shift or "", 0)
        plants[(row.skill, row.branch or "")][row.shift or ""] += 1
    known = sorted({shift for counts in plants.values() for shift in counts if shift}) or [""]
    out = []
    for skill in skills:
        fact = facts.get(skill) or {}
        need = rules.shift_need(fact.get("custom_cover_per_shift"), s["cover_per_shift"],
                                crews.get(fact.get("custom_work_section")))
        for (name, plant), counts in sorted(plants.items()):
            if name != skill:
                continue
            found = rules.shift_cover(counts, need, known)
            out.append({"skill": skill, "branch": plant, "need": need, "by_shift": counts,
                        "status": found["status"], "short": found["short"], "critical": fact.get("custom_critical"),
                        "risk": rules.RISK[found["status"]]})
    return out
