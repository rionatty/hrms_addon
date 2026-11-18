// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A session's trainees and their tests (learning_sheets.py): Get Trainees
// fills those who attended; Submit puts the marks on the Training Result.
frappe.ui.form.on("Training Results Sheet", {
	setup(frm) {
		frm.set_query("training_event", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.training_event) {
			frm.add_custom_button(__("Get Trainees"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.learning_sheets.trainees", { training_event: frm.doc.training_event })
					.then((found) => {
						const have = new Set((frm.doc.rows || []).map((row) => row.employee));
						(found.rows || []).forEach((row) => {
							if (!have.has(row.employee)) {
								frm.add_child("rows", { employee: row.employee, employee_name: row.employee_name, attempt: 1,
									assessment_type: frm.doc.assessment_type });
							}
						});
						frm.set_value("pass_mark", found.pass_mark);
						frm.refresh_field("rows");
					})
			).addClass("btn-primary");
		}
		hrms_addon.sheet_progress(frm);
	},
});
