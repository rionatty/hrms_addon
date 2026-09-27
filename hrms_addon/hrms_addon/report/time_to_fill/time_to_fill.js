// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Time to Fill"] = {
	filters: [
		{ fieldname: "from_date", label: __("Requested From"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "designation", label: __("Job Title"), fieldtype: "Link", options: "Designation" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Pending", "Open & Approved", "Filled", "On Hold", "Rejected", "Cancelled"],
		},
	],
};
