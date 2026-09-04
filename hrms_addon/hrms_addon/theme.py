# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Desk theme palette.

The SAP B1 navy theme in public/css/hrms_addon.bundle.css drives every
colour through CSS custom properties. This module lets those properties
be overridden at runtime from the "HRMS Addon Theme Settings" screen —
no CSS edit, no bench build.

Flow:
  settings doc -> get_palette() -> extend_bootinfo -> frappe.boot
  -> public/js/hrms_addon_theme.js sets the properties on :root

FIELD_TO_VAR is the whole contract: add a Color field to the doctype,
add its CSS variable here, and it becomes adjustable. DEFAULTS must
mirror the :root block in the stylesheet — they are what "Reset to
Defaults" restores and what the form shows as placeholders.

The --hra- prefix is deliberate. Stock Addon ships the same theme under
--agri-, so both apps can be installed on one site without either one's
palette overwriting the other's.
"""

import frappe

# doctype fieldname -> CSS custom property
FIELD_TO_VAR = {
    "primary_navy":          "--hra-primary",
    "section_header_colour": "--hra-primary-mid",
    "sidebar_background":    "--hra-shell",
    "navbar_background":     "--hra-shell-dark",
    "canvas_top":            "--hra-canvas-top",
    "canvas_bottom":         "--hra-canvas-bottom",
    "accent_colour":         "--hra-accent",
    "selected_highlight":    "--hra-shell-marker",
    "zebra_tint":            "--hra-pale",
    "border_colour":         "--hra-border",
}

# Must match the :root blocks in public/css/hrms_addon.bundle.css — note
# there are TWO: the palette at the top, and the cockpit canvas further
# down. (Stock Addon's copy drifted here: its DEFAULTS still carried the
# pre-lightening canvas values, so "Reset to Defaults" restored a canvas
# darker than the one the stylesheet actually ships. Verified against the
# stylesheet and corrected below.)
DEFAULTS = {
    "primary_navy":          "#14395E",
    "section_header_colour": "#2A5A8C",
    "sidebar_background":    "#3A5F86",
    "navbar_background":     "#33547A",
    "canvas_top":            "#3A6A9A",
    "canvas_bottom":         "#4878A4",
    "accent_colour":         "#0A6ED1",
    "selected_highlight":    "#F0AB00",
    "zebra_tint":            "#EEF3F9",
    "border_colour":         "#C3D0E0",
}


def get_palette():
    """{css_variable: colour} for the desk to apply. Empty when the
    override is off.

    Deliberately swallows everything: this runs on every session boot,
    and a half-migrated site or a malformed colour must never be able to
    stop people logging in.
    """
    try:
        if not frappe.db.exists("DocType", "HRMS Addon Theme Settings"):
            return {}
        settings = frappe.get_cached_doc("HRMS Addon Theme Settings")
        if not settings.get("enabled"):
            return {}
        palette = {}
        for fieldname, css_var in FIELD_TO_VAR.items():
            value = (settings.get(fieldname) or "").strip()
            if value:
                palette[css_var] = value
        return palette
    except Exception:
        return {}


def workspace_cockpit_enabled():
    """Is the (opt-in) navy workspace cockpit switched on?

    It repaints ERPNext's own workspace layout wholesale, and that layout
    differs between versions, so it stays off unless asked for.
    """
    try:
        if not frappe.db.exists("DocType", "HRMS Addon Theme Settings"):
            return 0
        settings = frappe.get_cached_doc("HRMS Addon Theme Settings")
        return 1 if (settings.get("enabled") and settings.get("workspace_cockpit")) else 0
    except Exception:
        return 0


def boot_session(bootinfo):
    """extend_bootinfo hook — ship the palette with the desk boot so the
    colours are applied before first paint (no extra round trip)."""
    bootinfo.hrms_addon_theme = get_palette()
    bootinfo.hrms_addon_workspace_cockpit = workspace_cockpit_enabled()
