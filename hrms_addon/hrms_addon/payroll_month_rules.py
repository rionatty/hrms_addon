# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The months of a payroll year, each open or closed (payroll_months.py; Luuka,
5 Nov 2026: "when creating for the inetrire year its should break it down with
payroll period so that i can be able to close and open period by default is
should be open, on payroll period ist should list the ones are open").

No Frappe import, like the other *_rules.py modules, so
scripts/verify_payroll_months.py runs it without a bench.

A Payroll Period is Frappe HR's year. Its months are made from its dates when it
is saved (payslip_rules.months_of): the periods that close in it, each named for
the month it closes in, as the slip names it. A month keeps its status however
often the year is saved, and starts open. Whoever closes one is written beside
it, whatever was sent.

A monthly payroll is picked from its company's open months and runs only for one
of them. Nothing is saved, submitted, cancelled or deleted in a closed month, on
a payroll or a salary slip, until it is opened again.
"""

OPEN, CLOSED = "Open", "Closed"
STATUSES = (OPEN, CLOSED)


def rows_for_year(months, sent, stored, user, now):
    """The year's rows: one for each of its months, whatever else was sent. A row's status is what was sent, else what is
    stored, else open; a month just closed says who by and when, and an open one says neither. months: from
    payslip_rules.months_of; sent, stored: the rows as sent and as they were."""
    sent_status = {row.get("period_name"): row.get("status") for row in sent or []}
    was = {row.get("period_name"): row for row in stored or []}
    rows = []
    for month in months or []:
        name = month["period_name"]
        before = was.get(name)
        status = sent_status.get(name) or (before.get("status") if before else None) or OPEN
        if status not in STATUSES:
            status = OPEN
        row = dict(month, status=status, closed_by=None, closed_on=None)
        if before:
            row["name"] = before.get("name")
        if status == CLOSED:
            already = before and before.get("status") == CLOSED
            row["closed_by"] = before.get("closed_by") if already else user
            row["closed_on"] = before.get("closed_on") if already else now
        rows.append(row)
    return rows


def dropped_closed(months, stored):
    """The closed months that dates like these would lose, by name."""
    kept = {month["period_name"] for month in months or []}
    return [row.get("period_name") for row in stored or []
            if row.get("status") == CLOSED and row.get("period_name") not in kept]


def listed(rows):
    """The open months, the first still to run first, as a payroll picks from them."""
    months = sorted((row for row in rows or [] if row.get("status") == OPEN), key=lambda row: row.get("start_date"))
    return [{"name": row.get("period_name"), "start": str(row.get("start_date")), "end": str(row.get("end_date"))}
            for row in months]


def why_closed(name, month):
    """Why nothing can be done in this month, or None."""
    if month and month.get("status") == CLOSED:
        return "%s is closed. Open it in Payroll Period %s first." % (name, month.get("parent"))
    return None


def why_not_open(name, month, company):
    """Why a payroll cannot run for this month, or None."""
    if not month:
        return "%s has no %s to run. Add the year in Payroll Period first." % (company, name)
    return why_closed(name, month)
