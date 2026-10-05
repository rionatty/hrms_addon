// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Appraisal, carrying both of Luuka's forms: the Supervisory
// Skills Evaluation Form (LPL/HR/18) and the balanced scorecard (LPL PMS).
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

const HA_BSC = "Balanced Scorecard";
// where the appraisal is still in the employee's hands, before any rating
const HA_EARLY = ["Draft", "Pending Self-Appraisal"];
const HA_QUARTERS = ["Q1", "Q2", "Q3", "Q4"];
// the employee's own columns, shown only where they appraise themselves
const HA_SELF_COLUMNS = [
	["custom_factors", "employee_rating"],
	["custom_objectives", "employee_rating"],
	["custom_bsc_kpis", "self_percent"],
	["custom_bsc_competencies", "self_score"],
];
// every signatory's remarks, on either form (appraisal_approval.ALL_REMARK_FIELDS)
const HA_REMARK_FIELDS = [
	"custom_employee_remarks",
	"custom_supervisor_remarks",
	"custom_hod_remarks",
	"custom_hrm_remarks",
	"custom_production_remarks",
	"custom_gm_remarks",
	"custom_ed_remarks",
];

frappe.ui.form.on("Appraisal", {
	setup(frm) {
		// only a template made ready to be used
		frm.set_query("appraisal_template", () => ({ filters: { custom_is_active: 1 } }));
		frm.set_query("custom_supervisor", () => ({ filters: { status: "Active" } }));
	},
	refresh(frm) {
		ha_self_columns(frm);
		ha_quarter_columns(frm);
		ha_remarks(frm);
		ha_improvement_plan(frm);
		// where the year so far leaves the employee on the nine-box, for HR
		// and the Talent Council (talent_card.js)
		if (hrms_addon.talent_card) hrms_addon.talent_card.attach(frm, frm.doc.employee);
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(
				__("Download Sheet"),
				() =>
					window.open(
						frappe.urllib.get_full_url(
							"/api/method/hrms_addon.hrms_addon.appraisals.download_sheet?appraisal=" +
								encodeURIComponent(frm.doc.name)
						)
					),
				__("Appraise Offline")
			);
			frm.add_custom_button(__("Upload Filled Sheet"), () => ha_upload_sheet(frm), __("Appraise Offline"));
			if (HA_EARLY.includes(frm.doc.workflow_state || "Draft")) {
				frm.add_custom_button(__("Get from Template"), () =>
					frappe
						.xcall("hrms_addon.hrms_addon.appraisals.apply_template", {
							appraisal: frm.doc.name,
							template: frm.doc.appraisal_template,
						})
						.then(() => frm.reload_doc())
				);
			}
		}
		frm.trigger("show_score");
	},
	show_score(frm) {
		frm.dashboard.clear_headline();
		const colours = {
			Excellent: "green",
			"Very Good": "green",
			Good: "blue",
			Fair: "orange",
			Average: "orange",
			Poor: "red",
			"Below Average": "red",
		};
		const bsc = frm.doc.custom_form_type === HA_BSC;
		const total = bsc ? frm.doc.custom_bsc_overall : frm.doc.custom_total_score;
		const band = bsc ? frm.doc.custom_bsc_band : frm.doc.custom_band;
		// a score not given is kept as 0: only a rated appraisal has a headline
		if (!band) return;
		const number = (value) => frappe.format(value || 0, { fieldtype: "Float" });
		const parts = bsc
			? [
					__("Section A {0}/80", [number(frm.doc.custom_bsc_section_a_score)]),
					__("Section B {0}/20", [number(frm.doc.custom_bsc_section_b_score)]),
					__("{0} {1}%", [frm.doc.custom_quarter || __("Overall"), number(total)]),
			  ]
			: [
					__("Ratable Factors {0}/60", [number(frm.doc.custom_factors_score)]),
					__("Objectives {0}/40", [number(frm.doc.custom_objectives_score)]),
					__("Total {0}%", [number(total)]),
			  ];
		if (frm.doc.custom_self_appraisal && frm.doc.self_score) {
			parts.push(__("Self {0}%", [number(frm.doc.self_score)]));
		}
		const year = frm.doc.custom_annual_score;
		if (year !== undefined && year !== null && (frm.doc.custom_quarter_results || []).length > 1) {
			parts.push(__("Year to Date {0}%", [number(year)]));
		}
		frm.dashboard.set_headline(
			`<span>${parts.map((p) => frappe.utils.escape_html(p)).join(" &nbsp;|&nbsp; ")}</span>` +
				(band
					? ` <span class="indicator-pill ${colours[band] || "gray"}">${frappe.utils.escape_html(
							__(band)
					  )}</span>`
					: "")
		);
	},
	custom_form_type(frm) {
		frm.trigger("show_score");
	},
	custom_quarter(frm) {
		ha_quarter_columns(frm);
		frm.trigger("show_score");
	},
	custom_self_appraisal(frm) {
		ha_self_columns(frm);
	},
	// the supervisor follows the employee's Reports To, and their name with it
	employee(frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, "reports_to").then((r) => {
			const boss = (r.message && r.message.reports_to) || "";
			if (boss !== (frm.doc.custom_supervisor || "")) frm.set_value("custom_supervisor", boss);
		});
	},
	appraisal_template(frm) {
		if (frm.is_new() || !frm.doc.appraisal_template) return;
		if (HA_EARLY.includes(frm.doc.workflow_state || "Draft")) {
			frappe.show_alert({ message: __("Save to fill the form from this template."), indicator: "blue" });
		} else {
			frappe.show_alert({
				message: __("The appraisal keeps the template it is being rated on."),
				indicator: "orange",
			});
		}
	},
});

