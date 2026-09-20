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
		}
	},
});
