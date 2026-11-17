// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Each supervisor's production score and people index (supervisor_scorecard.py).
const SUS_LIGHTS = {
	"On Target": "green",
	Attention: "orange",
	"Needs Attention": "orange",
	Critical: "red",
	"Critical: Red Flag": "red",
	"No Data": "gray",
};
function sus_light(value, row, column, data, default_formatter) {
	const shown = default_formatter(value, row, column, data);
	if (column.fieldname.endsWith("status") && SUS_LIGHTS[value]) {
		return `<span class="indicator-pill ${SUS_LIGHTS[value]}">${shown}</span>`;
	}
	return data && data.bold ? `<b>${shown}</b>` : shown;
}

frappe.query_reports["Supervisor Scorecard"] = {
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
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
	],
	formatter: sus_light,
};
