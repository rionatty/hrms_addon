// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Luuka's names in the search bar. The three advances are Frappe HR's own
// Employee Advance with an Advance Type (advances.py), so "Salary
// Advance" is not a DocType the search bar knows: typed, it finds nothing.
// Each is taught here, as Frappe teaches its own "Background Jobs": the
// name opens the advances of that type, and "New ..." starts one.
//
// app_include_js, a plain file rather than a bundle, so a change to it
// needs no `bench build`.

$(document).on("app_ready", () => {
	const utils = frappe.search && frappe.search.utils;
	if (!utils || !utils.make_function_searchable) return;
	if (!frappe.model.can_read("Employee Advance")) return;
	if (frappe.model.can_read("Salary Advance Request")) {
		utils.make_function_searchable(
			() => frappe.set_route("List", "Salary Advance Request"),
			__("Salary Advance")
		);
		if (frappe.model.can_create("Salary Advance Request")) {
			utils.make_function_searchable(
				() => frappe.new_doc("Salary Advance Request"),
				__("New Salary Advance")
			);
		}
	}
	for (const kind of ["Leave Advance", "Special Advance"]) {
		utils.make_function_searchable(
			() => frappe.set_route("List", "Employee Advance", { custom_advance_type: kind }),
			__(kind)
		);
		if (frappe.model.can_create("Employee Advance")) {
			utils.make_function_searchable(
				() => frappe.new_doc("Employee Advance", { custom_advance_type: kind }),
				__("New {0}", [__(kind)])
			);
		}
	}
});
