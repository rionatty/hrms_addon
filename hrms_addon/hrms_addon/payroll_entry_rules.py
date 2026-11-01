# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Whether a payroll run's salary slips may be made again (payroll_entries.py).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_payroll_recreate.py exercises it without a bench.

Frappe HR makes a run's slips when the run is submitted, and has no way to
make them again but to cancel the run and amend it. While the slips are
drafts and nothing is posted, the drafts can be deleted and made again on the
same run (1 Nov 2026; Luuka: "i want to create a button that will do the
work"). Once a slip is submitted, or the payroll posted, the run is cancelled
as Frappe HR does it: that takes back what was posted.
"""

RUNNING = "Queued"


def why_not_recreate(docstatus, status, slips_submitted, submitted_slips, journal_entries):
    """The reason a run's slips may not be made again, as the user is told it, or None where they may.

    docstatus, status, slips_submitted: the run's; submitted_slips: how many of its slips are submitted;
    journal_entries: how many entries post its payroll."""
    if docstatus != 1:
        return "Only a submitted payroll has salary slips to make again."
    if status == RUNNING:
        return "The salary slips are being made. Wait for it to finish."
    if slips_submitted or submitted_slips:
        return "Some salary slips are submitted. Cancel the payroll to start again."
    if journal_entries:
        return "The payroll is posted. Cancel the payroll to start again."
    return None
