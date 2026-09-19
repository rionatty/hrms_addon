// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Contract Expiry Status"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nActive\nExpiring Soon\nExpired\nRenewed\nNot Renewed",
		},
		{ fieldname: "ending_within", label: __("Ending Within (Days)"), fieldtype: "Int", default: 365 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_left" && data && data.days_left !== null && data.days_left !== undefined) {
			const colour = data.days_left < 0 ? "red" : data.days_left <= 30 ? "orange" : data.days_left <= 90 ? "blue" : "";
			if (colour) {
				value = `<span class="indicator-pill ${colour}">${value}</span>`;
			}
		}
		return value;
	},
};
