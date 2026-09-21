// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Talent Review", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		frm.add_custom_button(__("Draft Placements"), () =>
			frappe
				.xcall("hrms_addon.hrms_addon.talent.draft_placements", { review: frm.doc.name })
				.then(() => frm.reload_doc())
		);
		frm.add_custom_button(__("Placements"), () =>
			frappe.set_route("List", "Talent Placement", { talent_review: frm.doc.name })
		);
		if (frm.doc.placements_created) {
			frm.dashboard.set_headline(
				`<span>${__("{0} placements drafted", [frm.doc.placements_created])}</span>` +
					(frm.doc.calibration && frm.doc.calibration.length
						? ` <span class="indicator-pill orange">${__("{0} moved in calibration", [
								frm.doc.calibration.length,
						  ])}</span>`
						: "")
			);
		}
	},
});
