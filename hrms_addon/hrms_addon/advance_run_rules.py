# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Cancelling an advance run: the rules, with no Frappe in them.

A Salary Advance Processing and a Leave Advance Processing each make a bank
entry for Finance, and what they pay goes onto the payroll as deductions.
Those records point at one another while they are submitted, so each has to
come back in its turn: the bank entry, then the advances, then the run.
"""

DRAFT, SUBMITTED, CANCELLED = 0, 1, 2

NOTHING, DELETE, CANCEL, REFUSE = "nothing", "delete", "cancel", "refuse"

SALARY_RUN = "Salary Advance Processing"
LEAVE_RUN = "Leave Advance Processing"

# What a run's own cancel takes back. The form leaves these out of Frappe's
# "Cancel All Documents", which would cancel them before the run and be
# refused by the run they belong to.
TAKEN_BACK = {
    SALARY_RUN: ("Employee Advance", "Journal Entry", "Additional Salary"),
    LEAVE_RUN: ("Leave Advance", "Journal Entry", "Additional Salary"),
}

# What keeps the name of its bank entry. Finance cancel the entry on its
# own; none of these is a document to cancel first.
BANK_ENTRY_KEPT_BY = (SALARY_RUN, LEAVE_RUN, "Leave Advance")


def bank_entry_step(docstatus, may_cancel):
    """What a run's cancel does with its bank entry: a draft is deleted, a
    posted one is cancelled by somebody who may cancel bank entries and
    stops anybody else, and one already cancelled or gone is left."""
    if docstatus is None or int(docstatus) == CANCELLED:
        return NOTHING
    if int(docstatus) == DRAFT:
        return DELETE
    return CANCEL if may_cancel else REFUSE


def first_taken(deductions, on_slips):
    """The first advance a submitted salary slip has taken a recovery of,
    with that slip: (advance, slip), or None.

    deductions  [(additional salary, advance)] in the order to report them
    on_slips    {additional salary: salary slip}
    """
    for deduction, advance in deductions:
        if on_slips.get(deduction):
            return advance, on_slips[deduction]
    return None
