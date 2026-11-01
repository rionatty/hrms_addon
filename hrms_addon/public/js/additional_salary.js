// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Additional Salary. A deduction cancelled by itself leaves the
// advance, loan or penalty it recovers standing, with the amount still
// outstanding (recoveries.addition_on_cancel), so Cancel does not offer to
// cancel them too.
// doctype_js, read from disk when the form loads: no `bench build`.

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
