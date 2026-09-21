// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Succession Coverage"] = {
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
		{
			fieldname: "risk_level",
			label: __("Risk if Lost"),
			fieldtype: "Select",
			options: "\nHigh\nMedium\nLow",
		},
		{
			fieldname: "coverage",
			label: __("Coverage"),
			fieldtype: "Select",
			options: "\nCovered\nAt Risk\nGap",
		},
		{ fieldname: "gaps_only", label: __("Gaps Only"), fieldtype: "Check" },
		{
			fieldname: "single_person_only",
			label: __("Single-Person Technical Roles Only"),
			fieldtype: "Check",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "coverage" && data && data.coverage) {
			const colour = data.coverage === "Gap" ? "red" : data.coverage === "At Risk" ? "orange" : "green";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (column.fieldname === "ready_now" && data && !data.ready_now) {
			value = `<span class="indicator-pill red">${value}</span>`;
		}
		return value;
	},
};
