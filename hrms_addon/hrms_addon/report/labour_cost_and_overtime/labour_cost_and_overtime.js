// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Labour and overtime by section with the four flags, day by day, Day and
// Night (labour_cost_and_overtime.py).
function lco_monday(back) {
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const day = (today.getDay() + 6) % 7;
	return frappe.datetime.add_days(frappe.datetime.get_today(), -day - 7 * back);
}

frappe.query_reports["Labour Cost and Overtime"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: lco_monday(1), reqd: 1 },
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(lco_monday(0), -1),
			reqd: 1,
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: "By Section\nDay by Day\nDay and Night",
			default: "By Section",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const shown = default_formatter(value, row, column, data);
		if (column.fieldname === "flag" && value) return `<span class="indicator-pill red">${shown}</span>`;
		return shown;
	},
};
