# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Salary slips shared with the employees before the payroll is run (Luuka,
8 Nov 2026: "need share salary slips with employees before proceeding to
execution. this is to help precheck with employees, it should have bulk
sending and bulk printing").

No Frappe import, like the other *_rules.py modules, so
scripts/verify_slip_share.py checks it without a bench. slip_share.py sends
and prints on the site.

Once a payroll's slips are made, and before they are submitted, HR send
each employee their own slip by email to check, as a Pay Slip PDF marked
"for checking, not yet paid". Whoever has no email gets theirs printed: one
PDF of every slip, or of only those the email could not reach.

A slip is sent once as it stands. Sending again reaches only the slips
changed since (Recreate Salary Slips makes new ones), unless HR ask for all
of them again.
"""

# a slip is printed, and emailed, in Luuka's own Pay Slip
PRINT_FORMAT = "Pay Slip"
# what the payroll's Print Slips may print
ALL, NOT_SENT = "all", "not sent"
PRINTS = (ALL, NOT_SENT)
# no more names than this in the note that says who has no email
NAMES_SAID = 20


def share_errors(run):
    """Whether a payroll's slips may be sent to the employees now: made, and
    not yet submitted. run: docstatus, salary_slips_created,
    salary_slips_submitted."""
    if _int(run.get("salary_slips_submitted")):
        return ["The slips are submitted already: they are shared before the payroll is run, to be checked."]
    if _int(run.get("docstatus")) != 1 or not _int(run.get("salary_slips_created")):
        return ["Create the salary slips first."]
    return []


def recipient(employee):
    """The address an employee's slip goes to: their preferred email, as
    Frappe HR emails a submitted slip, else the user they sign in with."""
    for value in (employee.get("prefered_email"), employee.get("user_id")):
        value = _text(value)
        if "@" in value:
            return value
    return None


def to_send(slips, again=False):
    """The slips to send: every draft not sent since it last changed, or every
    draft when HR send them all again. slips: name, docstatus, modified,
    custom_shared_on."""
    picked = []
    for slip in slips or ():
        if _int(slip.get("docstatus")) != 0:
            continue
        sent = _text(slip.get("custom_shared_on"))[:19]
        if not again and sent and sent >= _text(slip.get("modified"))[:19]:
            continue
        picked.append(slip)
    return picked


def to_print(slips, which):
    """The slips Print Slips puts in its PDF: every slip not cancelled, or
    only those no email took (never sent, or changed since). slips: name,
    docstatus, modified, custom_shared_on."""
    alive = [slip for slip in slips or () if _int(slip.get("docstatus")) < 2]
    if which != NOT_SENT:
        return alive
    return [slip for slip in alive
            if not _text(slip.get("custom_shared_on")) or
            _text(slip.get("custom_shared_on"))[:19] < _text(slip.get("modified"))[:19]]


def subject(period):
    return "Salary slip for %s, to check" % period


def message(name, period, password_policy=None):
    """The email a slip goes with. password_policy: the PDF's password
    format, where Payroll Settings protect a slip."""
    text = ("Dear %s,<br><br>Your salary slip for %s is attached for you to check before the payroll is paid. "
            "If anything on it is wrong, please tell HR before then." % (name, period))
    if password_policy:
        text += "<br><br>The slip is password protected: the password is %s." % password_policy
    return text


def summary(sent, without_email, unchanged, failed):
    """What HR are told once the slips are sent."""
    lines = ["%d salary slip%s sent to the employees to check." % (sent, "" if sent == 1 else "s")]
    if unchanged:
        lines.append("%d had theirs already, unchanged since." % unchanged)
    if failed:
        lines.append("%d could not be sent: see the Error Log." % len(failed))
    if without_email:
        named = ", ".join(without_email[:NAMES_SAID])
        more = len(without_email) - NAMES_SAID
        lines.append("%d have no email: print theirs (Print Slips, those not sent): %s%s."
                     % (len(without_email), named, " and %d more" % more if more > 0 else ""))
    return " ".join(lines)


def _int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value):
    return str(value or "").strip()
