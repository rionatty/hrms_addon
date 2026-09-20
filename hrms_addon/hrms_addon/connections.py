# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections: what this app adds, shown on the standard documents it hangs
off, so nothing has to be found by searching for its DocType.

Frappe builds a form's Connections from the DocType's own `*_dashboard.py`
(ours ship beside each DocType) and, for a DocType another app owns, from
the `override_doctype_dashboards` hook, which chains — each app is handed
what the one before it returned and adds to it (frappe/model/meta.py,
get_dashboard_data).

  Employee             its reviews, probation evaluations and contracts
  Employee Onboarding  what its approval set off: the same three
  Job Opening          the shortlist and the interview report for the post

A count is only found where the other document carries a plain Link field
to this one: Frappe filters {fieldname: name} on the target
(frappe/desk/notifications.py, get_external_links), and a link that lives in
a child table is not searched. That is why an Employee Contract knows its
onboarding, and why the shortlist's own Connections (its dashboard, which
walks its candidates) are the way round that works for Job Applicant and
Interview.
"""

from frappe import _

ONBOARDING_DOCS = ["Onboarding Review", "Probation Evaluation", "Employee Contract"]
# what follows afterwards: a promotion, a change of designation or a salary
# review, and where the pay is sent
SERVICE_DOCS = ["Employee Position Change", "Employee Data Change Request"]
# how the person is doing, and what was agreed where they fell short
PERFORMANCE_DOCS = ["Appraisal", "Performance Improvement Plan"]
# the day to day: why someone was away, and the overtime they worked
ATTENDANCE_DOCS = ["Off Duty Request", "Gate Pass"]


def employee_dashboard(data=None):
    """Employee: everything that follows the person through their service."""
    data = data or {}
    transactions = data.setdefault("transactions", [])
    transactions.append({"label": _("Probation and Contracts"), "items": list(ONBOARDING_DOCS)})
    transactions.append({"label": _("Position and Pay"), "items": list(SERVICE_DOCS)})
    transactions.append({"label": _("Performance"), "items": list(PERFORMANCE_DOCS)})
    transactions.append({"label": _("Attendance"), "items": list(ATTENDANCE_DOCS)})
    return data


def employee_onboarding_dashboard(data=None):
    """Employee Onboarding: what the HR Manager's approval set off. Frappe HR
    ships no dashboard for it, so this one sets the field the counts use."""
    data = data or {}
    data.setdefault("fieldname", "onboarding")
    data.setdefault("transactions", []).append({"label": _("After Joining"), "items": list(ONBOARDING_DOCS)})
    return data


def training_event_dashboard(data=None):
    """Training Event: the requisitions it answers, on top of Frappe HR's
    own Training Result and Training Feedback. The schedule that booked it
    is a Link on the event itself."""
    data = data or {}
    data.setdefault("non_standard_fieldnames", {}).update({"Training Requisition": "training_event"})
    data.setdefault("transactions", []).append({"label": _("Requested By"), "items": ["Training Requisition"]})
    return data


def job_opening_dashboard(data=None):
    """Job Opening: the shortlist and the interview report for the post.
    Frappe HR's own dashboard counts Job Applicants through `job_title`, so
    ours name their own field instead of changing that."""
    data = data or {}
    data.setdefault("non_standard_fieldnames", {}).update({"Interview Shortlist": "job_opening",
                                                           "Interview Report": "job_opening"})
    data.setdefault("transactions", []).append({"label": _("Shortlisting"),
                                                "items": ["Interview Shortlist", "Interview Report"]})
    return data
