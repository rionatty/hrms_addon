// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Leave Plan Adherence"] = {
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
	],
};
