// HRMS Addon — client-side branding.
//
// Almost all of the white-labelling is done SERVER-side, by writing
// Frappe's own Website Settings / Navbar Settings fields — see
// hrms_addon/hrms_addon/branding.py. Do not add anything here that
// could be done there instead; a stored field beats a DOM patch.
//
// What is left for this file is the handful of labels that are rendered
// in the browser from each app's own hooks, which the server has no
// supported way to override from a different app:
//
//   * the app name in the workspace sidebar switcher ("Frappe HR")
//   * the same name on the /app/desktop launcher tiles
//
// Both come from frappe.boot.apps_data, which is built from every
// installed app's `add_to_apps_screen` hook. We rewrite the boot copy
// BEFORE the sidebar reads it, which is why this file is loaded as a
// plain asset in app_include_js rather than waiting on a ready event.
//
// Opt-in: "Rebrand App Labels In The Desk" on HRMS Addon Branding. Off
// by default, because renaming somebody else's app in their own UI is
// a decision, not a default.

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;

	const branding = frappe.boot.hrms_addon_branding || {};
	if (!branding.rebrand_app_labels) return;

	const product = (branding.product_name || "").trim();
	if (!product) return;

	// Apps whose label is Frappe's own product naming rather than a
	// description of what the app does. Renaming these is the point;
	// renaming, say, a client's own app would not be.
	const REBRAND = {
		frappe: true,
		erpnext: true,
		hrms: true,
		hrms_addon: true,
	};

	const apps = (frappe.boot.apps_data && frappe.boot.apps_data.apps) || [];
	apps.forEach((app) => {
		if (!REBRAND[app.name]) return;
		app.app_title = product;
		if (branding.company_logo) app.app_logo_url = branding.company_logo;
	});

	// The sidebar switcher caches the title it rendered with, so a
	// route change after boot can put the old one back. Cheap to redo.
	function relabel_sidebar() {
		const el = document.querySelector(".sidebar-app-switcher .app-title, .app-switcher-menu .app-title");
		if (el && el.textContent.trim() && el.textContent.trim() !== product) {
			el.textContent = product;
		}
	}

	$(document).on("startup", relabel_sidebar);
	$(document).on("page-change", () => setTimeout(relabel_sidebar, 60));
})();
