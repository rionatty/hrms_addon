# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The desk home's panels below what waits for the user: the dashboards
Luuka asked for on 20 Oct 2026 ("on the home dashboard wich other dasboard
can we add, please be smart"), built on 21 Oct ("lets build the dasboard
now").

No Frappe import, like the other *_rules.py modules, so
scripts/verify_home_panels.py checks it without a bench. home_panels.py
reads the site and public/js/hrms_addon_home.js draws the panels.

  payroll      Payroll Readiness: the pay period's steps, each turning green
               as it is done; on top from the 18th to the 25th
  plants       Plants at a Glance: each plant's people today and its
               overtime this period; it takes the place of Today
  output       Output and Labour Cost: metres and per meter pay by plant,
               with overtime hours and cost, against the period before
  movement     Workforce Movement: joiners and leavers by month, turnover,
               and the headcount by status
  deadlines    Deadlines: probations, contracts, clearances, settlements,
               suspensions and documents coming due
  recruitment  Recruitment Pipeline: requisitions through to offers, the
               openings that have waited longest, this week's interviews
  data_health  Data Health: employee records missing what payroll and the
               clock need

WHO SEES WHICH

Each panel shows to the roles it is for (PANELS), and only where Theme
Settings have not switched it off. Payroll is the HR Manager's and the
Payroll Officer's; the plants and the movement are HR's and management's;
the output is management's and payroll's; the deadlines, recruitment and
data health are HR's. Money is shown only to MONEY_ROLES, and only as a
company's or a plant's total: no panel shows anybody's own pay.
"""

import datetime

PAYROLL, PLANTS, OUTPUT, MOVEMENT = "payroll", "plants", "output", "movement"
DEADLINES, RECRUITMENT, DATA_HEALTH = "deadlines", "recruitment", "data_health"

HR_ROLES = ("HR Manager", "HR User", "System Manager")
# the company's management: the read-only management view and the two who sign for the company
EXECUTIVE_ROLES = ("Executive Director", "General Manager", "Management Viewer")
PAYROLL_ROLES = ("HR Manager", "Payroll Officer", "System Manager")
# money as a plant's or the company's total, never a person's
MONEY_ROLES = ("HR Manager", "Payroll Officer", "System Manager", "Executive Director", "General Manager")

# (key, title, the Theme Settings switch, the roles it shows to), in the order the desk draws them
PANELS = (
    (PAYROLL, "Payroll Readiness", "home_payroll", PAYROLL_ROLES),
    (PLANTS, "Plants at a Glance", "home_plants", HR_ROLES + EXECUTIVE_ROLES),
    (OUTPUT, "Output and Labour Cost", "home_output", PAYROLL_ROLES + EXECUTIVE_ROLES),
    (MOVEMENT, "Workforce Movement", "home_movement", HR_ROLES + EXECUTIVE_ROLES),
    (DEADLINES, "Deadlines", "home_deadlines", HR_ROLES),
    (RECRUITMENT, "Recruitment Pipeline", "home_recruitment", HR_ROLES),
    (DATA_HEALTH, "Data Health", "home_data_health", HR_ROLES),
)
SWITCHES = tuple(switch for _key, _title, switch, _roles in PANELS)
TITLES = {key: title for key, title, _switch, _roles in PANELS}

# Payroll Readiness sits on top, beside what waits for the user, from the 18th to the 25th: the week before
# the period closes, when its steps are due
TOP_FROM, TOP_TO = 18, 25

# how long a user's panels are kept before they are read again
CACHE_SECONDS = 300


def switched_on(stored):
    """The switches Theme Settings hold, as on or off. stored: {fieldname:
    value} as the Single stores it; a switch never saved is on, as its
    field's default says."""
    stored = stored or {}
    out = {}
    for switch in SWITCHES:
        value = stored.get(switch)
        out[switch] = True if value is None or value == "" else bool(int(value))
    return out


def panels_for(roles, switches=None):
    """The panels a user's desk has, in the desk's order: those their roles
    are for that Theme Settings have not switched off. switches as
    switched_on gives them; none given are all on."""
    roles = set(roles or ())
    switches = switches if switches is not None else switched_on({})
    return [key for key, _title, switch, allowed in PANELS if roles & set(allowed) and switches.get(switch, True)]


def money_for(roles):
    """Whether money is shown to the user at all."""
    return bool(set(roles or ()) & set(MONEY_ROLES))


def payroll_on_top(today):
    """Payroll Readiness sits on top from the 18th to the 25th."""
    return TOP_FROM <= today.day <= TOP_TO


# ── Payroll Readiness ─────────────────────────────────────────────────
# The period is the one that ends in this month, the 26th to the 25th, so the payroll work after the 25th (the
# entry, the slips, the bank) is still counted against it. Each step is due so many days after the period's
# last day; one not done by then is late. (key, what it is called, days after the period it is due by)
STEPS = (
    ("clock", "Attendance from the clock", 1),
    ("overtime", "Overtime approved", 1),
    ("output", "Output pay runs", 2),
    ("advances", "Advances and recoveries", 0),
    ("drafted", "Payroll entry made", 2),
    ("slips", "Salary slips submitted", 5),
    ("bank", "Salaries sent to the bank", 6),
)
DONE, OPEN, LATE, TODO, NONE = "done", "open", "late", "todo", "none"
# what a step's facts are where they could not be read (home._or's fallback)
UNREADABLE = "unreadable"
# a clock not read for this long is failing (biotime.ALERT_AFTER_HOURS)
CLOCK_STALE_HOURS = 3
# a punch the clock read and could not place on anybody's day (Attendance Device Log)
UNPLACED_PUNCHES = ("Failed", "Unknown Employee")
# an Overtime Request still waiting for a decision, and one approved but not yet on the attendance
OVERTIME_WAITING = ("Draft", "Requested", "Authorised")
OVERTIME_APPROVED = "Costed"
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def _plural(number, one, many=None):
    return "%d %s" % (number, one if number == 1 else (many or one + "s"))


def _clock(fact, today, start, end, now):
    """The BioTime clock: read lately, without an error, and past the period's last day once it is over.
    fact: {"enabled", "last_success", "error", "unplaced" (punches of the period it could not place)}."""
    target = {"route": ["Form", "BioTime Server"]}
    if not fact.get("enabled"):
        return {"done": False, "started": False, "note": "The clock is not switched on", **target}
    last = fact.get("last_success")
    if isinstance(last, str):
        try:
            last = datetime.datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last = None
    stale = not last or (now is not None and (now - last).total_seconds() > CLOCK_STALE_HOURS * 3600)
    unplaced = int(fact.get("unplaced") or 0)
    tail = " · %s not placed" % _plural(unplaced, "punch", "punches") if unplaced else ""
    if fact.get("error"):
        return {"done": False, "started": True, "urgent": True, "note": "The last read failed" + tail, **target}
    if stale:
        when = last.strftime("%d %b %H:%M") if last else "never"
        return {"done": False, "started": True, "urgent": True, "note": "Not read since %s%s" % (when, tail), **target}
    if today > end:
        past = last.date() > end
        said = ("Read past %s" if past else "Not read past %s yet") % end.strftime("%d %b")
        return {"done": past and not unplaced, "started": True, "note": said + tail, **target}
    return {"done": False, "started": True, "note": "Read at %s%s" % (last.strftime("%H:%M"), tail), **target}


def _overtime(fact, today, start, end, now):
    """Every request of the period decided and on the attendance, and every Overtime Slip of it submitted.
    fact: {"total", "waiting", "approved", "slips" (slips of the period still in draft)}."""
    total, waiting = int(fact.get("total") or 0), int(fact.get("waiting") or 0)
    approved, slips = int(fact.get("approved") or 0), int(fact.get("slips") or 0)
    target = {"route": ["List", "Overtime Request"],
              "filters": {"overtime_date": ["between", [str(start), str(end)]]}}
    if not total and not slips:
        return {"done": True, "started": False, "note": "No overtime this period", **target}
    said = []
    if waiting:
        said.append("%d waiting for approval" % waiting)
    if approved:
        said.append("%d approved, not on the attendance yet" % approved)
    if slips:
        said.append(_plural(slips, "slip") + " in draft")
    if waiting:
        target["filters"]["status"] = ["in", list(OVERTIME_WAITING)]
    return {"done": not said, "started": True,
            "note": " · ".join(said) or "All %d approved and on the slips" % total, **target}


def _output(fact, today, start, end, now):
    """A submitted Output Pay Run for each plant and section that has output in the period, and no report of it
    left out of one. fact: {"needed": ["Kawempe Per Meter", ...], "paid": [...], "unpaid_reports"}."""
    needed, paid = list(fact.get("needed") or []), set(fact.get("paid") or [])
    loose = int(fact.get("unpaid_reports") or 0)
    target = {"route": ["List", "Output Pay Run"],
              "filters": {"year": end.year, "month": MONTHS[end.month - 1]}}
    if not needed:
        return {"done": True, "started": False, "note": "No output to pay this period", **target}
    left = [name for name in needed if name not in paid]
    note = "%d of %d paid" % (len(needed) - len(left), len(needed))
    if left:
        note += " · %s%s to go" % (", ".join(left[:2]), " and %d more" % (len(left) - 2) if len(left) > 2 else "")
    if loose:
        note += " · %s not in a run" % _plural(loose, "report")
    return {"done": not left and not loose, "started": len(left) < len(needed), "note": note, **target}


def _advances(fact, today, start, end, now):
    """The month's salary advance run made and paid, and every recovery of the period on the payroll.
    fact: {"run": None, "draft", "submitted" or "paid", "unposted"}."""
    run, unposted = fact.get("run"), int(fact.get("unposted") or 0)
    target = {"route": ["List", "Salary Advance Processing"],
              "filters": {"year": end.year, "month": MONTHS[end.month - 1]}}
    said = {None: "No advance run this month", "draft": "The advance run is in draft",
            "submitted": "The advance run waits for Finance to pay it", "paid": "The advance run is paid"}[run]
    if unposted:
        said += " · %s not on the payroll" % _plural(unposted, "recovery", "recoveries")
    return {"done": run == "paid" and not unposted, "started": run is not None, "note": said, **target}


def _drafted(fact, today, start, end, now):
    """A Payroll Entry for the period. fact: {"entries": [{"name", "docstatus", "status", "error"}]}."""
    entries = list(fact.get("entries") or [])
    target = {"route": ["List", "Payroll Entry"], "filters": {"start_date": str(start), "end_date": str(end)}}
    failed = [entry for entry in entries if entry.get("status") == "Failed"]
    if failed:
        return {"done": False, "started": True, "urgent": True, "note": "A payroll entry failed", **target}
    if not entries:
        return {"done": False, "started": False, "note": "Not made yet", **target}
    return {"done": True, "started": True, "note": _plural(len(entries), "entry", "entries") + " made", **target}


def _slips(fact, today, start, end, now):
    """Every Payroll Entry of the period submitted, with its slips."""
    entries = list(fact.get("entries") or [])
    target = {"route": ["List", "Salary Slip"], "filters": {"start_date": str(start), "end_date": str(end)}}
    if not entries:
        return {"done": False, "started": False, "note": "No payroll entry yet", **target}
    submitted = [entry for entry in entries if entry.get("docstatus") == 1 and entry.get("slips_submitted")]
    made = [entry for entry in entries if entry.get("docstatus") == 1]
    if len(submitted) == len(entries):
        return {"done": True, "started": True, "note": "Submitted", **target}
    note = "Slips made, not yet submitted" if made else "The entry is not submitted yet"
    return {"done": False, "started": bool(made), "note": note, **target}


def _bank(fact, today, start, end, now):
    """The bank entry made from each Payroll Entry and submitted. fact: {"entries", "paid" (entries with one)}."""
    entries = list(fact.get("entries") or [])
    paid = int(fact.get("paid") or 0)
    target = {"route": ["List", "Journal Entry"], "filters": {"voucher_type": "Bank Entry"}}
    if not entries:
        return {"done": False, "started": False, "note": "No payroll entry yet", **target}
    if paid >= len(entries):
        return {"done": True, "started": True, "note": "Bank entry submitted", **target}
    return {"done": False, "started": bool(paid), "note": "%d of %d paid" % (paid, len(entries)), **target}


STEP_READERS = {"clock": _clock, "overtime": _overtime, "output": _output, "advances": _advances,
                "drafted": _drafted, "slips": _slips, "bank": _bank}


def payroll_steps(facts, today, start, end, now=None):
    """Payroll Readiness: each step of the period with where it stands. facts: {step key: what the site says,
    or None where the user may not read it}. A step is done, late (not done and past its day, or failing),
    under way, or not started; one the user may not read says so and counts for nothing."""
    out = []
    for key, label, after in STEPS:
        fact = (facts or {}).get(key)
        if fact is None or fact.get(UNREADABLE):
            out.append({"key": key, "label": label, "state": NONE,
                        "note": "Not open to you" if fact is None else "Could not be read"})
            continue
        read = STEP_READERS[key](fact, today, start, end, now)
        due = end + datetime.timedelta(days=after)
        if read["done"]:
            state = DONE
        elif read.get("urgent") or today > due:
            state = LATE
        else:
            state = OPEN if read["started"] else TODO
        row = {"key": key, "label": label, "state": state, "note": read["note"], "route": read.get("route")}
        if read.get("filters"):
            row["filters"] = read["filters"]
        out.append(row)
    return out


def payroll_note(steps, start, end):
    """What the panel's heading says: the period, and how many of its steps are done."""
    counted = [step for step in steps if step["state"] != NONE]
    done = sum(1 for step in counted if step["state"] == DONE)
    return "%s to %s · %d of %d done" % (start.strftime("%d %b"), end.strftime("%d %b"), done, len(counted))


# ── Deadlines ─────────────────────────────────────────────────────────
# what comes due, looked for from so many days back (still undone) to so many days ahead
DEADLINES_BACK = 60
PROBATION_AHEAD, CONTRACT_AHEAD, CLEARANCE_AHEAD = 30, 60, 30
SETTLEMENT_AHEAD, SUSPENSION_AHEAD, DOCUMENT_AHEAD = 30, 14, 60
DEADLINES_SHOWN = 8
DOCUMENT_BACK = 30
DECIDED_PROBATION = ("Confirmed", "Not Confirmed")
# a contract nobody has decided: still running, or past its end with no renewal (contract_rules)
CONTRACT_UNDECIDED = ("Active", "Expiring Soon", "Expired")
# a settlement the Executive Director has approved that payroll has not scheduled (settlement_approval)
SETTLEMENT_WAITING = "Pending Payroll"
# a suspension approved or under way (suspension_rules)
SUSPENSION_RUNNING = ("Approved", "In Progress")
# each kind of deadline: (key, what a row says, what the heading counts it as)
DEADLINE_KINDS = (
    ("probation", "Probation ends", "probation"),
    ("contract", "Contract ends", "contract"),
    ("clearance", "Clearance pending", "clearance"),
    ("settlement", "Settlement not paid", "settlement"),
    ("suspension", "Back from suspension", "suspension"),
    ("document", "%s expires", "document"),
)


def window(today, ahead, back=DEADLINES_BACK):
    """(from, to) of what a kind of deadline looks at."""
    return today - datetime.timedelta(days=back), today + datetime.timedelta(days=ahead)


def due_words(today, day):
    """How a deadline's day is said: today, tomorrow, in 5 days, or how late it is."""
    gap = (day - today).days
    if gap < 0:
        return "overdue by %s" % _plural(-gap, "day")
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    return "in %d days" % gap


def due_band(today, day):
    gap = (day - today).days
    return "overdue" if gap < 0 else "today" if gap == 0 else "soon" if gap <= 7 else "later"


def deadlines(found, today, shown=DEADLINES_SHOWN):
    """What comes due, the longest overdue first and then the nearest: rows the home lists, and a count of each
    kind for the heading. found: [{"kind", "day", "who", "doctype", "docname", "what" (a document's type)}]."""
    labels = {key: label for key, label, _counted in DEADLINE_KINDS}
    rows, counts = [], {}
    for item in found or []:
        day = _day(item.get("day"))
        kind = item.get("kind")
        if not day or kind not in labels:
            continue
        label = labels[kind] % (item.get("what") or "Document") if "%s" in labels[kind] else labels[kind]
        rows.append({"title": "%s: %s" % (label, item.get("who") or ""), "doctype": item.get("doctype"),
                     "docname": item.get("docname"), "when": due_words(today, day), "band": due_band(today, day),
                     "date": str(day), "kind": kind})
        counts[kind] = counts.get(kind, 0) + 1
    rows.sort(key=lambda row: (row["date"], row["title"]))
    plural = {"probation": ("probation", "probations"), "contract": ("contract", "contracts"),
              "clearance": ("clearance", "clearances"), "settlement": ("settlement", "settlements"),
              "suspension": ("suspension", "suspensions"), "document": ("document", "documents")}
    note = " · ".join("%d %s" % (counts[key], plural[key][0] if counts[key] == 1 else plural[key][1])
                      for key, _label, _counted in DEADLINE_KINDS if counts.get(key))
    return {"rows": rows[:shown], "note": note, "total": len(rows)}


def probation_open(row):
    """A probation still to be decided: confirmed or not confirmed is decided; an extension runs to its new date."""
    return (row.get("custom_probation_status") or "") not in DECIDED_PROBATION


# ── Recruitment Pipeline ──────────────────────────────────────────────
# an applicant still in the running, and one shortlisted; an interview held and one still to come; a live offer
APPLYING = ("Open", "Replied", "Hold")
SHORTLISTED = "Shortlisted"
INTERVIEWED = ("Under Review", "Cleared")
INTERVIEW_COMING = ("Pending", "Under Review")
OFFER_LIVE = "Awaiting Response"
# a requisition filled within this many days counts toward the time to fill
FILLED_WITHIN = 180
PIPELINE_SHOWN = 3


def week_of(today):
    """(Monday, Sunday) of today's week."""
    monday = today - datetime.timedelta(days=today.weekday())
    return monday, monday + datetime.timedelta(days=6)


def pipeline(facts, today):
    """The recruitment pipeline: each stage's figure, the figures about it, and the rows under it.
    facts: {"requisitions" (awaiting approval), "openings": [{"name", "job_title", "posted_on"}],
    "applicants", "shortlisted", "interviewed", "offered", "filled": [days to fill], "interviews":
    [{"name", "job_applicant", "applicant_name", "scheduled_on", "opening"}]}."""
    openings = list(facts.get("openings") or [])
    stages = [
        ("requisitions", "Requisitions in approval", facts.get("requisitions"), ["List", "Job Requisition"],
         {"status": "Pending"}),
        ("openings", "Openings live", len(openings), ["List", "Job Opening"], {"status": "Open"}),
        ("applicants", "Applicants", facts.get("applicants"), ["List", "Job Applicant"],
         {"status": ["in", list(APPLYING)]}),
        ("shortlisted", "Shortlisted", facts.get("shortlisted"), ["List", "Job Applicant"], {"status": SHORTLISTED}),
        ("interviewed", "Interviewed", facts.get("interviewed"), ["List", "Interview"],
         {"status": ["in", list(INTERVIEWED)]}),
        ("offered", "Offers awaiting a reply", facts.get("offered"), ["List", "Job Offer"], {"status": OFFER_LIVE}),
    ]
    out_stages = [{"key": key, "label": label, "value": int(value or 0), "route": route, "filters": filters,
                   "band": "navy"} for key, label, value, route, filters in stages]
    ages = []
    for opening in openings:
        posted = _day(opening.get("posted_on"))
        if posted:
            ages.append(((today - posted).days, opening))
    ages.sort(key=lambda item: (-item[0], str(item[1].get("name"))))
    filled = [float(days) for days in facts.get("filled") or [] if days is not None]
    figures = [
        {"label": "Days open, on average",
         "text": "%d days" % round(sum(age for age, _opening in ages) / len(ages)) if ages else "None open"},
        {"label": "Time to fill",
         "text": "%d days" % round(sum(filled) / len(filled)) if filled else "None filled yet"},
        {"label": "Interviews this week", "value": len(facts.get("interviews") or [])},
    ]
    rows = []
    for interview in sorted(facts.get("interviews") or [], key=lambda row: (str(row.get("scheduled_on")),
                                                                           str(row.get("name"))))[:PIPELINE_SHOWN]:
        day = _day(interview.get("scheduled_on"))
        rows.append({"title": interview.get("applicant_name") or interview.get("job_applicant") or "",
                     "doctype": "Interview", "docname": interview.get("name"),
                     "when": due_words(today, day) if day and day >= today else "held",
                     "band": "today" if day == today else "soon" if day and day > today else "none",
                     "date": str(day) if day else ""})
    longest = [{"title": opening.get("job_title") or opening.get("name"), "doctype": "Job Opening",
                "docname": opening.get("name"), "when": "open %s" % _plural(age, "day"),
                "band": "overdue" if age > 60 else "today" if age > 30 else "none"} for age, opening in
               ages[:PIPELINE_SHOWN]]
    return {"stages": out_stages, "figures": figures, "rows": rows, "longest": longest}


def pipeline_note(facts):
    """The heading's line: the openings, and those applying to them."""
    return "%s · %s" % (_plural(len(facts.get("openings") or []), "opening"),
                        _plural(int(facts.get("applicants") or 0), "applicant"))


def days_to_fill(posted, completed):
    """The days from a requisition's posting to its filling, or None where either is missing."""
    posted, completed = _day(posted), _day(completed)
    if not posted or not completed or completed < posted:
        return None
    return (completed - posted).days


# ── Plants at a Glance ────────────────────────────────────────────────
# somebody whose Employee has no plant
UNPLACED = "No plant"
IN = ("in", "late")


def plants(people, where, overtime=None, clocks=None, punched=None, known=True):
    """Each plant's people today and its overtime this period, the plant with the fewest in first: a plant that
    needs somebody is not hidden by the alphabet. The plant is the Employee's own Branch, as the site has it.

    people: the active employees, [{"name", "branch"}]; where: {employee: where they are today, a key of
    home_rules.WHERE}; overtime: {employee: approved hours this period}; clocks: {plant: how many clocks
    stand there}; punched: the plants whose clocks have sent a punch today. A plant with clocks and no punch
    today is silent: its people cannot be counted in. known is False for somebody who may read neither the
    clock nor the attendance: their plants say nothing of today, rather than a nought that reads as nobody."""
    seats = {}
    for person in people or []:
        plant = person.get("branch") or UNPLACED
        seat = seats.setdefault(plant, {"plant": plant, "staff": 0, "in": 0, "late": 0, "absent": 0, "on_leave": 0,
                                        "not_in": 0, "overtime": 0.0})
        seat["staff"] += 1
        key = (where or {}).get(person.get("name"), "not_in")
        if key in IN:
            seat["in"] += 1
        if key in seat and key != "in":
            seat[key] += 1
        seat["overtime"] += float((overtime or {}).get(person.get("name")) or 0)
    punched = set(punched or ())
    out = []
    for plant, seat in seats.items():
        share = float(seat["in"]) / seat["staff"] if seat["staff"] else 0.0
        seat["overtime"] = round(seat["overtime"], 1)
        seat["silent"] = known and bool((clocks or {}).get(plant)) and plant not in punched
        seat["band"] = "overdue" if seat["silent"] else "today" if share < 0.5 else "good"
        seat["route"] = ["attendance-board"]
        if plant != UNPLACED:
            seat["options"] = {"branch": plant}
        out.append(seat)
    out.sort(key=lambda seat: (float(seat["in"]) / seat["staff"] if seat["staff"] else 1.0, seat["plant"]))
    if not known:
        for seat in out:
            seat.update({"in": None, "late": None, "absent": None, "on_leave": None, "not_in": None, "band": "none"})
    return out


def plants_note(rows):
    """The heading's line: everybody, and how many are in where that is known."""
    staff = sum(row["staff"] for row in rows or [])
    if any(row["in"] is None for row in rows or []):
        return "%s staff" % format(staff, ",")
    present = sum(row["in"] for row in rows or [])
    return "%s staff · %s in" % (format(staff, ","), format(present, ","))


def overtime_hours(lines):
    """{employee: approved overtime hours}: those paid where they are on the attendance, else those authorised."""
    out = {}
    for line in lines or []:
        hours = float((line.get("payable_hours") if line.get("sent") else line.get("hours")) or 0)
        out[line.get("employee")] = out.get(line.get("employee"), 0.0) + hours
    return out


# ── Output and Labour Cost ────────────────────────────────────────────
PER_METER, PER_PIECE = "Per Meter", "Per Piece"
# the ways of being paid by output, each with a run a month at its plant (Employee.custom_pay_category)
OUTPUT_SECTIONS = ("Per Meter", "Per Piece", "Hourly")
# an Overtime Request whose hours are approved: costed, or on the attendance
OVERTIME_COUNTED = ("Costed", "Sent to Payroll")


def same_days_before(start, today):
    """The period before this one, cut to as many days as this one has run: a period part-way through is
    compared with the same part of the last."""
    year, month = (start.year - 1, 12) if start.month == 1 else (start.year, start.month - 1)
    try:
        before = start.replace(year=year, month=month)
    except ValueError:
        before = start.replace(year=year, month=month, day=28)
    return before, before + (today - start)


def output_figures(reports):
    """{plant: {"metres", "pieces", "pay"}} from the submitted Daily Production Reports: the work done in each
    section and what it pays. reports: [{"branch", "section", "total_output", "total_amount"}]."""
    out = {}
    for row in reports or []:
        seat = out.setdefault(row.get("branch") or UNPLACED, {"metres": 0.0, "pieces": 0.0, "pay": 0.0})
        key = "metres" if row.get("section") == PER_METER else "pieces"
        seat[key] += float(row.get("total_output") or 0)
        seat["pay"] += float(row.get("total_amount") or 0)
    return out


def overtime_figures(lines, branches):
    """{plant: {"hours", "cost"}} from the approved overtime's lines, each at its employee's plant. Hours on
    the attendance are those paid; those still to go there, those authorised. lines: [{"employee", "hours",
    "payable_hours", "amount", "sent"}]; branches: {employee: plant}."""
    out = {}
    for line in lines or []:
        seat = out.setdefault((branches or {}).get(line.get("employee")) or UNPLACED, {"hours": 0.0, "cost": 0.0})
        seat["hours"] += float((line.get("payable_hours") if line.get("sent") else line.get("hours")) or 0)
        seat["cost"] += float(line.get("amount") or 0)
    return out


def output_rows(now, before, overtime_now, overtime_before, money):
    """Each plant's output and overtime against the same days of the last period: [{"plant", "figures":
    [{"label", "kind", "value", "before", "direction", "percent"}]}]. kind says how a figure is written
    (count, money, hours); money only where the user may see it."""
    rows = []
    for plant in sorted(set(now) | set(before) | set(overtime_now) | set(overtime_before)):
        made, was = now.get(plant, {}), before.get(plant, {})
        extra, extra_was = overtime_now.get(plant, {}), overtime_before.get(plant, {})
        figures = []
        for key, label in (("metres", "Metres"), ("pieces", "Pieces")):
            if made.get(key) or was.get(key):
                figures.append(dict(change(made.get(key), was.get(key)), label=label, kind="count"))
        if money and (made.get("pay") or was.get("pay")):
            figures.append(dict(change(made.get("pay"), was.get("pay")), label="Output pay", kind="money"))
        figures.append(dict(change(extra.get("hours"), extra_was.get("hours")), label="Overtime", kind="hours"))
        if money:
            figures.append(dict(change(extra.get("cost"), extra_was.get("cost")), label="Overtime cost", kind="money"))
        rows.append({"plant": plant, "figures": figures})
    return rows


def output_note(start, today):
    """The heading's line: the days counted, and what they are set against."""
    return "%s to %s, against the same days last period" % (start.strftime("%d %b"), today.strftime("%d %b"))


# ── Workforce Movement ────────────────────────────────────────────────
MOVEMENT_MONTHS = 6
TURNOVER_MONTHS = 12
LEFT = "Left"


def _month_start(day, back):
    year, month = day.year, day.month - back
    while month < 1:
        year, month = year - 1, month + 12
    return datetime.date(year, month, 1)


def left_when(row):
    """The day somebody left, where the record says they left after it was made: a leaver entered with their
    leaving already behind them (the import's, with a stand-in date) moved nothing that day."""
    if row.get("status") != LEFT:
        return None
    left = _day(row.get("relieving_date"))
    made = _day(row.get("creation"))
    if not left or (made and made > left):
        return None
    return left


def movement(people, counts_as, today, months=MOVEMENT_MONTHS):
    """Joiners and leavers by month, the oldest first, the leavers of the last twelve months against today's
    headcount, and those still on the books by their status.

    people: [{"name", "status", "custom_employee_status", "date_of_joining", "relieving_date", "creation"}];
    counts_as: {status: what Frappe's status it counts as} (employee_status.counts)."""
    starts = [_month_start(today, back) for back in range(months - 1, -1, -1)]
    columns = []
    for index, first in enumerate(starts):
        after = starts[index + 1] if index + 1 < len(starts) else _month_start(today, -1)
        joined = sum(1 for row in people or [] if _day(row.get("date_of_joining"))
                     and first <= _day(row.get("date_of_joining")) < after)
        left = sum(1 for row in people or [] if left_when(row) and first <= left_when(row) < after)
        columns.append({"label": first.strftime("%b"), "month": str(first), "joined": joined, "left": left})
    year_ago = _month_start(today, TURNOVER_MONTHS - 1) - datetime.timedelta(days=1)
    leavers = sum(1 for row in people or [] if left_when(row) and year_ago < left_when(row) <= today)
    on_books = [row for row in people or [] if row.get("status") != LEFT]
    active = sum(1 for row in on_books if row.get("status") == "Active")
    tally = {}
    for row in on_books:
        name = row.get("custom_employee_status") or row.get("status") or "Not set"
        if (counts_as or {}).get(name, row.get("status")) == LEFT:
            continue
        tally[name] = tally.get(name, 0) + 1
    statuses = [{"label": name, "value": value, "band": "good" if (counts_as or {}).get(name) == "Active" else "today",
                 "route": ["List", "Employee"], "filters": {"custom_employee_status": name}}
                for name, value in sorted(tally.items(), key=lambda item: (-item[1], item[0]))]
    rate = round(100.0 * leavers / active, 1) if active else 0.0
    return {"months": columns, "turnover": {"leavers": leavers, "rate": rate, "headcount": active},
            "statuses": statuses}


def movement_note(found):
    """The heading's line: the year's leavers against today's headcount."""
    turnover = found.get("turnover") or {}
    return "%s left in 12 months · %s active" % (format(int(turnover.get("leavers") or 0), ","),
                                                 format(int(turnover.get("headcount") or 0), ","))


# ── Data Health ───────────────────────────────────────────────────────
# Each check of an active employee's record: (key, what it is called, what it stops, how the list is opened
# where a filter can say it, how loudly). The rest open on the employees found.
HEALTH_CHECKS = (
    ("clock", "No clock ID", "They cannot clock in",
     {"attendance_device_id": ["is", "not set"], "custom_automatic_attendance": 0}, "overdue"),
    ("bank", "Paid by bank, no account number", "Their pay has nowhere to go",
     {"salary_mode": "Bank", "bank_ac_no": ["is", "not set"]}, "overdue"),
    ("salary", "No salary structure", "Payroll cannot pay them", None, "overdue"),
    ("nssf", "No NSSF number", "NSSF cannot be filed for them", {"custom_nssf_no": ["is", "not set"]}, "today"),
    ("tin", "No TIN", "PAYE cannot be filed for them", {"custom_tin": ["is", "not set"]}, "today"),
    ("birth", "Birth date to check", "Before 1945, after today, or under 16 when they joined", None, "today"),
    ("twice", "Maybe on the list twice", "The same NIN, NSSF number, or name and birth date", None, "today"),
)
OLDEST_BIRTH_YEAR = 1945
YOUNGEST_AT_JOINING = 16
# who may read an employee's bank fields (security_rules.PRIVILEGED_ROLES): for anybody else they are blank
BANK_ROLES = ("HR Manager", "HR User", "Payroll Officer")
# the most employees a list is opened on by name
OPENED_ON = 500


def _age(born, on):
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def _same(rows, key):
    """Those who share a value of `key` with somebody else."""
    seen = {}
    for row in rows:
        value = key(row)
        if value:
            seen.setdefault(value, []).append(row.get("name"))
    return {name for names in seen.values() if len(names) > 1 for name in names}


def data_health(people, assigned, today, bank_known=True):
    """What the active employees' records are missing, each a row the home lists with how many and the list
    it opens: only the checks that find somebody. people: [{"name", "employee_name", "attendance_device_id",
    "custom_automatic_attendance", "salary_mode", "bank_ac_no", "custom_nssf_no", "custom_tin", "custom_nin",
    "date_of_birth", "date_of_joining"}]; assigned: the employees with a salary structure in force, None where
    the user may not read the assignments; bank_known: whether the user may read the bank fields, which are
    blank for everybody else."""
    found = {key: [] for key, _label, _note, _filters, _band in HEALTH_CHECKS}
    for row in people or []:
        name = row.get("name")
        if not str(row.get("attendance_device_id") or "").strip() and not row.get("custom_automatic_attendance"):
            found["clock"].append(name)
        if bank_known and row.get("salary_mode") == "Bank" and not str(row.get("bank_ac_no") or "").strip():
            found["bank"].append(name)
        if assigned is not None and name not in assigned:
            found["salary"].append(name)
        if not str(row.get("custom_nssf_no") or "").strip():
            found["nssf"].append(name)
        if not str(row.get("custom_tin") or "").strip():
            found["tin"].append(name)
        born, joined = _day(row.get("date_of_birth")), _day(row.get("date_of_joining"))
        if born and (born.year < OLDEST_BIRTH_YEAR or born > today
                     or (joined and _age(born, joined) < YOUNGEST_AT_JOINING)):
            found["birth"].append(name)
    plain = lambda value: "".join(str(value or "").split()).upper()  # noqa: E731
    twice = _same(people or [], lambda row: plain(row.get("custom_nin"))) \
        | _same(people or [], lambda row: plain(row.get("custom_nssf_no"))) \
        | _same(people or [], lambda row: (" ".join(sorted(str(row.get("employee_name") or "").lower().split())),
                                           str(row.get("date_of_birth") or ""))
                if row.get("employee_name") and row.get("date_of_birth") else None)
    found["twice"] = sorted(twice)
    rows = []
    for key, label, note, filters, band in HEALTH_CHECKS:
        names = found[key]
        if not names:
            continue
        opened = dict(filters) if filters else {"name": ["in", sorted(names)[:OPENED_ON]]}
        rows.append({"key": key, "label": label, "note": note, "value": len(names), "band": band,
                     "route": ["List", "Employee"], "filters": dict({"status": "Active"}, **opened)})
    return rows


# ── Where each panel goes ─────────────────────────────────────────────
# HR's desk (home_rules.HR): Plants at a Glance takes the place of Today there
HR_VIEW = "hr"
TOP, SECTIONS, ROW = "top", "sections", "row"


def places(keys, view, today):
    """Each panel of a desk with where it goes: Payroll Readiness on top in its week, Plants at a Glance in
    Today's place on HR's desk, and the rest in the rows under what waits: [{"key", "title", "place"}]."""
    out = []
    for key in keys or []:
        if key == PAYROLL and payroll_on_top(today):
            place = TOP
        elif key == PLANTS and view == HR_VIEW:
            place = SECTIONS
        else:
            place = ROW
        out.append({"key": key, "title": TITLES[key], "place": place})
    return out


def change(now, before):
    """A figure against the period before: {"value", "before", "direction",
    "percent"}. direction is up, down or same; percent is None where there
    was nothing before to compare with."""
    now = float(now or 0)
    before = float(before or 0)
    direction = "up" if now > before else "down" if now < before else "same"
    percent = round(100.0 * (now - before) / before, 1) if before else None
    return {"value": now, "before": before, "direction": direction, "percent": percent}


def _day(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _who(row):
    return row.get("employee_name") or row.get("employee") or row.get("name") or ""
