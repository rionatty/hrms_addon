// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Thirteen weeks or twelve months, as lines (excellence_trends.py).
frappe.query_reports["Excellence Trends"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: "13 Weeks\n12 Months", default: "13 Weeks" },
	],
};
