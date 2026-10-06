// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Appraisal Results: every appraisal of a period with what is to become of
// the employee, and how far that has got. Prepare Report for Management
// puts the appraisals shown, or the ones ticked, on a Performance Review
// for the General Manager and the Executive Director to approve.

const HA_AR_METHODS = "hrms_addon.hrms_addon.appraisals.";
const HA_AR_OUTCOMES = ["Promotion", "Salary Increase", "Performance Improvement Plan", "Close"];
const HA_AR_OUTCOME_COLOURS = {
	Promotion: "green",
	"Salary Increase": "blue",
	"Performance Improvement Plan": "red",
	Close: "gray",
};
const HA_AR_STAGES = ["Recommended", "Proposed by HR", "With Management", "Approved", "Not Rated Yet"];
const HA_AR_STAGE_COLOURS = {
	"Not Rated Yet": "gray",
	Recommended: "gray",
	"Proposed by HR": "blue",
	"With Management": "orange",
	Approved: "green",
};
// below the pass mark a score is red (appraisal_rules.PIP_BELOW)
const HA_AR_PASS_MARK = 60;

frappe.query_reports["Appraisal Results"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "appraisal_cycle", label: __("Appraisal Cycle"), fieldtype: "Link", options: "Appraisal Cycle" },
		{ fieldname: "year", label: __("Year"), fieldtype: "Int" },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "outcome", label: __("Outcome"), fieldtype: "Select", options: [""].concat(HA_AR_OUTCOMES) },
		{ fieldname: "stage", label: __("Stage"), fieldtype: "Select", options: [""].concat(HA_AR_STAGES) },
		{
			fieldname: "form_type",
			label: __("Form"),
			fieldtype: "Select",
			options: ["", "Supervisory Skills (LPL/HR/18)", "Balanced Scorecard"],
		},
		{ fieldname: "score_from", label: __("Score From"), fieldtype: "Percent" },
		{ fieldname: "score_to", label: __("Score To"), fieldtype: "Percent" },
		{ fieldname: "on_pip", label: __("On an Improvement Plan"), fieldtype: "Check" },
		{ fieldname: "include_unrated", label: __("Include Not Rated Yet"), fieldtype: "Check" },
	],

	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "outcome" && data.outcome) {
			return `<span class="indicator-pill ${HA_AR_OUTCOME_COLOURS[data.outcome] || "gray"}">${value}</span>`;
		}
		if (column.fieldname === "stage" && data.stage) {
			return `<span class="indicator-pill ${HA_AR_STAGE_COLOURS[data.stage] || "gray"}">${value}</span>`;
		}
		if (column.fieldname === "score") {
			// a score not given is kept as 0: only a rated appraisal is below the mark
			return hrms_addon.pip.score_html(value, !!data.band && Number(data.score) < HA_AR_PASS_MARK);
		}
		if (column.fieldname === "employee_name") {
			return hrms_addon.pip.mark_html(value, data.on_pip);
		}
		return value;
	},

	onload(report) {
		if (frappe.model.can_create("Performance Review")) {
			report.page.add_inner_button(__("Prepare Report for Management"), () => ha_appraisal_results_prepare(report));
		}
	},
};

function ha_appraisal_results_prepare(report) {
	const filters = report.get_filter_values();
	if (!filters.appraisal_cycle) {
		frappe.msgprint(__("Choose the Appraisal Cycle first: a report covers one quarter."));
		return;
	}
	const ticked = frappe.query_report
		.get_checked_items()
		.map((row) => row.appraisal)
		.filter(Boolean);
	frappe.confirm(
		ticked.length
			? __("Put the {0} ticked appraisals on a Performance Review for management?", [ticked.length])
			: __("Put the appraisals shown on a Performance Review for management?"),
		() =>
			frappe
				.xcall(HA_AR_METHODS + "review_from_results", { filters: filters, appraisals: ticked })
				.then((result) => {
					let message = __("{0} added to {1}.", [result.added, result.name]);
					if (result.unfinished) {
						message += " " + __("{0} not completed yet, left out.", [result.unfinished]);
					}
					frappe.show_alert({ message: message, indicator: "green" }, 7);
					frappe.set_route("Form", "Performance Review", result.name);
				})
	);
}
