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
	// The headline says at a glance whether this role's scorecard adds up.
	// A template with no scorecard on it yet says nothing, so a plain
	// Frappe HR KRA template is left as it is.
	show_weights(frm) {
		frm.dashboard.clear_headline();
		const rows = (frm.doc.custom_perspectives || []).length + (frm.doc.custom_competencies || []).length;
		if (!rows) return;
		const a = frm.doc.custom_objectives_weight || 0;
		const b = frm.doc.custom_competencies_weight || 0;
		const good = a === 80 && b === 20;
		frm.dashboard.set_headline(
			`<span>${__("Section A")} <b>${a}</b>/80 &nbsp;|&nbsp; ${__("Section B")} <b>${b}</b>/20</span>` +
				` <span class="indicator-pill ${good ? "green" : "orange"}">${
					good ? __("Adds up") : __("Does not add up")
				}</span>`
		);
	},
});
