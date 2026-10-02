// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Needs Form", {
	onload(frm) {
		if (frm.is_new()) {
			if (!frm.doc.year) frm.set_value("year", new Date().getFullYear() + 1);
			if (!frm.doc.employee) {
				frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then((r) => {
					if (r.message && r.message.name) frm.set_value("employee", r.message.name);
				});
			}
			// the form's questions (LPL/TRG/FRM06), one row each, to answer
			if (!(frm.doc.questions || []).length) {
				frappe.xcall("hrms_addon.hrms_addon.training.get_needs_questions").then((rows) => {
					(rows || []).forEach((row) => frm.add_child("questions", row));
					frm.refresh_field("questions");
				});
			}
		}
	},
	refresh(frm) {
		// the questions are the form's, not added or taken off here
		frm.set_df_property("questions", "cannot_add_rows", true);
		frm.set_df_property("questions", "cannot_delete_rows", true);
	},
});
