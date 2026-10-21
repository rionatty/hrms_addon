# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Overtime: what a day's overtime is worth, and who signs for it.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_overtime.py exercises them without a bench.

WHAT THIS DOES NOT BUILD

Frappe HR already ships the pricing and the payroll route: an Overtime
Type carries the multipliers, an Attendance row carries the hours worked
beyond the standard, and an Overtime Slip gathers those rows for a period,
prices them and writes the Additional Salary the payroll run reads. None of
that is rebuilt here.

What was missing is Luuka's own middle: LPL/HR/14 is raised and authorised
BEFORE the work is done, and nothing carried the authorised hours onto the
attendance the slip reads, so approved overtime and paid overtime were two
separate stories. This closes that, and adds the cost check HR do between
the authority and the payroll.

THE THREE KINDS OF DAY

The Employment Act (Cap 219, s.53 and s.54) sets the floor: overtime on a
normal working day is one and a half times, and work on a public holiday
or a rest day is twice. Luuka's own policy sits on top for production:
public-holiday work is paid a flat day plus the special overtime, which is
why the holiday multiplier is a policy figure on the Overtime Type and not
a constant here.

A day is read, not typed: a date on the employee's holiday list is a
public holiday, their weekly off is a rest day, a day they are on approved
leave is a leave day, and anything else is a weekday.

WHOSE TYPE IT IS

The Overtime Types are Luuka's own, and none is made or named here (21 Oct
2026: "dont predefine any overtime type you should pick from the one
assigned"). Each lists the employees it is for, and a person's overtime
goes under the type that lists them, on every kind of day: the type pays a
rest day and a public holiday at its own weekend and holiday rates
(multiplier_for). The type goes onto the attendance the Overtime Slip
reads, so it is what they are paid, not only what the cost check shows.

