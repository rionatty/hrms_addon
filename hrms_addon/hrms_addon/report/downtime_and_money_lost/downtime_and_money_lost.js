// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Why machines stood and where the money went (downtime_and_money_lost.py).
frappe.query_reports["Downtime and Money Lost"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{
			fieldname: "work_section",
			label: __("Section"),
			fieldtype: "Link",
			options: "Work Section",
			get_query() {
				const branch = frappe.query_report.get_filter_value("branch");
				return { filters: branch ? { branch } : {} };
			},
		},
		{ fieldname: "shift", label: __("Shift"), fieldtype: "Select", options: "\nDay\nNight" },
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: "By Reason\nBy Machine\nBy Section\nMoney Lost",
			default: "By Reason",
		},
	],
};
