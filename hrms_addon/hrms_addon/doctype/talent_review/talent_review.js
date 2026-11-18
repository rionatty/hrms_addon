// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// A review: its placements drafted in the background, its calibration
// sessions, and the Talent Council's pack of it as slides.

frappe.ui.form.on("Talent Review", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		frm.add_custom_button(__("Draft Placements"), () =>
			frappe
				.xcall("hrms_addon.hrms_addon.talent.draft_placements", { review: frm.doc.name })
				.then((result) => {
					if (result && result.log) {
						frappe.show_alert({ message: __("Placements are being drafted. You will be told when it is done."), indicator: "blue" });
					}
					frm.reload_doc();
				})
		);
		frm.add_custom_button(__("Placements"), () =>
			frappe.set_route("List", "Talent Placement", { talent_review: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Calibration Sessions"), () =>
			frappe.set_route("List", "Calibration Session", { talent_review: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Calibration Log"), () =>
			frappe.set_route("List", "Talent Calibration Log", { talent_review: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Talent Command"), () => frappe.set_route("talent-command"), __("View"));
		frm.add_custom_button(__("New Calibration Session"), () =>
			frappe.new_doc("Calibration Session", { talent_review: frm.doc.name }), __("Calibration"));
		frm.add_custom_button(__("Council Pack Slides"), () => {
			window.open(`/api/method/hrms_addon.hrms_addon.talent_council.download_deck?review=${encodeURIComponent(frm.doc.name)}`);
		}, __("Calibration"));
		const parts = [];
		if (frm.doc.placements_created) parts.push(__("{0} placements drafted", [frm.doc.placements_created]));
		if (frm.doc.mid_year_done) parts.push(__("mid-year calibrated"));
		if (frm.doc.year_end_done) parts.push(__("year-end calibrated"));
		if (parts.length) frm.dashboard.set_headline(`<span>${frappe.utils.escape_html(parts.join(", "))}</span>`);
	},
});
