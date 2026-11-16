# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Deleting what a Data Import made (import_undo.py; checks: scripts/verify_import_undo.py). No Frappe import.

Luuka, 15 Nov 2026, after importing 723 Salary Advance Requests: "add a button to delete data impported through data
import to allow quick deletion".

  undoable       only an import that inserted new records, once it has finished: an import that updated records
                 made nothing of its own, and deleting what it touched would delete what was there before
  reason         why a record stayed, in one plain line
  result_lines   the message when it is done: how many went; those another document holds, counted by that
                 document; and each other one that stayed, with why
"""

import re

INSERT = "Insert New Records"
FINISHED = ("Success", "Partial Success")
# the most records named in a message; the rest are counted
SHOWN = 10
LONGEST = 200
# Frappe's words when another document links to the record (raise_link_exists_exception)
LINKED = " is linked with "
# Frappe's delete puts one clean-up job per record on the default queue, and refuses the next delete once that queue
# holds its limit (Luuka, 16 Nov 2026: 73 of 694 refused, "Too many queued background jobs (550)"). The deletion
# waits while the queue is half full, a second at a time, ten minutes at most.
PAUSE = 1
MOST_WAIT = 600


def busy(limit):
    """How many queued jobs make the deletion wait: half Frappe's limit."""
    return max(1, int(limit) // 2)


def undoable(import_type, status):
    return import_type == INSERT and status in FINISHED


def reason(text):
    """Frappe's message without its markup, on one line, cut short when long."""
    plain = " ".join(re.sub(r"<[^>]+>", " ", str(text if text is not None else "")).split())
    if not plain:
        return "Not deleted."
    return plain if len(plain) <= LONGEST else plain[:LONGEST - 3].rstrip() + "..."


def result_lines(doctype, total, deleted, failed, shown=SHOWN):
    """A line each: how many of the records the import made were deleted; those another document holds, counted by
    that document, with what to do (Luuka, 16 Nov 2026: 694 held by one Salary Advance Processing were ten long
    lines); then each other one that stayed, with why."""
    out = ["Deleted %d of the %d %s records this import made." % (deleted, total, doctype)]
    if failed:
        out.append("Not deleted, %d:" % len(failed))
        held, other = {}, []
        for name, why in failed:
            if LINKED in why:
                holder = why.split(LINKED, 1)[1].strip()
                held[holder] = held.get(holder, 0) + 1
            else:
                other.append((name, why))
        holders = sorted(held.items(), key=lambda pair: (-pair[1], pair[0]))
        out += ["%d linked with %s. Delete or cancel it first, then press Delete Imported Records again." % (count, holder)
                for holder, count in holders[:shown]]
        if len(holders) > shown:
            out.append("and %d more documents that hold some of them." % (len(holders) - shown))
        out += ["%s: %s" % (name, why) for name, why in other[:shown]]
        if len(other) > shown:
            out.append("and %d more." % (len(other) - shown))
    if deleted:
        out.append("Deleted records can be restored from Deleted Document.")
    return out
