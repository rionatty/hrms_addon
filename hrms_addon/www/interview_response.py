# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The candidate's answer to an interview invitation (/interview-response):
interview-response.html, with what interview_response.page_context gives
for the key in the link."""

import frappe
from frappe import _

from hrms_addon.hrms_addon.interview_response import page_context

no_cache = 1
sitemap = 0


def get_context(context):
    context.no_cache = 1
    context.title = _("Your interview")
    interview = page_context(frappe.form_dict.get("key"))
    link = str(interview.get("meeting_link") or "")
    # only a web address becomes a link on the page
    interview.meeting_url = link if link.lower().startswith(("http://", "https://")) else ""
    context.interview = interview
