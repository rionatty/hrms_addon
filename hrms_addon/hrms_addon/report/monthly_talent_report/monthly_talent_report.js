// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Monthly Talent Report"] = {
	filters: [
		{ fieldname: "month", label: __("Any Day in the Month"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
	],
};
