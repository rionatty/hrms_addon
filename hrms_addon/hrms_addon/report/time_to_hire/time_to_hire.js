// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Time to Hire"] = {
	filters: [
		{ fieldname: "from_date", label: __("Offers From"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -6) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "job_opening", label: __("Job Opening"), fieldtype: "Link", options: "Job Opening" },
		{ fieldname: "designation", label: __("Designation"), fieldtype: "Link", options: "Designation" },
	],
};
