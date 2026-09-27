// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Applicant Screening: tick applicants and Set Status in one go, or Screen
// Again an opening's applicants (cv_screening.py).

const HA_SCREENING = "hrms_addon.hrms_addon.cv_screening.";
const HA_RESULT_COLOURS = { Meets: "green", "Below Pass Mark": "orange", "Does Not Meet": "red" };

frappe.query_reports["Applicant Screening"] = {
	filters: [
		{ fieldname: "job_opening", label: __("Job Opening"), fieldtype: "Link", options: "Job Opening" },
		{
			fieldname: "result",
			label: __("Result"),
			fieldtype: "Select",
			options: ["", "Meets", "Below Pass Mark", "Does Not Meet", "Not Checked"],
		},
		{ fieldname: "min_score", label: __("Match at Least"), fieldtype: "Percent" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Replied", "Shortlisted", "Hold", "Rejected", "Accepted"],
		},
		{ fieldname: "from_date", label: __("Applied From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date" },
	],

	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "screening_result" && data && data.screening_result) {
			return `<span class="indicator-pill ${HA_RESULT_COLOURS[data.screening_result] || "gray"}">${value}</span>`;
		}
		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Set Status"), () => ha_screening_set_status(report));
		report.page.add_inner_button(__("Screen Again"), () => ha_screening_again(report));
	},
};

function ha_screening_set_status(report) {
	const ticked = frappe.query_report
		.get_checked_items()
		.map((row) => row.job_applicant)
		.filter(Boolean);
	if (!ticked.length) {
		frappe.msgprint(__("Tick the applicants first."));
		return;
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Set Status for {0} Ticked", [ticked.length]),
		fields: [
			{
				fieldname: "status",
				fieldtype: "Select",
				label: __("Status"),
				reqd: 1,
				options: ["Open", "Replied", "Hold", "Rejected"],
				description: __("Rejected sends the regret email where HR Settings says so."),
			},
		],
		primary_action_label: __("Set Status"),
		primary_action(values) {
			frappe
				.xcall(HA_SCREENING + "set_applicant_status", { applicants: ticked, status: values.status })
				.then((result) => {
					dialog.hide();
					const esc = (text) => frappe.utils.escape_html(text);
					const lines = [__("{0} changed.", [result.changed.length])];
					if (result.skipped.length) {
						lines.push("", __("Left as they were:"));
						result.skipped.forEach(([name, why]) => lines.push(esc(name) + ": " + esc(why)));
					}
					frappe.msgprint(lines.join("<br>"), __("Set Status"));
					report.refresh();
				});
		},
	});
	dialog.show();
}

function ha_screening_again(report) {
	const opening = report.get_filter_value("job_opening");
	if (!opening) {
		frappe.msgprint(__("Choose the Job Opening to screen again."));
		return;
	}
	frappe
		.xcall(HA_SCREENING + "rescreen", { job_opening: opening })
		.then((message) => frappe.show_alert({ message: message, indicator: "green" }));
}
