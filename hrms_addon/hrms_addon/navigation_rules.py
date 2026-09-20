# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Where everything this app adds is reached from in the desk.

No Frappe import, like the other *_rules.py modules, so scripts/verify_navigation.py
exercises them without a bench.

Frappe HR's own workspaces are the place people already work, so each thing
is put beside the standard documents it belongs with — Recruitment,
Tenure and HR Setup — rather than on a page of its own that has to be
remembered. Two lists carry it:

  CARDS    the cards on the workspace page: a card is a Card Break in the
           Workspace's `links` plus a `card` block in its `content`
  SIDEBAR  the entries in the left sidebar (a Workspace Sidebar's `items`),
           either at the top or under one of its sections

Both are added to what Frappe HR ships, never in place of it: an upstream
update rewrites those records and navigation.py puts these back on the next
migrate, so anything of theirs that moved or was renamed survives.
"""

DOCTYPE, REPORT = "DocType", "Report"

# workspace -> [(card, [(label, what it opens, kind)])]. A card that Frappe
# HR already has (Reports, Onboarding) is added to, not replaced.
CARDS = {
    "Recruitment": [
        ("Shortlisting", [
            ("Interview Shortlist", "Interview Shortlist", DOCTYPE),
            ("Interview Report", "Interview Report", DOCTYPE),
        ]),
        ("Score Sheet Setup", [
            ("Interview Criterion", "Interview Criterion", DOCTYPE),
            ("Interview Criteria Group", "Interview Criteria Group", DOCTYPE),
        ]),
        ("Candidate Lists", [
            ("Qualification Type", "Qualification Type", DOCTYPE),
            ("Examination Level", "Examination Level", DOCTYPE),
            ("District", "District", DOCTYPE),
            ("Spoken Language", "Spoken Language", DOCTYPE),
            ("Relationship", "Relationship", DOCTYPE),
        ]),
    ],
    "Tenure": [
        ("Probation and Contracts", [
            ("Onboarding Review", "Onboarding Review", DOCTYPE),
            ("Probation Evaluation", "Probation Evaluation", DOCTYPE),
            ("Employee Contract", "Employee Contract", DOCTYPE),
            ("Contract Expiry Status", "Contract Expiry Status", REPORT),
        ]),
        ("Onboarding Setup", [
            ("Onboarding Settings", "Onboarding Settings", DOCTYPE),
            ("Tool of Work", "Tool of Work", DOCTYPE),
            ("Tool Provider", "Tool Provider", DOCTYPE),
            ("Probation Factor", "Probation Factor", DOCTYPE),
        ]),
    ],
    "HR Setup": [
        ("Job Description Lists", [
            ("KRA Perspective", "KRA Perspective", DOCTYPE),
            ("KRA Level", "KRA Level", DOCTYPE),
            ("KRA Unit", "KRA Unit", DOCTYPE),
            ("KRA Data Source", "KRA Data Source", DOCTYPE),
            ("KRA Review Frequency", "KRA Review Frequency", DOCTYPE),
            ("JD Relationship Type", "JD Relationship Type", DOCTYPE),
            ("JD Stakeholder Type", "JD Stakeholder Type", DOCTYPE),
            ("JD Authority Level", "JD Authority Level", DOCTYPE),
            ("JD Horizon", "JD Horizon", DOCTYPE),
            ("JD ISO Standard", "JD ISO Standard", DOCTYPE),
            ("JD Specification Type", "JD Specification Type", DOCTYPE),
            ("JD Requirement Priority", "JD Requirement Priority", DOCTYPE),
            ("JD Competency Category", "JD Competency Category", DOCTYPE),
        ]),
    ],
}

# The report each report link is for, so Frappe opens it on the right list
REPORT_DOCTYPES = {"Contract Expiry Status": "Employee Contract"}

# workspace -> [(label, what it opens, kind, section, after)]
#   section: the sidebar section it goes under ("Setup", "Reports"), or None
#            for the top level
#   after:   the entry it follows, where it matters; otherwise it goes last
#            in its part of the list
SIDEBAR = {
    "Recruitment": [
        ("Interview Shortlist", "Interview Shortlist", DOCTYPE, None, "Job Applicant"),
        ("Interview Report", "Interview Report", DOCTYPE, None, "Interview"),
        ("Interview Criterion", "Interview Criterion", DOCTYPE, "Setup", None),
        ("Interview Criteria Group", "Interview Criteria Group", DOCTYPE, "Setup", None),
        ("Qualification Type", "Qualification Type", DOCTYPE, "Setup", None),
    ],
    "Tenure": [
        ("Onboarding Review", "Onboarding Review", DOCTYPE, None, "Employee Onboarding"),
        ("Probation Evaluation", "Probation Evaluation", DOCTYPE, None, "Onboarding Review"),
        ("Employee Contract", "Employee Contract", DOCTYPE, None, "Probation Evaluation"),
        ("Contract Expiry Status", "Contract Expiry Status", REPORT, "Reports", None),
        ("Onboarding Settings", "Onboarding Settings", DOCTYPE, "Setup", None),
        ("Tool of Work", "Tool of Work", DOCTYPE, "Setup", None),
        ("Tool Provider", "Tool Provider", DOCTYPE, "Setup", None),
        ("Probation Factor", "Probation Factor", DOCTYPE, "Setup", None),
    ],
}

CARD_BREAK, LINK, SECTION = "Card Break", "Link", "Section Break"


def link_row(label, link_to, kind):
    """A Workspace Link row for one thing to open."""
    return {
        "type": LINK,
        "label": label,
        "link_type": kind,
        "link_to": link_to,
        "hidden": 0,
        "onboard": 0,
        "link_count": 0,
        "is_query_report": 0,
        "report_ref_doctype": REPORT_DOCTYPES.get(link_to) if kind == REPORT else None,
    }


def card_row(label):
    return {"type": CARD_BREAK, "label": label, "link_type": None, "link_to": None, "hidden": 0, "onboard": 0,
            "link_count": 0, "is_query_report": 0}


def merge_links(rows, cards):
    """The Workspace's `links` with our cards in it: a card it already has is
    added to (never rewritten), a card it does not have is appended, and a
    link already there is left alone. Every Card Break's link_count is worked
    out again at the end, which is what the page counts by."""
    rows = [dict(row) for row in rows]
    for card, links in cards:
        start = next((i for i, row in enumerate(rows) if row.get("type") == CARD_BREAK and row.get("label") == card), None)
        if start is None:
            rows.append(card_row(card))
            start = len(rows) - 1
        end = next((i for i in range(start + 1, len(rows)) if rows[i].get("type") == CARD_BREAK), len(rows))
        have = {row.get("link_to") for row in rows[start + 1:end]}
        rows[end:end] = [link_row(*link) for link in links if link[1] not in have]
    return count_links(rows)


def count_links(rows):
    """Each Card Break counts the links that follow it."""
    rows = [dict(row) for row in rows]
    card = None
    for row in rows:
        if row.get("type") == CARD_BREAK:
            card, row["link_count"] = row, 0
        elif card is not None:
            card["link_count"] += 1
    return rows


def block_id(card):
    """The id of a card's block in the page's content. Ours is worked out
    from the card's name, not random like Frappe's, so running this again
    finds the block it wrote last time instead of adding another."""
    return "ha" + "".join(word.capitalize() for word in "".join(c if c.isalnum() else " " for c in card).split())


def merge_content(blocks, cards):
    """The page's content with a block for each of our cards, added once."""
    blocks = [dict(block) for block in blocks]
    have = {(block.get("data") or {}).get("card_name") for block in blocks if block.get("type") == "card"}
    for card, _ in cards:
        if card not in have:
            blocks.append({"id": block_id(card), "type": "card", "data": {"card_name": card, "col": 4}})
    return blocks


def sidebar_row(label, link_to, kind, child=0):
    return {"type": LINK, "label": label, "link_type": kind, "link_to": link_to, "icon": "", "child": child,
            "indent": 0, "collapsible": 1, "keep_closed": 0, "show_arrow": 0}


def merge_sidebar(items, entries):
    """The sidebar's items with ours among them: under the section each names
    where there is one, else after the entry it follows, else before the
    first section. One already there is left where it is."""
    items = [dict(item) for item in items]
    for label, link_to, kind, section, after in entries:
        if any(item.get("link_to") == link_to and item.get("type") == LINK for item in items):
            continue
        at = _seat(items, section, after)
        items.insert(at, sidebar_row(label, link_to, kind, child=1 if section else 0))
    return items


def _seat(items, section, after):
    if section:
        start = next((i for i, item in enumerate(items)
                      if item.get("type") == SECTION and item.get("label") == section), None)
        if start is not None:
            end = next((i for i in range(start + 1, len(items)) if items[i].get("type") == SECTION), len(items))
            # the section's own rows are the ones marked as its children
            while end > start + 1 and not items[end - 1].get("child"):
                end -= 1
            return end
        return len(items)
    if after:
        at = next((i for i, item in enumerate(items) if item.get("label") == after), None)
        if at is not None:
            return at + 1
    first_section = next((i for i, item in enumerate(items) if item.get("type") == SECTION), None)
    return len(items) if first_section is None else first_section
