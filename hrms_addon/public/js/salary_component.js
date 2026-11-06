// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A component's Cost Account, where the employer's share is booked (employer_costs.py): an expense of the row's company.
frappe.ui.form.on("Salary Component", {
	setup(frm) {
		frm.set_query("custom_cost_account", "accounts", (doc, cdt, cdn) => ({
			filters: { company: locals[cdt][cdn].company, is_group: 0, root_type: "Expense" },
		}));
	},
});
