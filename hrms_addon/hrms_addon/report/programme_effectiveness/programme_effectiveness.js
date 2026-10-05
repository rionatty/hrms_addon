// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Programme Effectiveness"] = {
	filters: [
		{ fieldname: "program_type", label: __("Programme"), fieldtype: "Select", options: "\nLeadership Development\nMentoring and Coaching\nLearning and Development" },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
	],
};
