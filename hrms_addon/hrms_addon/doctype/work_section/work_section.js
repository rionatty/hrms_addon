// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A plant's production section (excellence.py): its roster is the plant's
// people, its standards are kept by date, its labour rates can come from
// their pay.
frappe.ui.form.on("Work Section", {
	setup(frm) {
		frm.set_query("employee", "assignments", () => ({
			filters: Object.assign({ status: "Active" }, frm.doc.branch ? { branch: frm.doc.branch } : {}),
		}));
		frm.set_query("department", () => ({
			filters: frm.doc.company ? { company: frm.doc.company } : {},
		}));
	},
	rates_from_payroll(frm) {
		const work = () =>
			frappe
				.xcall("hrms_addon.hrms_addon.excellence.rates_from_payroll", { section: frm.doc.name })
				.then(() => {
					frappe.show_alert({ message: __("Rates worked out from the payroll"), indicator: "green" });
					frm.reload_doc();
				});
		if (frm.is_new() || frm.is_dirty()) {
			frm.save().then(work);
		} else {
			work();
		}
	},
});
