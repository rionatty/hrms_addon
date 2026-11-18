// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// One calibration sitting over a plant's or a department's placements: the
// box each was proposed in, the box agreed and why, the spread against the
// guide; submitted, the agreed moves are applied in the background
// (calibration.py).

frappe.ui.form.on("Calibration Session", {
	refresh(frm) {
		if (frm.doc.job_log) {
			frm.add_custom_button(__("Job Log"), () => frappe.set_route("Form", "Talent Job Log", frm.doc.job_log));
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Calibration Log"), () =>
				frappe.set_route("List", "Talent Calibration Log", { calibration_session: frm.doc.name }));
			frm.add_custom_button(__("Talent Board"), () => frappe.set_route("talent-board"));
		}
		if (frm.doc.off_guide) {
			frm.dashboard.add_comment(__("Off the guide: {0}", [frm.doc.off_guide]), "orange", true);
		}
	},
	get_placements(frm) {
		const go = () => frappe
			.xcall("hrms_addon.hrms_addon.calibration.get_placements", { session: frm.doc.name })
			.then((added) => {
				frappe.show_alert({ message: __("{0} placements added", [added || 0]), indicator: "green" });
				frm.reload_doc();
			});
		if (frm.is_dirty() || frm.is_new()) frm.save().then(go);
		else go();
	},
});
