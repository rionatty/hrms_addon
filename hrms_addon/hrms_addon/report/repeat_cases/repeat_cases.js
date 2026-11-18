// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The case patterns (repeat_cases.py): repeat employees, flagged cases, and the
// cases by section, cause, type, shift, employment or supervisor. Names follow
// the Manufacturing Excellence Settings.

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
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
		},
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: [
				"Employees with Repeat Cases",
				"Cases with Flags",
				"By Section",
				"By Cause",
				"By Case Type",
				"By Shift",
				"By Employment",
				"By Supervisor",
			].join("\n"),
			default: "Employees with Repeat Cases",
		},
	],
};
