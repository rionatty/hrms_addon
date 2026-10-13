// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Serving Notice"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "branch",
			label: __("Plant"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "exit_type",
			label: __("Exit Type"),
			fieldtype: "Select",
			options: ["", "Voluntary", "Involuntary"],
		},
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Serving Notice", "Left in the Last 30 Days", "All Open Exits"],
			default: "Serving Notice",
			reqd: 1,
		},
	],
	// the last days of a notice, and a notice cut short, stand out
	formatter(value, row, column, data, default_formatter) {
		const text = default_formatter(value, row, column, data);
		if (!data) return text;
		if (column.fieldname === "days_left" && data.stage !== "Left" && data.days_left <= 3) {
			return `<span class="text-danger bold">${text}</span>`;
		}
		if (column.fieldname === "days_left" && data.stage !== "Left" && data.days_left <= 7) {
			return `<span class="text-warning bold">${text}</span>`;
		}
		if (column.fieldname === "days_short" && data.days_short > 0) {
			return `<span class="text-danger">${text}</span>`;
		}
		return text;
	},
};
