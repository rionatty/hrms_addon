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
#  - hrms_addon_alerts.js: My Alerts, the user's own assignments and unread
#    notifications down the right of the desk (hrms_addon/hrms_addon/alerts.py)
app_include_js = [
    "/assets/hrms_addon/js/hrms_addon_theme.js",
    "/assets/hrms_addon/js/form_sidebar_toggle.js",
    "/assets/hrms_addon/js/hrms_addon_branding.js",
    "/assets/hrms_addon/js/hrms_addon_alerts.js",
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
    # The onboarding fills itself from the candidate (onboarding.py); an
    # accepted offer starts one
    "Employee Onboarding": "public/js/employee_onboarding.js",
    "Job Offer": "public/js/job_offer.js",
    # The session and the evaluation form (training.py): print the attendance
    # list and the evaluation forms, key the evaluations in, the summary
    "Training Event": "public/js/training_event.js",
    "Training Feedback": "public/js/training_feedback.js",
    # The Supervisory Skills Evaluation Form (LPL/HR/18) lives on Frappe
    # HR's Appraisal; the cycle carries the sheet for appraising offline
    "Appraisal": "public/js/appraisal.js",
    "Appraisal Cycle": "public/js/appraisal_cycle.js",
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
    "methods": [
        "hrms_addon.hrms_addon.careers.job_posting_details",
        # the Training Evaluation Summary print: every evaluation of a session consolidated
        "hrms_addon.hrms_addon.training.consolidated",
        # the promotion, designation and salary letters print the gross both
        # in figures and in words
        "hrms_addon.hrms_addon.positions.in_words",
    ],
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
#  - seed the interview score sheet's criteria, see hrms_addon/interviews.py;
#  - seed the onboarding templates and the Workplace Rules and Regulations,
#    see hrms_addon/onboarding.py.
after_install = [
    "hrms_addon.hrms_addon.pick_lists.after_install",
    "hrms_addon.hrms_addon.bio_data.after_install",
    "hrms_addon.hrms_addon.interviews.after_install",
    "hrms_addon.hrms_addon.onboarding.after_install",
    "hrms_addon.hrms_addon.probation.after_install",
    # the items of the Training Evaluation Form (LPL/TRG/FRM05)
    "hrms_addon.hrms_addon.pick_lists.seed_training_masters",
    "hrms_addon.hrms_addon.pick_lists.seed_appraisal_masters",
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
    # Promotions, changes of designation and salary reviews: the Candidate
    # Preamble's own signatures, Supervisor to Executive Director, and the
    # Legal Manager role the renewal and salary letters witness with.
    # See position_approval.py.
    "hrms_addon.hrms_addon.positions.setup_workflows_on_migrate",
    # The appraisal round: the Supervisory Skills Evaluation Form's own
    # signatures on Frappe HR's Appraisal, and the rights the supervisor,
    # Production Manager and General Manager need on it.
    # See appraisal_approval.py.
    "hrms_addon.hrms_addon.appraisals.setup_workflows_on_migrate",
    # Employee Onboarding: started by the branch HR Officer, approved by the
    # HR Manager. See onboarding_approval.py.
    "hrms_addon.hrms_addon.onboarding.setup_workflow_on_migrate",
    # The 30-60-90 reviews (Staff Onboarding Form) and the End of probation
    # evaluation, through their signatures. See review_approval.py and
    # probation_approval.py.
    "hrms_addon.hrms_addon.reviews.setup_workflow_on_migrate",
    "hrms_addon.hrms_addon.probation.setup_workflow_on_migrate",
    # The Training Needs Assessment (HR Manager, then General Manager) and the
    # Training Calendar (General Manager). See tna_approval.py and
    # calendar_approval.py.
    "hrms_addon.hrms_addon.training.setup_workflows_on_migrate",
    # What this app adds, on Frappe HR's own workspace pages and sidebars, so
    # it is reached where people already work (navigation.py). Added to what
    # Frappe HR ships, and re-applied here because an update rewrites those
    # records; it must run after Frappe has re-imported them.
    "hrms_addon.hrms_addon.navigation.setup_on_migrate",
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
                    "Job Requisition-custom_branch",
                    "Job Requisition-custom_position_category",
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
                    "Job Requisition-custom_gm_signoff_section",
                    "Job Requisition-custom_gm",
                    "Job Requisition-custom_gm_signoff_cb",
                    "Job Requisition-custom_gm_date",
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
                    "Department-custom_position_category",
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
                    "Designation-custom_tools_tab",
                    "Designation-custom_tools",
                    "KRA-custom_kpi_section",
                    "KRA-custom_perspective",
                    "KRA-custom_applies_to",
                    "KRA-custom_kpi_cb1",
                    "KRA-custom_unit",
                    "KRA-custom_target",
                    "KRA-custom_kpi_cb2",
                    "KRA-custom_source",
                    "KRA-custom_frequency",
                    "Job Applicant-custom_branch",
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
                    "Employee-custom_place_of_birth",
                    "Employee-custom_personal_bio_data_tab",
                    "Employee-custom_residence_section",
                    "Employee-custom_home_village",
                    "Employee-custom_home_district",
                    "Employee-custom_residence_cb",
                    "Employee-custom_current_residence",
                    "Employee-custom_current_division",
                    "Employee-custom_current_district",
                    "Employee-custom_spouse_section",
                    "Employee-custom_spouse_name",
                    "Employee-custom_spouse_cb",
                    "Employee-custom_spouse_occupation",
                    "Employee-custom_spouse_phone",
                    "Employee-custom_parents_section",
                    "Employee-custom_parents",
                    "Employee-custom_next_of_kin_section",
                    "Employee-custom_next_of_kin",
                    "Employee-custom_children_section",
                    "Employee-custom_children",
                    "Employee-custom_bio_data_declaration_section",
                    "Employee-custom_bio_data_signed_on",
                    "Employee-custom_bio_data_declaration_cb",
                    "Employee-custom_signed_bio_data_form",
                    "Employee-custom_professional_section",
                    "Employee-custom_professional_qualifications",
                    "Employee-custom_probation_end_date",
                    "Employee-custom_probation_status",
                    "Employee-custom_tools_tab",
                    "Employee-custom_employee_tools",
                    "Job Offer-custom_branch",
                    "Employee Onboarding-custom_branch",
                    "Employee Onboarding-custom_onboarding_status",
                    "Employee Onboarding-custom_hr_officer",
                    "Employee Onboarding-custom_head_of_department",
                    "Employee Onboarding-custom_supervisor",
                    "Employee Onboarding-custom_orientation_section",
                    "Employee Onboarding-custom_rules_signed_on",
                    "Employee Onboarding-custom_orientation_cb",
                    "Employee Onboarding-custom_signed_workplace_rules",
                    "Employee Onboarding-custom_tools_section",
                    "Employee Onboarding-custom_tools",
                    "Employee Onboarding-custom_salary_section",
                    "Employee Onboarding-custom_salary_structure",
                    "Employee Onboarding-custom_salary_from",
                    "Employee Onboarding-custom_income_tax_slab",
                    "Employee Onboarding-custom_salary_cb",
                    "Employee Onboarding-custom_base_salary",
                    "Employee Onboarding-custom_variable_pay",
                    "Employee Onboarding-custom_salary_structure_assignment",
                    "Employee Onboarding-custom_training_section",
                    "Employee Onboarding-custom_training_required",
                    "Employee Onboarding-custom_training_program",
                    "Employee Onboarding-custom_training_type",
                    "Employee Onboarding-custom_training_scope",
                    "Employee Onboarding-custom_training_cb",
                    "Employee Onboarding-custom_trainer_name",
                    "Employee Onboarding-custom_trainer_email",
                    "Employee Onboarding-custom_training_start",
                    "Employee Onboarding-custom_training_days",
                    "Employee Onboarding-custom_training_location",
                    "Employee Onboarding-custom_training_event",
                    "Employee Onboarding-custom_hrm_approval_section",
                    "Employee Onboarding-custom_hrm_approved_by",
                    "Employee Onboarding-custom_hrm_approved_on",
                    "Employee Onboarding-custom_hrm_approval_cb",
                    "Employee Onboarding-custom_hrm_remarks",
                    "Employment Type-custom_contract_months",
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
                    "Training Event-custom_branch",
                    "Training Event-custom_department",
                    "Training Event-custom_schedule",
                    "Training Event-custom_calendar_entry",
                    "Training Event-custom_trainer_2",
                    "Training Event-custom_trainer_3",
                    "Training Event-custom_shift",
                    "Training Event-custom_memo_approved_by",
                    "Training Event-custom_memo_approved_on",
                    "Training Event-custom_after_section",
                    "Training Event-custom_signed_attendance",
                    "Training Event-custom_reminders_sent",
                    "Training Event-custom_after_cb",
                    "Training Event-custom_evaluations",
                    "Training Event-custom_evaluation_score",
                    "Training Event-custom_evaluation_band",
                    "Training Feedback-custom_ratings_section",
                    "Training Feedback-custom_ratings",
                    "Training Feedback-custom_score",
                    "Training Feedback-custom_score_cb",
                    "Training Feedback-custom_band",
                    "Training Feedback-custom_questions_section",
                    "Training Feedback-custom_expectations",
                    "Training Feedback-custom_learnt",
                    "Training Feedback-custom_application",
                    "Training Feedback-custom_questions_cb",
                    "Training Feedback-custom_remaining_gaps",
                    "Training Feedback-custom_trainer_recommendations",
                    "Training Feedback-custom_hr_recommendations",
                    "Training Feedback-custom_signed_on",
                    "Employee-custom_bank_branch",
                    "Employee-custom_bank_account_name",
                    "Employee-custom_salary_from_month",
                    "Employee-custom_wages_phone_section",
                    "Employee-custom_wages_phone",
                    "Employee-custom_wages_phone_cb",
                    "Employee-custom_wages_phone_names",
                    "Employee-custom_bank_declaration_section",
                    "Employee-custom_bank_declared_on",
                    "Employee-custom_bank_witness",
                    "Employee-custom_bank_declaration_cb",
                    "Employee-custom_signed_bank_form",
                    "Appraisal-custom_round_section",
                    "Appraisal-custom_plan",
                    "Appraisal-custom_quarter",
                    "Appraisal-custom_round_cb",
                    "Appraisal-custom_branch",
                    "Appraisal-custom_supervisor",
                    "Appraisal-custom_appraisal_status",
                    "Appraisal-custom_section_a",
                    "Appraisal-custom_factors",
                    "Appraisal-custom_section_b",
                    "Appraisal-custom_objectives",
                    "Appraisal-custom_section_c",
                    "Appraisal-custom_factors_score",
                    "Appraisal-custom_objectives_score",
                    "Appraisal-custom_section_c_cb",
                    "Appraisal-custom_total_score",
                    "Appraisal-custom_band",
                    "Appraisal-custom_annual_score",
                    "Appraisal-custom_general_section",
                    "Appraisal-custom_roles",
                    "Appraisal-custom_skills",
                    "Appraisal-custom_achievements",
                    "Appraisal-custom_challenges",
                    "Appraisal-custom_employee_section",
                    "Appraisal-custom_employee_remarks",
                    "Appraisal-custom_employee_cb",
                    "Appraisal-custom_employee_signed_by",
                    "Appraisal-custom_employee_signed_on",
                    "Appraisal-custom_supervisor_section",
                    "Appraisal-custom_supervisor_remarks",
                    "Appraisal-custom_supervisor_cb",
                    "Appraisal-custom_supervisor_by",
                    "Appraisal-custom_supervisor_on",
                    "Appraisal-custom_hrm_section",
                    "Appraisal-custom_hrm_remarks",
                    "Appraisal-custom_hrm_cb",
                    "Appraisal-custom_hrm_by",
                    "Appraisal-custom_hrm_on",
                    "Appraisal-custom_production_section",
                    "Appraisal-custom_production_remarks",
                    "Appraisal-custom_production_cb",
                    "Appraisal-custom_production_by",
                    "Appraisal-custom_production_on",
                    "Appraisal-custom_gm_section",
                    "Appraisal-custom_gm_remarks",
                    "Appraisal-custom_gm_cb",
                    "Appraisal-custom_gm_by",
                    "Appraisal-custom_gm_on",
                    "Appraisal-custom_return_section",
                    "Appraisal-custom_return_remarks",
                    "Appraisal-custom_outcome",
                    "Appraisal-custom_performance_review",
                    "Appraisal Cycle-custom_plan_section",
                    "Appraisal Cycle-custom_plan",
                    "Appraisal Cycle-custom_quarter",
                    "Appraisal Cycle-custom_plan_cb",
                    "Appraisal Cycle-custom_soft_deadline",
                    "Appraisal Cycle-custom_hard_deadline",
                    "Appraisal Cycle-custom_reminders_sent",
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
                    "Job Requisition-department-reqd",
                    "Job Requisition-main-field_order",
                    "Job Opening-employment_type-fetch_from",
                    "Job Opening-employment_type-fetch_if_empty",
                    "Job Opening-location-label",
                    "Job Opening-location-reqd",
                    "Job Opening-location-fetch_from",
                    "Job Opening-location-fetch_if_empty",
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
                    "Employee Onboarding-main-default_print_format",
                    "Interview Type-expected_skill_set-reqd",
                    "Training Feedback-feedback-label",
                    "Training Feedback-feedback-reqd",
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
#
# Employee Onboarding: Frappe HR's controller, except that when the Employee
# cannot be created or saved yet it lists the onboarding tasks still open
# (its own message names none). See overrides/employee_onboarding.py.
override_doctype_class = {
    "Employee Onboarding": "hrms_addon.hrms_addon.overrides.employee_onboarding.EmployeeOnboarding",
}

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
    "Appraisal": {
        # LPL/HR/18: Section C from the supervisor's ratings, the
        # signatures, and the year to date (appraisals.py)
        "validate": "hrms_addon.hrms_addon.appraisals.appraisal_validate",
        "on_cancel": "hrms_addon.hrms_addon.appraisals.appraisal_on_cancel",
    },
    "Employee Onboarding": {
        # Defaults from the candidate, the workflow step's checks and stamp,
        # and each activity given to the branch's own people, not every
        # holder of its role (onboarding.py)
        "validate": "hrms_addon.hrms_addon.onboarding.validate",
        # the steps after the start are updates after submit: no validate
        "before_update_after_submit": "hrms_addon.hrms_addon.onboarding.before_update_after_submit",
        # after Frappe HR made the tasks
        "on_submit": "hrms_addon.hrms_addon.onboarding.after_tasks",
        "on_update_after_submit": "hrms_addon.hrms_addon.onboarding.after_tasks",
        # a salary structure it drafted goes with it
        "on_cancel": "hrms_addon.hrms_addon.onboarding.on_cancel",
    },
    "Employee": {
        # the candidate's onboarding learns its Employee even once its tasks
        # are all done, which Frappe HR's own link skips (onboarding.py)
        "on_update": "hrms_addon.hrms_addon.onboarding.link_onboarding",
    },
    # The session and the evaluation form of Luuka's training process
    # (training.py): submitting the event says the training was held; each
    # evaluation scores itself and the event keeps the consolidated score
    "Training Event": {
        "on_submit": "hrms_addon.hrms_addon.training.event_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.training.event_on_cancel",
    },
    "Training Feedback": {
        "validate": "hrms_addon.hrms_addon.training.feedback_validate",
        "on_submit": "hrms_addon.hrms_addon.training.feedback_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.training.feedback_on_cancel",
    },
}

# Scheduled Tasks
# ---------------

# Contracts: each one's status, and the HR Officer told a year, a quarter and
# a month before it ends (contracts.py, Onboarding Settings)
scheduler_events = {
    "daily": [
        "hrms_addon.hrms_addon.contracts.daily",
        # Training: the HR Officer reminded a month before a calendar training
        # to schedule it; everyone booked reminded a week, a day and the
        # morning before a session (training.py)
        "hrms_addon.hrms_addon.training.daily",
        # An internship whose end date has passed is marked Completed
        # (positions.py)
        "hrms_addon.hrms_addon.positions.daily",
        # Performance: the HR Officer told when a quarter closes, and
        # everyone appraising reminded before the deadlines
        "hrms_addon.hrms_addon.appraisals.daily",
        # A Performance Improvement Plan's review dates and its end
        "hrms_addon.hrms_addon.pips.daily",
    ],
}

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

# What this app adds, on the Connections of the standard documents it hangs
# off, so nothing has to be found by searching for its DocType. Our own
# DocTypes carry their own <doctype>_dashboard.py instead. See connections.py.
override_doctype_dashboards = {
    "Employee": "hrms_addon.hrms_addon.connections.employee_dashboard",
    "Employee Onboarding": "hrms_addon.hrms_addon.connections.employee_onboarding_dashboard",
    "Job Opening": "hrms_addon.hrms_addon.connections.job_opening_dashboard",
    "Training Event": "hrms_addon.hrms_addon.connections.training_event_dashboard",
}

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