// The self-appraisal columns, hidden where the employee does not appraise
// themselves. The grid is rebuilt only when what it shows has to change.
function ha_self_columns(frm) {
	const show = !!frm.doc.custom_self_appraisal;
	for (const [table, fieldname] of HA_SELF_COLUMNS) {
		const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
		if (!grid) continue;
		const df = (grid.docfields || []).find((d) => d.fieldname === fieldname);
		if (!df || !df.hidden === show) continue;
		grid.update_docfield_property(fieldname, "hidden", show ? 0 : 1);
		grid.reset_grid();
	}
}

// Only the quarter appraised is filled in: its percentage and comments open,
// the earlier quarters as their own appraisals recorded them and the later
// ones on their own appraisals (the server keeps it so, appraisals.py).
function ha_quarter_columns(frm) {
	const grid = frm.fields_dict.custom_bsc_kpis && frm.fields_dict.custom_bsc_kpis.grid;
	if (!grid) return;
	let changed = false;
	for (const quarter of HA_QUARTERS) {
		const closed = quarter === frm.doc.custom_quarter ? 0 : 1;
		for (const fieldname of [quarter.toLowerCase() + "_percent", quarter.toLowerCase() + "_comments"]) {
			const df = (grid.docfields || []).find((d) => d.fieldname === fieldname);
			if (!df || (df.read_only ? 1 : 0) === closed) continue;
			grid.update_docfield_property(fieldname, "read_only", closed);
			changed = true;
		}
	}
	if (changed) grid.reset_grid();
}

// Each signatory's remarks open only at their own step (appraisal_approval
// remark_steps, from the server); the others stay as they were written.
function ha_remarks(frm) {
	const steps = (frm.doc.__onload && frm.doc.__onload.remark_steps) || {};
	const state = frm.doc.workflow_state || "Draft";
	for (const fieldname of HA_REMARK_FIELDS) {
		if (!frm.fields_dict[fieldname]) continue;
		frm.set_df_property(fieldname, "read_only", steps[fieldname] === state ? 0 : 1);
	}
}

// An employee on an improvement plan, said in red at the top
function ha_improvement_plan(frm) {
	if (!frm.doc.custom_on_pip || !frm.doc.custom_improvement_plan) return;
	const plan = (frm.doc.__onload && frm.doc.__onload.improvement_plan) || {};
	const link = `<a href="/app/performance-improvement-plan/${encodeURIComponent(
		frm.doc.custom_improvement_plan
	)}">${frappe.utils.escape_html(frm.doc.custom_improvement_plan)}</a>`;
	const until = plan.end_date ? " " + __("until {0}", [frappe.datetime.str_to_user(plan.end_date)]) : "";
	frm.set_intro(
		__("{0} is on an improvement plan: {1} ({2}){3}.", [
			frappe.utils.escape_html(frm.doc.employee_name || frm.doc.employee),
			link,
			frappe.utils.escape_html(__(plan.status || "Draft")),
			until,
		]),
		"red"
	);
}

