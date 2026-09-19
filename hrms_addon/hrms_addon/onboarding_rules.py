# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Onboarding: Luuka's To-Be induction process (blueprint 1.2.4), steps 1 to 4.

No Frappe import, like the other *_rules.py modules, so scripts/verify_onboarding.py
exercises it without a bench.

  1. The candidate reports for work (outside the system).
  2. The HR Officer runs the orientation (policies, procedures, health and
     safety, code of conduct; the Workplace Rules and Regulations, LPL/HR/05,
     signed) and hands the new employee over to the Head of Department.
  3. The HR Officer creates the Employee and prints the Personal Bio-Data
     Form (LPL/HR/16) for the employee to fill in.
  4. The HR Officer updates the Employee from the completed form.

Frappe HR's Employee Onboarding carries it: its template's activities become
tasks when the onboarding starts, and Create Employee is refused until the
activities marked required for it are done. So orientation, the rules and
the handover are required; the Bio-Data form comes after the Employee.

WHO GETS A TASK

Frappe HR assigns an activity given to a role to EVERY enabled user holding
the role (hrms/controllers/employee_boarding_controller.py). Luuka's people
belong to branches (org_rules.py), so before the tasks are made each role is
resolved to the onboarding's own people: see activity_assignees().

WHICH TEMPLATE

pick_template(): one HR made for the Job Title or the Department wins;
otherwise the production template for a non-administrative department (the
production roles walk through the process and visit the plants), the
standard one for the rest.

WHAT IS STILL TO DO

