// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Monthly Manpower and Headcount"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: Number(frappe.datetime.get_today().slice(0, 4)),
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("January") },
				{ value: 2, label: __("February") },
				{ value: 3, label: __("March") },
				{ value: 4, label: __("April") },
				{ value: 5, label: __("May") },
				{ value: 6, label: __("June") },
				{ value: 7, label: __("July") },
				{ value: 8, label: __("August") },
				{ value: 9, label: __("September") },
				{ value: 10, label: __("October") },
				{ value: 11, label: __("November") },
				{ value: 12, label: __("December") },
			],
			default: Number(frappe.datetime.get_today().slice(5, 7)),
		},
		{
			fieldname: "use_attendance_cycle",
			label: __("Use the 26th-to-25th Cycle"),
			fieldtype: "Check",
			default: 1,
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "employment_type",
			label: __("Employment Type"),
			fieldtype: "Link",
			options: "Employment Type",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "movement" && data && data.movement) {
			const colour = data.movement < 0 ? "red" : "green";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (column.fieldname === "unpriced" && data && data.unpriced) {
			value = `<span class="indicator-pill orange">${value}</span>`;
		}
		return value;
	},
};
