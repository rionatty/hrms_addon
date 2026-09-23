// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Luuka's three advances on Frappe HR's own Employee Advance: the leave
// advance (4.2), the salary advance (4.10) and the special advance
// LPL/HR/21 calls a loan. The Advance Type decides whose desk it lands on.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Employee Advance", {
	setup(frm) {
		// Frappe HR's own filter warns that no employee is selected when the
		// account is filled from the employee before the employee is stored
		// on the form. Same filter, without the warning.
		frm.set_query("advance_account", () => ({
			filters: {
				root_type: "Asset",
				is_group: 0,
				company: frm.doc.company,
				account_currency: frm.doc.currency,
				account_type: "Receivable",
			},
		}));
	},
	refresh(frm) {
		frm.trigger("show_eligibility");
		frm.trigger("show_recovery");
		if (frm.doc.docstatus === 1 && frm.doc.custom_outstanding > 0) {
			frm.add_custom_button(__("Mark Recovered"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.recoveries.catch_up_for", {
						doctype: frm.doctype,
						name: frm.doc.name,
					})
					.then(() => frm.reload_doc())
			);
		}
	},
	// The charts draw this as "Qualify for advance?"; the answer is worked
	// out on every save, so it is worth saying before anyone approves.
	show_eligibility(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.employee) return;
		const ok = frm.doc.custom_qualifies;
		const limit = frappe.format(frm.doc.custom_limit || 0, {
			fieldtype: "Currency",
			options: "currency",
		});
		frm.dashboard.set_headline(
			`<span>${__("Limit")} <b>${limit}</b></span>` +
				` <span class="indicator-pill ${ok ? "green" : "orange"}">${
					ok ? __("Qualifies") : __("Does not qualify")
				}</span>` +
				(ok
					? ""
					: ` <span class="text-muted">${frappe.utils.escape_html(
							frm.doc.custom_eligibility_remarks || ""
					  )}</span>`)
		);
	},
	// the recovery goes onto the payroll once the payment is recorded
	// against the advance: say where it stands
	show_recovery(frm) {
		if (frm.doc.docstatus !== 1) return;
		const rows = frm.doc.custom_recoveries || [];
		const waiting = rows.filter((row) => !row.additional_salary && !row.recovered).length;
		if (!waiting) return;
		frm.dashboard.add_comment(
			flt(frm.doc.paid_amount)
				? __("{0} instalment(s) are waiting for the rest of the payment to be recorded.", [waiting])
				: __(
						"Record the payment on this advance (Create > Payment): its recovery goes onto the payroll when it is recorded."
				  ),
			"orange",
			true
		);
	},
	custom_advance_type(frm) {
		if (frm.doc.custom_advance_type !== "Leave Advance") {
			frm.set_value("custom_leave_application", null);
		}
	},
	advance_amount(frm) {
		if (!frm.doc.custom_approved_amount) {
			frm.set_value("custom_approved_amount", frm.doc.advance_amount);
		}
	},
});
