// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Interview Type — one round of one JD. Loaded through hooks.py doctype_js,
// after HRMS's own form script.
//
// Get Criteria from JD fills the round's Score Sheet: the JD's competencies
// weighed by their priority, then the general list once each
// (interviews.get_round_criteria). HR removes what the round does not score.

frappe.ui.form.on("Interview Type", {
	refresh(frm) {
		if (frm.doc.designation && frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Get Criteria from JD"), () => ha_criteria_from_jd(frm));
		}
	},
});

function ha_criteria_from_jd(frm) {
	const fill = () =>
		frappe
			.xcall("hrms_addon.hrms_addon.interviews.get_round_criteria", { designation: frm.doc.designation })
			.then((rows) => {
				frm.clear_table("custom_criteria");
				(rows || []).forEach((row) => frm.add_child("custom_criteria", row));
				frm.refresh_field("custom_criteria");
				frm.dirty();
			});
	if ((frm.doc.custom_criteria || []).length) {
		frappe.confirm(__("Replace the criteria listed?"), fill);
	} else {
		fill();
	}
}
