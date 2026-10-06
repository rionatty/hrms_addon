// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// the colour of each word the report shows: a rating on the evaluation
// form's scale, attendance, the result against the pass mark, the status
const HA_TRAINING_PILLS = {
	Excellent: "green",
	"Very Good": "green",
	Good: "orange",
	Average: "orange",
	"Below Average": "red",
	Present: "green",
	Absent: "red",
	"Not Marked": "gray",
	Effective: "green",
	"Not Effective": "red",
	Held: "green",
	Scheduled: "blue",
	Cancelled: "gray",
};
// typed in from the paper forms: shown as text
const HA_TRAINING_TEXT = ["trainer", "employee_name", "item", "question", "answer"];

frappe.query_reports["Training Report"] = {
	filters: [
		{
			fieldname: "view",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Trainings", "Participants", "Evaluation Items", "Comments"],
			default: "Trainings",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_end(),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "training_program",
			label: __("Training Program"),
			fieldtype: "Link",
			options: "Training Program",
		},
		{
			fieldname: "training_event",
			label: __("Training"),
			fieldtype: "Link",
			options: "Training Event",
			get_query: () => ({ filters: { docstatus: ["<", 2] } }),
		},
		{ fieldname: "talent_only", label: __("Talent Programmes Only"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		if (data && HA_TRAINING_TEXT.includes(column.fieldname)) {
			value = frappe.utils.escape_html(value == null ? "" : String(value));
		}
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const word = data[column.fieldname];
		if (["rating", "attendance", "result", "status"].includes(column.fieldname) && HA_TRAINING_PILLS[word]) {
			value = `<span class="indicator-pill ${HA_TRAINING_PILLS[word]}">${value}</span>`;
		}
		if (data.item === "Overall") {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
