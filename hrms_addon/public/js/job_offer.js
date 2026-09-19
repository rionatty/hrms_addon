// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Job Offer form, loaded through hooks.py doctype_js. HRMS ships its own
// job_offer.js; both run, this one adds to it.
//
// Once the candidate accepts, the offer starts the onboarding (Create >
// Employee Onboarding, which fills itself from the candidate), or opens the
// one already started.

frappe.ui.form.on("Job Offer", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status !== "Accepted") {
			return;
		}
		frappe.db
			.get_value("Employee Onboarding", { job_offer: frm.doc.name, docstatus: ["!=", 2] }, "name")
			.then((r) => {
				const onboarding = r.message && r.message.name;
				if (onboarding) {
					frm.add_custom_button(
						__("Employee Onboarding"),
						() => frappe.set_route("Form", "Employee Onboarding", onboarding),
						__("View")
					);
				} else if (frappe.model.can_create("Employee Onboarding")) {
					frm.add_custom_button(
						__("Employee Onboarding"),
						() =>
							frappe.new_doc("Employee Onboarding", {
								job_applicant: frm.doc.job_applicant,
								job_offer: frm.doc.name,
							}),
						__("Create")
					);
				}
			});
	},
});
