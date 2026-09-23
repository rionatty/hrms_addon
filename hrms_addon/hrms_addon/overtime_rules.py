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

WHAT A WEEKDAY PAYS DEPENDS ON THE GROSS

The minutes of 16 and 20 July 2026 (Reward and Compensation, §4.12)
record Luuka's practice: "the overtime multiplier is 1 for gross salaries
above UGX 500,000, 1.5 for those below UGX 500,000, and 2 for public
holidays". So a weekday has two Overtime Types, and each person's hours go
under the one their own gross puts them in — on the attendance the
Overtime Slip reads, so it is what they are paid, not only what the cost
check shows. The 1x is under the Act's 1.5x floor this module was built
to; it is Luuka's minuted practice and it stays a figure on the type,
where it can be changed, not a constant here. So does the line: the
higher earners' type carries it ("For Monthly Gross Above"), and the gross
it is compared with is the one the employee's salary structure works out.
"""

WEEKDAY = "Weekday"
REST_DAY = "Rest Day"
PUBLIC_HOLIDAY = "Public Holiday"
LEAVE_DAY = "Leave Day"
KINDS = (WEEKDAY, REST_DAY, PUBLIC_HOLIDAY, LEAVE_DAY)

# The Employment Act's floor. A type on the site may pay more than this;
# it may not pay less, which is what below_the_act() is for.
ACT_MULTIPLIERS = {WEEKDAY: 1.5, REST_DAY: 2.0, PUBLIC_HOLIDAY: 2.0, LEAVE_DAY: 2.0}

# The names the three Overtime Types are seeded under
TYPE_NAMES = {WEEKDAY: "Weekday Overtime", REST_DAY: "Rest Day Overtime",
              PUBLIC_HOLIDAY: "Public Holiday Overtime", LEAVE_DAY: "Rest Day Overtime"}
# and the weekday type for those whose gross is above the line (§4.12).
# The type is seeded with this line and its multiplier; both are then the
# type's, where HR change them.
GROSS_THRESHOLD = 500000.0
HIGHER_EARNERS = "Weekday Overtime (Above UGX 500,000)"
HIGHER_EARNER_MULTIPLIER = 1.0

# Luuka's month: the attendance cycle runs 26 to 25 and is worked as 26
# days of ten standard hours (attendance_rules.STANDARD_HOURS), which is
# what an hour of pay is divided out of.
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


def type_name_for(kind, gross=None, lines=None):
    """The Overtime Type a day falls under for one person. On a weekday it
    depends on what they earn: of the types with a gross line (lines: {type
    name: monthly gross above}), the one with the highest line their gross
    is above; otherwise the weekday type."""
    if kind == WEEKDAY and gross is not None:
        above = sorted((float(line), name) for name, line in (lines or {}).items()
                       if float(line or 0) > 0 and float(gross or 0) > float(line))
        if above:
            return above[-1][1]
    return TYPE_NAMES.get(kind, TYPE_NAMES[WEEKDAY])


def gross_lines(types):
    """{type name: its monthly gross line}, for the types that have one."""
    return {name: float(row.get("custom_gross_above") or 0) for name, row in (types or {}).items()
            if row and float(row.get("custom_gross_above") or 0) > 0}


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


def below_the_act(kind, multiplier):
    """A rate under the statutory floor is not a policy decision anybody
    is allowed to make quietly."""
    if multiplier in (None, ""):
        return False
    return float(multiplier) < ACT_MULTIPLIERS[kind]


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


def priced(rows, rates, kind, overtime_type=None, types=None, grosses=None):
    """Price a request's rows. rates: {employee: monthly base}, which an
    hour of ordinary pay is worked out of; grosses: {employee: monthly
    gross}, which decides their type.

    types: {Overtime Type name: its row}. Each person is priced under the
    type their own gross puts them in (minutes §4.12); `overtime_type`
    is the day's own type, used where theirs is not on the site.

    A row whose employee has no base yet is priced at nothing and says so,
    rather than being dropped: HR are checking the cost, and a line they
    cannot see is worse than a line that reads zero.
    """
    multiplier = multiplier_for(kind, overtime_type)
    lines = gross_lines(types)
    out, total, unpriced = [], 0.0, []
    for row in rows or []:
        base = rates.get(row.get("employee"))
        theirs = (types or {}).get(type_name_for(kind, (grosses or {}).get(row.get("employee")), lines))
        own = multiplier_for(kind, theirs) if theirs else multiplier
        rate = hourly_rate(base)
        cost = amount(row.get("hours"), rate, own)
        if not rate:
            unpriced.append(row.get("employee_name") or row.get("employee"))
        out.append(dict(row, hourly_rate=rate, multiplier=own, amount=cost))
        total += cost
    return {"rows": out, "total": round(total, 2), "multiplier": multiplier,
            "unpriced": unpriced}


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
    if facts.get("unpriced"):
        errors.append("There is no salary on record for %s, so this overtime cannot be costed. "
                      "Assign their salary structure first." % _and(facts["unpriced"]))
    if not facts.get("cost_centre"):
        errors.append("Say which cost centre carries this overtime.")
    return errors


def payroll_errors(facts):
    """And before it is passed on to be paid."""
    errors = []
    if facts.get("status") != "Costed":
        errors.append("Overtime reaches payroll after HR have checked what it costs.")
    missing = [row.get("employee_name") or row.get("employee") for row in facts.get("rows") or []
               if not row.get("attendance")]
    if missing:
        errors.append("There is no attendance for %s on that day, so the hours have nothing to "
                      "sit on. Mark their attendance first." % _and(missing))
    return errors


def attendance_update(row, kind, standard_hours=STANDARD_HOURS_PER_DAY, gross=None, lines=None):
    """What goes onto the employee's Attendance row so Frappe HR's own
    Overtime Slip picks the hours up: the type their gross puts them in,
    the duration, and the standard day it is measured against."""
    return {"overtime_type": type_name_for(kind, gross, lines),
            "actual_overtime_duration": float(row.get("hours") or 0),
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
