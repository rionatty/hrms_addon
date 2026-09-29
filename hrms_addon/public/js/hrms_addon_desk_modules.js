// HRMS Addon — the modules taken off the desk (HRMS Addon Branding > Desk
// Modules).
//
// The server sets each tile's hidden flag (hrms_addon/hrms_addon/
// desk_modules.py), which the desktop and the sidebar's list of modules
// honour. A user who has rearranged their own desktop sees their saved copy
// of the tiles instead, so the tiles are hidden here by name as well, which
// covers them without touching anyone's saved layout.
//
// A plain asset in app_include_js, so a change to it needs no `bench build`.

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;
	frappe.provide("hrms_addon");

	function css_string(value) {
		return String(value).replace(/[\\"]/g, "\\$&").replace(/[\n\r\f]/g, " ");
	}

	hrms_addon.hide_desk_modules = function (labels) {
		const selectors = (labels || []).map((label) => `.desktop-icon[data-id="${css_string(label)}"]`);
		let style = document.getElementById("ha-hidden-modules");
		if (!style) {
			style = document.createElement("style");
			style.id = "ha-hidden-modules";
			document.head.appendChild(style);
		}
		style.textContent = selectors.length ? `${selectors.join(",\n")} { display: none !important; }` : "";
	};

	hrms_addon.hide_desk_modules(frappe.boot.hrms_addon_hidden_modules);
})();
