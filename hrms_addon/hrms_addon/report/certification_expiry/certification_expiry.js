// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const EXPIRY_LIGHT = {
	Compliant: "green",
	Valid: "green",
	"Due Soon": "orange",
	Overdue: "red",
	Expired: "red",
	Pending: "blue",
	"Not Applicable": "gray",
};

frappe.query_reports["Certification Expiry"] = {
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
		{ fieldname: "certification", label: __("Certification"), fieldtype: "Link", options: "Certification" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{
			fieldname: "window",
			label: __("Show"),
			fieldtype: "Select",
			options: "Run Out\nWithin 30 Days\nWithin 60 Days\nWithin 90 Days\nWithin 180 Days\nAll",
			default: "Within 180 Days",
		},
		{
			fieldname: "verification_status",
			label: __("Checked"),
			fieldtype: "Select",
			options: "\nUnverified\nVerified\nRejected",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status) {
			value = `<span class="indicator-pill ${EXPIRY_LIGHT[data.status] || "gray"}">${value}</span>`;
		}
		if (column.fieldname === "days_left" && data && data.days_left !== null && data.days_left < 0) {
			value = `<span style="color:#A62B25">${value}</span>`;
		}
		return value;
	},
};
