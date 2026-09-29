// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Salary Structure. A submitted structure takes new components
// (a new allowance or deduction) without being cancelled; none is taken off,
// since a component is stopped by giving it the condition 0
// (salary_structures.rows_after_submit checks the rows added). Cancelling it
// leaves the onboarding and the position change that name it as they are.
// doctype_js, read from disk when the form loads: no `bench build`.

frappe.ui.form.on("Salary Structure", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([
				...(frm.ignore_doctypes_on_cancel_all || []),
				"Employee Onboarding",
				"Employee Position Change",
			]),
		];
	},
	refresh(frm) {
		const submitted = frm.doc.docstatus === 1 ? 1 : 0;
		for (const table of ["earnings", "deductions", "employer_contributions"]) {
			if (frm.fields_dict[table]) frm.set_df_property(table, "cannot_delete_rows", submitted);
		}
	},
});
