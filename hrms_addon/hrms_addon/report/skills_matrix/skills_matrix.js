// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const SKM_LIGHTS = { Competent: "#DDF3E6", Gap: "#F8DADA", "Certificate Needed": "#FCEFCF", "Reassessment Due": "#FCEFCF" };

frappe.query_reports["Skills Matrix"] = {
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
	],
	formatter(value, row, column, data, default_formatter) {
		const shown = default_formatter(value, row, column, data);
		const status = data && data._status && data._status[column.fieldname];
		return status && SKM_LIGHTS[status]
			? `<span style="display:block;background:${SKM_LIGHTS[status]};border-radius:4px;padding:0 6px">${shown}</span>`
			: shown;
	},
};
