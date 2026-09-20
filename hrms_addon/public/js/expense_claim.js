// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Employees Claim Form (LPL/HR/27) on Frappe HR's own Expense Claim.
// The supervisor's line — "Genuine-to be paid or not approved" — is what
// the claim carries up the chain.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Expense Claim", {
	refresh(frm) {
		frm.trigger("show_standard");
	},
	// "Wedding gifts and claims that are standard especially for
	// production can be updated on the system": say what Luuka pay for
	// this kind of claim, so nobody has to remember it.
	show_standard(frm) {
		frm.dashboard.clear_headline();
		const first = (frm.doc.expenses || [])[0];
		if (!first || !first.expense_type) return;
		frappe.db
			.get_value("Expense Claim Type", first.expense_type, [
				"custom_is_standard",
				"custom_standard_amount",
				"custom_requires_evidence",
			])
			.then((result) => {
				const row = (result && result.message) || {};
				if (!row.custom_is_standard && !row.custom_requires_evidence) return;
				const parts = [];
				if (row.custom_is_standard) {
					parts.push(
						`${__("Standard claim")}: <b>${frappe.format(row.custom_standard_amount || 0, {
							fieldtype: "Currency",
						})}</b>`
					);
				}
				if (row.custom_requires_evidence) {
					parts.push(
						`<span class="indicator-pill ${frm.doc.custom_evidence ? "green" : "orange"}">${
							frm.doc.custom_evidence ? __("Evidence attached") : __("Paid on evidence")
						}</span>`
					);
				}
				frm.dashboard.set_headline(parts.join(" &nbsp;|&nbsp; "));
			});
	},
	custom_genuine(frm) {
		if (!frm.doc.custom_genuine && !frm.doc.custom_supervisor_remarks) {
			frappe.show_alert({
				message: __("Say in the supervisor's remarks why the claim is not genuine."),
				indicator: "orange",
			});
		}
	},
});

frappe.ui.form.on("Expense Claim Detail", {
	expense_type(frm) {
		frm.trigger("show_standard");
	},
});
