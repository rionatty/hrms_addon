# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Deleting what a Data Import made (import_undo.py; checks: scripts/verify_import_undo.py). No Frappe import.

Luuka, 15 Nov 2026, after importing 723 Salary Advance Requests: "add a button to delete data impported through data
import to allow quick deletion".

  undoable       only an import that inserted new records, once it has finished: an import that updated records
                 made nothing of its own, and deleting what it touched would delete what was there before
  reason         why a record stayed, in one plain line
  result_lines   the message when it is done: how many went, and which stayed and why
"""

import re

INSERT = "Insert New Records"
FINISHED = ("Success", "Partial Success")
# the most records named in a message; the rest are counted
SHOWN = 10
LONGEST = 200


def undoable(import_type, status):
    return import_type == INSERT and status in FINISHED


def reason(text):
    """Frappe's message without its markup, on one line, cut short when long."""
    plain = " ".join(re.sub(r"<[^>]+>", " ", str(text if text is not None else "")).split())
    if not plain:
        return "Not deleted."
    return plain if len(plain) <= LONGEST else plain[:LONGEST - 3].rstrip() + "..."


def result_lines(doctype, total, deleted, failed, shown=SHOWN):
    """A line each: how many of the records the import made were deleted, then each one that stayed, with why."""
    out = ["Deleted %d of the %d %s records this import made." % (deleted, total, doctype)]
    if failed:
        out.append("Not deleted, %d:" % len(failed))
        out += ["%s: %s" % (name, why) for name, why in failed[:shown]]
        if len(failed) > shown:
            out.append("and %d more." % (len(failed) - shown))
    if deleted:
        out.append("Deleted records can be restored from Deleted Document.")
    return out
