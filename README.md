## HRMS Addon

HR customisations for Frappe HR / ERPNext. Built against **frappe 16.33 /
erpnext 16.34 / hrms 16.17**.

Right now the app is the **UI and white-labelling layer** — the SAP
Business One navy desk theme lifted from
[`rionatty/stock_addon`](https://github.com/rionatty/stock_addon) branch
`pre-sap`, plus branding, density and workspace-ordering controls. No HR
business logic yet; that is what gets built on top.

### What ships

| Piece | Where | Needs `bench build`? |
|---|---|---|
| B1 navy desk theme | `public/css/hrms_addon.bundle.css` | yes |
| Runtime palette | `hrms_addon/theme.py` | no |
| Desk JS (palette, density, status colours) | `public/js/hrms_addon_theme.js` | no |
| Collapsible form sidebar | `public/js/form_sidebar_toggle.js` | no |
| Client-side app relabelling | `public/js/hrms_addon_branding.js` | no |
| Theme + density screen | `hrms_addon/doctype/hrms_addon_theme_settings/` | no |
| Branding screen | `hrms_addon/doctype/hrms_addon_branding/` | no |
| Branding applier | `hrms_addon/branding.py` | no |
| Workspace reorganisation | `hrms_addon/workspace_setup.py` | no |
| Its own workspace | `hrms_addon/workspace/hrms_addon/` | no |

### The launcher tile

The app's tile lands on `/desk/hrms-addon`, the Workspace record shipped at
`hrms_addon/hrms_addon/workspace/hrms_addon/`. It holds links to the Theme
and Branding screens, which otherwise are only reachable by search.

Two things make this easy to break, so `scripts/verify_branding.py` checks
both:

- **The prefix is `/desk/`, not `/app/`.** v16 rewrites `/app/(.*)` to
  `/desk/\1` (`website_redirects` in frappe's hooks), so an `/app/…` route
  silently becomes `/desk/…` and 404s under a name you never typed.
- **`app_home` is the hook that matters.** `frappe/boot.py` builds the
  tile's route from the `app_home` hook — falling back to
  `"/desk/" + slug(first workspace)` — and never reads the `route` key in
  `add_to_apps_screen`. The sidebar switcher reads that key instead, so
  both are set and must agree.

Renaming the Workspace record means changing `app_home` too;
`slug()` is just `name.lower().replace(" ", "-")`.

### Density

**HRMS Addon Theme Settings → Density** — Comfortable / Compact / Dense.
Applies live, independent of the colour switch. Ships as **Compact**.

It moves form section padding, control spacing and grid rows, workspace
card padding, the `/app/desktop` launcher — and the **content width**.

Compact and Dense run content **edge to edge**; Comfortable restores
upstream's centred 900px column. That is Frappe's own `--page-max-width`,
which workspaces, forms, the form footer, the grid-row editor and tree
views all read, so they uncap together.

The trade-off is real and worth knowing before you pick: a form is
label/value pairs in two columns, so on a 1691px content area each column
clears 800px and a date field renders that wide, with its value a long way
from its label. An intermediate cap doesn't fix that — it just puts the
gutters back. If it bothers you, switch to **Comfortable**. Frappe's own
per-user *Toggle Full Width* still works on top of either.

The launcher is worth knowing about. Upstream v16 sizes it so that
`.icons-container` is a flex item of a centred flex parent — which makes
it `max-content` wide, which collapses every `1fr` grid column onto the
127px tile. The result is always `6 × 127 + 5 × 16 = 842px`, centred,
however wide the screen is, and hard-capped at 18 tiles by three fixed
rows. Widening it takes three changes together (a real container width,
fixed column tracks instead of `1fr`, and `justify-content: center`);
any one alone is a no-op. Comfortable deliberately leaves all of it
alone — that setting means "upstream spacing". The full reasoning is in
the DENSITY block of the stylesheet.

### Branding

**HRMS Addon Branding** writes Frappe's own fields rather than
overriding templates. Nothing here patches a `.html`.

| Field | Lands in | Drives |
|---|---|---|
| Product Name | `Website Settings.app_name` | desk browser tab, login heading, login emails |
| Company Logo | `Website Settings.app_logo` **and** `Navbar Settings.app_logo` | desk navbar, `/app/desktop` header, login page |
| Favicon | `Website Settings.favicon` | browser tab icon |
| Splash Image | `Website Settings.splash_image` | the desk boot splash |
| Footer "Powered By" | `Website Settings.footer_powered` | replaces "Powered by ERPNext" on every public page |

Two of those need a note:

- **The logo is written twice on purpose.** The desk navbar resolves via
  `get_app_logo()` (Website Settings → Navbar Settings → `app_logo_url`
  hook), but `/app/desktop` reads `Navbar Settings.app_logo` *only* — it
  never looks at Website Settings. Writing both keeps them in step.
- **Footer "Powered By" needs no override.** `footer_info.html` uses this
  field when set and falls through to a template otherwise; ERPNext ships
  its own `footer_powered.html` shadowing Frappe's. Setting the field
  beats both.

**Safety rule: a blank field is never pushed.** Migrate re-applies this on
every deploy, and silently wiping a logo someone set by hand would be a
nasty surprise. Clear a value at its source instead. `scripts/verify_branding.py`
asserts the code still honours this.

The launcher tile for this app comes from the static `app_logo_url` /
`add_to_apps_screen` hooks, which cannot read a database field — they
point at `public/images/company-logo-placeholder.svg`. **Replace that file**
rather than the path; the Branding screen's "Use Placeholder Logo" button
references it too.

Frappe caps neither brand mark's height (`#brand-logo { width: auto }`,
and nothing at all on the navbar `img`), so a real logo would overflow the
52px bar. The stylesheet caps both.

**Rebrand App Labels In The Desk** is opt-in and off by default — renaming
someone else's app inside their own UI is a decision, not a default.

### Workspace reorganisation

`hrms_addon/workspace_setup.py` holds four declarations —
`WORKSPACE_ORDER`, `WORKSPACE_HIDE`, `SIDEBAR_LINKS`, `SIDEBAR_HIDE` —
so changing the menu is a data edit, not a code change. **They ship empty**,
pending the agreed order, and `apply_on_migrate` is a no-op until they are
filled in.

It only ever nudges `sequence_id` / `is_hidden` / `idx` on records that
already exist, and skips anything not installed. These are ERPNext's and
Frappe HR's own Workspace records — deleting and recreating them would
lose site customisations and fight every upstream update.

### Namespacing

Everything is prefixed so this app can sit on the same site as Stock Addon
without either clobbering the other:

| | Stock Addon | HRMS Addon |
|---|---|---|
| CSS variables | `--agri-*` | `--hra-*` |
| Cockpit class | `.sa-cockpit` | `.ha-cockpit` |
| Sidebar classes | `.sa-sidebar-toggle`, `.sa-form-sidebar-collapsed` | `.ha-sidebar-toggle`, `.ha-form-sidebar-collapsed` |
| Boot keys | `stock_addon_theme` | `hrms_addon_theme`, `hrms_addon_density`, `hrms_addon_branding` |
| localStorage | `stock_addon:form_sidebar_collapsed` | `hrms_addon:form_sidebar_collapsed` |

Both ship the same base palette, so installing both is visually harmless —
but enable **Use Custom Colours** in only one of the two settings screens.

### Install

```
bench get-app hrms_addon /path/to/hrms_addon
bench --site <site> install-app hrms_addon
bench build --app hrms_addon
bench --site <site> clear-cache
```

`bench build` is required — `app_include_css` points at a bundle. Every JS
file is a plain asset and loads without it.

### Verifying

The palette, density and branding contracts are each declared in three or
four places by necessity (server boot, form script, doctype schema,
stylesheet). Two scripts assert they still agree. Neither needs a bench,
a site or a database:

```bash
python scripts/verify_js.py && python scripts/verify_positions.py && python scripts/verify_performance.py && python scripts/verify_palette.py && python scripts/verify_branding.py && python scripts/verify_fixtures.py && python scripts/verify_requisition_workflow.py && python scripts/verify_job_description.py && python scripts/verify_bio_data.py && python scripts/verify_careers.py && python scripts/verify_interviews.py && python scripts/verify_onboarding.py && python scripts/verify_probation.py && python scripts/verify_contracts.py && python scripts/verify_alerts.py && python scripts/verify_navigation.py && python scripts/verify_training.py
```

`verify_careers.py` covers the careers portal: the Job Opening page
(`templates/generators/job_opening.html`, which replaces HRMS's template of
the same path because Frappe searches the last-installed app first), the
Job Application Form web form at `/apply` (step 1 the application, steps 2 to
5 the Pre-Interview Bio-Data) and their stylesheet
`public/css/careers.css`. It checks that the page escapes what it prints and
shows only the candidate-facing parts of the Job Title's Job Description,
that every form field matches Job Applicant, that every list a candidate
picks from is seeded (a candidate cannot add a District or a Language), and
that the form's script has no Jinja delimiters, since Frappe renders it
through Jinja.

The Job Openings list (`www/jobs/index.html`) replaces HRMS's page the same
way, but only its markup: `www/jobs/index.py` builds the page with HRMS's
`get_context` and serves HRMS's own `index.js` and `index.css`, so search,
filters, sort and paging are still HRMS's code. The check reads HRMS's
script and fails if any element it looks for (`#sort`, `[name=card]`, the
filter checkboxes, ...) is missing from the page, which is what an HRMS
update that renames one would otherwise break silently.

`verify_job_description.py` does the same for the Job Description template on
Designation: it loads `jd_rules.py` without Frappe and checks the Balanced
Scorecard rules against real splits, including one (15.7/22.1/51.4/10.8)
that is 100% on paper but 99.99999999999999 in floating point. It also
checks the pick lists behind every dropdown of the KRA form and the JD
tables (the KRA lists, plus JD Relationship Type, Stakeholder Type,
Authority Level, Horizon, ISO Standard, Specification Type, Requirement
Priority and Competency Category): each field links to its master, no
Select is left in a JD table, and the masters are seeded once with the
values Luuka's documents use (plus any value already stored) by patch or
`after_install`, never by fixtures or `after_migrate`, which would bring
back values HR deleted. The moves of old JD text boxes into the tables
are run against the lines of LPL/JD/SM/001.

Bulk loading works two ways. **Data Import** (Document Type: Designation)
takes the tables with their Job Title — a child table is never its own
Document Type in Frappe, so this is the only way it can work — and every
pick list of the app allows import as well, so HR loads a list in one file
instead of typing values one at a time. Both verifiers fail if a master
loses `allow_import`.

The second way is per Job Title, on the form. Every table on the Job
Description tab can be filled from a CSV: each has **Download** and
**Upload** under it (Allow Bulk Edit on its Designation field). HRMS's own **Required Skills** table on the same form has them too,
set by property setter because the field is theirs (`hrms/setup.py`), which
is why `jd_rules.UPLOADABLE_TABLES` — every table the save hook cleans — is
the JD tables plus that one. Download gives the table as a CSV; fill it in
Excel, save it as CSV and Upload it. The file's rows replace the table's
rows, and saving the Job Title applies the JD rules as usual. Values picked
from a list (and KRAs, Skills, Job Titles) must already exist, as Upload creates
none. Two things Excel writes into such a file are repaired on save by
`jd_rules.uploaded_value`: a weighting saved as "25%" counts as 25, and
the curly quotes, dashes and bullets of a file saved in Excel's plain CSV
format (Windows-1252), which Frappe's upload reads as Latin-1, are put
back. The form's Download is Frappe's file with a UTF-8 byte order mark in
front, so Excel opens text that is already there correctly. The check
compares its rows with Frappe's `grid.js`, and fails if an update changes
what Upload reads.

`verify_bio_data.py` covers the Pre-Interview Bio-Data Form (LPL/HR/19) on
Job Applicant's Bio-Data tab. It loads `bio_data_rules.py` without Frappe
and runs a filled-in form through the save checks and through the
carry-over onto Employee (Create > Employee on a Job Offer or an Employee
Onboarding, routed through `bio_data.py` by `override_whitelisted_methods`),
checking every Employee field it writes exists upstream and that nothing
already on the Employee is overwritten. It also checks the Bio-Data pick
lists and child tables, the one-off Skill permission for HR User, and that
the print format only prints fields that exist, escaped.

The print format's HTML is generated into
`hrms_addon/print_format/pre_interview_bio_data_form/`; migrate re-imports
an app's Print Format only when its `modified` is newer than the site's
copy, so bump `modified` with every change to it.

`verify_interviews.py` covers the interview process. Each panel member's
**Interview Feedback** is Luuka's Candidate Interview Evaluation / Score Form
(LPL/HR/17): every criterion in the Interview Criterion list (seeded once with
the form's 17, in five Interview Criteria Groups) is scored 1 to 5 or N/A,
with a comment, and the sheet works out its total, the percentage of what it
could have scored (N/A counts for nothing either way) and the form's rating,
Excellent (90-100%) down to Below Average. The recommendation, Offer, Shortlist
(interview again) or Reject, sets HRMS's Cleared / Rejected result, and the
percentage becomes HRMS's average rating, so the Interview's panel average
and star summary use the scores. HRMS's star-rated skill assessment is set
aside by property setters. "Submit Feedback" on an Interview opens the sheet:
`public/js/interview.js` drops HRMS's handler for that event with Frappe's
own `frappe.ui.form.off` and adds one that opens the form. The Interview's
Feedback tab shows the panel's average per criterion
(`override_whitelisted_methods`). The candidate's salary history, benefits
and notice period are asked on the application form and kept on the Job
Applicant, and every sheet prints them. The check loads
`interview_rules.py` without Frappe, runs sheets through every boundary of
the scale (27 of 30 is exactly 90%, compared in whole numbers), and pins
what the design relies on in HRMS: the button still fires
`submit_feedback`, the feedback's average rating still feeds the Interview,
and the Feedback tab still reads skill and rating.

The **Interview Shortlist** comes before the interviews, one per Job
Opening, laid out like Luuka's shortlist sheet. **Get Applicants** lists
everyone who applied and can still be shortlisted, each written out from
their Pre-Interview Bio-Data: name and contacts, education, work experience,
and certifications and licences, most recent first. A qualification counts
as a certification or licence by its **Qualification Type**, a new Bio-Data
list the application form asks for. Submitting marks the applicants
Shortlisted (cancelling puts them back to Open unless another shortlist
still lists them). **Schedule Interviews** then books an HRMS Interview per
candidate, back to back from a start time, with the Interview Type's panel;
one HRMS refuses is reported and the rest still go ahead.

The **Interview Report** closes the day, laid out like Luuka's report:
one per Job Opening and interview date. **Get Interview Results** fills the
panel (everyone who sat on that day's Interviews, with their designations)
and each candidate: qualifications and experience from the Bio-Data, the
panel's score sheets averaged into a score and rating, the recommendations
counted ("Offer 3, Reject 1"), the decision when most of the panel agreed,
and the salary expectation as the start of the remarks. HR writes the
remarks and the recommendations, then sends it on. It goes, as the paper
says, through the Human Resource Manager to the Executive Director: a
Frappe Workflow, **Interview Report Approval**, declared in
`interview_report_approval.py` (no Frappe import) and built on every
migrate by `workflows.py`, the builder the Job Requisition approval now
shares. The Executive Director's approval submits the report; each step
stamps its sign-off, printed on the report with the Head of Department's.

`verify_requisition_workflow.py` loads `requisition_approval.py` directly —
it deliberately imports nothing from Frappe — and walks every approval
path: submit, each approval, rejection, revision, and a hand-typed approval
being reverted.

`verify_onboarding.py` covers the induction on Frappe HR's Employee
Onboarding: its workflow, what each step needs before it may be taken
(the Workplace Rules signed, the Employee created and its bio-data
recorded, the Supervisor, the Salary Structure and base salary, the tools
of work issued or found not needed, a required training set up), the
tools of work themselves (what every new employee gets, one request per
provider, what is still pending) and the training window. It also pins
what the design relies on in Frappe HR — how it assigns an activity's
task, when it links a new Employee back to its onboarding, and that an
update after submit runs no `validate` — so an upstream change that would
break it fails here instead of on the site.

`verify_probation.py` covers the End of Probation Evaluation /
Confirmation Form (LPL/HR/32) and the 30-60-90 day reviews (the Staff
Onboarding Form, LPL/HR/04): the form's 13 ratable factors, the 60/40
weighting with N/A left out, its bands and pass mark, the objectives taken
from the Job Title's Key Result Areas, and the route from HR through the
supervisor, the branch General Manager (non-administrative positions
only), the Head of Department and the HR Manager's recommendation to the
Executive Director's decision, with each step's checks and signature.
It also checks what the decision does to the Employee — confirmed,
extended (which makes the next evaluation) or not confirmed, which hands
HR the termination process.

`verify_alerts.py` covers **My Alerts**, the column down the right of the
desk (`public/js/hrms_addon_alerts.js`, `hrms_addon/alerts.py`). It shows
one person their own work — the assignments on their ToDo list and the
notifications they have not read — coloured by how soon each matters:
overdue red, due today or tomorrow amber, due within the week blue, the
rest grey, and a High priority assignment never quieter than amber. New
ones arrive by Frappe's own realtime `notification` event and are
announced with a toast in the same colour.

It is a **flex column of the desk body**, not an overlay: Frappe lays the
desk out as a flex row (`scss/desk/main.scss`), so a third child takes its
width from the page rather than covering it. Below 992px there is no room
for a third column and it steps aside. The check exercises the bands
without a bench and then pins the contracts between the parts: every query
filtered on `frappe.session.user` and no function taking a user to look
at, the methods the script calls whitelisted (and the two that change
something POST-only), titles escaped, a colour for every band in the
stylesheet, and the script's toast colours identical to the rules'.

`verify_navigation.py` also runs `navigation.py` against a stand-in site
that keeps child rows the way Frappe does: `append` keeps the number a row
already carries, and rows come back ordered by `idx`. A row put into the
middle of a table therefore takes a number already in use, and the two come
back interleaved — which is how the training links ended up in the wrong
cards and added again on each migrate. So the rows are numbered afresh
whenever they are written, and each link of ours is cleared from wherever
it is found and put back once at the end of its own card. The simulation
runs on a fresh site and on one already spoilt, in both read orders, and
checks a second migrate writes nothing.

`verify_js.py` covers every script the app ships. A form script that does
not parse is not a small fault: Frappe stops setting the form up where the
script throws, and the form comes up with its sections empty and nowhere to
type (the Training Requisition once shipped with a line break inside a
string). Form scripts are served as they are, not built, so nothing else
notices. The check scans each file for a string or regular expression
running past its line, an open comment or template and unmatched brackets;
really parses it where node or Chrome is at hand; and holds every form
script (a DocType's own, or one `doctype_js` attaches to a Frappe HR form)
to its DocType: handlers registered on it, and only fields, tables and
child columns that exist named in `set_value`, `set_query`, `add_child`,
`frm.doc.…` and the like.

`verify_positions.py` covers contract management (the Contract Management
forms). **Employee Position Change** carries all three letters, told apart
by its Change Type: a promotion, a change of designation or a salary
review. Every one of them says the other terms stand, so it amends the
running contract by default; Luuka asked for both, so it can issue a new
one instead, from the effective date, closing the old one the day before.
The Candidate Preamble Promotion Form is filled for a promotion and signed
by the Supervisor, the HR Manager, the General Manager and the Executive
Director, whose approval submits it and applies the change: the Employee
master, a Salary Structure Assignment from the effective date, and the
contract. Cancelling puts back what was there. **Employee Data Change
Request** is LPL/HR/34 and LPL/HR/33 in one: the old bank account or wages
phone number is read off the employee, the new one is typed, and the
Employee is written to only when HR approves, so there is a record of who
asked and who agreed. **Intern Placement** is the Intern Placement Letter,
its plant chosen per intern. The Legal Manager role the renewal and salary
letters witness with is created on migrate. The check exercises the rules
without a bench, walks the signatures, and holds every letter to the words
on the paper and to fields that exist.

`verify_performance.py` covers the appraisal round (the flowchart and
test cases 1 to 10), on the shape of the **Supervisory Skills Evaluation
Form** (LPL/HR/18): twelve ratable factors worth 60, up to eight
objectives worth 40, the form's bands, and comments and signatures from
the Employee, the Supervisor, the HR Manager, the Production Manager and
the General Manager. It is built on Frappe HR's own Appraisal Cycle and
Appraisal — the form is added to the Appraisal as custom fields rather
than replacing it — so the round keeps its appraisee list and the
Appraisal Overview chart fills as appraisals are scored. The **Appraisal
Plan** is the HR Officer's year: four quarters with their windows, a soft
deadline on the 25th and a hard one at the month's end. The daily job
tells the HR Officer when a quarter closes and reminds everyone
appraising a week, a day and on the day before. A quarter opens an
Appraisal Cycle and an Appraisal per employee. The supervisor rates in
the system, or the sheet is downloaded, filled away from it and uploaded
back. The **Performance Review** is the report shared with top
management, and its decisions are carried out: a promotion or a salary
increase raises an Employee Position Change, a score below 60 a
**Performance Improvement Plan** — an agreement with a standard to reach,
the support the company gives, how it is measured and when it is looked
at again, reviewed while it runs and closed with an outcome.

Luuka runs **two appraisal forms side by side**, so the same check covers
the **balanced scorecard** (LPL PMS FY 2026) as well. A graded role whose
job title has an active **BSC Appraisal Template** is appraised on it; a
supervisor stays on LPL/HR/18. The scorecard weights the four balanced
scorecard perspectives to 80 between them (the weight is set once per
perspective, not per KPI), scores each quarter on the percentage achieved
and the year out of ten, adds five competencies weighted to 20, and bands
at 90/80/70/60 rather than 90/75/60/50. It is signed by the Appraiser, the
Employee, the Head of Department, the HR Manager and the Executive
Director, so the workflow carries both chains and the two junctions that
differ turn on the Form Type. Luuka's own PMS workbooks import straight
in, one sheet per role: a sheet whose weights do not total 80 and 20 is
kept but left inactive with the reason on it, because the numbers are
theirs to correct. Their workbook also divides a quarter by a further ten,
which scores a perfect quarter 8 of 80; Luuka confirmed the quarterly
score is real, so that stray tenth is dropped here.

`verify_training.py` covers the training process (the To-Be flowchart, test
cases 1 to 10), built on Frappe HR's own Training Program, Training Event
and Training Feedback. Before a session: the employee's **Training Needs
Form** (LPL/TRG/FRM06), the Head of Department's **Training Requisition**
(topic, required skills, target employees; the branch HR Officer told), the
HR Officer's **Training Needs Assessment** (objectives, methods; approved by
the HR Manager then the General Manager, or returned to amend), the
**Training Calendar** (the planner, LPL/TRAINING/01, drawn from the approved
needs and approved by the General Manager) and the **Monthly Training
Schedule**, which books a draft Training Event per line with the
requisition's people as participants and tells the HODs, trainers and
trainees. The HR Officer is reminded a month before a calendar training;
everyone booked is reminded a week, a day and the morning before. The
event stays a draft while scheduled — Frappe HR lets a submitted event's
participants change but not their attendance — so attendance is marked and
the signed sheet attached on the draft, and submitting it says the training
was held. Then **Create Evaluations** drafts a Training Feedback per
participant present, carrying LPL/TRG/FRM05's ten rated items and six
questions; each scores itself and the event keeps the consolidated score.
The check exercises the rules without a bench, walks both workflows, and
pins what the glue relies on upstream (the event's mandatory fields, that
attendance is not allow_on_submit, that feedback needs a submitted event).

`verify_contracts.py` covers contract management: a contract's status on a
day, the alerts a year, a quarter and a month before its end (each sent
once, a contract first seen inside several thresholds getting one alert),
the end from the Employment Type's usual length, a renewal's dates, no two
contracts at once, the signed copy before it is submitted, the daily job,
the Contract Expiry Status report and the three letters.

`verify_fixtures.py` also needs the upstream apps checked out (it reads
their doctype JSON to resolve `insert_after`, Link targets and fetch
sources). It looks in `../ERPNext/{frappe,erpnext,hrms}`; set
`FRAPPE_APPS_ROOT` if yours live elsewhere.

Between them they check that the field→variable maps match across Python
and JS, that shipped defaults match the stylesheet's `:root`, that no
`var()` reference is undefined (an undefined one is *silently* dropped by
the browser), that every `frappe.call` and `after_migrate` path resolves to
a real function, that all three parts of the launcher fix are present, and
that no `stock_addon` identifier survived the port into live code.

Run both before committing a change to any of them.

### Editing the theme

Colours are adjustable at runtime from **HRMS Addon Theme Settings** — no
CSS edit, no rebuild. To add a new adjustable colour:

1. add a `Color` field to `hrms_addon_theme_settings.json`
2. add `fieldname -> "--hra-var"` to `FIELD_TO_VAR` in `theme.py`
3. add the same pair to `HA_THEME_FIELDS` in the form script
4. add the shipped value to `DEFAULTS` in `theme.py` **and** to `:root` in
   the stylesheet — the two must agree

`scripts/verify_palette.py` fails if you miss one of the four.

The three rules at the top of the stylesheet were each learned the hard
way. Read them before touching it.

#### License

mit
