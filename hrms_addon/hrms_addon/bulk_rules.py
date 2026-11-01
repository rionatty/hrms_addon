# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How a large selection on a list is worked through (bulk.py).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_bulk.py exercises it without a bench.

Frappe v16 submits, cancels or edits at most 500 records from a list, in one
job on the short queue, and deletes any number in one job on the default
queue, stopped after five minutes. Luuka work on thousands at a time (1 Nov
2026: "everything the clinet operates on a very large data"): a selection
beyond what Frappe does while the user waits is split into batches of 500,
each a job of its own on the long queue, with time enough for 500 heavy
records.
"""

BATCH = 500        # records in a job: Frappe's own cap on one bulk job
DELETE_NOW = 10    # Frappe deletes up to 10 while the user waits, and so does this
TIMEOUT = 3000     # seconds a batch may take on the long queue: 500 records at six seconds each


def batches(names, size=BATCH):
    """The names in batches of `size`, in the order they were chosen: every name once."""
    names = list(names or ())
    return [names[start:start + size] for start in range(0, len(names), size)]
