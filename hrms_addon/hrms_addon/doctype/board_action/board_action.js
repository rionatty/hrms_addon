// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A board action, carried from quarter to quarter (board_pack.py).
frappe.ui.form.on("Board Action", {
	onload(frm) {
		if (!frm.is_new()) return;
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		const quarter = "Q" + (Math.floor(today.getMonth() / 3) + 1);
		if (!frm.doc.raised_year) frm.set_value("raised_year", today.getFullYear());
		if (!frm.doc.raised_quarter) frm.set_value("raised_quarter", quarter);
		if (!frm.doc.due_year) frm.set_value("due_year", today.getFullYear());
		if (!frm.doc.due_quarter) frm.set_value("due_quarter", quarter);
		if (!frm.doc.company) frm.set_value("company", frappe.defaults.get_user_default("Company"));
	},
});
