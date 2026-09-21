// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Luuka's balanced scorecard is built on Frappe HR's own Appraisal
// Template rather than beside it: one template per role, the four
// perspectives weighted to 80 and the competencies to 20, and the whole
// LPL PMS workbook read straight in — one sheet per role.
//
// The appraisal picks its template up by itself from the employee's role,
// so what is set here is what an appraiser sees already filled in.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Appraisal Template", {
	refresh(frm) {
		frm.add_custom_button(__("Import PMS Workbook"), () =>
			frappe.prompt(
				[
					{
						fieldname: "review_year",
						fieldtype: "Int",
						label: __("Review Year"),
						reqd: 1,
						default: frm.doc.custom_review_year || new Date().getFullYear(),
					},
					{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company") },
					{
						fieldname: "activate",
						fieldtype: "Check",
						label: __("Activate the ones that add up"),
						default: 1,
						description: __("A sheet whose weights do not total 80 and 20 is imported but left inactive."),
					},
				],
				(values) => {
					new frappe.ui.FileUploader({
						restrictions: { allowed_file_types: [".xlsx"] },
						on_success: (file) =>
							frappe
								.xcall("hrms_addon.hrms_addon.bsc.import_workbook", {
									file_url: file.file_url,
									review_year: values.review_year,
									company: values.company,
									activate: values.activate ? 1 : 0,
								})
								.then((found) => {
									const flagged = (found.flagged || []).length;
									frappe.msgprint({
										title: __("Scorecards imported"),
										indicator: flagged ? "orange" : "green",
										message: [
											__("{0} created, {1} updated.", [
												(found.created || []).length,
												(found.updated || []).length,
											]),
											flagged
												? __("{0} left inactive because their weights do not add up:", [flagged]) +
												  "<ul>" +
												  (found.flagged || [])
														.map(
															(row) =>
																"<li>" +
																frappe.utils.escape_html(row.sheet) +
																" — " +
																frappe.utils.escape_html((row.problems || []).join("; ")) +
																"</li>"
														)
														.join("") +
												  "</ul>"
												: "",
											(found.skipped || []).length
												? __("Skipped (no scorecard on the sheet): {0}", [
														(found.skipped || []).join(", "),
												  ])
												: "",
										]
											.filter(Boolean)
											.join("<br>"),
									});
								}),
					});
				},
				__("Import an LPL PMS workbook"),
				__("Choose the file")
			)
		);
		frm.trigger("show_weights");
	},
	// Frappe HR's own KRA and rating tables are hidden on a scorecard
	// template, but hiding a table does not stop its rows being checked:
	// one blank row left in it refuses the save with "KRA is required in
	// every row", about a table nobody can see. A blank row is dropped
	// here, before Frappe's mandatory check runs (form.js runs validate
	// and before_save first, save.js checks afterwards). A row with
	// anything in it is left alone — a plain Frappe HR template keeps its
	// KRAs.
	before_save(frm) {
		if (!(frm.doc.custom_perspectives || []).length && !(frm.doc.custom_competencies || []).length) {
			return;
		}
		const drop = (table, filled) => {
			const rows = frm.doc[table] || [];
			const kept = rows.filter(filled);
			if (kept.length === rows.length) return;
			frm.doc[table] = kept;
			frm.refresh_field(table);
		};
		drop("goals", (row) => row.key_result_area || row.per_weightage);
		drop("rating_criteria", (row) => row.criteria || row.per_weightage);
	},
	// The headline says at a glance whether this role's scorecard adds up.
	// A template with no scorecard on it yet says nothing, so a plain
	// Frappe HR KRA template is left as it is.
	//
	// The totals are summed from the rows on screen rather than read off
	// custom_objectives_weight, which the server only fills on save: a
	// template being typed for the first time would otherwise read 0/80
	// while the rows plainly say otherwise.
	show_weights(frm) {
		frm.dashboard.clear_headline();
		const perspectives = frm.doc.custom_perspectives || [];
		const competencies = frm.doc.custom_competencies || [];
		if (!perspectives.length && !competencies.length) return;
		const total = (rows) => rows.reduce((sum, row) => sum + (row.weight || 0), 0);
		const a = total(perspectives);
		const b = total(competencies);
		const good = a === 80 && b === 20;
		frm.dashboard.set_headline(
			`<span>${__("Section A")} <b>${a}</b>/80 &nbsp;|&nbsp; ${__("Section B")} <b>${b}</b>/20</span>` +
				` <span class="indicator-pill ${good ? "green" : "orange"}">${
					good ? __("Adds up") : __("Does not add up")
				}</span>`
		);
	},
});

// and it moves as the weights are typed, not only when the form is saved
frappe.ui.form.on("BSC Template Perspective", {
	weight(frm) {
		frm.trigger("show_weights");
	},
	custom_perspectives_remove(frm) {
		frm.trigger("show_weights");
	},
});

frappe.ui.form.on("BSC Template Competency", {
	weight(frm) {
		frm.trigger("show_weights");
	},
	custom_competencies_remove(frm) {
		frm.trigger("show_weights");
	},
});
