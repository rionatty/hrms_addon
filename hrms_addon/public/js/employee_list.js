// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Employee list, and the form's header: each employee's Status as Luuka
// names it (Resigned, On Hold...), in its own colour, where ERPNext shows
// the System Status under it (employee_status.py). The statuses come with
// the boot. doctype_list_js, read from disk when the list loads, so a change
// to it needs no `bench build`.

(() => {
	const settings = (frappe.listview_settings["Employee"] = frappe.listview_settings["Employee"] || {});
	if (settings.ha_status_shown) return;
	settings.ha_status_shown = true;
	settings.add_fields = [...(settings.add_fields || []), "custom_employee_status"];
	// the list opens on the working staff by the Status, the one the form
	// shows: every status that counts as Active
	const statuses = frappe.boot.hrms_addon_employee_statuses || {};
	const working = Object.keys(statuses).filter((name) => statuses[name].counts_as === "Active");
	if (working.length) settings.filters = [["custom_employee_status", "in", working]];
	const frappes_own = settings.get_indicator;
	settings.get_indicator = function (doc) {
		const chosen = doc.custom_employee_status;
		const known = (frappe.boot.hrms_addon_employee_statuses || {})[chosen];
		// an employee without one, or a status made since the page loaded
		if (!chosen || !known) return frappes_own ? frappes_own.call(this, doc) : undefined;
		return [__(chosen), known.colour || "gray", "custom_employee_status,=," + chosen];
	};
})();
