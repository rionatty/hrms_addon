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
		ha_claim_show_standard(frm, false);
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
		ha_claim_show_standard(frm, true);
	},
});

// "Wedding gifts and claims that are standard especially for production
// can be updated on the system": say what Luuka pay for this kind of
// claim, so nobody has to remember it. A type picked also says what the
// claim is for, which shows the fields it needs: whose loss, when the
// child was born and how many.
function ha_claim_show_standard(frm, picked) {
	frm.dashboard.clear_headline();
	const first = (frm.doc.expenses || [])[0];
	if (!first || !first.expense_type) return;
	frappe.db
		.get_value("Expense Claim Type", first.expense_type, [
			"custom_is_standard",
			"custom_standard_amount",
			"custom_requires_evidence",
			"custom_occasion",
			"custom_counts_children",
		])
		.then((result) => {
			const row = (result && result.message) || {};
			if (picked && frm.doc.docstatus === 0 && row.custom_occasion && !frm.doc.custom_occasion) {
				frm.set_value("custom_occasion", row.custom_occasion);
			}
			if (!row.custom_is_standard && !row.custom_requires_evidence) return;
			const parts = [];
			if (row.custom_is_standard) {
				const amount = frappe.format(row.custom_standard_amount || 0, { fieldtype: "Currency" });
				parts.push(
					`${__("Standard claim")}: <b>${amount}</b>${
						row.custom_counts_children ? " " + __("a child") : ""
					}`
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
}