A type may carry a gross line ("For Monthly Gross Above"): it is then for
those it lists whose monthly gross, as their salary structure works it
out, is above the line. The minutes of 16 and 20 July 2026 (Reward and
Compensation, §4.12) are why: "the overtime multiplier is 1 for gross
salaries above UGX 500,000, 1.5 for those below UGX 500,000, and 2 for
public holidays". Somebody two types list is paid under the one with the
higher line their gross is above; two with nothing between them is said,
not guessed.
"""

WEEKDAY = "Weekday"
REST_DAY = "Rest Day"
PUBLIC_HOLIDAY = "Public Holiday"
LEAVE_DAY = "Leave Day"
KINDS = (WEEKDAY, REST_DAY, PUBLIC_HOLIDAY, LEAVE_DAY)

# The Employment Act's floor: what a day is paid at where its type gives
# no rate for it (multiplier_for).
ACT_MULTIPLIERS = {WEEKDAY: 1.5, REST_DAY: 2.0, PUBLIC_HOLIDAY: 2.0, LEAVE_DAY: 2.0}

# Luuka's month: the attendance cycle runs 26 to 25 and is worked as 26
# days of ten standard hours (attendance_rules.STANDARD_HOURS), which is
# what an hour of pay is divided out of. A Shift Type that gives its own
# hours is priced by its own standard day instead (hours_per_month).
DAYS_PER_MONTH = 26
STANDARD_HOURS_PER_DAY = 10.0
HOURS_PER_MONTH = DAYS_PER_MONTH * STANDARD_HOURS_PER_DAY

STATUSES = ("Draft", "Requested", "Authorised", "Costed", "Sent to Payroll", "Rejected",
            "Cancelled")


def kind_of_day(facts):
    """What sort of day the overtime falls on, for one employee.

    facts: "on_holiday_list" (the date is a holiday for them),
    "is_weekly_off" (their rest day), "on_leave" (approved leave that day).
    """
    if facts.get("on_leave"):
        return LEAVE_DAY
    if facts.get("on_holiday_list") and not facts.get("is_weekly_off"):
        return PUBLIC_HOLIDAY
    if facts.get("is_weekly_off"):
        return REST_DAY
    return WEEKDAY


def _listed(row, key):
    return {value for value in ((row or {}).get(key) or []) if value}


# why somebody no Overtime Type lists is paid none
NOT_LISTED = "no Overtime Type lists them. Add them on a type's Eligibility tab."


def person_type(gross, types, employee=None, department=None):
    """The Overtime Type a person's overtime falls under, and why none
    where none does: (name, None) or (None, why).

    types: {name: its row, with "employees" (those it lists),
    "excluded_departments" (those it is not paid to) and its gross line}.

    The type is the one that lists them, whatever the day: none is named or
    made for them (Luuka, 21 Oct 2026: each of their types is for a set of
    employees; "dont predefine any overtime type you should pick from the
    one assigned").

      - somebody no type lists is paid under none, and is told so;
      - a type is not paid to the departments it leaves out, even to
        somebody it lists;
      - nor to somebody whose gross is not above its gross line;
      - of the types left, the one with the highest line their gross is
        above. Two left with nothing between them are said, not guessed.

    With no types given at all (None, not a site with none), nobody's
    eligibility is being judged, and the day is priced at the Act's floor."""
    if types is None:
        return None, None
    listed = sorted(name for name, row in types.items() if employee and employee in _listed(row, "employees"))
    if not listed:
        return None, NOT_LISTED
    paid = [name for name in listed if not (department and department in _listed(types[name], "excluded_departments"))]
    if not paid:
        return None, "%s is not paid to %s." % (listed[0], department)
    fit = [name for name in paid if not _under_line(types[name], gross)]
    if not fit:
        nearest = min(paid, key=lambda name: _line(types[name]))
        return None, "%s is for a monthly gross above %s." % (nearest, format(_line(types[nearest]), ",.0f"))
    top = max(_line(types[name]) for name in fit)
    first = [name for name in fit if _line(types[name]) == top]
    if len(first) > 1:
        return None, "%s list them. Keep them on one." % _and(first)
    return first[0], None


def _line(row):
    """A type's gross line, 0 where it has none."""
    return float((row or {}).get("custom_gross_above") or 0)


def _under_line(row, gross):
    """Whether a type has a gross line the person's gross is not above: the
    line says who the type is for (minutes §4.12, "above UGX 500,000")."""
    return _line(row) > 0 and float(gross or 0) <= _line(row)


def eligibility_errors(rows):
    """The people on a request no Overtime Type is open to, as messages.
    rows: as priced gives them."""
    return ["%s is not eligible for this overtime: %s" % (row.get("employee_name") or row.get("employee"),
                                                          row["not_eligible"])
            for row in rows or [] if row.get("employee") and row.get("not_eligible")]


def multiplier_for(kind, overtime_type=None):
    """The rate for the day. The Overtime Type on the site wins — it is
    where policy is kept — and the Act's floor is used only where the type
    says nothing.
    """
    if not overtime_type:
        return ACT_MULTIPLIERS[kind]
    if kind == PUBLIC_HOLIDAY and overtime_type.get("applicable_for_public_holiday"):
        given = overtime_type.get("public_holiday_multiplier")
    elif kind in (REST_DAY, LEAVE_DAY) and overtime_type.get("applicable_for_weekend"):
        given = overtime_type.get("weekend_multiplier")
    else:
        given = overtime_type.get("standard_multiplier")
    return float(given) if given else ACT_MULTIPLIERS[kind]


def hours_per_month(standard_hours=None, days=None, day_hours=None):
    """The hours a month's pay is for: the month's days (Payroll Settings'
    Days in a Pay Month, which the Overtime Slip divides by too; 26 where
    none is given) of a day's hours. A day's hours are Payroll Settings'
    Hours in a Pay Day, Luuka's 8, where given; else the shift's standard
    hours, ten where the shift gives none."""
    standard, days, day_hours = _number(standard_hours), _number(days), _number(day_hours)
    if day_hours <= 0:
        day_hours = standard if standard > 0 else STANDARD_HOURS_PER_DAY
    return (days if days > 0 else DAYS_PER_MONTH) * day_hours


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def hourly_rate(monthly_base, hours_per_month=HOURS_PER_MONTH):
    """An hour of ordinary pay, out of the monthly base."""
    if not monthly_base or not hours_per_month:
        return 0.0
    return round(float(monthly_base) / float(hours_per_month), 4)


def amount(hours, rate, multiplier):
    """What those hours cost at that rate."""
    if not (hours and rate and multiplier):
        return 0.0
    return round(float(hours) * float(rate) * float(multiplier), 2)


def priced(rows, rates, kind, types=None, grosses=None, standards=None, kinds=None, departments=None, days=None,
           day_hours=None):
    """Price a request's rows. rates: {employee: monthly base}, which an
    hour of ordinary pay is worked out of; grosses: {employee: monthly
    gross}, which a type's gross line is compared with; standards:
    {employee: the standard hours of their shift}, the day that hour is
    divided out of where no day_hours are given; days and day_hours: the
    month's days and a day's hours (hours_per_month); kinds: {employee:
    what sort of day it is for them}, since one person's rest day is
    another's working day. `kind` is the sheet's, for anybody not in
    `kinds`.

    types: {Overtime Type name: its row}. Each person is priced under the
    type that lists them (person_type), at its rate for their day, with
    departments: {employee: department} saying which types leave them out.
    Somebody no type is open to is priced at nothing, and the row says why
    ("not_eligible"). With no types given, every day is priced at the Act's
    floor.

    A row whose employee has no base yet is priced at nothing and says so,
    rather than being dropped: HR are checking the cost, and a line they
    cannot see is worse than a line that reads zero.
    """
    out, total, unpriced = [], 0.0, []
    for row in rows or []:
        base = rates.get(row.get("employee"))
        day = (kinds or {}).get(row.get("employee")) or kind
        named, why = person_type((grosses or {}).get(row.get("employee")), types, row.get("employee"),
                                 (departments or {}).get(row.get("employee")))
        own = 0.0 if why else multiplier_for(day, (types or {}).get(named) if named else None)
        rate = hourly_rate(base, hours_per_month((standards or {}).get(row.get("employee")), days, day_hours))
        cost = amount(row.get("hours"), rate, own)
        if not rate:
            unpriced.append(row.get("employee_name") or row.get("employee"))
        out.append(dict(row, hourly_rate=rate, multiplier=own, amount=cost, day_kind=day, overtime_type=named,
                        not_eligible=why))
        total += cost
    return {"rows": out, "total": round(total, 2), "unpriced": unpriced}


def over_the_cap(hours, cap):
    """Frappe HR's Overtime Type carries a ceiling. A request over it is
    not refused here — the Act allows it with consent — but it is said."""
    if not cap:
        return False
    return float(hours or 0) > float(cap)


def cost_check_errors(facts):
    """What HR must have in front of them before the cost is accepted."""
    errors = []
    if facts.get("status") != "Authorised":
        errors.append("Overtime is costed once the authorising officer has signed it.")
    if not (facts.get("rows") or []):
        errors.append("There is nobody on the request to cost.")
    if facts.get("not_eligible"):
        errors.extend(facts["not_eligible"])
    if facts.get("unpriced"):
        errors.append("There is no salary on record for %s, so this overtime cannot be costed. "
                      "Assign their salary structure first." % _and(facts["unpriced"]))
    return errors


def payroll_errors(facts):
    """And before it is passed on to be paid. rows carry "attendance" (the
    day's, if any), "status" (what it reads), "absent" (it reads absent)
    and "clocked_in" (it has a clock-in all the same). Overtime does not
    sit on a day the attendance says was not worked: the day would be
    docked and its overtime paid. Nor on any day not marked Present, which
    Frappe HR's Overtime Slip does not read: the hours would be written
    down and never paid."""
    errors = []
    if facts.get("status") != "Costed":
        errors.append("Overtime reaches payroll after HR have checked what it costs.")
    missing = [row.get("employee_name") or row.get("employee") for row in facts.get("rows") or []
               if not row.get("attendance")]
    if missing:
        errors.append("There is no attendance for %s on that day, so the hours have nothing to "
                      "sit on. Mark their attendance first." % _and(missing))
    absent = [row for row in facts.get("rows") or [] if row.get("attendance") and row.get("absent")]
    never = [row.get("employee_name") or row.get("employee") for row in absent if not row.get("clocked_in")]
    half = [row.get("employee_name") or row.get("employee") for row in absent if row.get("clocked_in")]
    if never:
        errors.append("%s did not clock in on that day and the attendance reads absent. Correct the "
                      "attendance, or amend the sheet without them." % _and(never))
    if half:
        errors.append("%s clocked in on that day with no clock-out, so the attendance reads absent. "
                      "Correct the attendance first." % _and(half))
    other = ["%s (%s)" % (row.get("employee_name") or row.get("employee"), row.get("status"))
             for row in facts.get("rows") or []
             if row.get("attendance") and not row.get("absent") and row.get("status") not in (None, "", PAID_ON)]
    if other:
        errors.append("Overtime is paid on a day the attendance reads %s, which it does not for %s. Correct the "
                      "attendance first." % (PAID_ON, _and(other)))
    return errors


# what each request not yet with payroll waits for
NEXT_STEP = {"Draft": "Submit", "Requested": "Approval by the authorising officer", "Authorised": "Approval by HR",
             "Costed": "Send to Payroll"}


def waiting(requests):
    """Of an employee's overtime requests, those whose hours are not on the
    attendance yet, oldest first, each with the step it waits for:
    [{"name", "overtime_date", "hours", "status", "next"}]. One sent to
    payroll, rejected or cancelled is not waiting for anything.

    requests: [{"name", "overtime_date", "hours", "status"}]."""
    out = []
    for request in requests or []:
        status = request.get("status") or "Draft"
        if status not in NEXT_STEP:
            continue
        out.append({"name": request.get("name"), "overtime_date": request.get("overtime_date"),
                    "hours": float(request.get("hours") or 0), "status": status, "next": NEXT_STEP[status]})
    return sorted(out, key=lambda row: (str(row["overtime_date"]), str(row["name"])))


# the one attendance status Frappe HR's Overtime Slip reads hours from
PAID_ON = "Present"
# overtime the clock shows within this of what was authorised is paid in
# full: a quarter of an hour, the grace a shift gives a late arrival
CLOCK_TOLERANCE_HOURS = 0.25


def worked_overtime(kind, working_hours, standard_hours=STANDARD_HOURS_PER_DAY):
    """The overtime the clock shows for a day it measured: the hours past
    the shift's standard ones on a working day, and every hour on a rest
    day, a public holiday or a day of leave."""
    hours = max(float(working_hours or 0), 0.0)
    if kind == WEEKDAY:
        return round(max(hours - float(standard_hours or STANDARD_HOURS_PER_DAY), 0.0), 2)
    return round(hours, 2)


def clock_hours(worked, minimum_minutes=0, step_minutes=0, cap=0):
    """The overtime to request for what the clock shows on a day: nothing
    under the least that counts, counted down to whole steps, and never
    past the type's ceiling for a day.

    worked: the overtime the clock shows, in hours (worked_overtime)."""
    minutes = max(float(worked or 0), 0.0) * 60
    if minutes + 1e-6 < float(minimum_minutes or 0):
        return 0.0
    step = float(step_minutes or 0)
    if step > 0:
        minutes = int((minutes + 1e-6) // step) * step
    hours = minutes / 60
    if cap and float(cap) > 0:
        hours = min(hours, float(cap))
    return round(hours, 2)


def clock_sheets(lines):
    """The requests to raise for a day's overtime by the clock: one for each
    requester and section, people in the order given.

    lines: [{"employee", "employee_name", "hours", "requester", "branch",
    "department", "company"}]. Returns [{"requester", "branch",
    "department", "company", "employees": [{"employee", "employee_name",
    "hours"}]}]. Somebody with nobody to name as requester is left out:
    a request has to be somebody's."""
    sheets, order = {}, []
    for line in lines or []:
        if not line.get("employee") or not line.get("requester") or float(line.get("hours") or 0) <= 0:
            continue
        key = (line["requester"], line.get("branch"), line.get("department"), line.get("company"))
        if key not in sheets:
            sheets[key] = []
            order.append(key)
        sheets[key].append({"employee": line["employee"], "employee_name": line.get("employee_name"),
                            "hours": float(line["hours"])})
    return [{"requester": key[0], "branch": key[1], "department": key[2], "company": key[3], "employees": sheets[key]}
            for key in order]


def payable_hours(authorised, worked=None):
    """What is paid: the hours authorised, up to the hours the clock shows.
    Nobody is paid for overtime the clock says they did not work, and
    nobody for more than was authorised. `worked` is None for a day the
    clock did not measure (marked by hand, or no clock-out): then what was
    authorised stands, and the row says the clock was not asked."""
    authorised = max(float(authorised or 0), 0.0)
    if worked is None:
        return round(authorised, 2)
    worked = max(float(worked), 0.0)
    if worked >= authorised - CLOCK_TOLERANCE_HOURS:
        # a clock-out a few minutes before the hour is not docked
        return round(authorised, 2)
    return round(worked, 2)


def reject_errors(status, reason):
    """An overtime sheet is refused while it is still being decided, and
    with the reason. One already with the payroll is on the attendance and
    on a slip: it is cancelled, not refused."""
    errors = []
    if status not in ("Requested", "Authorised", "Costed"):
        errors.append("Overtime is refused before it reaches the payroll, not %s." % (
            "once it is there" if status == "Sent to Payroll" else "while it is %s" % (status or "a draft")))
    if not str(reason or "").strip():
        errors.append("Say why the overtime is refused.")
    return errors


def attendance_update(row, overtime_type, standard_hours=STANDARD_HOURS_PER_DAY, hours=None):
    """What goes onto the employee's Attendance row so Frappe HR's own
    Overtime Slip picks the hours up: their Overtime Type, as person_type
    chose it, the duration paid (`hours`, else what was authorised), and
    the standard day it is measured against."""
    return {"overtime_type": overtime_type,
            "actual_overtime_duration": float(row.get("hours") or 0) if hours is None else float(hours),
            "standard_working_hours": float(standard_hours)}


def slip_window(cycle_from, cycle_to):
    """One slip per employee per attendance cycle, so the dates it covers
    are the cycle's own (attendance_rules.cycle_window)."""
    return {"start_date": cycle_from, "end_date": cycle_to}


def _and(items):
    items = [str(item) for item in items]
    if len(items) == 1:
        return items[0]
    return "%s and %s" % (", ".join(items[:-1]), items[-1])