// A KPI's weighted scores as its percentages are typed: the weight times
// the percentage achieved (bsc_rules.quarter_score); the perspectives and
// the sections follow when the appraisal is saved.
function ha_kpi_scores(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	for (const quarter of HA_QUARTERS) {
		const percent = row[quarter.toLowerCase() + "_percent"];
		row[quarter.toLowerCase() + "_score"] =
			percent === undefined || percent === null || percent === ""
				? null
				: flt((flt(row.weight) * flt(percent)) / 100, 2);
	}
	const current = frm.doc.custom_quarter ? row[frm.doc.custom_quarter.toLowerCase() + "_score"] : null;
	row.score = current === undefined ? null : current;
	frm.refresh_field("custom_bsc_kpis");
}

function ha_upload_sheet(frm) {
	new frappe.ui.FileUploader({
		restrictions: { allowed_file_types: [".xlsx"] },
		on_success: (file) =>
			frappe
				.xcall("hrms_addon.hrms_addon.appraisals.upload_sheet", {
					file_url: file.file_url,
					appraisal: frm.doc.name,
				})
				.then((found) => {
					ha_sheet_summary(found);
					frm.reload_doc();
				}),
	});
}

// What an upload took and what it did not, and why
function ha_sheet_summary(found) {
	const esc = frappe.utils.escape_html;
	const list = (rows, text) =>
		rows.length ? "<ul>" + rows.map((row) => "<li>" + text(row) + "</li>").join("") + "</ul>" : "";
	const updated = found.updated || [];
	const skipped = found.skipped || [];
	const problems = found.problems || [];
	frappe.msgprint({
		title: __("Appraisal sheet"),
		indicator: skipped.length || problems.length ? "orange" : "green",
		message: [
			__("{0} appraisal(s) updated.", [updated.length]),
			list(updated, (row) => esc(row.employee_name || row.appraisal) + ": " + esc((row.fields || []).join(", "))),
			skipped.length ? __("Not taken:") : "",
			list(skipped, (row) => esc(row.sheet) + ": " + esc(row.reason)),
			problems.length ? __("Left as they were:") : "",
			list(problems, (row) => esc(row.sheet) + ": " + esc(row.problem)),
		]
			.filter(Boolean)
			.join(""),
	});
}

for (const table of ["Appraisal Factor Rating", "Appraisal Objective Rating"]) {
	frappe.ui.form.on(table, {
		supervisor_rating(frm) {
			frm.trigger("show_score");
		},
	});
}

// A percentage achieved is from 0 to 100 and a competency is scored from 0
// to 10 (bsc_rules.figure_errors, refused at every save): a figure out of
// its range is taken off as it is typed.
function ha_in_range(cdt, cdn, field, top, message) {
	const value = locals[cdt][cdn][field];
	if (value === undefined || value === null || value === "" || (flt(value) >= 0 && flt(value) <= top)) {
		return true;
	}
	frappe.show_alert({ message: message, indicator: "red" });
	frappe.model.set_value(cdt, cdn, field, null);
	return false;
}

function ha_percent_check(field) {
	return (frm, cdt, cdn) => {
		if (ha_in_range(cdt, cdn, field, 100, __("A percentage achieved is from 0 to 100."))) {
			ha_kpi_scores(frm, cdt, cdn);
		}
	};
}

frappe.ui.form.on("BSC Appraisal KPI", {
	self_percent: ha_percent_check("self_percent"),
	q1_percent: ha_percent_check("q1_percent"),
	q2_percent: ha_percent_check("q2_percent"),
	q3_percent: ha_percent_check("q3_percent"),
	q4_percent: ha_percent_check("q4_percent"),
});

frappe.ui.form.on("BSC Appraisal Competency", {
	self_score(frm, cdt, cdn) {
		ha_in_range(cdt, cdn, "self_score", 10, __("A competency is scored from 0 to 10."));
	},
	score(frm, cdt, cdn) {
		if (ha_in_range(cdt, cdn, "score", 10, __("A competency is scored from 0 to 10."))) {
			frm.trigger("show_score");
		}
	},
});
