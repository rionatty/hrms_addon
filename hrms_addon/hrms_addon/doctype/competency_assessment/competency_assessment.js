// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// An employee's level in a skill (competency.py): the skills offered are those
// HR have given a type; the assessor is not the employee.
frappe.ui.form.on("Competency Assessment", {
	setup(frm) {
		frm.set_query("skill", () => ({ filters: { custom_skill_type: ["is", "set"] } }));
		frm.set_query("assessed_by", () => ({ filters: { status: "Active" } }));
	},
	refresh(frm) {
		const colour = { Competent: "green", Gap: "red", "Certificate Needed": "orange", "Reassessment Due": "orange" };
		if (frm.doc.status && colour[frm.doc.status]) {
			frm.dashboard.set_headline(__("{0}: level needed {1}.", [__(frm.doc.status), frm.doc.required_level || ""]),
				colour[frm.doc.status]);
		}
	},
});
