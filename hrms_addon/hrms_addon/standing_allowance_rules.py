# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The allowances an employee is paid every month: House Rent, Transport,
Meals, Airtime, and whatever HR adds next.

Each is one of Frappe HR's recurring Additional Salaries, so payroll pays
it, the tax formulas see it in the gross, and pay.monthly_gross counts it.
What this adds is one place to manage them, on the employee's Salary
Structure Assignment, without cancelling anything:

  add       any earning, from a day, until a day or until it is ended
  change    a new amount from a day: the allowance as it was ends the day
            before and the new amount runs on from that day, so what was
            paid keeps the amount it was paid at
  end       a last day, or none again to let it run on
  remove    one entered by mistake and never paid
  plan      on an employee's first assignment, before it is submitted: the
            allowances are listed on the draft and added when it is

Frappe HR's own rules shape these. A recurring Additional Salary must have
a last day, so one left to run is given OPEN_END and shown without a last
day. One component runs once at a time for an employee. HR may make and
disable them but not cancel them, so a removal disables.

No Frappe import: scripts/verify_standing_allowances.py loads this file on
its own.
"""

import datetime

EARNING = "Earning"
# "until it is ended": the last day a recurring Additional Salary must have
OPEN_END = datetime.date(2099, 12, 31)

RUNNING, STARTS, ENDED = "Running", "Starts", "Ended"
CORRECT, SUCCEED = "correct", "succeed"


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _day(value):
    value = _date(value)
    return value.strftime("%d-%m-%Y") if value else ""


def _money(value):
    return "{:,.0f}".format(_num(value)) if _num(value) == int(_num(value)) else "{:,.2f}".format(_num(value))


def is_open(to_date):
    """Left to run until it is ended."""
    to_date = _date(to_date)
    return to_date is None or to_date >= OPEN_END


def last_day(to_date, relieving=None):
    """The last day to keep on the record: OPEN_END when none is given, and
    never past the day the employee leaves."""
    end = OPEN_END if is_open(to_date) else _date(to_date)
    relieving = _date(relieving)
    return min(end, relieving) if relieving else end


def state(record, day):
    start, end = _date(record.get("from_date")), last_day(record.get("to_date"))
    day = _date(day)
    if start and day and start > day:
        return STARTS
    if day and end < day:
        return ENDED
    return RUNNING


def view(records, day, paid=()):
    """The employee's allowances for the panel: those running first, then
    those still to start, then those that have ended, each by name.

    records: {"name", "salary_component", "amount", "from_date", "to_date"}
    paid: the names a submitted salary slip has paid."""
    order = {RUNNING: 0, STARTS: 1, ENDED: 2}
    rows = []
    for record in records or []:
        rows.append({
            "name": record.get("name"), "salary_component": record.get("salary_component"),
            "amount": _num(record.get("amount")), "from_date": _date(record.get("from_date")),
            "to_date": None if is_open(record.get("to_date")) else _date(record.get("to_date")),
            "state": state(record, day), "paid": record.get("name") in set(paid or ()),
        })
    rows.sort(key=lambda row: (order[row["state"]], str(row["salary_component"] or ""), str(row["from_date"] or "")))
    return rows


def total_running(rows):
    return round(sum(_num(row.get("amount")) for row in rows or [] if row.get("state") == RUNNING), 2)


def overlaps(first_from, first_to, second_from, second_to):
    first_from, second_from = _date(first_from), _date(second_from)
    return bool(first_from and second_from
                and first_from <= last_day(second_to) and second_from <= last_day(first_to))


def clash(component, from_date, to_date, others, but=None):
    """The other allowance of this component that runs in the same days, as a
    message; None when there is none. `but` names a record to leave out."""
    for other in others or []:
        if other.get("salary_component") != component or other.get("name") == but:
            continue
        if overlaps(from_date, to_date, other.get("from_date"), other.get("to_date")):
            until = "" if is_open(other.get("to_date")) else " to %s" % _day(other.get("to_date"))
            return ("%s of %s already runs from %s%s. Change its amount or end it instead."
                    % (component, _money(other.get("amount")), _day(other.get("from_date")), until))
    return None


def add_errors(facts):
    """Why an allowance cannot be added, as messages.

    facts: "salary_component", "component" ({"type", "disabled"}, None when
    it does not exist), "amount", "from_date", "to_date", "joined",
    "relieving", "assigned_from" (the employee's first salary structure
    assignment, None without one), "others" (their other allowances)."""
    errors = []
    name, component = facts.get("salary_component"), facts.get("component")
    if not name:
        errors.append("Choose the allowance.")
    elif not component:
        errors.append("%s is not a salary component." % name)
    elif (component.get("type") or EARNING) != EARNING:
        errors.append("%s is a deduction. An allowance is an earning." % name)
    elif int(_num(component.get("disabled"))):
        errors.append("%s is disabled." % name)
    if _num(facts.get("amount")) <= 0:
        errors.append("Enter an amount of more than nothing.")
    start, end = _date(facts.get("from_date")), _date(facts.get("to_date"))
    if not start:
        errors.append("Enter the day it starts.")
        return errors
    if end and end < start:
        errors.append("The last day cannot be before the first.")
    assigned = _date(facts.get("assigned_from"))
    if not assigned:
        errors.append("The employee has no salary structure assignment yet. Submit one first.")
    elif start < assigned:
        errors.append("It cannot start before the employee's first salary structure assignment on %s." % _day(assigned))
    joined, relieving = _date(facts.get("joined")), _date(facts.get("relieving"))
    if joined and start < joined:
        errors.append("It cannot start before the employee joined on %s." % _day(joined))
    if relieving and (start > relieving or (end and end > relieving)):
        errors.append("The employee leaves on %s. It cannot run past that day." % _day(relieving))
    found = clash(name, start, end, facts.get("others")) if name else None
    if found:
        errors.append(found)
    return errors


def plan_errors(planned, facts):
    """Why the allowances listed on a draft assignment cannot be added when
    it is submitted, as messages naming the row.

    Frappe HR takes no Additional Salary from before the employee's first
    submitted assignment, so on a first assignment they are listed and are
    added on submit. Each is judged as add_errors judges one, with the
    assignment itself as the first there is, and against the rows before it
    as well as the allowances already on record.

    planned: [{"salary_component", "component", "amount", "from_date" (blank:
    the assignment's), "to_date"}]. facts: "assignment_from", "assigned_from"
    (an earlier submitted assignment's first day, if any), "joined",
    "relieving", "others"."""
    opens = _date(facts.get("assignment_from"))
    firsts = [day for day in (_date(facts.get("assigned_from")), opens) if day]
    others = list(facts.get("others") or [])
    errors = []
    for index, row in enumerate(planned or [], 1):
        start = planned_start(row.get("from_date"), opens)
        found = add_errors({
            "salary_component": row.get("salary_component"), "component": row.get("component"),
            "amount": row.get("amount"), "from_date": start, "to_date": row.get("to_date"),
            "joined": facts.get("joined"), "relieving": facts.get("relieving"),
            "assigned_from": min(firsts) if firsts else None, "others": others})
        errors += ["Allowance %d: %s" % (index, message) for message in found]
        others.append({"name": "allowance %d" % index, "salary_component": row.get("salary_component"),
                       "amount": row.get("amount"), "from_date": start, "to_date": row.get("to_date")})
    return errors


def planned_start(from_date, assignment_from):
    """The day an allowance listed on a draft starts: its own, else the
    assignment's first day."""
    return _date(from_date) or _date(assignment_from)


def change_plan(record, amount, from_date, paid=False):
    """How an allowance takes a new amount.

    {"errors": [...]}, or {"kind": CORRECT} when the amount is put right from
    the allowance's own first day (only while no slip has paid it), or
    {"kind": SUCCEED, "end_on": the day before} when the new amount starts
    later: the allowance as it was ends then, and a new one runs on."""
    errors = []
    amount, start = _num(amount), _date(from_date)
    began, ends = _date(record.get("from_date")), last_day(record.get("to_date"))
    if amount <= 0:
        errors.append("Enter an amount of more than nothing.")
    elif round(amount, 2) == round(_num(record.get("amount")), 2):
        errors.append("That is the amount it already has.")
    if not start:
        errors.append("Enter the day the new amount starts.")
    elif began and start < began:
        errors.append("The new amount cannot start before the allowance did on %s." % _day(began))
    elif start > ends:
        errors.append("The allowance ends on %s. Add a new one instead." % _day(ends))
    elif start == began and paid:
        errors.append("A salary slip has paid this allowance from %s. Enter the day the new amount starts."
                      % _day(began))
    if errors:
        return {"errors": errors}
    if start == began:
        return {"kind": CORRECT}
    return {"kind": SUCCEED, "end_on": start - datetime.timedelta(days=1)}


def end_errors(record, to_date, others=()):
    """Why an allowance cannot take this last day (None: run on), as
    messages. Running it on, or later than before, must not run it into
    another of the same component."""
    errors = []
    began, end = _date(record.get("from_date")), _date(to_date)
    if end and began and end < began:
        errors.append("The last day cannot be before it started on %s." % _day(began))
        return errors
    if last_day(end) > last_day(record.get("to_date")):
        found = clash(record.get("salary_component"), began, end, others, but=record.get("name"))
        if found:
            errors.append(found)
    return errors


def remove_errors(record, paid=False):
    if paid:
        return ["A salary slip has paid this allowance, so it stays on record. End it instead."]
    return []
