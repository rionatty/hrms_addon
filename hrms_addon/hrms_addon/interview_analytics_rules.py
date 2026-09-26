# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The interview reports' arithmetic: how each panel member scores against
their colleagues on the same candidates, how many pass each round, and how
long a hire takes.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_interview_reports.py exercises it without a bench. The three
Script Reports (report/interviewer_calibration, report/interview_pass_rate,
report/time_to_hire) read the documents and hand them here.
"""

import datetime

# no-shows and withdrawals (interview_rules.ABSENT)
ABSENT = ("No-Show", "Withdrew")


def calibration(sheets):
    """Each panel member against the colleagues who scored the same candidates.

    sheets: submitted score sheets (interviewer, interview, percent,
    recommendation). Returns one row per interviewer, by user: sheets, their
    average %, the colleagues' average % on the interviews they shared
    (None where nobody else scored), the difference there (above 0: they mark
    higher than their colleagues), compared (the interviews shared), and the
    shares of their recommendations that were Offer and Reject.
    """
    by_interview = {}
    for sheet in sheets or ():
        if _get(sheet, "interviewer") and _get(sheet, "interview"):
            by_interview.setdefault(_get(sheet, "interview"), []).append(sheet)
    people = {}
    for panel in by_interview.values():
        for sheet in panel:
            me = people.setdefault(_get(sheet, "interviewer"),
                                   {"own": [], "pairs": [], "offer": 0, "reject": 0, "recommended": 0})
            own = float(_get(sheet, "percent") or 0)
            me["own"].append(own)
            others = [float(_get(other, "percent") or 0) for other in panel if other is not sheet]
            if others:
                me["pairs"].append((own, sum(others) / len(others)))
            recommendation = _get(sheet, "recommendation") or ""
            if recommendation:
                me["recommended"] += 1
                me["offer"] += recommendation == "Offer"
                me["reject"] += recommendation == "Reject"
    rows = []
    for interviewer in sorted(people):
        me = people[interviewer]
        shared_own, others = _mean([own for own, _ in me["pairs"]]), _mean([mark for _, mark in me["pairs"]])
        rows.append({
            "interviewer": interviewer,
            "sheets": len(me["own"]),
            "average": _mean(me["own"]),
            "others_average": others,
            "difference": round(shared_own - others, 2) if me["pairs"] else None,
            "compared": len(me["pairs"]),
            "offer_share": _share(me["offer"], me["recommended"]),
            "reject_share": _share(me["reject"], me["recommended"]),
        })
    return rows


def pass_rates(interviews):
    """How each round went, per opening and round.

    interviews: (job_opening, interview_type, round, status, docstatus,
    attendance), cancelled documents left out by the caller. Returns rows by
    opening, then round: booked, attended, absent (a no-show or a
    withdrawal), cleared, rejected, awaiting (held, not yet decided), and the
    pass rate, cleared over those decided (None before any is).
    """
    groups = {}
    for row in interviews or ():
        key = (_get(row, "job_opening") or "", _int(_get(row, "round")), _get(row, "interview_type") or "")
        group = groups.setdefault(key, {"booked": 0, "attended": 0, "absent": 0, "cleared": 0, "rejected": 0,
                                        "awaiting": 0})
        group["booked"] += 1
        status, docstatus = _get(row, "status"), _int(_get(row, "docstatus"))
        if _get(row, "attendance") in ABSENT or (status == "Cancelled" and docstatus == 0):
            group["absent"] += 1
            continue
        group["attended"] += 1
        if docstatus == 1 and status == "Cleared":
            group["cleared"] += 1
        elif docstatus == 1 and status == "Rejected":
            group["rejected"] += 1
        else:
            group["awaiting"] += 1
    rows = []
    for (opening, number, interview_type), group in sorted(groups.items()):
        rows.append(dict(group, job_opening=opening, round=number, interview_type=interview_type,
                         pass_rate=_share(group["cleared"], group["cleared"] + group["rejected"])))
    return rows


def hire_timeline(applied_on, first_interview, offer_date, joined_on):
    """Days from the application to the first interview, to the offer and to
    joining (None where a step has not happened)."""
    start = _date(applied_on)
    return {
        "days_to_interview": _days(start, first_interview),
        "days_to_offer": _days(start, offer_date),
        "days_to_join": _days(start, joined_on),
    }


def averages(rows, fields):
    """{field: the average of the rows' values that are set, None where none is}."""
    return {field: _mean([row.get(field) for row in rows or () if row.get(field) is not None]) for field in fields}


def _days(start, end):
    end = _date(end)
    return (end - start).days if start and end else None


def _date(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _mean(values):
    values = [float(value) for value in values or () if value is not None]
    return round(sum(values) / len(values), 2) if values else None


def _share(part, whole):
    return round(part * 100.0 / whole, 2) if whole else None


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
