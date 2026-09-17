# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Careers portal list page (/jobs).

Replaces HRMS's page of the same route: Frappe looks for a www page in the
last-installed app first (frappe/website/page_renderers/template_page.py,
set_template_path), so index.html next to this file wins.

Only the markup and the look change. HRMS keeps the data and the behaviour:
its get_context builds the list, filters and paging, and its index.js (search,
filters, sort, paging, the mobile filter drawer) runs unchanged, so
index.html keeps every id and name that script looks for. Its index.css is
kept too, for the drawer; careers.css styles the rest.
"""

import frappe
from hrms.www.jobs.index import get_context as hrms_get_context

no_cache = 1


def get_context(context):
    hrms_get_context(context)
    context.body_class = "jobs-page lpl-jobs-page"
    # This folder ships no index.js / index.css of its own, so Frappe keeps
    # these instead of loading files from here.
    context.colocated_js = frappe.read_file(frappe.get_app_path("hrms", "www", "jobs", "index.js"))
    context.colocated_css = frappe.read_file(frappe.get_app_path("hrms", "www", "jobs", "index.css"))