Frappe HR refuses to create, or save, the Employee of a running onboarding
until every activity required for it has its task Completed or Cancelled,
and says only "All the mandatory tasks for employee creation are not
completed yet." pending_required() and pending_message() name them.
"""

import html
from urllib.parse import quote

HR_OFFICER_ROLE = "HR User"
HOD_ROLE = "Head of Department"

# A required activity stops Create Employee until its task is one of these
# (Frappe HR's own test, employee_onboarding.validate_employee_creation)
DONE_TASK_STATUSES = ("Completed", "Cancelled")

# The templates Luuka starts with, seeded once (HR's to change afterwards).
# Each activity: (what, role, begin on day, days allowed, required before the
# Employee is created, how). "What" is short: Frappe HR makes it the task's
# subject with the employee's name after it, in a field of 140 characters.
ORIENTATION = (
    "Orientation and tour of the office and production floor",
    HR_OFFICER_ROLE, 0, 0, 1,
    "Step 2 of the induction, on the first day: company policies, procedures, health and safety requirements, "
    "code of conduct and other induction information; a tour of the office and production floor; introductions "
    "to the staff and key personnel.",
)
WORKPLACE_RULES = (
    "Workplace Rules and Regulations (LPL/HR/05) read and signed",
    HR_OFFICER_ROLE, 0, 0, 1,
    "Print them from the onboarding (Print > Workplace Rules and Regulations), have the new employee sign, "
    "then record the date signed and attach the signed copy under Orientation.",
)
HANDOVER = (
    "Handover of the new employee to the Head of Department",
    HOD_ROLE, 0, 0, 1,
    "The Head of Department confirms the new employee has been received into the department: set this task "
    "to Completed.",
)
BIO_DATA = (
    "Personal Bio-Data Form (LPL/HR/16) filled in, signed and captured",
    HR_OFFICER_ROLE, 0, 1, 0,
    "After Create Employee: print the form from the Employee (Print > Personal Bio-Data Form, it comes "
    "pre-filled), have the employee check, complete and sign it, then update the Employee and record the date "
    "signed on its Personal Bio-Data tab.",
)
PROCESS_WALKTHROUGH = (
    "Production process walk-through with the Section In-Charge",
    HOD_ROLE, 1, 2, 0,
    "Production roles: the Section In-Charge takes the new employee through the production process.",
)
PLANT_VISITS = (
    "Plant visits: Kawempe, Namanve and Matugga",
    HOD_ROLE, 2, 5, 0,
    "Production roles: days scheduled at each plant to see what happens there.",
)

DEFAULT_TEMPLATE = "Luuka Onboarding"
PRODUCTION_TEMPLATE = "Luuka Onboarding - Production"
TEMPLATES = {
    DEFAULT_TEMPLATE: (ORIENTATION, WORKPLACE_RULES, HANDOVER, BIO_DATA),
    PRODUCTION_TEMPLATE: (ORIENTATION, WORKPLACE_RULES, HANDOVER, BIO_DATA, PROCESS_WALKTHROUGH, PLANT_VISITS),
}
ACTIVITY_FIELDS = ("activity_name", "role", "begin_on", "duration", "required_for_employee_creation", "description")

# A Department's Position Category (org_rules.POSITION_CATEGORIES) -> the
# template its new employees start from, when HR has made none for them
TEMPLATE_BY_CATEGORY = {"Non-Administrative": PRODUCTION_TEMPLATE, "Administrative": DEFAULT_TEMPLATE}


def template_activities(title):
    """The seeded activity rows of a template, as Employee Boarding Activity dicts."""
    return [dict(zip(ACTIVITY_FIELDS, activity)) for activity in TEMPLATES[title]]


def activity_assignees(role, named, holders, branch, department):
    """Who an onboarding activity given to `role` goes to: never every holder
    of the role, only this onboarding's own people.

    named:   {role: user} the people named on the onboarding: its HR Officer
             for HR User, its Head of Department for theirs
    holders: [{"user", "branches", "departments"}] the enabled users holding
             the role, with the branches and departments their User
             Permissions limit them to (an empty set is no limit)

    Returns the named person; else the holders limited to this branch (and,
    where they are limited to departments, to this department); else the
    holders with no branch limit, who serve every branch; else [] (the caller
    then gives the task to the HR Officer).
    """
    if named.get(role):
        return [named[role]]
    in_branch = sorted(
        h["user"] for h in holders
        if branch in h["branches"] and (not h["departments"] or department in h["departments"])
    )
    if in_branch:
        return in_branch
    return sorted(h["user"] for h in holders if not h["branches"])


def pick_template(templates, company, department, designation, category):
    """The Employee Onboarding Template a new employee starts from.

    templates: [{"name", "title", "company", "department", "designation"}]
    A template fits when each of its company, department and designation is
    blank or the employee's. Of those, one made for the Job Title wins, then
    one made for the Department; otherwise the one for the department's
    Position Category (TEMPLATE_BY_CATEGORY), else the standard one, else
    None (HR picks).
    """
    def fits(template):
        return all(not template.get(key) or template[key] == value
                   for key, value in (("company", company), ("department", department), ("designation", designation)))

    fitting = [t for t in templates if fits(t)]
    for key in ("designation", "department"):
        specific = sorted(t["name"] for t in fitting if t.get(key))
        if specific:
            return specific[0]
    by_title = {}
    for template in sorted(fitting, key=lambda t: t["name"]):
        by_title.setdefault(template.get("title"), template["name"])
    return by_title.get(TEMPLATE_BY_CATEGORY.get(category)) or by_title.get(DEFAULT_TEMPLATE)


def pending_required(activities):
    """The activities still stopping Create Employee, in their order.

    activities: [{"activity_name", "required_for_employee_creation", "task",
    "task_status", "assignees"}]; an activity whose task is missing counts as
    not done, as it does for Frappe HR.
    """
    return [a for a in activities
            if a.get("required_for_employee_creation") and a.get("task_status") not in DONE_TASK_STATUSES]


def pending_message(onboarding, pending):
    """The message HR sees instead of Frappe HR's: each task still to
    complete, linked, with its status and who has it. HTML, escaped."""
    items = []
    for activity in pending:
        name = html.escape(activity.get("activity_name") or "")
        task = activity.get("task")
        label = '<a href="/app/task/%s">%s</a>' % (quote(task), name) if task else name
        status = html.escape(activity.get("task_status") or "no task made")
        people = ", ".join(html.escape(person) for person in activity.get("assignees") or []) or "nobody assigned"
        items.append("<li>%s: %s, with %s</li>" % (label, status, people))
    return (
        '<p>These tasks of the onboarding <a href="/app/employee-onboarding/%s">%s</a> must be completed before '
        "the Employee can be created or saved:</p><ul>%s</ul>"
        "<p>Whoever has a task opens it and sets its Status to Completed.</p>"
        % (quote(onboarding or ""), html.escape(onboarding or ""), "".join(items))
    )


# The Workplace Rules and Regulations (LPL/HR/05) as issued, kept as Terms
# and Conditions of this title so HR can revise them without a release; the
# print format of the onboarding prints them with the acceptance to sign.
# Seeded once, never overwritten.
WORKPLACE_RULES_TITLE = "Workplace Rules and Regulations"
WORKPLACE_RULES_HTML = """\
<ol>
<li>Arrival time during day shift is 6:45am and night shift is 6:45pm. Any minute after that, means you are late. Late coming will not be tolerated.</li>
<li>Reporting to work drunk, drinking alcohol at the workplace and reporting to work under the influence of drugs is strictly prohibited.</li>
<li>No fighting, or influencing violence of any nature. If caught, you will lose your job.</li>
<li>Theft is strictly prohibited.</li>
<li>Do a proper handover to the next operator and a proper take over from the previous operator.</li>
<li>Ask for leave when not coming for work: communicate before time.</li>
<li>Respect your supervisors and workmates, promote team work.</li>
<li>Avoid wasting time, be time conscious (break teas, lunch breaks, wash rooms), supervise yourself, do not let your supervisor look for you.</li>
<li>Do not sleep on duty.</li>
<li>Do not loiter around, stay in your workplace.</li>
<li>Hygiene wise: be clean, smart, iron your clothes, comb your hair, be neat, always bath and shave.</li>
<li>Also, always keep your workplaces clean.</li>
<li>Do not smoke from work premises.</li>
</ol>
<h4>Production Quality Products: a Must</h4>
<ol>
<li>Quality is everyone's responsibility.</li>
<li>Never pack / pass on a bad product.</li>
<li>Endeavour to always produce best quality products to help us attract and retain our customers and compete with competitors.</li>
<li>If you do not know / understand anything, be honest to always ask and be trained.</li>
</ol>
<h4>Health and Safety &amp; Avoiding Accidents</h4>
<ol>
<li>Must wear proper PPEs (uniforms, helmet, aprons and overalls, gumboots, head veils and gloves). Always wear overalls with buttons, head caps, hair well combed and net.</li>
<li>Report all known or observed hazards to the supervisor or manager (open electrical wires, misplaced objects etc).</li>
<li>Must comply with any directions given by the management in relation to health and safety.</li>
<li>In case a machine develops a mechanical problem, first switch it off then inform the supervisor/manager to rectify the problem.</li>
<li>Always follow machine operations SOPs, do not make any by-pass or short cut; you would rather take your time than hurry and end up in problems. Please also avoid spoiling machines.</li>
<li>Always handle your knives properly.</li>
<li>Carefully use passage directives / ladders provided when moving around / in the plant (watch and mind your steps).</li>
<li>Avoid moving on slippery things like wet / oily floors and raw materials.</li>
</ol>
<h4>House Keeping Practices</h4>
<ul>
<li>Use right places / dustbins / waste bins to throw all used gloves and cotton wastes as availed in the plants.</li>
<li>Keep the workplace clean and free from oil spillages to avoid sliding on the floor.</li>
<li>Always leave your workplaces clean, participate in all cleanings and full housekeeping practices, do not leave the workplace in a mess for your relievers.</li>
<li>Read and obey safety signs and tags (lock outs, work in progress, do not touch, mind your step, debris falling) displayed in your working area.</li>
<li>Use tools correctly and for the intended purpose only.</li>
<li>Put tools away after use, don't leave things lying around where they can fall or hit someone.</li>
<li>Must report careless forklift operators/drivers.</li>
<li>Avoid horseplay inside the factory during operations.</li>
<li>Do not sit, lean, jump over or pass under machines.</li>
<li>Do not throw used gloves, nose masks and rubbish on the floor.</li>
<li>Do not operate any machines without wearing proper PPEs.</li>
<li>Do not operate any machine if you are not a machine operator or helper unless authorized to do so.</li>
<li>Do not touch, remove or fix anything on a machine that is in motion/running. First switch off the machine before touching inside. Call a machine operator, supervisor or electrician to help in rectifying a faulty machine.</li>
<li>Do not put food stuffs, cups, bags and clothes on top of machines or inside electrical cabinets/panels.</li>
<li>Do not sit on finished goods products / raw materials.</li>
</ul>
<h4>Punishable Offences</h4>
<ol>
<li>Absenteeism</li>
<li>Late coming</li>
<li>Sleeping on duty</li>
<li>Disrespect / insubordination, refusal to work where deployed</li>
<li>Production of bad quality products or damaging company property (may end up in recovery from salary), negligence, dishonesty (gross misconduct)</li>
<li>Poor performance / failure to achieve targets</li>
<li>Theft (gross misconduct)</li>
<li>Violence, abusing, fighting (gross misconduct)</li>
<li>Alcohol / drugs</li>
<li>Failure to put on proper and full safety wear</li>
</ol>
<h4>Disciplinary Procedures</h4>
<ol>
<li>Investigations</li>
<li>Verbal warning</li>
<li>Written warnings</li>
<li>Suspensions</li>
<li>Terminations</li>
<li>Summary dismissals (violence, abusing, fighting; theft; negligence, dishonesty: gross misconduct)</li>
<li>Desertions</li>
</ol>
<h4>Reporting Procedures</h4>
<ol>
<li>Supervisors, production officers, HR, Managers etc.</li>
</ol>
"""
