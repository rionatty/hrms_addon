// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Leave Advance Processing", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 },
		}));
		frm.set_query("leave_advance", "employees", () => ({
			filters: Object.assign(
				{ docstatus: 1, status: "Approved", company: frm.doc.company },
				frm.doc.branch ? { branch: frm.doc.branch } : {}
			),
		}));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},
	refresh(frm) {
		if (!frm.is_new() && (frm.doc.employees || []).length) {
			frm.add_custom_button(__("Download Excel"), () => {
				window.open(
					"/api/method/hrms_addon.hrms_addon.leave_advances.bank_file?name=" +
						encodeURIComponent(frm.doc.name)
				);
			});
		}
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("Bank Entry"), () =>
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry)
			);
		}
	},
	get_advances(frm) {
		const fetch = () =>
			frappe
				.xcall("hrms_addon.hrms_addon.leave_advances.get_advances", { name: frm.doc.name })
				.then((added) => {
					frm.reload_doc();
					frappe.show_alert({
						message: added
							? __("{0} leave advance(s) added.", [added])
							: __("No approved leave advance is waiting to be paid."),
						indicator: added ? "green" : "orange",
					});
				});
		if (frm.is_dirty() || frm.is_new()) {
			frm.save().then(fetch);
		} else {
			fetch();
		}
	},
});
