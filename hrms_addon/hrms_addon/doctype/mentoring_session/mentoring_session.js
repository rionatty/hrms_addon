// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// A mentor's session with a trainee or a successor: only the mentor writes
// it (graduates.py).

frappe.ui.form.on("Mentoring Session", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.mentor) {
			frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then((result) => {
				const found = result && result.message && result.message.name;
				if (found) frm.set_value("mentor", found);
			});
		}
	},
});
