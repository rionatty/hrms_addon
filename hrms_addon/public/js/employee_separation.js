// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Both of Luuka's exits on Frappe HR's own Employee Separation: voluntary
// (4.5) and involuntary (4.6). The two buttons are the two documents the
// charts draw after the interview — the Clearance Form (LPL/HR/22) and
// then the full and final settlement (LPL/HR/20).
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Employee Separation", {
	refresh(frm) {
		frm.trigger("show_notice");
		if (frm.is_new()) return;
		if (!frm.doc.custom_clearance) {
			frm.add_custom_button(__("Draw Up Clearance Form"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.exits.draw_up_clearance", {
						separation: frm.doc.name,
					})
					.then((clearance) => frappe.set_route("Form", "Clearance Form", clearance))
			);
		} else if (!frm.doc.custom_settlement) {
			frm.add_custom_button(__("Draw Up Settlement"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.settlements.draw_up", {
						separation: frm.doc.name,
					})
					.then((settlement) =>
						frappe.set_route("Form", "Full and Final Statement", settlement)
					)
			);
		}
	},
	// The chart asks "Notice served as required?" and the answer changes
	// what comes off the final pay, so say it plainly at the top.
	show_notice(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.custom_relieving_date) return;
		const served = frm.doc.custom_notice_served;
		const short = frm.doc.custom_notice_short_days || 0;
		frm.dashboard.set_headline(
			`<span>${__("Notice required")} <b>${frm.doc.custom_notice_days || 0}</b> ${__(
				"day(s)"
			)}</span>` +
				` <span class="indicator-pill ${served ? "green" : "orange"}">${
					served
						? __("Notice served")
						: __("{0} day(s) short, deducted from the final pay", [short])
				}</span>`
		);
	},
	custom_exit_type(frm) {
		if (frm.doc.custom_exit_type === "Involuntary") {
			frm.set_value("custom_notice_given", null);
		}
	},
	custom_relieving_date(frm) {
		frm.trigger("show_notice");
	},
});
