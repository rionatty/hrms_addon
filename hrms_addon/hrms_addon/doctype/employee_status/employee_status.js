// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe's own four statuses count as themselves: what they count as is not
// for changing here.

frappe.ui.form.on("Employee Status", {
	refresh(frm) {
		frm.set_df_property("counts_as", "read_only", frm.doc.is_standard ? 1 : 0);
		frm.set_df_property("disabled", "read_only", frm.doc.is_standard ? 1 : 0);
		frm.set_df_property("status_name", "read_only", frm.is_new() ? 0 : 1);
	},
});
