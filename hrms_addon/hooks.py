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
#  - e_signature.js: the Sign button and the signatures a document already
#    carries, on every signable form at once (signature_rules.SIGNABLE)
app_include_js = [
    "/assets/hrms_addon/js/hrms_addon_theme.js",
    "/assets/hrms_addon/js/form_sidebar_toggle.js",
    "/assets/hrms_addon/js/hrms_addon_branding.js",
    "/assets/hrms_addon/js/hrms_addon_alerts.js",
    "/assets/hrms_addon/js/e_signature.js",
    # "Salary Advance", "Leave Advance" and "Special Advance" by name in the
    # search bar: each is Frappe HR's Employee Advance with an Advance Type
    "/assets/hrms_addon/js/hrms_addon_search.js",
    # the HR calendar's roster, drawn on its page, the Annual Leave Plan and
    # the Monthly Training Schedule (calendar_board.py)
    "/assets/hrms_addon/js/hr_calendar_view.js",
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
    # A hired graduate becomes a Graduate Trainee Program from their own
    # applicant record (talent.py)
    "Job Applicant": "public/js/job_applicant_trainee.js",
    # The Gradar band and its ten steps on Frappe HR's own Employee Grade
    "Employee Grade": "public/js/employee_grade.js",
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
    # Luuka's scorecard is built on Frappe HR's own Appraisal Template:
    # the weights headline and Import PMS Workbook sit on their form
    "Appraisal Template": "public/js/appraisal_template.js",
    # LPL/HR/15 on their Leave Application: the balances headline, the
    # advance the form asks for, and the report back (leave.py)
    "Leave Application": "public/js/leave_application.js",
    # The leave worked through, and what a day of it is worth (encashments.py)
    "Leave Encashment": "public/js/leave_encashment.js",
    # The Executive Director's Reinstate, for an employee who left by
    # mistake (minutes §6.2, exits.py)
    "Employee": "public/js/employee.js",
    # Luuka's three advances on their Employee Advance (advances.py)
    "Employee Advance": "public/js/employee_advance.js",
    # LPL.HR.31 on their Travel Request (allowances.py)
    "Travel Request": "public/js/travel_request.js",
    # LPL/HR/27 on their Expense Claim (benefits.py)
    "Expense Claim": "public/js/expense_claim.js",
    # Both exits on their Employee Separation, with the two buttons the
    # charts draw: draw up LPL/HR/22, then the settlement (exits.py)
    "Employee Separation": "public/js/employee_separation.js",
    # LPL/HR/20 on their Full and Final Statement (settlements.py)
    "Full and Final Statement": "public/js/full_and_final_statement.js",
    # The non-disciplinary concern's timeline on their Employee Grievance
    "Employee Grievance": "public/js/employee_grievance.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
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
    # what each JD priority counts for in the CV screening
    "hrms_addon.hrms_addon.cv_screening.set_priority_weights",
    "hrms_addon.hrms_addon.bio_data.after_install",
    "hrms_addon.hrms_addon.interviews.after_install",
    "hrms_addon.hrms_addon.onboarding.after_install",
    "hrms_addon.hrms_addon.probation.after_install",
    # the items of the Training Evaluation Form (LPL/TRG/FRM05)
    "hrms_addon.hrms_addon.pick_lists.seed_training_masters",
    "hrms_addon.hrms_addon.pick_lists.seed_appraisal_masters",
    "hrms_addon.hrms_addon.pick_lists.seed_bsc_masters",
    # the five kinds of leave LPL/HR/15 offers
    "hrms_addon.hrms_addon.leave.seed_leave_types",
    # the five lines LPL.HR.31 prints, and the standard claims Luuka pay
    "hrms_addon.hrms_addon.allowances.seed_allowance_lines",
    "hrms_addon.hrms_addon.benefits.seed_standard_claims",
    # the disciplinary ladder and the misconduct the HR manual lists
    "hrms_addon.hrms_addon.discipline.seed_discipline_masters",
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
    # The Off Duty Request (LPL/HR/25): the Supervisor then the Section
    # Manager, with remarks for the HR Manager. See off_duty_approval.py.
    "hrms_addon.hrms_addon.attendance.setup_workflows_on_migrate",
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
    # The Annual Leave Plan (HODs, then the HR Officer) and LPL/HR/15's own
    # three signatures on Frappe HR's Leave Application. See leave_approval.py
    # and leave_plan_approval.py.
    "hrms_addon.hrms_addon.leave.setup_workflows_on_migrate",
    # Leave encashment on Frappe HR's own Leave Encashment: Supervisor, HR,
    # General Manager, Executive Director, back to HR, then the Accounts
    # Manager (minutes §4.5); and the earning it is paid under. See
    # encashment_approval.py.
    "hrms_addon.hrms_addon.encashments.setup_on_migrate",
    # Luuka's three advances on one Workflow, the Advance Type deciding whose
    # desk each lands on. See advance_approval.py.
    "hrms_addon.hrms_addon.advances.setup_workflows_on_migrate",
    # The Salary Advance Request: the employee applies, the supervisor
    # approves. See advance_request_approval.py.
    "hrms_addon.hrms_addon.salary_advances.setup_on_migrate",
    # The allowance application (Supervisor, HR Officer, General Manager,
    # then Accounts) and the Employees Claim Form's five desks. See
    # allowance_approval.py and claim_approval.py.
    "hrms_addon.hrms_addon.allowances.setup_workflows_on_migrate",
    "hrms_addon.hrms_addon.benefits.setup_workflows_on_migrate",
    # The staff loan: HOD, Executive Director, General Manager, the terms
    # Accounts settle and the employee's own consent. See loan_approval.py.
    "hrms_addon.hrms_addon.loans.setup_workflows_on_migrate",
    # A penalty for property lost or damaged: the supervisor's report, the
    # HR Officer's hearing, the employee's consent (LPL/HR/39), the HR
    # Manager, the Executive Director, back to the HR Officer and into the
    # payroll (minutes §4.11). See penalty_approval.py.
    "hrms_addon.hrms_addon.penalties.setup_workflows_on_migrate",
    # The exit interview's three signatures and the Clearance Form's two
    # chains, one per exit. See exit_interview_approval.py and
    # clearance_approval.py.
    "hrms_addon.hrms_addon.exits.setup_workflows_on_migrate",
    # The full and final settlement: Accounts, the employee, the Executive
    # Director, then payroll. See settlement_approval.py.
    "hrms_addon.hrms_addon.settlements.setup_workflows_on_migrate",
    # The disciplinary case: investigated by one person, decided by another
    # (5.3). See discipline_approval.py.
    "hrms_addon.hrms_addon.discipline.setup_workflows_on_migrate",
    # The nine-box placement, the development programme, the succession
    # position and the graduate trainee. See talent_approval.py,
    # talent_program_approval.py, succession_approval.py, trainee_approval.py.
    "hrms_addon.hrms_addon.talent.setup_workflows_on_migrate",
    # The three kinds of overtime day, at the Employment Act's floor, and a
    # word on the deploy if somebody has edited one below it. See
    # overtime_rules.py.
    "hrms_addon.hrms_addon.overtime.setup_on_migrate",
    # Luuka's own three shifts: the office day, and the twelve-hour day and
    # night the register's M and N stand for. See shift_rules.py.
    "hrms_addon.hrms_addon.shifts.setup_on_migrate",
    # The nineteen Gradar grades, G2 to G20. The bands are Luuka's to
    # price; a grade seeded with figures nobody agreed would be worse than
    # a grade with none. See grade_rules.py.
    "hrms_addon.hrms_addon.grades.setup_on_migrate",
    # The Auditor and Management Viewer roles, their read-only grants, and
    # permission level one on Employee's salary and bank fields for HR and
    # Payroll alone. See security_rules.py.
    "hrms_addon.hrms_addon.security.setup_on_migrate",
    # The documents an employee has to hold: the national ID, a work
    # permit, a driving permit. See document_rules.py.
    "hrms_addon.hrms_addon.documents.setup_on_migrate",
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
                    "Overtime Type-custom_gross_above",
                    "Job Opening-custom_screening_section",
                    "Job Opening-custom_pass_mark",
                    "Job Opening-custom_screening_questions",
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
                    "Job Applicant-custom_cv_text",
                    "Job Applicant-custom_cv_read_from",
                    "Job Applicant-custom_screening_section",
                    "Job Applicant-custom_screening_answers",
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
                    "Employee-custom_bank_loan_section",
                    "Employee-custom_has_bank_loan",
                    "Employee-custom_bank_loan_bank",
                    "Employee-custom_bank_loan_cb",
                    "Employee-custom_bank_loan_until",
                    "Employee-custom_pay_category",
                    "Employee-custom_hourly_rate",
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
                    "Appraisal-custom_form_type",
                    "Appraisal-custom_period",
                    "Appraisal-custom_bsc_section_a",
                    "Appraisal-custom_bsc_perspectives",
                    "Appraisal-custom_bsc_kpis",
                    "Appraisal-custom_assignments_section",
                    "Appraisal-custom_assignments",
                    "Appraisal-custom_bsc_section_b",
                    "Appraisal-custom_bsc_competencies",
                    "Appraisal-custom_bsc_scores_section",
                    "Appraisal-custom_bsc_section_a_score",
                    "Appraisal-custom_bsc_section_b_score",
                    "Appraisal-custom_bsc_scores_cb",
                    "Appraisal-custom_bsc_overall",
                    "Appraisal-custom_bsc_band",
                    "Appraisal-custom_bsc_band_meaning",
                    "Appraisal-custom_hod_section",
                    "Appraisal-custom_hod_remarks",
                    "Appraisal-custom_hod_cb",
                    "Appraisal-custom_hod_by",
                    "Appraisal-custom_hod_on",
                    "Appraisal-custom_ed_section",
                    "Appraisal-custom_ed_remarks",
                    "Appraisal-custom_ed_cb",
                    "Appraisal-custom_ed_by",
                    "Appraisal-custom_ed_on",
                    "Appraisal-custom_development_section",
                    "Appraisal-custom_continue",
                    "Appraisal-custom_development_cb1",
                    "Appraisal-custom_stop",
                    "Appraisal-custom_development_cb2",
                    "Appraisal-custom_start",
                    "Appraisal-custom_development_actions",
                    "Employee-custom_automatic_attendance",
                    "Appraisal Template-custom_role_section",
                    "Appraisal Template-custom_designation",
                    "Appraisal Template-custom_review_year",
                    "Appraisal Template-custom_department",
                    "Appraisal Template-custom_role_cb",
                    "Appraisal Template-custom_grade",
                    "Appraisal Template-custom_review_period",
                    "Appraisal Template-custom_company",
                    "Appraisal Template-custom_is_active",
                    "Appraisal Template-custom_section_a",
                    "Appraisal Template-custom_perspectives",
                    "Appraisal Template-custom_objectives_weight",
                    "Appraisal Template-custom_kpis",
                    "Appraisal Template-custom_section_b",
                    "Appraisal Template-custom_competencies",
                    "Appraisal Template-custom_competencies_weight",
                    "Appraisal Template-custom_source_section",
                    "Appraisal Template-custom_source_file",
                    "Appraisal Template-custom_source_cb",
                    "Appraisal Template-custom_source_sheet",
                    "Appraisal Template-custom_import_remarks",
                    "Leave Application-custom_lpl_section",
                    "Leave Application-custom_work_section",
                    "Leave Application-custom_designation",
                    "Leave Application-custom_branch",
                    "Leave Application-custom_lpl_cb",
                    "Leave Application-custom_date_of_appointment",
                    "Leave Application-custom_medical_certificate",
                    "Leave Application-custom_salary_requested_in_advance",
                    "Leave Application-custom_advance",
                    "Leave Application-custom_plan",
                    "Leave Application-custom_plan_row",
                    "Leave Application-custom_hro_section",
                    "Leave Application-custom_last_leave_type",
                    "Leave Application-custom_last_leave_from",
                    "Leave Application-custom_last_leave_to",
                    "Leave Application-custom_last_leave_days",
                    "Leave Application-custom_hro_cb",
                    "Leave Application-custom_balance_before",
                    "Leave Application-custom_balance_after",
                    "Leave Application-custom_sick_balance_before",
                    "Leave Application-custom_sick_balance_after",
                    "Leave Application-custom_hro_cb2",
                    "Leave Application-custom_hro_by",
                    "Leave Application-custom_hro_on",
                    "Leave Application-custom_approval_section",
                    "Leave Application-custom_leave_status",
                    "Leave Application-custom_supervisor_remarks",
                    "Leave Application-custom_supervisor_by",
                    "Leave Application-custom_supervisor_on",
                    "Leave Application-custom_approval_cb",
                    "Leave Application-custom_hod_remarks",
                    "Leave Application-custom_hod_by",
                    "Leave Application-custom_hod_on",
                    "Leave Application-custom_approval_cb2",
                    "Leave Application-custom_hr_remarks",
                    "Leave Application-custom_hr_by",
                    "Leave Application-custom_hr_on",
                    "Leave Application-custom_return_remarks",
                    "Leave Application-custom_accounts_section",
                    "Leave Application-custom_advance_amount",
                    "Leave Application-custom_accounts_cb",
                    "Leave Application-custom_accounts_by",
                    "Leave Application-custom_accounts_on",
                    "Leave Application-custom_back_section",
                    "Leave Application-custom_reported_back",
                    "Leave Application-custom_back_cb",
                    "Leave Application-custom_reported_back_on",
                    "Leave Encashment-custom_branch",
                    "Leave Encashment-custom_encashment_status",
                    "Leave Encashment-custom_lpl_section",
                    "Leave Encashment-custom_leave_application",
                    "Leave Encashment-custom_reason",
                    "Leave Encashment-custom_lpl_cb",
                    "Leave Encashment-custom_days_requested",
                    "Leave Encashment-custom_per_day",
                    "Leave Encashment-custom_approval_section",
                    "Leave Encashment-custom_supervisor_remarks",
                    "Leave Encashment-custom_supervisor_by",
                    "Leave Encashment-custom_supervisor_on",
                    "Leave Encashment-custom_approval_cb1",
                    "Leave Encashment-custom_hr_remarks",
                    "Leave Encashment-custom_hr_by",
                    "Leave Encashment-custom_hr_on",
                    "Leave Encashment-custom_approval_cb2",
                    "Leave Encashment-custom_gm_remarks",
                    "Leave Encashment-custom_gm_by",
                    "Leave Encashment-custom_gm_on",
                    "Leave Encashment-custom_management_section",
                    "Leave Encashment-custom_ed_remarks",
                    "Leave Encashment-custom_ed_by",
                    "Leave Encashment-custom_ed_on",
                    "Leave Encashment-custom_approval_cb3",
                    "Leave Encashment-custom_forwarded_by",
                    "Leave Encashment-custom_forwarded_on",
                    "Leave Encashment-custom_approval_cb4",
                    "Leave Encashment-custom_accounts_remarks",
                    "Leave Encashment-custom_accounts_by",
                    "Leave Encashment-custom_accounts_on",
                    "Leave Encashment-custom_return_remarks",
                    "Employee Advance-custom_lpl_section",
                    "Employee Advance-custom_advance_type",
                    "Employee Advance-custom_badge_no",
                    "Employee Advance-custom_work_section",
                    "Employee Advance-custom_branch",
                    "Employee Advance-custom_lpl_cb",
                    "Employee Advance-custom_date_of_appointment",
                    "Employee Advance-custom_gross_pay",
                    "Employee Advance-custom_outstanding_before",
                    "Employee Advance-custom_leave_application",
                    "Employee Advance-custom_salary_advance_request",
                    "Employee Advance-custom_salary_advance_run",
                    "Employee Advance-custom_reason",
                    "Employee Advance-custom_advance_status",
                    "Employee Advance-custom_eligibility_section",
                    "Employee Advance-custom_qualifies",
                    "Employee Advance-custom_limit",
                    "Employee Advance-custom_pay_category",
                    "Employee Advance-custom_processing_date",
                    "Employee Advance-custom_period_start",
                    "Employee Advance-custom_eligibility_cb",
                    "Employee Advance-custom_eligibility_remarks",
                    "Employee Advance-custom_days_absent",
                    "Employee Advance-custom_off_duty_days",
                    "Employee Advance-custom_requested_on",
                    "Employee Advance-custom_attendance_section",
                    "Employee Advance-custom_attendance_confirmed",
                    "Employee Advance-custom_attendance_cb",
                    "Employee Advance-custom_attendance_remarks",
                    "Employee Advance-custom_sanction_section",
                    "Employee Advance-custom_section_head_amount",
                    "Employee Advance-custom_section_head_remarks",
                    "Employee Advance-custom_section_head_by",
                    "Employee Advance-custom_section_head_on",
                    "Employee Advance-custom_sanction_cb",
                    "Employee Advance-custom_ed_amount",
                    "Employee Advance-custom_ed_remarks",
                    "Employee Advance-custom_ed_by",
                    "Employee Advance-custom_ed_on",
                    "Employee Advance-custom_signoff_section",
                    "Employee Advance-custom_accounts_manager_remarks",
                    "Employee Advance-custom_accounts_manager_by",
                    "Employee Advance-custom_accounts_manager_on",
                    "Employee Advance-custom_hr_remarks",
                    "Employee Advance-custom_hr_by",
                    "Employee Advance-custom_hr_on",
                    "Employee Advance-custom_signoff_cb",
                    "Employee Advance-custom_payroll_remarks",
                    "Employee Advance-custom_payroll_by",
                    "Employee Advance-custom_payroll_on",
                    "Employee Advance-custom_finance_remarks",
                    "Employee Advance-custom_finance_by",
                    "Employee Advance-custom_finance_on",
                    "Employee Advance-custom_return_remarks",
                    "Employee Advance-custom_recovery_section",
                    "Employee Advance-custom_approved_amount",
                    "Employee Advance-custom_instalments",
                    "Employee Advance-custom_first_recovery_month",
                    "Employee Advance-custom_recovery_cb",
                    "Employee Advance-custom_recovered_amount",
                    "Employee Advance-custom_outstanding",
                    "Employee Advance-custom_recovery_component",
                    "Employee Advance-custom_recoveries",
                    "Employee Advance-custom_consent_section",
                    "Employee Advance-custom_consent",
                    "Employee Advance-custom_consent_cb",
                    "Employee Advance-custom_consent_on",
                    "Employee Advance-custom_paid_section",
                    "Employee Advance-custom_paid_on",
                    "Employee Advance-custom_paid_cb",
                    "Employee Advance-custom_bank_reference",
                    "Travel Request-custom_lpl_section",
                    "Travel Request-custom_badge_no",
                    "Travel Request-custom_grade",
                    "Travel Request-custom_department",
                    "Travel Request-custom_branch",
                    "Travel Request-custom_lpl_cb",
                    "Travel Request-custom_start_date",
                    "Travel Request-custom_start_time",
                    "Travel Request-custom_end_date",
                    "Travel Request-custom_end_time",
                    "Travel Request-custom_allowance_status",
                    "Travel Request-custom_totals_section",
                    "Travel Request-custom_total",
                    "Travel Request-custom_advance",
                    "Travel Request-custom_less_advance",
                    "Travel Request-custom_totals_cb",
                    "Travel Request-custom_balance_due",
                    "Travel Request-custom_qualifies",
                    "Travel Request-custom_eligibility_remarks",
                    "Travel Request-custom_approval_section",
                    "Travel Request-custom_supervisor_remarks",
                    "Travel Request-custom_supervisor_by",
                    "Travel Request-custom_supervisor_on",
                    "Travel Request-custom_approval_cb",
                    "Travel Request-custom_hr_remarks",
                    "Travel Request-custom_hr_by",
                    "Travel Request-custom_hr_on",
                    "Travel Request-custom_approval_cb2",
                    "Travel Request-custom_gm_remarks",
                    "Travel Request-custom_gm_by",
                    "Travel Request-custom_gm_on",
                    "Travel Request-custom_return_remarks",
                    "Travel Request-custom_payment_section",
                    "Travel Request-custom_paid_amount",
                    "Travel Request-custom_paid_on",
                    "Travel Request-custom_payment_cb",
                    "Travel Request-custom_payment_reference",
                    "Travel Request-custom_accounts_remarks",
                    "Travel Request-custom_accounts_by",
                    "Travel Request-custom_accounts_on",
                    "Travel Request Costing-custom_days",
                    "Travel Request Costing-custom_rate",
                    "Travel Request Costing-custom_remarks",
                    "Expense Claim-custom_lpl_section",
                    "Expense Claim-custom_badge_no",
                    "Expense Claim-custom_work_section",
                    "Expense Claim-custom_branch",
                    "Expense Claim-custom_occasion",
                    "Expense Claim-custom_relation",
                    "Expense Claim-custom_lpl_cb",
                    "Expense Claim-custom_claim_details",
                    "Expense Claim-custom_reason",
                    "Expense Claim-custom_evidence",
                    "Expense Claim-custom_claim_status",
                    "Expense Claim-custom_approval_section",
                    "Expense Claim-custom_genuine",
                    "Expense Claim-custom_supervisor_remarks",
                    "Expense Claim-custom_supervisor_by",
                    "Expense Claim-custom_supervisor_on",
                    "Expense Claim-custom_approval_cb",
                    "Expense Claim-custom_hod_remarks",
                    "Expense Claim-custom_hod_by",
                    "Expense Claim-custom_hod_on",
                    "Expense Claim-custom_hr_remarks",
                    "Expense Claim-custom_hr_by",
                    "Expense Claim-custom_hr_on",
                    "Expense Claim-custom_approval_cb2",
                    "Expense Claim-custom_gm_remarks",
                    "Expense Claim-custom_gm_by",
                    "Expense Claim-custom_gm_on",
                    "Expense Claim-custom_return_remarks",
                    "Expense Claim-custom_payment_section",
                    "Expense Claim-custom_paid_on",
                    "Expense Claim-custom_payment_cb",
                    "Expense Claim-custom_payment_reference",
                    "Expense Claim-custom_accounts_remarks",
                    "Expense Claim-custom_accounts_by",
                    "Expense Claim-custom_accounts_on",
                    "Expense Claim Type-custom_lpl_section",
                    "Expense Claim Type-custom_is_standard",
                    "Expense Claim Type-custom_standard_amount",
                    "Expense Claim Type-custom_percent_of_gross",
                    "Expense Claim Type-custom_max_times",
                    "Expense Claim Type-custom_lpl_cb",
                    "Expense Claim Type-custom_occasion",
                    "Expense Claim Type-custom_requires_evidence",
                    "Expense Claim Type-custom_is_allowance_line",
                    "Expense Claim Type-custom_for_gender",
                    "Expense Claim Type-custom_relations",
                    "Employee Separation-custom_lpl_section",
                    "Employee Separation-custom_exit_type",
                    "Employee Separation-custom_reason",
                    "Employee Separation-custom_branch",
                    "Employee Separation-custom_date_of_joining",
                    "Employee Separation-custom_lpl_cb",
                    "Employee Separation-custom_notice_given",
                    "Employee Separation-custom_notice_days",
                    "Employee Separation-custom_relieving_date",
                    "Employee Separation-custom_notice_served",
                    "Employee Separation-custom_notice_short_days",
                    "Employee Separation-custom_letter_section",
                    "Employee Separation-custom_termination_date",
                    "Employee Separation-custom_termination_reason",
                    "Employee Separation-custom_letter_cb",
                    "Employee Separation-custom_summoned_on",
                    "Employee Separation-custom_letter_signed_on",
                    "Employee Separation-custom_property_handed_on",
                    "Employee Separation-custom_progress_section",
                    "Employee Separation-custom_exit_interview",
                    "Employee Separation-custom_clearance",
                    "Employee Separation-custom_progress_cb",
                    "Employee Separation-custom_settlement",
                    "Employee Separation-custom_tools_handed",
                    "Employee Separation-custom_status_updated",
                    "Exit Interview-custom_lpl_section",
                    "Exit Interview-custom_exit_status",
                    "Exit Interview-custom_separation",
                    "Exit Interview-custom_branch",
                    "Exit Interview-custom_supervisor_remarks",
                    "Exit Interview-custom_supervisor_by",
                    "Exit Interview-custom_supervisor_on",
                    "Exit Interview-custom_lpl_cb",
                    "Exit Interview-custom_hod_remarks",
                    "Exit Interview-custom_hod_by",
                    "Exit Interview-custom_hod_on",
                    "Exit Interview-custom_lpl_cb2",
                    "Exit Interview-custom_hr_remarks",
                    "Exit Interview-custom_hr_by",
                    "Exit Interview-custom_hr_on",
                    "Exit Interview-custom_return_remarks",
                    "Full and Final Statement-custom_lpl_section",
                    "Full and Final Statement-custom_settlement_status",
                    "Full and Final Statement-custom_separation",
                    "Full and Final Statement-custom_clearance",
                    "Full and Final Statement-custom_exit_type",
                    "Full and Final Statement-custom_branch",
                    "Full and Final Statement-custom_lpl_cb",
                    "Full and Final Statement-custom_gross_pay",
                    "Full and Final Statement-custom_months_served",
                    "Full and Final Statement-custom_notice_short_days",
                    "Full and Final Statement-custom_leave_balance",
                    "Full and Final Statement-custom_net_payable",
                    "Full and Final Statement-custom_net_in_words",
                    "Full and Final Statement-custom_bank_section",
                    "Full and Final Statement-custom_account_name",
                    "Full and Final Statement-custom_bank_name",
                    "Full and Final Statement-custom_bank_cb",
                    "Full and Final Statement-custom_bank_branch",
                    "Full and Final Statement-custom_account_number",
                    "Full and Final Statement-custom_approval_section",
                    "Full and Final Statement-custom_accounts_remarks",
                    "Full and Final Statement-custom_accounts_by",
                    "Full and Final Statement-custom_accounts_on",
                    "Full and Final Statement-custom_employee_signed",
                    "Full and Final Statement-custom_employee_remarks",
                    "Full and Final Statement-custom_employee_signed_by",
                    "Full and Final Statement-custom_employee_signed_on",
                    "Full and Final Statement-custom_approval_cb",
                    "Full and Final Statement-custom_ed_remarks",
                    "Full and Final Statement-custom_ed_by",
                    "Full and Final Statement-custom_ed_on",
                    "Full and Final Statement-custom_payroll_remarks",
                    "Full and Final Statement-custom_payroll_by",
                    "Full and Final Statement-custom_payroll_on",
                    "Full and Final Statement-custom_return_remarks",
                    "Full and Final Statement-custom_payroll_section",
                    "Full and Final Statement-custom_payroll_date",
                    "Full and Final Statement-custom_salary_component",
                    "Full and Final Statement-custom_payroll_cb",
                    "Full and Final Statement-custom_additional_salary",
                    "Employee Grievance-custom_lpl_section",
                    "Employee Grievance-custom_reported_to",
                    "Employee Grievance-custom_assigned_hod",
                    "Employee Grievance-custom_booked_on",
                    "Employee Grievance-custom_branch",
                    "Employee Grievance-custom_lpl_cb",
                    "Employee Grievance-custom_due_on",
                    "Employee Grievance-custom_overdue",
                    "Employee Grievance-custom_informal_notes",
                    "Employee Grievance-custom_outcome_section",
                    "Employee Grievance-custom_meeting_notes",
                    "Employee Grievance-custom_remedy",
                    "Employee Grievance-custom_outcome_cb",
                    "Employee Grievance-custom_outcome_accepted",
                    "Employee Grievance-custom_appeal_filed",
                    "Employee Grievance-custom_appealed_on",
                    "Employee Grievance-custom_appeals_authority",
                    "Employee Grievance-custom_appeal_outcome",
                    "Grievance Type-custom_lpl_section",
                    "Grievance Type-custom_timeline_days",
                    "Grievance Type-custom_lpl_cb",
                    "Grievance Type-custom_default_handler",
                    "Shift Type-custom_allowance_section",
                    "Shift Type-custom_shift_allowance",
                    "Shift Type-custom_allowance_cb",
                    "Shift Type-custom_allowance_component",
                    "Employee Grade-custom_gradar_section",
                    "Employee Grade-custom_grade_code",
                    "Employee Grade-custom_gradar_points",
                    "Employee Grade-custom_min_salary",
                    "Employee Grade-custom_gradar_cb",
                    "Employee Grade-custom_max_salary",
                    "Employee Grade-custom_step_count",
                    "Employee Grade-custom_second_approval",
                    "Employee Grade-custom_steps_section",
                    "Employee Grade-custom_steps",
                    "Travel Request-custom_destination",
                    "Travel Request-custom_currency",
                    "Travel Request-custom_per_diem_rate",
                    "Travel Request-custom_scale_remarks",
                    "Travel Request Costing-custom_from_scale",
                    "Employee-custom_documents_tab",
                    "Employee-custom_documents_section",
                    "Employee-custom_documents",
                    "Employee-custom_documents_status",
                    "Employee-custom_flags_section",
                    "Employee-custom_is_foreign",
                    "Employee-custom_drives",
                    "Employee-custom_operates_machinery",
                    "Employee-custom_flags_cb",
                    "Employee-custom_sacco_member",
                    "Employee-custom_union_member",
                    "Employee-custom_ppe_size",
                    "Employee-custom_plant_cost_centre",
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
                    "Appraisal-appraisal_template-mandatory_depends_on",
                    "Appraisal-appraisal_template-description",
                    "Appraisal-appraisal_kra-hidden",
                    "Appraisal-goals-hidden",
                    "Appraisal-self_ratings-hidden",
                    "Appraisal Template-goals-hidden",
                    "Appraisal Template-rating_criteria-hidden",
                    "Appraisal Template-section_break_7-hidden",
                    "Employee-ctc-permlevel",
                    "Employee-salary_currency-permlevel",
                    "Employee-salary_mode-permlevel",
                    "Employee-bank_name-permlevel",
                    "Employee-bank_ac_no-permlevel",
                    "Employee-iban-permlevel",
                    "Appraisal Template-goals-reqd",
                    "Appraisal Template-goals-description",
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

# An employee is shown the leave plans of their own plant and department
permission_query_conditions = {
    "Annual Leave Plan": "hrms_addon.hrms_addon.leave.plan_query_conditions",
}

has_permission = {
    "Annual Leave Plan": "hrms_addon.hrms_addon.leave.plan_has_permission",
}

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
        # Pre-Interview Bio-Data (LPL/HR/19): dates, years, repeated rows;
        # then the CV read and the screening answers lined up (cv_screening.py)
        "validate": [
            "hrms_addon.hrms_addon.bio_data.validate",
            "hrms_addon.hrms_addon.cv_screening.applicant_validate",
        ],
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
    "Appraisal Template": {
        # the role's balanced scorecard, carried on Frappe HR's own
        # template: the weights total 80 and 20 before it goes active (bsc.py)
        "validate": "hrms_addon.hrms_addon.bsc.template_validate",
    },
    # LPL/HR/15 on Frappe HR's own Leave Application: the balances of
    # Part 2, the three signatures of Part 3, and the advance of Part 4
    # (leave.py)
    "Leave Application": {
        "validate": "hrms_addon.hrms_addon.leave.application_validate",
        "on_submit": "hrms_addon.hrms_addon.leave.application_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.leave.application_on_cancel",
    },
    # Leave worked through, paid instead (minutes §4.5): after Frappe HR's
    # own validate has read the balance, the chain's checks and the days
    # priced from the salary where no per-day amount is set (encashments.py)
    # However the day is marked, a late arrival acknowledged in advance
    # makes it a full day, not a late one (attendance.py)
    "Attendance": {
        "validate": "hrms_addon.hrms_addon.attendance.attendance_validate",
    },
    "Leave Encashment": {
        "validate": "hrms_addon.hrms_addon.encashments.encashment_validate",
        "on_submit": "hrms_addon.hrms_addon.encashments.encashment_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.encashments.encashment_on_cancel",
    },
    # Luuka's three advances on Frappe HR's own Employee Advance: who may
    # take one, the two sanctions LPL/HR/21 carries, and the instalments it
    # is recovered in (advances.py)
    # output pay: Per Meter, Per Piece and the hourly casuals (output_pay.py)
    "Production Machine": {
        "validate": "hrms_addon.hrms_addon.output_pay.machine_validate",
    },
    "Daily Production Report": {
        "validate": "hrms_addon.hrms_addon.output_pay.report_validate",
        "on_submit": "hrms_addon.hrms_addon.output_pay.report_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.output_pay.report_on_cancel",
    },
    "Output Pay Run": {
        "validate": "hrms_addon.hrms_addon.output_pay.run_validate",
        "on_submit": "hrms_addon.hrms_addon.output_pay.run_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.output_pay.run_on_cancel",
    },
    "Employee Advance": {
        "validate": "hrms_addon.hrms_addon.advances.advance_validate",
        "on_submit": "hrms_addon.hrms_addon.advances.advance_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.advances.advance_on_cancel",
    },
    # An advance paid out goes onto the payroll, and a cancelled payment
    # takes back what the payroll has not taken (advances.py)
    "Payment Entry": {
        "on_submit": "hrms_addon.hrms_addon.advances.payment_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.advances.payment_on_cancel",
    },
    "Journal Entry": {
        "on_submit": "hrms_addon.hrms_addon.advances.payment_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.advances.payment_on_cancel",
    },
    # The slip that takes a loan's, a penalty's or an advance's monthly
    # deduction marks that month recovered, and a cancelled slip gives it
    # back (recoveries.py)
    "Salary Slip": {
        "on_submit": "hrms_addon.hrms_addon.recoveries.slip_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.recoveries.slip_on_cancel",
    },
    # LPL.HR.31, the travel allowance, on Frappe HR's own Travel Request:
    # the days and the rate on each line, the totals, and the four
    # signatures the chart gives (allowances.py)
    "Travel Request": {
        "validate": "hrms_addon.hrms_addon.allowances.allowance_validate",
        "on_submit": "hrms_addon.hrms_addon.allowances.allowance_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.allowances.allowance_on_cancel",
    },
    # LPL/HR/27, the Employees Claim Form, on their own Expense Claim: the
    # supervisor's "genuine" line and the chain above it (benefits.py)
    "Expense Claim": {
        "validate": "hrms_addon.hrms_addon.benefits.claim_validate",
        "on_submit": "hrms_addon.hrms_addon.benefits.claim_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.benefits.claim_on_cancel",
    },
    # Both exits on Frappe HR's own Employee Separation: the notice the Act
    # asks for, whether it was served, and the letter an involuntary exit
    # carries (exits.py)
    "Employee Separation": {
        "validate": "hrms_addon.hrms_addon.exits.separation_validate",
        "on_submit": "hrms_addon.hrms_addon.exits.separation_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.exits.separation_on_cancel",
    },
    # The exit interview's three signatures (4.5, step 4)
    "Exit Interview": {
        "validate": "hrms_addon.hrms_addon.exits.interview_validate",
        "on_submit": "hrms_addon.hrms_addon.exits.interview_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.exits.interview_on_cancel",
    },
    # The non-disciplinary concern (5.4) on Frappe HR's own Employee
    # Grievance: the HOD it is assigned to and the timeline the system
    # The Gradar band and its ten steps on Frappe HR's own Employee Grade,
    # and a word where a salary is set outside the band it belongs to
    # (grades.py)
    "Employee Grade": {
        "validate": "hrms_addon.hrms_addon.grades.grade_validate",
    },
    "Salary Structure Assignment": {
        "validate": "hrms_addon.hrms_addon.grades.assignment_validate",
    },
    # Submitting a signable document is itself an approval, and an
    # approval nobody can point at is not much of one, so it is written
    # into the Signature Log. Frappe reads "*" alongside a doctype's own
    # handlers; signatures.log_submission filters on SIGNABLE, so one
    # entry covers all of them and none of the blocks above is disturbed.
    "*": {
        "on_submit": "hrms_addon.hrms_addon.signatures.log_submission",
    },
    # watches (discipline.py)
    "Employee Grievance": {
        "validate": "hrms_addon.hrms_addon.discipline.concern_validate",
        "on_submit": "hrms_addon.hrms_addon.discipline.concern_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.discipline.concern_on_cancel",
    },
    # LPL/HR/20 on their Full and Final Statement: what is due, what comes
    # off, the employee's own signature and the payroll run it is paid in
    # (settlements.py)
    "Full and Final Statement": {
        "validate": "hrms_addon.hrms_addon.settlements.settlement_validate",
        "on_submit": "hrms_addon.hrms_addon.settlements.settlement_on_submit",
        "on_cancel": "hrms_addon.hrms_addon.settlements.settlement_on_cancel",
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
        # Each document's status and the days left on it, worked out on
        # the employee's own form (documents.py); and an employee who has
        # left comes back only through the Executive Director's
        # reinstatement (minutes §6.2, exits.py)
        "validate": [
            "hrms_addon.hrms_addon.documents.employee_validate",
            "hrms_addon.hrms_addon.exits.employee_validate",
        ],
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
        # Attendance: top management marked present without punching, and
        # a gate pass nobody closed (attendance.py)
        "hrms_addon.hrms_addon.attendance.daily",
        # The punches that never landed, pushed again (devices.py)
        "hrms_addon.hrms_addon.devices.daily",
        # Leave: a planned leave falling due told to the employee and their
        # supervisor, and a leave nobody has reported back from (leave.py)
        "hrms_addon.hrms_addon.leave.daily",
        # Advances: one waiting to be paid, and one still owed after its
        # last instalment should have been taken (advances.py)
        "hrms_addon.hrms_addon.advances.daily",
        # Salary advance requests past their last month are ended; the
        # Payroll Officer and HR are reminded when requests close and on the
        # processing date (salary_advances.py)
        "hrms_addon.hrms_addon.salary_advances.daily",
        # An allowance approved and waiting on Accounts (allowances.py)
        "hrms_addon.hrms_addon.allowances.daily",
        # A claim waiting on Accounts, and whose birthday is coming — the
        # second recommendation of the test script (benefits.py)
        "hrms_addon.hrms_addon.benefits.daily",
        # Loans: a repayment falling due, and one fully repaid (loans.py)
        "hrms_addon.hrms_addon.loans.daily",
        # What a slip took that is not marked on its loan, penalty or
        # advance yet, such as a slip submitted before the hook existed
        # (recoveries.py)
        "hrms_addon.hrms_addon.recoveries.daily",
        # Exits: a notice period that has run out, and an exit with no
        # clearance form drawn up (exits.py)
        "hrms_addon.hrms_addon.exits.daily",
        # Employee relations: an appeal window that lapses, a concern past
        # its timeline, a suspension that ends today (discipline.py)
        "hrms_addon.hrms_addon.discipline.daily",
        # Talent: a review cycle that opens and drafts its placements, a
        # trainee milestone that has fallen due, top talent flagged a
        # flight risk (talent.py)
        "hrms_addon.hrms_addon.talent.daily",
        # Shifts: every active rotation whose period has turned gets its
        # Shift Assignments for the period ahead, and on the 25th the
        # shift allowances are drawn for the cycle that closed (shifts.py)
        "hrms_addon.hrms_addon.shifts.daily",
        "hrms_addon.hrms_addon.shifts.monthly",
        # A document running out: three months, a month, a week, and the
        # day it goes, each threshold crossed once (documents.py)
        "hrms_addon.hrms_addon.documents.daily",
    ],
    "hourly": [
        # Every enabled ZKTeco machine read and pushed into Employee
        # Checkin. See devices.py.
        "hrms_addon.hrms_addon.devices.pull_all",
        # and the punches BioTime is holding, which is where the machines
        # push them (biotime.py). Nothing happens while it is switched off.
        "hrms_addon.hrms_addon.biotime.pull_all",
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
