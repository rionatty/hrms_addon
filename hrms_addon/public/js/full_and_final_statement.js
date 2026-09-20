// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Full and Final Settlement Agreement (LPL/HR/20) on Frappe HR's own
// Full and Final Statement: the final salary, leave encashment, notice
// pay, severance and net claims, less what comes off, and the bank
// account it is remitted to.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Full and Final Statement", {
	refresh(frm) {
		frm.trigger("show_net");
	},
	// The agreement is signed for one figure, so show it and say it in
	// words the way the paper does.
	show_net(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.custom_net_payable) return;
		const money = (value) => frappe.format(value || 0, { fieldtype: "Currency" });
		frm.dashboard.set_headline(
			`<span>${__("Due")} <b>${money(frm.doc.total_payable_amount)}</b>` +
				` &nbsp;|&nbsp; ${__("Less")} <b>${money(frm.doc.total_receivable_amount)}</b>` +
				` &nbsp;|&nbsp; ${__("Net")} <b>${money(frm.doc.custom_net_payable)}</b></span>` +
				(frm.doc.custom_net_in_words
					? ` <span class="text-muted">${frappe.utils.escape_html(
							frm.doc.custom_net_in_words
					  )}</span>`
					: "")
		);
	},
	custom_employee_signed(frm) {
		if (frm.doc.custom_employee_signed && !frm.doc.custom_account_number) {
			frappe.show_alert({
				message: __("LPL/HR/20 remits to the employee's own account: give the account number."),
				indicator: "orange",
			});
		}
	},
});
