// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Board Leavers"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -2) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_end() },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },		{ fieldname: "population", label: __("Population"), fieldtype: "Select", options: ["", "Permanent", "Casual", "Expatriate"] },
		{ fieldname: "exit_type", label: __("Exit Type"), fieldtype: "Select", options: ["", "Voluntary", "Involuntary"] },
		{ fieldname: "regrettable", label: __("Regrettable Only"), fieldtype: "Check" },
	],
};
