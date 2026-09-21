// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The non-disciplinary concern (5.4) on Frappe HR's own Employee
// Grievance. The whole of that chart is the timeline, so the form says
// where the concern stands against it.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Employee Grievance", {
	refresh(frm) {
		frm.trigger("show_timeline");
	},
	show_timeline(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.custom_due_on) return;
		const left = frappe.datetime.get_day_diff(frm.doc.custom_due_on, frappe.datetime.get_today());
		const settled = ["Resolved", "Invalid", "Cancelled"].includes(frm.doc.status);
		frm.dashboard.set_headline(
			`<span>${__("Due")} <b>${frappe.datetime.str_to_user(frm.doc.custom_due_on)}</b></span>` +
				` <span class="indicator-pill ${settled ? "green" : left < 0 ? "red" : "orange"}">${
					settled
						? __("Settled")
						: left < 0
						? __("{0} day(s) overdue", [-left])
						: __("{0} day(s) left", [left])
				}</span>`
		);
	},
	grievance_type(frm) {
		if (!frm.doc.grievance_type || frm.doc.custom_due_on) return;
		frappe.db
			.get_value("Grievance Type", frm.doc.grievance_type, [
				"custom_timeline_days",
				"custom_default_handler",
			])
			.then((result) => {
				const row = (result && result.message) || {};
				if (row.custom_default_handler && !frm.doc.custom_assigned_hod) {
					frm.set_value("custom_assigned_hod", row.custom_default_handler);
				}
				const days = row.custom_timeline_days || 14;
				frm.set_value(
					"custom_due_on",
					frappe.datetime.add_days(frm.doc.date || frappe.datetime.get_today(), days)
				);
			});
	},
	custom_appeal_filed(frm) {
		if (frm.doc.custom_appeal_filed && frm.doc.custom_appeals_authority === frm.doc.custom_assigned_hod) {
			frappe.show_alert({
				message: __("An appeal is heard by someone who has not already handled the concern."),
				indicator: "red",
			});
		}
	},
});
