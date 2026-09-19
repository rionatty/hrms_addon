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
# Job Requisition: Requested By defaults to the logged-in employee.
# doctype_js is read from disk when the form loads, so a change to it
# needs no `bench build`.
#
# Designation (Job Title): running per-perspective totals under the Key
# Result Areas table of the Job Description tab.
doctype_js = {
    "Job Requisition": "public/js/job_requisition.js",
    "Designation": "public/js/designation.js",
    # Submit Feedback opens the score sheet (LPL/HR/17) instead of HRMS's star dialog
    "Interview": "public/js/interview.js",
    "Interview Feedback": "public/js/interview_feedback.js",
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
# job_posting_details: the Job Opening page of the careers portal
# (templates/generators/job_opening.html) shows the Job Title's Job
# Description through it. See hrms_addon/careers.py.
jinja = {
    "methods": ["hrms_addon.hrms_addon.careers.job_posting_details"],
}

# Installation
# ------------

# before_install = "hrms_addon.install.before_install"
# One-off setup on a fresh install. Frappe marks every patch as already run
# when an app is installed, so what the patches do on existing sites has to
# be repeated here:
#  - seed the pick lists (KRA form, Job Description tables, Bio-Data tab),
#    see hrms_addon/pick_lists.py;
#  - let HR User add Skills, see hrms_addon/bio_data.py;
#  - seed the interview score sheet's criteria, see hrms_addon/interviews.py.
after_install = [
    "hrms_addon.hrms_addon.pick_lists.after_install",
    "hrms_addon.hrms_addon.bio_data.after_install",
    "hrms_addon.hrms_addon.interviews.after_install",
]

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
    # Interview Report approval (through the HR Manager to the Executive
    # Director), built the same way. See interview_report_approval.py.
    "hrms_addon.hrms_addon.interviews.setup_report_workflow_on_migrate",
    # Interview Shortlist screening: HR, then the HOD's second and final
    # screening. See interview_shortlist_approval.py.
    "hrms_addon.hrms_addon.interviews.setup_shortlist_workflow_on_migrate",
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
                    "Job Opening-custom_show_job_description",
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
                    "Designation-custom_jd_reporting_lines",
                    "Designation-custom_jd_stakeholder_section",
                    "Designation-custom_jd_stakeholders",
                    "Designation-custom_jd_authority_section",
                    "Designation-custom_jd_decision_authorities",
                    "Designation-custom_jd_work_cycle_section",
                    "Designation-custom_jd_planning_horizons",
                    "Designation-custom_jd_iso_section",
                    "Designation-custom_jd_iso_responsibilities",
                    "Designation-custom_jd_specs_section",
                    "Designation-custom_jd_specifications",
                    "Designation-custom_jd_competency_section",
                    "Designation-custom_jd_competencies",
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
                    "KRA-custom_kpi_section",
                    "KRA-custom_perspective",
                    "KRA-custom_applies_to",
                    "KRA-custom_kpi_cb1",
                    "KRA-custom_unit",
                    "KRA-custom_target",
                    "KRA-custom_kpi_cb2",
                    "KRA-custom_source",
                    "KRA-custom_frequency",
                    "Job Applicant-custom_previous_salary",
                    "Job Applicant-custom_current_benefits",
                    "Job Applicant-custom_expected_benefits",
                    "Job Applicant-custom_notice_period",
                    "Job Applicant-custom_bio_data_tab",
                    "Job Applicant-custom_personal_section",
                    "Job Applicant-custom_date_of_birth",
                    "Job Applicant-custom_gender",
                    "Job Applicant-custom_marital_status",
                    "Job Applicant-custom_no_of_children",
                    "Job Applicant-custom_citizenship",
                    "Job Applicant-custom_personal_cb1",
                    "Job Applicant-custom_home_village",
                    "Job Applicant-custom_home_district",
                    "Job Applicant-custom_current_residence",
                    "Job Applicant-custom_current_district",
                    "Job Applicant-custom_personal_cb2",
                    "Job Applicant-custom_nin",
                    "Job Applicant-custom_nssf_no",
                    "Job Applicant-custom_tin",
                    "Job Applicant-custom_health_issues",
                    "Job Applicant-custom_parents_section",
                    "Job Applicant-custom_parents",
                    "Job Applicant-custom_next_of_kin_section",
                    "Job Applicant-custom_next_of_kin",
                    "Job Applicant-custom_qualifications_section",
                    "Job Applicant-custom_qualifications",
                    "Job Applicant-custom_school_results_section",
                    "Job Applicant-custom_school_results",
                    "Job Applicant-custom_employment_history_section",
                    "Job Applicant-custom_employment_history",
                    "Job Applicant-custom_skills_section",
                    "Job Applicant-custom_skills",
                    "Job Applicant-custom_languages_section",
                    "Job Applicant-custom_languages",
                    "Job Applicant-custom_declaration_section",
                    "Job Applicant-custom_bio_data_date",
                    "Job Applicant-custom_declaration_cb",
                    "Job Applicant-custom_signed_bio_data",
                    "Employee-custom_nin",
                    "Employee-custom_tin",
                    "Employee-custom_nssf_no",
                    "Interview Feedback-custom_interviewer_designation",
                    "Interview Feedback-custom_evaluation_section",
                    "Interview Feedback-custom_scores",
                    "Interview Feedback-custom_score_summary_section",
                    "Interview Feedback-custom_total_score",
                    "Interview Feedback-custom_max_score",
                    "Interview Feedback-custom_score_cb",
                    "Interview Feedback-custom_score_percent",
                    "Interview Feedback-custom_score_band",
                    "Interview Feedback-custom_recommendation",
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
                    "Job Requisition-main-field_order",
                    "Job Opening-employment_type-fetch_from",
                    "Job Opening-employment_type-fetch_if_empty",
                    "Job Opening-job_application_route-description",
                    "KRA-main-search_fields",
                    "Employee-passport_details_section-label",
                    "Designation-skills-allow_bulk_edit",
                    "Interview Feedback-skill_assessment-reqd",
                    "Interview Feedback-skill_assessment-hidden",
                    "Interview Feedback-section_break_4-hidden",
                    "Interview Feedback-result-reqd",
                    "Interview Feedback-result-read_only",
                    "Interview Feedback-result-description",
                    "Interview Feedback-section_break_7-label",
                    "Interview Feedback-feedback-label",
                    "Interview Feedback-main-default_print_format",
                    "Interview Type-expected_skill_set-reqd",
                    "Interview Type-expected_skill_set-hidden",
                    "Interview Type-expected_average_rating-description",
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
        # Job Description tables: KRA weightings total 100%, nothing listed twice
        "validate": "hrms_addon.hrms_addon.designation.validate",
    },
    "Job Applicant": {
        # Pre-Interview Bio-Data (LPL/HR/19): dates, years, repeated rows
        "validate": "hrms_addon.hrms_addon.bio_data.validate",
    },
    "Interview Feedback": {
        # Score sheet (LPL/HR/17): totals, rating and result from the scores
        "validate": "hrms_addon.hrms_addon.interviews.feedback_validate",
    },
    "Interview": {
        # Cancelling a submitted interview to correct it: the shortlist and the
        # report that list it are records of it, not dependants
        "on_cancel": "hrms_addon.hrms_addon.interviews.unblock_cancel",
    },
    "Job Offer": {
        # the same for an offer made from an approved Interview Report
        "on_cancel": "hrms_addon.hrms_addon.interviews.unblock_cancel",
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
# Create > Employee on a Job Offer or an Employee Onboarding builds the new
# Employee form. These wrap the HRMS originals and fill the form from the
# candidate's Pre-Interview Bio-Data first, so Date of Birth, Gender and the
# rest are there before HR saves. See hrms_addon/bio_data.py.
override_whitelisted_methods = {
    "hrms.hr.doctype.job_offer.job_offer.make_employee": "hrms_addon.hrms_addon.bio_data.make_employee_from_job_offer",
    "hrms.hr.doctype.employee_onboarding.employee_onboarding.make_employee": (
        "hrms_addon.hrms_addon.bio_data.make_employee_from_onboarding"
    ),
    # the Interview's Feedback tab: averages per score sheet criterion
    "hrms.hr.doctype.interview.interview.get_skill_wise_average_rating": (
        "hrms_addon.hrms_addon.interviews.get_skill_wise_average_rating"
    ),
    # A file uploaded from the website (the careers portal's CV) is stored
    # private, whatever the dialog asks. The dialog posts to "upload_file";
    # the saved web form attaches the file through the full name.
    "upload_file": "hrms_addon.hrms_addon.uploads.upload_file",
    "frappe.handler.upload_file": "hrms_addon.hrms_addon.uploads.upload_file",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps

# override_doctype_dashboards = {}

# exempt linked doctypes from being automatically cancelled
#
# The Interview Shortlist and the Interview Report list the Interviews and Job
# Offers made from them. Cancelling one of those must not offer to cancel the
# shortlist or the approved report as well (interviews.unblock_cancel then
# lets the cancel through).
auto_cancel_exempted_doctypes = ["Interview Shortlist", "Interview Report"]

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
