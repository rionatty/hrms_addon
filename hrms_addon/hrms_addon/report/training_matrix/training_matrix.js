// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The matrix (training_matrix.py): a tree from plant down to employee, a
// column per training category; a coloured cell opens its requirements.
const MATRIX_COLOURS = { green: "#DDF3E6", amber: "#FCEFCF", red: "#F8DADA" };

frappe.query_reports["Training Matrix"] = {
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
		{ fieldname: "designation", label: __("Job Title"), fieldtype: "Link", options: "Designation" },
		{
			fieldname: "down_to",
			label: __("Down To"),
			fieldtype: "Select",
			options: "Plant\nDepartment\nJob Title\nEmployee",
			default: "Employee",
		},
	],
	tree: true,
	name_field: "id",
	parent_field: "parent_id",
	initial_depth: 1,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data || !data._heat || !(column.fieldname in data._heat)) {
			return value;
		}
		const band = data._heat[column.fieldname];
		if (!band) {
			return `<span class="text-muted">–</span>`;
		}
		const options = Object.assign({}, data._filters || {});
		if ((data._categories || {})[column.fieldname]) {
			options.training_category = data._categories[column.fieldname];
		}
		options.status = ["!=", "Not Applicable"];
		const route = encodeURIComponent(JSON.stringify(options));
		return `<a style="display:block;background:${MATRIX_COLOURS[band]};border-radius:4px;padding:0 6px;color:inherit"
			onclick="frappe.route_options = JSON.parse(decodeURIComponent('${route}')); frappe.set_route('List', 'Employee Training Requirement'); return false;"
			href="#">${value}</a>`;
	},
};
