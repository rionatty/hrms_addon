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

### Density

**HRMS Addon Theme Settings → Density** — Comfortable / Compact / Dense.
Applies live, independent of the colour switch. Ships as **Compact**.

It moves form section padding, control spacing and grid rows, workspace
card padding, and the `/app/desktop` launcher.

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
python scripts/verify_palette.py && python scripts/verify_branding.py
```

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
