// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Advance Payment Report"] = {
	filters: [
		{
			fieldname: "salary_advance_processing",
			label: __("Salary Advance Processing"),
			fieldtype: "Link",
			options: "Salary Advance Processing",
			reqd: 1,
		},
		{
			fieldname: "salary_mode",
			label: __("Salary Mode"),
			fieldtype: "Select",
			options: "\nBank\nCash\nCheque",
		},
	],
};
