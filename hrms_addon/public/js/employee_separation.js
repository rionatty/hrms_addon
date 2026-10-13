// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Both of Luuka's exits on Frappe HR's own Employee Separation: voluntary
// (4.5) and involuntary (4.6). The two buttons are the two documents the
// charts draw after the interview — the Clearance Form (LPL/HR/22) and
// then the full and final settlement (LPL/HR/20). The headline follows the
// notice: what is required, whether it is served, and the days left.
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
		const html =
			`<span>${__("Notice required")} <b>${frm.doc.custom_notice_days || 0}</b> ${__(
				"day(s)"
			)}</span>` +
			` <span class="indicator-pill ${served ? "green" : "orange"}">${
				served
					? __("Notice served")
					: __("{0} day(s) short, deducted from the final pay", [short])
			}</span>`;
		frm.dashboard.set_headline(html);
		if (!frm.doc.employee || frm.doc.docstatus === 2) return;
		// where the notice stands today
		const name = frm.doc.name;
		const args = { employee: frm.doc.employee, last_day: frm.doc.custom_relieving_date };
		if (frm.doc.custom_notice_given) args.notice_given = frm.doc.custom_notice_given;
		frappe.xcall("hrms_addon.hrms_addon.exits.notice_for", args).then((notice) => {
			// the answer is for the exit that asked, not one opened since
			if (!notice || !notice.stage || frm.doc.name !== name) return;
			frm.dashboard.set_headline(html + ha_notice_stage(notice));
		});
	},
	// the last day the notice runs to, offered when the letter's date goes in
	custom_notice_given(frm) {
		if (!frm.doc.employee || !frm.doc.custom_notice_given) return;
		if (frm.doc.custom_exit_type === "Involuntary" || frm.doc.custom_relieving_date) return;
		frappe
			.xcall("hrms_addon.hrms_addon.exits.notice_for", {
				employee: frm.doc.employee,
				notice_given: frm.doc.custom_notice_given,
			})
			.then((notice) => {
				if (!notice || !notice.suggested_last_day || frm.doc.custom_relieving_date) return;
				frm.set_value("custom_relieving_date", notice.suggested_last_day);
				frappe.show_alert({
					message: __("{0} day(s) of notice run to {1}.", [
						notice.required_days,
						frappe.datetime.str_to_user(notice.suggested_last_day),
					]),
					indicator: "blue",
				});
			});
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

function ha_notice_stage(notice) {
	if (notice.stage === "Left") {
		return ` <span class="indicator-pill gray">${__("Left")}</span>`;
	}
	if (notice.stage === "Last Day Today") {
		return ` <span class="indicator-pill red">${__("Last day today")}</span>`;
	}
	const colour = notice.days_left <= 3 ? "red" : notice.days_left <= 7 ? "orange" : "blue";
	return ` <span class="indicator-pill ${colour}">${__("{0} day(s) left", [notice.days_left])}</span>`;
}
