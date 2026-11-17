// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const SKC_LIGHTS = { "No Cover": "red", "Single Point of Failure": "red", Thin: "orange", OK: "green", "Not Assessed": "gray" };

frappe.query_reports["Skills Cover"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "work_section", label: __("Section"), fieldtype: "Link", options: "Work Section" },
		{
			fieldname: "skill_type",
			label: __("Skill Type"),
			fieldtype: "Select",
			options: "\nMachine or Area\nTechnical\nSafety\nQuality\nBehavioural\nLeadership",
		},
		{ fieldname: "critical_only", label: __("Critical Only"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		const shown = default_formatter(value, row, column, data);
		return column.fieldname === "cover" && SKC_LIGHTS[value]
			? `<span class="indicator-pill ${SKC_LIGHTS[value]}">${shown}</span>`
			: shown;
	},
};
