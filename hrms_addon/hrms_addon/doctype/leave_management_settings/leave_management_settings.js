// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Leave Management Settings", {
	setup(frm) {
		frm.set_query("leave_advance_account", () => ({
			filters: {
				company: frappe.defaults.get_user_default("Company"),
				root_type: "Asset",
				is_group: 0,
				account_type: ["not in", ["Receivable", "Payable"]],
			},
		}));
	},
	allocate_now(frm) {
		const run = () =>
			frappe
				.xcall("hrms_addon.hrms_addon.leave_accrual.allocate_now")
				.then((message) => frappe.show_alert({ message: message, indicator: "blue" }));
		if (frm.is_dirty()) {
			frm.save().then(run);
		} else {
			run();
		}
	},
});
