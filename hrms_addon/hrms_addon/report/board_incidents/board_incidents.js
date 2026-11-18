// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Board Incidents"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -2) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_end() },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{
			fieldname: "severity", label: __("Severity"), fieldtype: "Select",
			options: ["", "Near Miss", "First Aid", "Medical Treatment", "Lost Time", "Fatality"],
		},
	],
};
