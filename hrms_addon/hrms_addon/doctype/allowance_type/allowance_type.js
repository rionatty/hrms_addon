// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// An Allowance Type: how it is worked out and who pays it (allowances.py).

frappe.ui.form.on("Allowance Type", {
	setup(frm) {
		frm.set_query("salary_component", () => ({ filters: { type: "Earning" } }));
		frm.set_query("account", "accounts", (doc, cdt, cdn) => ({
			filters: { company: locals[cdt][cdn].company, is_group: 0 },
		}));
	},
});
