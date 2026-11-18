// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The year's training budget lines against actual and forecast spend
// (learning_value.budget_vs_actual).
frappe.query_reports["Training Budget vs Actual"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
			default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "year", label: __("Year"), fieldtype: "Int", default: new Date().getFullYear(), reqd: 1 },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "group_by", label: __("By"), fieldtype: "Select", default: "Plant",
			options: "Plant\nDepartment\nCategory\nProgramme\nProvider\nMonth\nCost Type\nCost Centre" },
	],
};
