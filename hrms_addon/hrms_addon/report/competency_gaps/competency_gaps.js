// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Competency Gaps"] = {
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
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nGap\nCertificate Needed\nReassessment Due",
		},
	],
};
