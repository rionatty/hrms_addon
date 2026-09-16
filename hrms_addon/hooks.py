app_name = "hrms_addon"
app_title = "HRMS Addon"
app_publisher = "CyveTech"
app_description = "HR customisations for Frappe HR / ERPNext"
app_email = "musembiferdinand080@gmail.com"
app_license = "mit"
# required_apps = ["frappe/hrms"]

# Branding
# --------
# The mark shown on this app's own launcher tile and in the apps screen.
# Without it Frappe falls back to a grey letter-tile (which is exactly
# why "Stock Addon" shows a plain "S" today).
#
# This is a STATIC hook — it cannot read a database field, so it points
# at a shipped placeholder file. Replace the file itself; every consumer
# below and the Branding screen's default both reference this path.
#
# The uploadable, per-site logo is a different mechanism: see
# hrms_addon/hrms_addon/branding.py, which writes Website Settings and
# Navbar Settings and covers the navbar, launcher header and login page.
app_logo_url = "/assets/hrms_addon/images/company-logo-placeholder.svg"

# Where the launcher tile and the sidebar app-switcher land.
#
# Two different consumers, so both are set and they must agree:
#   * frappe/boot.py builds apps_data.app_route from the `app_home` HOOK,
#     falling back to "/desk/" + slug(first workspace of this app). It
#     does NOT read the "route" key below.
#   * the sidebar switcher reads the add_to_apps_screen entry.
#
# The /app prefix is deliberate and load-bearing. It is NOT about
# navigation — v16 rewrites "/app/(.*)" to "/desk/\1", so both spellings
# open the same page. It matters because of this, in
# frappe/desk/doctype/desktop_icon/desktop_icon.py:
#
#     if app_icon_link and not app_icon_link.startswith("/app"):
#         icon.hidden = 1
#         icon.parent_icon = None
#
# An app whose icon link does not start with /app gets all of its OWN
# workspaces hidden from the launcher. Frappe HR demonstrates it on this
# site: app_home = "/desk/people", and its Leaves / Recruitment /
# Expenses / Payroll workspaces are missing from the launcher grid, while
# ERPNext — which ships no app icon at all — shows every one of its
# workspaces. We will have more than one workspace, so /app it is.
#
# "hrms-addon" is slug("HRMS Addon"): frappe/desk/utils.py slug() is just
# name.lower().replace(" ", "-"). It resolves to the Workspace record
# shipped at hrms_addon/workspace/hrms_addon/, so renaming that record
# means changing this too.
#
# NOTE: changing this value does not move an EXISTING tile. Frappe copies
# `route` into a Desktop Icon row once, at install, and never re-reads the
# hook. hrms_addon/apps_screen.py re-syncs the row on every migrate.
app_home = "/app/hrms-addon"

add_to_apps_screen = [
    {
        "name": app_name,
        "logo": app_logo_url,
        "title": app_title,
        "route": app_home,
    }
]

# Includes in <head>
# ------------------

# SAP Business One navy desk theme, ported from rionatty/stock_addon
# branch `pre-sap`. Everything below this heading is presentation only —
# no HR logic lives here yet.
#
# Bundle file — requires `bench build --app hrms_addon` after deploy.
app_include_css = "hrms_addon.bundle.css"

# Desk-wide scripts (plain asset paths — no bench build needed):
#  - hrms_addon_theme.js: colour overrides, layout density, status colours
#  - form_sidebar_toggle.js: collapse/expand the right-hand form panel
#  - hrms_addon_branding.js: the few labels that are rendered client-side
#    from each app's own hooks and so cannot be set server-side
app_include_js = [
    "/assets/hrms_addon/js/hrms_addon_theme.js",
    "/assets/hrms_addon/js/form_sidebar_toggle.js",
    "/assets/hrms_addon/js/hrms_addon_branding.js",
]

