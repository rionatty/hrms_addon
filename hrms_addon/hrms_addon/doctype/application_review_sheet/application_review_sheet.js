// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A supervisor's trainees from one session (learning_sheets.py): answer for
// each, then Submit; each answer goes to the trainee's own review.
frappe.ui.form.on("Application Review Sheet", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.dashboard.set_headline(__("Answer the three questions for each trainee, then Submit."), "blue");
		}
		hrms_addon.sheet_progress(frm);
	},
});
