// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Loan", {
	refresh(frm) {
		frm.trigger("show_loan");
		if (frm.doc.docstatus === 1 && frm.doc.outstanding > 0) {
			frm.add_custom_button(__("Mark Recovered"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.loans.mark_recovered", {})
					.then(() => frm.reload_doc())
			);
		}
	},
	// "Approved?" on the chart rests on this, so say it before anyone signs.
	show_loan(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.employee) return;
		const money = (value) => frappe.format(value || 0, { fieldtype: "Currency" });
		const ok = frm.doc.qualifies;
		const parts = [`${__("Limit")} <b>${money(frm.doc.limit)}</b>`];
		if (frm.doc.monthly_instalment) {
			parts.push(`${__("Monthly")} <b>${money(frm.doc.monthly_instalment)}</b>`);
		}
		if (frm.doc.docstatus === 1) {
			parts.push(`${__("Outstanding")} <b>${money(frm.doc.outstanding)}</b>`);
		}
		frm.dashboard.set_headline(
			`<span>${parts.join(" &nbsp;|&nbsp; ")}</span>` +
				` <span class="indicator-pill ${ok ? "green" : "orange"}">${
					ok ? __("Qualifies") : __("Does not qualify")
				}</span>` +
				(ok
					? ""
					: ` <span class="text-muted">${frappe.utils.escape_html(
							frm.doc.eligibility_remarks || ""
					  )}</span>`)
		);
	},
	loan_amount(frm) {
		if (!frm.doc.approved_amount) {
			frm.set_value("approved_amount", frm.doc.loan_amount);
		}
	},
	approved_amount(frm) {
		if (frm.doc.approved_amount && !frm.doc.liability) {
			frm.set_value(
				"liability",
				__("Staff loan of {0}", [
					frappe.format(frm.doc.approved_amount, { fieldtype: "Currency" }),
				])
			);
		}
	},
});
