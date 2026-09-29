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
// the employee's own columns, shown only where they appraise themselves
const HA_SELF_COLUMNS = [
	["custom_factors", "employee_rating"],
	["custom_objectives", "employee_rating"],
	["custom_bsc_perspectives", "self_score"],
	["custom_bsc_competencies", "self_score"],
];

frappe.ui.form.on("Appraisal", {
	setup(frm) {
		// only a template made ready to be used
		frm.set_query("appraisal_template", () => ({ filters: { custom_is_active: 1 } }));
		frm.set_query("custom_supervisor", () => ({ filters: { status: "Active" } }));
	},
	refresh(frm) {
		ha_self_columns(frm);
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
		if (total === undefined || total === null) return;
		const band = bsc ? frm.doc.custom_bsc_band : frm.doc.custom_band;
		const number = (value) => frappe.format(value || 0, { fieldtype: "Float" });
		const parts = bsc
			? [
					__("Section A {0}/80", [number(frm.doc.custom_bsc_section_a_score)]),
					__("Section B {0}/20", [number(frm.doc.custom_bsc_section_b_score)]),
					__("{0} {1}%", [frm.doc.custom_period || __("Overall"), number(total)]),
			  ]
			: [
					__("Ratable Factors {0}/60", [number(frm.doc.custom_factors_score)]),
					__("Objectives {0}/40", [number(frm.doc.custom_objectives_score)]),
					__("Total {0}%", [number(total)]),
			  ];
		if (frm.doc.custom_self_appraisal && frm.doc.self_score) {
			parts.push(__("Self {0}%", [number(frm.doc.self_score)]));
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
	custom_period(frm) {
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

frappe.ui.form.on("BSC Appraisal Perspective", {
	q1_percent(frm) {
		frm.trigger("show_score");
	},
	q2_percent(frm) {
		frm.trigger("show_score");
	},
	q3_percent(frm) {
		frm.trigger("show_score");
	},
	annual_score(frm) {
		frm.trigger("show_score");
	},
});

frappe.ui.form.on("BSC Appraisal Competency", {
	score(frm) {
		frm.trigger("show_score");
	},
});
