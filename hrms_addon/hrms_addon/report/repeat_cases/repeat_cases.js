// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Employees with repeated cases (repeat_cases.py); names can be hidden.

frappe.query_reports["Repeat Cases"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "work_section", label: __("Section"), fieldtype: "Link", options: "Work Section" },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "hide_names", label: __("Hide Names"), fieldtype: "Check" },
	],
};
