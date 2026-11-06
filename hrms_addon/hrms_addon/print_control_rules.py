# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The control line at the top of every form this app prints (Luuka, 5 Nov
2026: "For all print out documents, the forms should have control numbers up
there for audit purposes"): the document's own number, which nothing else
carries, until Luuka give the forms numbers of their own; what it stands at;
and who printed it, when. No Frappe import, like the other *_rules.py modules
(scripts/verify_form_prints.py).

The Pay Slip is printed on a page of its own size and carries none.
"""

import html

DOCSTATUS = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
# the prints that carry none: the Pay Slip's page is 270 by 600 points, and a
# line more puts the slip on two
WITHOUT = ("Pay Slip",)
STYLE = ("font-family: Arial, Helvetica, sans-serif !important; font-size: 9.5px !important; "
         "color: #000 !important; text-align: right; margin: 0 0 6px; line-height: 1.3;")


def status_of(doc):
    """What a printed document stands at: its workflow's state, else its
    status, else whether it is a draft, submitted or cancelled."""
    for field in ("workflow_state", "status"):
        value = doc.get(field)
        if value:
            return str(value)
    try:
        return DOCSTATUS.get(int(doc.get("docstatus") or 0), "Draft")
    except (TypeError, ValueError):
        return "Draft"


def control_line(number, status, printed_by, printed_on):
    """The line, as HTML: Control No. <number> · <status> · Printed by <who> on <when>."""
    parts = ["Control No. <b>%s</b>" % html.escape(str(number or ""))]
    if status:
        parts.append(html.escape(str(status)))
    parts.append("Printed by %s on %s" % (html.escape(str(printed_by or "")), html.escape(str(printed_on or ""))))
    return '<div class="lpl-control" style="%s">%s</div>' % (STYLE, " &middot; ".join(parts))
