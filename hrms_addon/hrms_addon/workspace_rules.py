# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Where this app's links go in another app's workspace.

No Frappe import, like the other *_rules.py modules: scripts/verify_interviews.py
runs it on Frappe HR's own Recruitment workspace without a bench.

A workspace's links are one ordered table. A "Card Break" row starts a card and
every "Link" row after it belongs to that card until the next Card Break
(frappe/desk/doctype/workspace/workspace.py get_link_groups). The Card Break's
link_count must match, because the workspace editor cuts a card out of the
table by that count when it saves.
"""


def plan_card_links(rows, card, wanted):
    """The workspace's rows with `wanted` added to `card`.

    rows:   the workspace's links in order, dicts with type, label,
            link_type and link_to (anything else is carried through).
    card:   the label of the Card Break to add to.
    wanted: [(label, link_type, link_to, after)]: each goes straight after
            the card's link labelled `after`, first in the card when `after`
            is None, and last in the card when `after` is not there.

    A link the card already has (same link_type and link_to) stays where it
    is, so running this again changes nothing. New rows are dicts with
    "new": True. Returns None when the workspace has no such card.
    """
    rows = [dict(row) for row in rows or []]
    start = next((i for i, row in enumerate(rows) if row.get("type") == "Card Break" and row.get("label") == card), None)
    if start is None:
        return None
    for label, link_type, link_to, after in wanted:
        end = _card_end(rows, start)
        if any(row.get("link_type") == link_type and row.get("link_to") == link_to for row in rows[start + 1:end]):
            continue
        position = start + 1
        if after is not None:
            anchor = next((i for i in range(start + 1, end) if rows[i].get("label") == after), None)
            position = anchor + 1 if anchor is not None else end
        rows.insert(position, {"type": "Link", "label": label, "link_type": link_type, "link_to": link_to, "new": True})
    return rows


def card_links(rows, card):
    """The labels of the links in `card`, in order (None when there is no such card)."""
    start = next((i for i, row in enumerate(rows or []) if row.get("type") == "Card Break" and row.get("label") == card), None)
    if start is None:
        return None
    return [row.get("label") for row in rows[start + 1:_card_end(rows, start)]]


def _card_end(rows, start):
    end = start + 1
    while end < len(rows) and rows[end].get("type") != "Card Break":
        end += 1
    return end
