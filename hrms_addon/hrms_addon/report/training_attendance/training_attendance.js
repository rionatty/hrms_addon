// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Who came to each session, or each employee's sessions (training_attendance.py).
frappe.query_reports["Training Attendance"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "training_program", label: __("Training Program"), fieldtype: "Link", options: "Training Program" },
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			reqd: 1,
		},
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: "Session\nEmployee", default: "Session" },
	],
};
