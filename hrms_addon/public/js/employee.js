// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The minutes' §6.2: "Accidentally terminated workers cannot be
// reinstated; permission rests only with the Executive Director." The
// Executive Director brings back an employee who left by mistake, and
// says why (exits.py).
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.
//
// The employee's talent card is drawn here too, for HR and the Talent
// Council (talent_card.js).
//
// The Status picked (Resigned, On Hold...) sets Frappe's own under it, the
// System Status, so the form asks for what that one needs: a relieving date
// for a status that counts as Left. The save sets it as well
// (employee_status.py).

function ha_employee_counts_as(status) {
	const known = (frappe.boot.hrms_addon_employee_statuses || {})[status];
	if (known) return Promise.resolve(known.counts_as);
	// a status made since the page loaded
	return frappe.db.get_value("Employee Status", status, "counts_as").then((r) => (r.message || {}).counts_as);
}

frappe.ui.form.on("Employee", {
	custom_employee_status(frm) {
		const chosen = frm.doc.custom_employee_status;
		if (!chosen) return;
		ha_employee_counts_as(chosen).then((counts_as) => {
			if (counts_as && frm.doc.custom_employee_status === chosen && frm.doc.status !== counts_as) {
				frm.set_value("status", counts_as);
			}
		});
	},
	refresh(frm) {
		if (
			frm.is_new() &&
			!frm.doc.custom_employee_status &&
			(frappe.boot.hrms_addon_employee_statuses || {})[frm.doc.status]
		) {
			frm.set_value("custom_employee_status", frm.doc.status);
		}
		if (hrms_addon.talent_card) hrms_addon.talent_card.attach(frm, frm.doc.name);
		if (frm.doc.status !== "Left" || !frappe.user.has_role("Executive Director")) return;
		frm.add_custom_button(__("Reinstate"), () => {
			frappe.prompt(
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Why is the employee reinstated?"),
					reqd: 1,
				},
				(values) =>
					frappe
						.xcall("hrms_addon.hrms_addon.exits.reinstate", {
							employee: frm.doc.name,
							reason: values.reason,
						})
						.then(() => frm.reload_doc()),
				__("Reinstate {0}", [frm.doc.employee_name || frm.doc.name]),
				__("Reinstate")
			);
		});
	},
});
