// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Who was invited, registered and came to each session, or by employee,
// department or plant (session_attendance.py).
frappe.query_reports["Session Attendance"] = {
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
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: "Session\nEmployee\nDepartment\nPlant",
			default: "Session",
		},
		{ fieldname: "include_scheduled", label: __("Sessions to Come Too"), fieldtype: "Check" },
	],
};
