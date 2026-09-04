## HRMS Addon

HR customisations for Frappe HR / ERPNext.

At this point the app contains **the UI layer only** — the SAP Business One
navy desk theme lifted from [`rionatty/stock_addon`](https://github.com/rionatty/stock_addon)
branch `pre-sap`. No HR logic, no doctypes beyond the theme settings, no
fixtures. That is the base the HR features get built on.

### What ships

| Piece | File | Notes |
|---|---|---|
| B1 navy desk theme | `hrms_addon/public/css/hrms_addon.bundle.css` | 903 lines, self-contained; needs `bench build` |
| Runtime palette | `hrms_addon/hrms_addon/theme.py` | field → CSS-variable contract + shipped defaults |
| Desk JS | `hrms_addon/public/js/hrms_addon_theme.js` | applies the boot palette; status indicator colours |
| Collapsible form sidebar | `hrms_addon/public/js/form_sidebar_toggle.js` | round handle on the form/panel boundary, remembered per browser |
| Theme settings screen | `hrms_addon/hrms_addon/doctype/hrms_addon_theme_settings/` | live colour preview, WCAG contrast readout, Reset to Defaults |

The **Workspace Cockpit** (navy canvas + floating white tiles on workspace
pages) is included but **off by default** — it repaints ERPNext's own
workspace layout, which varies between versions. Switch it on from the
settings screen if you want it.

### Namespacing

Everything is prefixed so this app can sit on the same site as Stock Addon
without either one clobbering the other:

| | Stock Addon | HRMS Addon |
|---|---|---|
| CSS variables | `--agri-*` | `--hra-*` |
| Cockpit class | `.sa-cockpit` | `.ha-cockpit` |
| Sidebar classes | `.sa-sidebar-toggle`, `.sa-form-sidebar-collapsed` | `.ha-sidebar-toggle`, `.ha-form-sidebar-collapsed` |
| Boot keys | `stock_addon_theme` | `hrms_addon_theme` |
| localStorage | `stock_addon:form_sidebar_collapsed` | `hrms_addon:form_sidebar_collapsed` |

Both apps ship the same base palette, so installing both is visually
harmless — but enable **Use Custom Colours** in only one of the two
settings screens, or the two palettes fight over the same desk.

### Install

```
bench get-app hrms_addon /path/to/hrms_addon
bench --site <site> install-app hrms_addon
bench build --app hrms_addon
bench --site <site> clear-cache
```

`bench build` is required — `app_include_css` points at a bundle. The two
JS files are plain assets and load without it.

### Editing the theme

Colours are adjustable at runtime from **HRMS Addon Theme Settings** (System
Manager only) — no CSS edit, no rebuild. To add a new adjustable colour:

1. add a `Color` field to `hrms_addon_theme_settings.json`
2. add `fieldname -> "--hra-var"` to `FIELD_TO_VAR` in `theme.py`
3. add the same pair to `HA_THEME_FIELDS` in `hrms_addon_theme_settings.js`
4. add the shipped value to `DEFAULTS` in `theme.py` **and** to the `:root`
   block in the stylesheet — the two must agree

The three rules at the top of the stylesheet were each learned the hard way.
Read them before touching it.

#### License

mit
