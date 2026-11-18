// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Graduate Trainee Progress"] = {
	filters: [
		{ fieldname: "cohort", label: __("Cohort"), fieldtype: "Link", options: "Graduate Cohort" },
		{ fieldname: "discipline", label: __("Discipline"), fieldtype: "Data" },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
	],
};
