// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Additional Salary. A deduction cancelled by itself leaves the
// advance, loan or penalty it recovers standing, with the amount still
// outstanding (recoveries.addition_on_cancel), so Cancel does not offer to
// cancel them too.
// doctype_js, read from disk when the form loads: no `bench build`.

// Luuka, 16 Nov 2026: "Epertiates are currency in uSD yet their advance are un UGX". One paid in another currency
// than the company's may have an Additional Salary in either: shillings come off their slip at the payroll's rate
// (currency_payroll.additional_validate). Frappe HR sets the currency only when the employee is chosen.
frappe.ui.form.on("Additional Salary", {
	refresh(frm) {
		ha_additional_currencies(frm);
	},
	employee(frm) {
		ha_additional_currencies(frm);
	},
	company(frm) {
		ha_additional_currencies(frm);
	},
});

function ha_additional_currencies(frm) {
	const doc = frm.doc;
	if (doc.docstatus !== 0 || !doc.employee || !doc.company) return;
	frappe
		.xcall("hrms_addon.hrms_addon.currency_payroll.additional_currencies", {
			employee: doc.employee,
			company: doc.company,
		})
		.then((allowed) => {
			allowed = allowed || [];
			frm.set_query("currency", () => ({ filters: { name: ["in", allowed] } }));
			frm.set_df_property(
				"currency",
				"description",
				allowed.length > 1 ? __("{0} or {1}. An amount in {1} is taken at the payroll's rate.", allowed) : ""
			);
		});
}

frappe.ui.form.on("Additional Salary", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([
				...(frm.ignore_doctypes_on_cancel_all || []),
				"Employee Advance",
				"Leave Advance",
				"Employee Loan",
				"Employee Penalty",
			]),
		];
	},
});
