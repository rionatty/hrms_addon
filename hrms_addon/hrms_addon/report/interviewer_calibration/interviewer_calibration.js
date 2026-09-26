// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Interviewer Calibration"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "designation", label: __("Designation"), fieldtype: "Link", options: "Designation" },
		{ fieldname: "interview_type", label: __("Interview Type"), fieldtype: "Link", options: "Interview Type" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// well above or below their colleagues: worth a word in calibration
		if (column.fieldname === "difference" && data && data.difference !== null && data.difference !== undefined) {
			const colour = data.difference >= 10 ? "orange" : data.difference <= -10 ? "blue" : "";
			if (colour) {
				value = `<span class="indicator-pill ${colour}">${value}</span>`;
			}
		}
		return value;
	},
};
