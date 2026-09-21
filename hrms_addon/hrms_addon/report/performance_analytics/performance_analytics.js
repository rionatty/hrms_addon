// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Performance Analytics"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "appraisal_cycle",
			label: __("Appraisal Cycle"),
			fieldtype: "Link",
			options: "Appraisal Cycle",
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "by_plant",
			label: __("Group by Plant Instead of Department"),
			fieldtype: "Check",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "completion" && data) {
			const colour = data.completion < 50 ? "red" : data.completion < 90 ? "orange" : "green";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (column.fieldname === "below_the_mark" && data && data.below_the_mark) {
			value = `<span class="indicator-pill red">${value}</span>`;
		}
		return value;
	},
};
