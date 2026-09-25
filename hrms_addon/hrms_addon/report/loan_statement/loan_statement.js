// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Loan Statement"] = {
	filters: [
		{
			fieldname: "loan",
			label: __("Loan"),
			fieldtype: "Link",
			options: "Employee Loan",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],
};
