// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Intern Placement", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Placed") {
			frm.set_intro(__("Placed. Print the Intern Placement Letter for signature."), "green");
		}
	},
	supervisor(frm) {
		if (!frm.doc.supervisor) return;
		frappe.db.get_value("Employee", frm.doc.supervisor, "designation").then((r) => {
			if (r.message && r.message.designation) {
				frm.set_value("supervisor_designation", r.message.designation);
			}
		});
	},
	setup(frm) {
		frm.set_query("supervisor", () => ({ filters: { status: "Active" } }));
	},
});
