// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Leave Schedule"] = {
	filters: [
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "branch",
			label: __("Plant"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],
};
