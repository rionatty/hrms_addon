// HRMS Addon — global desk JS.
// (ported from rionatty/stock_addon branch `pre-sap`.)
//
// Three jobs:
//   1. Apply the colour overrides from "HRMS Addon Theme Settings".
//      They ride along on the session boot (see hrms_addon/theme.py),
//      so the desk is painted before first render — no extra request,
//      no flash of the shipped palette.
//   2. Status indicator colours for HRMS Addon doctypes.
//   3. Round desk tiles: every tile on the launcher is cut to a circle,
//      and a tile this app ships a picture for (public/icons/desktop_icons,
//      named after the tile) shows ours, navy and round, instead of its
//      app's teal square.
//
// Wrapped in an IIFE so nothing here collides with Stock Addon's copy
// when both apps are installed on one site.

(function () {
	frappe.provide("hrms_addon");

	// ── 1. Theme colour overrides ──────────────────────────────
	hrms_addon.apply_palette = function (palette) {
		const root = document.documentElement;
		Object.entries(palette || {}).forEach(([cssVar, value]) => {
			if (value) root.style.setProperty(cssVar, value);
		});
	};

	// The navy workspace cockpit is opt-in: it repaints ERPNext's own
	// workspace layout, which differs between versions, so the standard
	// display is what ships unless the setting asks otherwise.
	hrms_addon.apply_cockpit = function (on) {
		document.documentElement.classList.toggle("ha-cockpit", !!on);
	};

	// Layout density — stamped on <html> as data-ha-density; the numbers
	// live in the DENSITY block of hrms_addon.bundle.css. Independent of
	// the colour override switch.
	hrms_addon.DENSITIES = ["Comfortable", "Compact", "Dense"];
	hrms_addon.DEFAULT_DENSITY = "Compact";

	hrms_addon.apply_density = function (density) {
		const value = hrms_addon.DENSITIES.includes(density)
			? density
			: hrms_addon.DEFAULT_DENSITY;
		document.documentElement.setAttribute("data-ha-density", value.toLowerCase());
	};

	function apply_boot_palette() {
		if (!frappe.boot) return;
		if (frappe.boot.hrms_addon_theme) {
			hrms_addon.apply_palette(frappe.boot.hrms_addon_theme);
		}
		hrms_addon.apply_cockpit(frappe.boot.hrms_addon_workspace_cockpit);
		hrms_addon.apply_density(frappe.boot.hrms_addon_density);
	}

	apply_boot_palette();               // boot is usually already inlined
	$(document).on("startup", apply_boot_palette);   // belt and braces

	// ── 3. Round desk tiles ────────────────────────────────────
	// Frappe takes a tile's picture from its app's own folder only
	// (frappe.utils.get_desktop_icon), so ours is looked for first. The
	// boot lists every app's pictures, so nothing is asked of the server.
	const app_picture = frappe.utils && frappe.utils.get_desktop_icon;
	if (app_picture && !hrms_addon.round_tiles) {
		hrms_addon.round_tiles = true;
		frappe.utils.get_desktop_icon = function (icon_name, variant) {
			const style = String(variant || "").toLowerCase();
			const ours = `assets/hrms_addon/icons/desktop_icons/${style}/${frappe.scrub(icon_name || "")}.svg`;
			const shipped = (((frappe.boot && frappe.boot.desktop_icon_urls) || {}).hrms_addon || {})[style] || [];
			return shipped.includes(ours) ? `/${ours}` : app_picture.call(this, icon_name, variant);
		};
	}
	// Styled from here rather than the bundle, so the tiles are round without
	// `bench build`. Letter and folder tiles share .icon-container.
	if (!document.getElementById("hra-round-tiles")) {
		$('<style id="hra-round-tiles"></style>').text(`
			.desktop-icon .icon-container { border-radius: 50% !important; overflow: hidden;
				transition: transform .15s ease, box-shadow .15s ease; }
			.desktop-icon .icon-container img.app-icon { border-radius: 50%; }
			.desktop-icon:hover .icon-container { transform: translateY(-2px);
				box-shadow: 0 6px 14px rgba(20, 57, 94, .22); }
		`).appendTo("head");
	}

	// ── 2. Status indicator colours ────────────────────────────
	const STATUS_COLORS = {
		// Generic workflow
		"Draft":       "gray",
		"Submitted":   "blue",
		"Approved":    "green",
		"Rejected":    "red",
		"Cancelled":   "red",
		"Completed":   "green",
		"Open":        "orange",
		"In Progress": "blue",
		"Pending":     "yellow",
		"Success":     "green",
		"Failed":      "red",
		// HR flavours
		"Active":      "green",
		"Inactive":    "gray",
		"Left":        "red",
		"Suspended":   "orange",
		"On Hold":     "orange",
		"Paid":        "green",
		"Unpaid":      "orange",
	};

	hrms_addon.get_status_color = (status) => STATUS_COLORS[status] || "gray";

	// Apply an indicator dot to the status field on our own forms.
	// Add each HRMS Addon doctype that carries a `status` field here.
	const STATUS_DOCTYPES = [];

	STATUS_DOCTYPES.forEach((dt) => {
		frappe.ui.form.on(dt, {
			refresh(frm) {
				const status = frm.doc.status;
				if (!status) return;
				frm.page.set_indicator(status, hrms_addon.get_status_color(status));
			},
		});
	});
})();
