// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The HR Excellence scorecard (hr_excellence_scorecard.py): eight pillars,
// each opening to the figures behind it, for a week, month or quarter.
const HES_LIGHTS = {
	"On Target": "green",
	Attention: "orange",
	"Needs Attention": "orange",
	Critical: "red",
	"Critical: Red Flag": "red",
	"No Data": "gray",
};
function hes_light(value, row, column, data, default_formatter) {
	const shown = default_formatter(value, row, column, data);
	if (column.fieldname.endsWith("status") && HES_LIGHTS[value]) {
		return `<span class="indicator-pill ${HES_LIGHTS[value]}">${shown}</span>`;
	}
	return data && data.bold ? `<b>${shown}</b>` : shown;
}
const HES_MONTH_NAMES = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];
function hes_week_now() {
	const today = new Date();
	const first = (year) => {
		const day = new Date(year, 0, 1);
		return new Date(year, 0, 1 + ((8 - day.getDay()) % 7));
	};
	let start = first(today.getFullYear());
	if (today < start) start = first(today.getFullYear() - 1);
	return Math.floor((today - start) / (7 * 86400000)) + 1;
}

frappe.query_reports["HR Excellence Scorecard"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{
			fieldname: "work_section",
			label: __("Section"),
			fieldtype: "Link",
			options: "Work Section",
			get_query() {
				const branch = frappe.query_report.get_filter_value("branch");
				return { filters: branch ? { branch } : {} };
			},
		},
		{ fieldname: "shift", label: __("Shift"), fieldtype: "Select", options: "\nDay\nNight" },
		{
			fieldname: "period_type",
			label: __("Period"),
			fieldtype: "Select",
			options: "Week\nMonth\nQuarter",
			default: "Month",
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "week",
			label: __("Week"),
			fieldtype: "Int",
			default: hes_week_now(),
			depends_on: "eval:doc.period_type=='Week'",
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: HES_MONTH_NAMES.join("\n"),
			default: HES_MONTH_NAMES[new Date().getMonth()],
			depends_on: "eval:doc.period_type=='Month'",
		},
		{
			fieldname: "quarter",
			label: __("Quarter"),
			fieldtype: "Select",
			options: "Q1\nQ2\nQ3\nQ4",
			default: "Q" + (Math.floor(new Date().getMonth() / 3) + 1),
			depends_on: "eval:doc.period_type=='Quarter'",
		},
	],
	tree: true,
	name_field: "id",
	parent_field: "parent_id",
	initial_depth: 0,
	formatter: hes_light,
};
