// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Each order's labour and losses against its value (order_feasibility.py).
const ORF_LIGHTS = { Feasible: "green", Marginal: "orange", "Not Feasible": "red" };
function orf_light(value, row, column, data, default_formatter) {
	const shown = default_formatter(value, row, column, data);
	if (column.fieldname === "feasibility" && ORF_LIGHTS[value]) {
		return `<span class="indicator-pill ${ORF_LIGHTS[value]}">${shown}</span>`;
	}
	return shown;
}

frappe.query_reports["Order Feasibility"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "finishing_section", label: __("Finishing Section"), fieldtype: "Link", options: "Work Section" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nRunning\nCompleted\nCancelled" },
		{
			fieldname: "feasibility",
			label: __("Feasibility"),
			fieldtype: "Select",
			options: "\nFeasible\nMarginal\nNot Feasible\nNo Output Yet\nSet Budget",
		},
	],
	formatter: orf_light,
};
