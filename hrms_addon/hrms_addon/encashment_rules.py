# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave encashment rules (Reward and Compensation, §4.5).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_encashment.py exercises them without a bench.

The minutes of 16 and 20 July 2026:

  "When an employee is required to work during their approved leave
  period, they apply for leave encashment. The application covers only
  the accumulated leave days being paid; there is no fixed maximum limit,
  as the limit is determined by Management. The application is submitted
  by the employee and approved by the immediate Supervisor, Human
  Resource, the General Manager, and the Executive Director before being
  returned to Human Resource. The application is then forwarded to the
  Accounts Manager in the Finance Department for processing, where the
  encashment amount is calculated based on the employee's salary and the
  accumulated leave days."

The application is Frappe HR's own Leave Encashment, which already holds
it to the accumulated balance and pays it through an Additional Salary on
the payroll. What Luuka add is the chain, the reason, and the amount
worked out from the salary: a day's pay is the gross over the working days
of a month, the same day's pay the final settlement encashes untaken leave
at (settlement_rules.py), unless a per-day amount is set on the salary
structure, which Frappe HR then uses.
"""

WORKING_DAYS_A_MONTH = 26


def application_errors(facts):
    """What an application says before it leaves the employee.

    facts: "days" (asked for), "balance" (accumulated), "reason", and the
    leave worked through, if one is named: "leave_employee",
    "leave_status", "leave_days"; "employee".
    """
    errors = []
    days = _num(facts.get("days"))
    if days <= 0:
        errors.append("Say how many leave days are to be paid.")
    elif facts.get("balance") is not None and days > _num(facts.get("balance")):
        errors.append("Only the accumulated leave is paid: %g day(s) are asked for and %g are "
                      "accumulated." % (days, _num(facts.get("balance"))))
    if not _text(facts.get("reason")):
        errors.append("Say why the leave was worked: encashment is for leave the employee was required "
                      "to work through.")
    if facts.get("leave_employee") is not None:
        if facts.get("leave_employee") != facts.get("employee"):
            errors.append("The leave worked through must be the employee's own.")
        elif facts.get("leave_status") != "Approved":
            errors.append("The leave worked through must be an approved leave.")
        elif days > _num(facts.get("leave_days")):
            errors.append("%g day(s) are asked for, and the leave worked through was %g day(s)."
                          % (days, _num(facts.get("leave_days"))))
    return errors


def management_errors(facts):
    """Management set the limit (the General Manager and the Executive
    Director may cut the days), but nobody raises what was asked for.

    facts: "days", "requested".
    """
    requested = _num(facts.get("requested"))
    if requested and _num(facts.get("days")) > requested:
        return ["%g day(s) were asked for; no more than that may be paid." % requested]
    if _num(facts.get("days")) <= 0:
        return ["Say how many leave days are to be paid."]
    return []


def per_day(gross, working_days=WORKING_DAYS_A_MONTH):
    """A day's pay: the gross over the working days of a month."""
    return round(_num(gross) / float(working_days or WORKING_DAYS_A_MONTH), 2)


def amount(gross, days, working_days=WORKING_DAYS_A_MONTH):
    return round(per_day(gross, working_days) * _num(days), 2)


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()
