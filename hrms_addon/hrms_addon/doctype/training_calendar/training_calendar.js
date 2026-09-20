// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Calendar", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Approved Needs"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.training.get_approved_needs", {
						year: frm.doc.calendar_year, branch: frm.doc.branch,
					})
					.then((rows) => {
						if (!rows.length) {
							frappe.show_alert({ message: __("No approved needs waiting for a calendar."), indicator: "blue" });
							return;
						}
						const have = new Set((frm.doc.entries || []).map((r) => r.need_row).filter(Boolean));
						for (const row of rows) {
							if (have.has(row.need_row)) continue;
							frm.add_child("entries", row);
						}
						frm.refresh_field("entries");
					})
			);
		}
	},
});
