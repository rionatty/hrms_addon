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

frappe.ui.form.on("Employee", {
	refresh(frm) {
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
