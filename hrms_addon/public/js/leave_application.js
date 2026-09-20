// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// LPL/HR/15 on Frappe HR's own Leave Application. Part 2 is the HR
// Officer's balances, Part 3 the three signatures and Part 4 what
// Accounts advanced; step 7 of the process — "Leave Advance Required?" —
// is the button below.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Leave Application", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved") {
			if (frm.doc.custom_salary_requested_in_advance && !frm.doc.custom_advance) {
				frm.add_custom_button(__("Raise Leave Advance"), () =>
					frappe
						.xcall("hrms_addon.hrms_addon.leave.raise_advance", {
							leave_application: frm.doc.name,
						})
						.then((advance) => {
							frappe.show_alert({
								message: __("Leave advance {0} raised.", [advance]),
								indicator: "green",
							});
							frappe.set_route("Form", "Employee Advance", advance);
						})
				);
			}
			if (!frm.doc.custom_reported_back) {
				frm.add_custom_button(__("Mark Reported Back"), () =>
					frm.set_value("custom_reported_back", 1).then(() => frm.save("Update"))
				);
			}
		}
		frm.trigger("show_balances");
	},
	// Part 2 of the form, said once at the top: what was left before this
	// leave and what is left after it.
	show_balances(frm) {
		frm.dashboard.clear_headline();
		if (!frm.doc.custom_balance_before) return;
		const after = frm.doc.custom_balance_after || 0;
		frm.dashboard.set_headline(
			`<span>${__("Leave due before")} <b>${frm.doc.custom_balance_before}</b>` +
				` &nbsp;|&nbsp; ${__("after")} <b>${after}</b></span>` +
				` <span class="indicator-pill ${after < 0 ? "red" : "green"}">${
					after < 0 ? __("Over the balance") : __("Within the balance")
				}</span>`
		);
	},
	custom_balance_before(frm) {
		frm.trigger("show_balances");
	},
	leave_type(frm) {
		// the two the form asks for a certificate with are the two it
		// marks "(Attach Medical Certificate)"
		frm.refresh_field("custom_medical_certificate");
	},
});
