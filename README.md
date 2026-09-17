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
python scripts/verify_palette.py && python scripts/verify_branding.py && python scripts/verify_fixtures.py && python scripts/verify_requisition_workflow.py && python scripts/verify_job_description.py && python scripts/verify_bio_data.py && python scripts/verify_careers.py
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

`verify_requisition_workflow.py` loads `requisition_approval.py` directly —
it deliberately imports nothing from Frappe — and walks every approval
path: submit, each approval, rejection, revision, and a hand-typed approval
being reverted.

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
