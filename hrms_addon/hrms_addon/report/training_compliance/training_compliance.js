// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const COMPLIANCE_LIGHT = {
	Compliant: "green",
	Valid: "green",
	"Due Soon": "orange",
	Overdue: "red",
	Expired: "red",
	Pending: "blue",
	"Not Applicable": "gray",
};

frappe.query_reports["Training Compliance"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "designation", label: __("Job Title"), fieldtype: "Link", options: "Designation" },
		{ fieldname: "training_category", label: __("Category"), fieldtype: "Link", options: "Training Category" },
		{ fieldname: "mandatory_only", label: __("Mandatory Categories Only"), fieldtype: "Check" },
		{
			fieldname: "light",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOverdue\nDue Soon\nCompliant",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "light" && data && data.light) {
			value = `<span class="indicator-pill ${COMPLIANCE_LIGHT[data.light] || "gray"}">${value}</span>`;
		}
		if (column.fieldname === "employee_name" && data && data.employee) {
			value = `<a href="/app/learning-passport/${encodeURIComponent(data.employee)}">${value}</a>`;
		}
		return value;
	},
};
