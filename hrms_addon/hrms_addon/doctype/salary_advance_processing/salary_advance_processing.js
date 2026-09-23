// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
	"October", "November", "December"];

frappe.ui.form.on("Salary Advance Processing", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 },
		}));
	},
	onload(frm) {
		if (!frm.is_new()) return;
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		if (!frm.doc.company) frm.set_value("company", frappe.defaults.get_user_default("Company"));
		if (!frm.doc.year) frm.set_value("year", today.getFullYear());
		if (!frm.doc.month) frm.set_value("month", MONTHS[today.getMonth()]);
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.processing_date) {
			frm.dashboard.set_headline(
				__("Processed on {0}. Payroll period {1} to {2}.", [
					frappe.datetime.str_to_user(frm.doc.processing_date),
					frappe.datetime.str_to_user(frm.doc.period_start),
					frappe.datetime.str_to_user(frm.doc.period_end),
				])
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Advance Payment Report"), () =>
				frappe.set_route("query-report", "Advance Payment Report", {
					salary_advance_processing: frm.doc.name,
				})
			);
			if (frm.doc.journal_entry) {
				frm.add_custom_button(__("Bank Entry"), () =>
					frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry)
				);
			}
		}
	},
	get_requests(frm) {
		const fetch = () =>
			frappe
				.xcall("hrms_addon.hrms_addon.salary_advances.get_requests", { name: frm.doc.name })
				.then((added) => {
					frappe.show_alert({ message: __("{0} request(s) added.", [added]), indicator: "green" });
					frm.reload_doc();
				});
		if (frm.is_dirty() || frm.is_new()) {
			frm.save().then(fetch);
		} else {
			fetch();
		}
	},
});
