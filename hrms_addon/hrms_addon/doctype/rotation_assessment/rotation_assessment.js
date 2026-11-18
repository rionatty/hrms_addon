// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// A rotation supervisor's assessment of a trainee's stint: the criteria
// from Talent Settings, 1 to 5 each, and a recommendation; submitted, it is
// written onto the stint (graduates.py).

frappe.ui.form.on("Rotation Assessment", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.supervisor) {
			frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then((result) => {
				const found = result && result.message && result.message.name;
				if (found) frm.set_value("supervisor", found);
			});
		}
	},
	refresh(frm) {
		if (frm.doc.trainee_program) {
			frm.add_custom_button(__("Graduate Trainee"), () =>
				frappe.set_route("Form", "Graduate Trainee Program", frm.doc.trainee_program));
		}
	},
});