# Ship the desk colour overrides ("HRMS Addon Theme Settings"), the layout
# density and the branding payload with the session boot, so they are
# applied before first paint. See hrms_addon/hrms_addon/theme.py.
extend_bootinfo = "hrms_addon.hrms_addon.theme.boot_session"

# include js, css files in header of web template
# web_include_css = "/assets/hrms_addon/css/hrms_addon.css"
# web_include_js = "/assets/hrms_addon/js/hrms_addon.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "hrms_addon/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# Job Requisition: Requested By default + Connections moved onto the
# Details tab. doctype_js is read from disk when the form loads, so a
# change to it needs no `bench build`.
#
# Designation (Job Title): pre-fills the four Balanced Scorecard rows of
# the Job Description tab.
doctype_js = {
    "Job Requisition": "public/js/job_requisition.js",
    "Designation": "public/js/designation.js",
}
# doctype_list_js = {"Leave Application": "public/js/leave_application_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "hrms_addon/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "hrms_addon.utils.jinja_methods",
# 	"filters": "hrms_addon.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "hrms_addon.install.before_install"
# after_install = "hrms_addon.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "hrms_addon.uninstall.before_uninstall"
# after_uninstall = "hrms_addon.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "hrms_addon.utils.before_app_install"
# after_app_install = "hrms_addon.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "hrms_addon.utils.before_app_uninstall"
# after_app_uninstall = "hrms_addon.utils.after_app_uninstall"

# Migration
# ---------
# Kept as a list from the start — Frappe only sees the LAST assignment of
# a hook name in this module, so append to this one rather than adding a
# second `after_migrate = ...`.
#
# Both entries below are self-healing and idempotent: they re-assert our
# settings after an ERPNext or Frappe HR update has overwritten them, and
# do nothing at all when everything already matches.
after_migrate = [
    # Push the Branding screen's values into Website Settings / Navbar
    # Settings. A blank field is skipped, never cleared.
    "hrms_addon.hrms_addon.branding.apply_branding_on_migrate",
    # Sidebar order + link order. A no-op until the declarations at the
    # top of workspace_setup.py are filled in.
    "hrms_addon.hrms_addon.workspace_setup.apply_on_migrate",
    # Re-point the launcher tile. Frappe bakes add_to_apps_screen into a
    # Desktop Icon row at INSTALL time and never re-reads the hook, so
    # editing the route above does nothing on a site that already has the
    # app. See apps_screen.py.
    "hrms_addon.hrms_addon.apps_screen.sync_on_migrate",
    # Job Requisition approval: roles, permissions, Workflow States and
    # Actions, and the Workflow. Python rather than fixtures because
    # workflow.json would import before the states it links to. See
    # job_requisition.py.
    "hrms_addon.hrms_addon.job_requisition.setup_on_migrate",
]

