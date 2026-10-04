# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Letters to candidates carry no link into the system (Oct 2026).

The interview invitation linked to a page of the system where the candidate
confirmed or asked for another time. Luuka: nothing sent to people outside
links into the system. The candidate now replies to the email, and HR
records the answer on the Interview (Candidate Response).

The invitation template is HR's once seeded, so the paragraph with the link
is replaced only where it is still exactly what was seeded; a template HR
changed keeps its words, and the link is taken out of it as it is sent
(interviews._invite, interview_rules.without_system_links). Safe to run
twice.

System Settings' Include Web View Link in Email is turned off as well: the
"View this in your browser" link it adds to a document emailed with its
print format is a keyed address into the system. hrms_addon's
templates/emails/print_link.html renders nothing in any case; the setting
is turned off so the screen says what happens.
"""

import frappe

from hrms_addon.hrms_addon import interview_rules as rules


def execute():
    names = {rules.INVITATION_TEMPLATE, frappe.db.get_single_value("HR Settings", "custom_invitation_template")
             if frappe.get_meta("HR Settings").has_field("custom_invitation_template") else None}
    for name in sorted(name for name in names if name):
        if not frappe.db.exists("Email Template", name):
            continue
        body = frappe.db.get_value("Email Template", name, "response_html") or ""
        if rules.LINK_PARAGRAPH in body:
            frappe.db.set_value("Email Template", name, "response_html",
                                body.replace(rules.LINK_PARAGRAPH, rules.REPLY_PARAGRAPH))
    # written even where it reads 0: a Check never saved reads 0 here but
    # shows its default, ticked, on the screen
    frappe.db.set_single_value("System Settings", "attach_view_link", 0)
