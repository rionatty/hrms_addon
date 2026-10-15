// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Live colour picking. Every change repaints the desk immediately by
// setting the CSS custom properties on :root, so the result is visible
// before saving. Leaving the form without saving puts the saved palette
// back — an unsaved experiment must not follow you around the desk.

// fieldname -> CSS variable. Source of truth is
// hrms_addon/hrms_addon/theme.py (FIELD_TO_VAR) — keep them in step.
const HA_THEME_FIELDS = {
	primary_navy:          "--hra-primary",
	dark_navy:             "--hra-primary-dark",
	section_header_colour: "--hra-primary-mid",
	sidebar_background:    "--hra-shell",
	navbar_background:     "--hra-shell-dark",
	canvas_top:            "--hra-canvas-top",
	canvas_bottom:         "--hra-canvas-bottom",
	accent_colour:         "--hra-accent",
	selected_highlight:    "--hra-shell-marker",
	page_background:       "--hra-wash",
	zebra_tint:            "--hra-pale",
	border_colour:         "--hra-border",
	danger_colour:         "--hra-danger",
	warning_colour:        "--hra-amber-text",
	success_colour:        "--hra-success",
};

function ha_relative_luminance(hex) {
	let body = (hex || "").replace("#", "");
	if (body.length === 3) body = body.split("").map((c) => c + c).join("");
	if (body.length !== 6) return null;
	const channels = [0, 2, 4].map((i) => {
		const v = parseInt(body.substr(i, 2), 16) / 255;
		return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
	});
	return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

// how far apart two colours are for reading, 1:1 to 21:1
function ha_contrast(text, background) {
	const a = ha_relative_luminance(text);
	const b = ha_relative_luminance(background);
	if (a === null || b === null) return null;
	return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

// a colour field's value, or the colour it ships with (its placeholder)
function ha_colour_of(frm, fieldname) {
	const field = frm.fields_dict[fieldname];
	return frm.doc[fieldname] || (field && field.df.placeholder) || "";
}

function ha_preview(frm) {
	const root = document.documentElement;
	// Density is independent of the colour switch — see theme.py.
	root.setAttribute("data-ha-density", (frm.doc.density || "Compact").toLowerCase());
	root.classList.toggle("ha-cockpit", ha_cockpit_on(frm.doc));
	Object.entries(HA_THEME_FIELDS).forEach(([fieldname, cssVar]) => {
		const value = (frm.doc[fieldname] || "").trim();
		if (frm.doc.enabled && value) {
			root.style.setProperty(cssVar, value);
		} else {
			root.style.removeProperty(cssVar);
		}
	});
}

// The cockpit repaints the workspace; the module pages draw it in the desk
// home's look instead, so it shows only with Module Pages set to Standard
// (theme.py workspace_cockpit_enabled).
function ha_cockpit_on(doc) {
	return !!(doc.enabled && doc.workspace_cockpit && doc.module_pages === "Standard");
}

function ha_restore_saved() {
	const root = document.documentElement;
	root.setAttribute(
		"data-ha-density",
		((frappe.boot && frappe.boot.hrms_addon_density) || "Compact").toLowerCase()
	);
	root.classList.toggle("ha-cockpit", !!(frappe.boot && frappe.boot.hrms_addon_workspace_cockpit));
	const saved = (frappe.boot && frappe.boot.hrms_addon_theme) || {};
	Object.values(HA_THEME_FIELDS).forEach((cssVar) => root.style.removeProperty(cssVar));
	Object.entries(saved).forEach(([cssVar, value]) => root.style.setProperty(cssVar, value));
}

// The colours text sits on, so the ones that can become unreadable: white
// on the navy of the headers and the sidebar (and the cockpit's canvas,
// where it shows), and Dark Navy on the gold of the buttons. Only a colour
// picked here is checked; a pair is checked as soon as either side is.
// 4.5:1 is the WCAG AA floor for body text.
function ha_show_contrast(frm) {
	if (!frm.doc.enabled) {
		frm.dashboard.clear_headline();
		return;
	}
	const white = "#FFFFFF";
	const checks = [
		[__("Primary Navy"), frm.doc.primary_navy, white],
		[__("Dark Navy"), frm.doc.dark_navy, white],
		[__("Sidebar"), frm.doc.sidebar_background, white],
	];
	if (ha_cockpit_on(frm.doc)) {
		checks.push([__("Canvas (Top)"), frm.doc.canvas_top, white], [__("Canvas (Bottom)"), frm.doc.canvas_bottom, white]);
	}
	if (frm.doc.selected_highlight || frm.doc.dark_navy) {
		checks.push([__("Text on Gold"), ha_colour_of(frm, "selected_highlight"), ha_colour_of(frm, "dark_navy")]);
	}
	const parts = [];
	let worst = false;
	checks.forEach(([label, colour, text]) => {
		if (!colour) return;
		const ratio = ha_contrast(text, colour);
		if (ratio === null) return;
		const ok = ratio >= 4.5;
		if (!ok) worst = true;
		parts.push(
			`${frappe.utils.escape_html(label)}: <b style="color:${ok ? "var(--green-600,#28a745)" : "var(--red-600,#dc3545)"}">` +
			`${ratio.toFixed(1)}:1</b>`
		);
	});
	if (!parts.length) {
		frm.dashboard.clear_headline();
		return;
	}
	frm.dashboard.set_headline(
		__("Text contrast") + ": " + parts.join(" &nbsp;·&nbsp; ") +
		(worst
			? ` &nbsp; <span style="color:var(--red-600,#dc3545)">${__("Below 4.5:1. Text will be hard to read.")}</span>`
			: ` &nbsp; <span class="text-muted">${__("All above the 4.5:1 readability floor.")}</span>`)
	);
}

const ha_handlers = {
	onload(frm) {
		// Put the saved palette back when navigating away with the
		// preview still applied.
		if (!window.__ha_theme_route_hook) {
			window.__ha_theme_route_hook = true;
			frappe.router.on("change", () => {
				const route = frappe.get_route() || [];
				if (route[1] !== "HRMS Addon Theme Settings") ha_restore_saved();
			});
		}
	},

	refresh(frm) {
		ha_preview(frm);
		ha_show_contrast(frm);

		frm.add_custom_button(__("Reset to Defaults"), () => {
			frappe.call({
				method: "hrms_addon.hrms_addon.doctype.hrms_addon_theme_settings.hrms_addon_theme_settings.get_default_palette",
				callback(r) {
					if (!r.message) return;
					Object.entries(r.message).forEach(([fieldname, value]) => {
						frm.set_value(fieldname, value);
					});
					frappe.show_alert({
						message: __("Default colours restored. Save to keep them."),
						indicator: "blue",
					});
				},
			});
		});

		frm.add_custom_button(__("Open a Workspace"), () => frappe.set_route("Workspaces", "Home"));
	},

	after_save(frm) {
		// Keep the client-side copy of the boot palette current, so
		// navigating away restores what was just saved, not what the
		// page loaded with.
		if (frappe.boot) {
			const palette = {};
			Object.entries(HA_THEME_FIELDS).forEach(([fieldname, cssVar]) => {
				const value = (frm.doc[fieldname] || "").trim();
				if (frm.doc.enabled && value) palette[cssVar] = value;
			});
			frappe.boot.hrms_addon_theme = palette;
			frappe.boot.hrms_addon_workspace_cockpit = ha_cockpit_on(frm.doc) ? 1 : 0;
			frappe.boot.hrms_addon_density = frm.doc.density || "Compact";
		}
		ha_show_contrast(frm);
	},

	enabled(frm) {
		ha_preview(frm);
		ha_show_contrast(frm);
	},

	workspace_cockpit(frm) {
		ha_preview(frm);
		ha_show_contrast(frm);
	},

	module_pages(frm) {
		ha_preview(frm);
		ha_show_contrast(frm);
	},

	density(frm) {
		ha_preview(frm);
	},
};

// Repaint on every colour change
Object.keys(HA_THEME_FIELDS).forEach((fieldname) => {
	ha_handlers[fieldname] = (frm) => {
		ha_preview(frm);
		ha_show_contrast(frm);
	};
});

frappe.ui.form.on("HRMS Addon Theme Settings", ha_handlers);
