// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Learning Health"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const shown = default_formatter(value, row, column, data);
		const colour = { Healthy: "green", Watch: "orange", "At Risk": "red", "No Data": "gray" }[value];
		return column.fieldname === "status" && colour ? `<span class="indicator-pill ${colour}">${shown}</span>` : shown;
	},
};
