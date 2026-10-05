// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Nine-Box Distribution"] = {
	filters: [
		{ fieldname: "talent_review", label: __("Talent Review"), fieldtype: "Link", options: "Talent Review" },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "grade", label: __("Grade"), fieldtype: "Link", options: "Employee Grade" },
	],
};
