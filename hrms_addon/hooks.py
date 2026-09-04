app_name = "hrms_addon"
app_title = "HRMS Addon"
app_publisher = "CyveTech"
app_description = "HR customisations for Frappe HR / ERPNext"
app_email = "musembiferdinand080@gmail.com"
app_license = "mit"
# required_apps = ["frappe/hrms"]

# Includes in <head>
# ------------------

# SAP Business One navy desk theme, ported from rionatty/stock_addon
# branch `pre-sap`. Everything below this heading is presentation only —
# no HR logic lives here yet.
#
# Bundle file — requires `bench build --app hrms_addon` after deploy.
app_include_css = "hrms_addon.bundle.css"

# Desk-wide scripts (plain asset paths — no bench build needed):
#  - hrms_addon_theme.js: colour overrides + status indicator colours
#  - form_sidebar_toggle.js: collapse/expand the right-hand form panel
app_include_js = [
    "/assets/hrms_addon/js/hrms_addon_theme.js",
    "/assets/hrms_addon/js/form_sidebar_toggle.js",
]

# Ship the desk colour overrides ("HRMS Addon Theme Settings") with the
# session boot so they are applied before first paint.
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
# doctype_js = {"Employee": "public/js/employee.js"}
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
# Workspace wiring, Client Script installers and list defaults go here as
# the HR features land. Kept as a list from the start — Frappe only sees
# the LAST assignment of a hook name in this module, so append to this
# one rather than adding a second `after_migrate = ...`.
# after_migrate = []

# Fixtures
# --------
# Custom Fields / Property Setters, installed on `bench migrate`
# (no bench build needed). Files live in hrms_addon/fixtures/ — the
# app-package root, next to this hooks.py. Frappe only syncs from there.
# fixtures = []

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

# doc_events = {}

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