# Fixtures
# --------
# Custom Fields / Property Setters, installed on `bench migrate` (no bench
# build needed). Files live in hrms_addon/fixtures/ — the app-package root,
# next to this hooks.py.
#
# Two things worth knowing, both from frappe/utils/fixtures.py:
#   * migrate imports EVERY .json in fixtures/ with force=True — these lists
#     do not filter the import. They only drive `bench export-fixtures`, so
#     they must name exactly what the files contain or an export will add
#     or drop records. scripts/verify_fixtures.py checks that they do.
#   * force=True overwrites on every migrate, so a change made by hand in
#     Customize Form to one of these records is reverted on the next deploy.
#     Change the fixture file instead.
#
# LPL/HR/36 "Recruitment Process, Staff Requisition Form" (Manpower
# Requisition). In the signed To-Be flow the HOD raises a Job Requisition,
# it is approved, then HR clicks Create Job Opening — so the paper form's
# fields live on Job Requisition. The vacancy descriptors are duplicated on
# Job Opening under the SAME fieldnames, which is what makes
# frappe.model.mapper.map_fields copy them across; the sign-off blocks stay
# on the requisition only, read-only, filled by the approval workflow.
#
# Job Requisition-main-field_order fixes the whole form layout. Without it
# Frappe's sorter (frappe/model/meta.py sort_fields) walks a custom Section
# Break forward past Tab Breaks to the next Section Break, which on this
# doctype drops the Job Description sections into the Connections tab.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                [
                    "Job Requisition-custom_employment_type",
                    "Job Requisition-custom_reason_section",
                    "Job Requisition-custom_reason_type",
                    "Job Requisition-custom_recruitment_heading",
                    "Job Requisition-custom_external_advert",
                    "Job Requisition-custom_internal_advert",
                    "Job Requisition-custom_head_hunt",
                    "Job Requisition-custom_reference_to_database",
                    "Job Requisition-custom_reason_cb",
                    "Job Requisition-custom_connections_section",
                    "Job Requisition-custom_connections_html",
                    "Job Requisition-custom_reporting_section",
                    "Job Requisition-custom_reporting_line",
                    "Job Requisition-custom_reporting_cb",
                    "Job Requisition-custom_subordinates",
                    "Job Requisition-custom_approvals_tab",
                    "Job Requisition-custom_department_signoff_section",
                    "Job Requisition-custom_supervisor",
                    "Job Requisition-custom_supervisor_date",
                    "Job Requisition-custom_signoff_cb1",
                    "Job Requisition-custom_process_owner",
                    "Job Requisition-custom_process_owner_date",
                    "Job Requisition-custom_signoff_cb2",
                    "Job Requisition-custom_hod",
                    "Job Requisition-custom_hod_date",
                    "Job Requisition-custom_hr_signoff_section",
                    "Job Requisition-custom_hr_officer",
                    "Job Requisition-custom_hr_officer_date",
                    "Job Requisition-custom_hr_signoff_cb",
                    "Job Requisition-custom_hrm",
                    "Job Requisition-custom_hrm_decision",
                    "Job Requisition-custom_hrm_date",
                    "Job Requisition-custom_ed_signoff_section",
                    "Job Requisition-custom_ed",
                    "Job Requisition-custom_ed_decision",
                    "Job Requisition-custom_ed_signoff_cb",
                    "Job Requisition-custom_ed_date",
                    "Job Opening-custom_reason_type",
                    "Job Opening-custom_recruitment_section",
                    "Job Opening-custom_external_advert",
                    "Job Opening-custom_internal_advert",
                    "Job Opening-custom_recruitment_cb",
                    "Job Opening-custom_head_hunt",
                    "Job Opening-custom_reference_to_database",
                    "Job Opening-custom_reporting_section",
                    "Job Opening-custom_reporting_line",
                    "Job Opening-custom_reporting_cb",
                    "Job Opening-custom_subordinates",
                    "Designation-custom_jd_tab",
                    "Designation-custom_jd_details_section",
                    "Designation-custom_jd_reports_to",
                    "Designation-custom_jd_department",
                    "Designation-custom_jd_section_unit",
                    "Designation-custom_jd_details_cb1",
                    "Designation-custom_jd_grade",
                    "Designation-custom_jd_date",
                    "Designation-custom_jd_details_cb2",
                    "Designation-custom_jd_reference",
                    "Designation-custom_jd_revision",
                    "Designation-custom_jd_purpose_section",
                    "Designation-custom_jd_purpose",
                    "Designation-custom_jd_kra_section",
                    "Designation-custom_jd_key_result_areas",
                    "Designation-custom_jd_reporting_section",
                    "Designation-custom_jd_direct_reports",
                    "Designation-custom_jd_reporting_cb",
                    "Designation-custom_jd_indirect_reports",
                    "Designation-custom_jd_stakeholder_section",
                    "Designation-custom_jd_internal_stakeholders",
                    "Designation-custom_jd_stakeholder_cb",
                    "Designation-custom_jd_external_stakeholders",
                    "Designation-custom_jd_authority_section",
                    "Designation-custom_jd_strategic_authority",
                    "Designation-custom_jd_authority_cb1",
                    "Designation-custom_jd_operational_authority",
                    "Designation-custom_jd_authority_cb2",
                    "Designation-custom_jd_managerial_authority",
                    "Designation-custom_jd_work_cycle_section",
                    "Designation-custom_jd_short_term",
                    "Designation-custom_jd_work_cycle_cb1",
                    "Designation-custom_jd_medium_term",
                    "Designation-custom_jd_work_cycle_cb2",
                    "Designation-custom_jd_long_term",
                    "Designation-custom_jd_iso_section",
                    "Designation-custom_jd_iso_9001",
                    "Designation-custom_jd_iso_22000",
                    "Designation-custom_jd_ims_leadership",
                    "Designation-custom_jd_iso_cb",
                    "Designation-custom_jd_iso_45001",
                    "Designation-custom_jd_iso_14001",
                    "Designation-custom_jd_specs_section",
                    "Designation-custom_jd_academic",
                    "Designation-custom_jd_specs_cb1",
                    "Designation-custom_jd_professional",
                    "Designation-custom_jd_specs_cb2",
                    "Designation-custom_jd_experience",
                    "Designation-custom_jd_competency_section",
                    "Designation-custom_jd_technical_competencies",
                    "Designation-custom_jd_competency_cb",
                    "Designation-custom_jd_behavioural_competencies",
                    "Designation-custom_jd_signoff_section",
                    "Designation-custom_jd_hrm",
                    "Designation-custom_jd_hrm_date",
                    "Designation-custom_jd_reviewed_by",
                    "Designation-custom_jd_reviewed_date",
                    "Designation-custom_jd_signoff_cb",
                    "Designation-custom_jd_approved_by",
                    "Designation-custom_jd_approved_date",
                    "Designation-custom_jd_md",
                    "Designation-custom_jd_md_date",
                ],
            ]
        ],
    },
    {
        "dt": "Property Setter",
        "filters": [
            [
                "name",
                "in",
                [
                    "Job Requisition-designation-label",
                    "Job Requisition-no_of_positions-label",
                    "Job Requisition-description-label",
                    "Job Requisition-reason_for_requesting-label",
                    "Job Requisition-expected_compensation-label",
                    "Job Requisition-expected_compensation-reqd",
                    "Job Requisition-connections_tab-show_dashboard",
                    "Job Requisition-connections_tab-hidden",
                    "Job Requisition-main-field_order",
                    "Job Opening-employment_type-fetch_from",
                    "Job Opening-employment_type-fetch_if_empty",
                ],
            ]
        ],
    },
]

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "hrms_addon.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"Employee": "hrms_addon.hrms_addon.overrides.employee_override.Employee"
# }

# Document Events
# ---------------
# Hook on document methods and events
# NOTE: doc_events must be assigned exactly ONCE in this module — a second
# assignment silently replaces the first and Frappe only sees the last one.

doc_events = {
    "Job Requisition": {
        # Requested By = the logged-in employee, before the mandatory check
        "before_validate": "hrms_addon.hrms_addon.job_requisition.before_validate",
        # Fills the Approvals tab as each approver acts; reverts typed edits
        "validate": "hrms_addon.hrms_addon.job_requisition.validate",
    },
    "Designation": {
        # Job Description: one row per scorecard perspective, totalling 100%
        "validate": "hrms_addon.hrms_addon.designation.validate",
    },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"daily": [
# 		"hrms_addon.tasks.daily"
# 	],
# }

# Testing
# -------

# before_tests = "hrms_addon.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "hrms_addon.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps

# override_doctype_dashboards = {}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["hrms_addon.utils.before_request"]
# after_request = ["hrms_addon.utils.after_request"]

# Job Events
# ----------
# before_job = ["hrms_addon.utils.before_job"]
# after_job = ["hrms_addon.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = []

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"hrms_addon.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
