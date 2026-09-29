// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Salary Structure Assignment. The onboarding and the position
// change that made an assignment keep it as a record, so cancelling the
// assignment to correct it leaves them, and what follows them, as they are
// (salary_structures.keep_records lets the cancel through).
// doctype_js, read from disk when the form loads: no `bench build`.

frappe.ui.form.on("Salary Structure Assignment", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([
				...(frm.ignore_doctypes_on_cancel_all || []),
				"Employee Onboarding",
				"Employee Position Change",
			]),
		];
	},
});
