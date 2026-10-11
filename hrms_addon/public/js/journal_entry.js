// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The bank entry of an advance run (Salary Advance Processing, Leave Advance
// Processing). Finance cancel it on its own: the run and its advances are
// not documents to cancel first, and what the payment put on the payroll
// comes off (advance_runs.journal_on_cancel).
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Journal Entry", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([
				...(frm.ignore_doctypes_on_cancel_all || []),
				"Salary Advance Processing",
				"Leave Advance Processing",
				"Leave Advance",
			]),
		];
	},
});
