// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Board Data Quality"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -2) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_end() },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{
			fieldname: "check", label: __("Check"), fieldtype: "Select",
			options: [
				{ value: "", label: "" },
				{ value: "blank_branch", label: __("Active employees with no plant") },
				{ value: "left_without_date", label: __("Left with no relieving date") },
				{ value: "hires_without_requisition", label: __("Hires with no requisition") },
				{ value: "slips_without_branch", label: __("Salary slips with no plant") },
			],
		},
	],
};
