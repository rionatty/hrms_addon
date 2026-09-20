// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("BSC Appraisal Template", {
	refresh(frm) {
		frm.add_custom_button(__("Import PMS Workbook"), () =>
			frappe.prompt(
				[
					{
						fieldname: "review_year",
						fieldtype: "Int",
						label: __("Review Year"),
						reqd: 1,
						default: frm.doc.review_year || new Date().getFullYear(),
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
	show_weights(frm) {
		frm.dashboard.clear_headline();
		const a = frm.doc.objectives_weight || 0;
		const b = frm.doc.competencies_weight || 0;
		const good = a === 80 && b === 20;
		frm.dashboard.set_headline(
			`<span>${__("Section A")} <b>${a}</b>/80 &nbsp;|&nbsp; ${__("Section B")} <b>${b}</b>/20</span>` +
				` <span class="indicator-pill ${good ? "green" : "orange"}">${
					good ? __("Adds up") : __("Does not add up")
				}</span>`
		);
	},
});
