// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Job Offer form, loaded through hooks.py doctype_js. HRMS ships its own
// job_offer.js; both run, this one adds to it.
//
// A submitted offer is sent to the candidate by email (Send Offer by Email,
// the offer attached) and has its Appointment Letter made from it (Create >
// Appointment Letter), or opens the one already made. The letter the
// candidate signs by hand is attached to the offer (Signed Appointment
// Letter).
//
// Once the candidate accepts, the offer starts the onboarding (Create >
// Employee Onboarding, which fills itself from the candidate), or opens the
// one already started.

frappe.ui.form.on("Job Offer", {
	refresh(frm) {
		ha_offer_letter(frm);
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

// the offer by email, and its appointment letter
function ha_offer_letter(frm) {
	if (frm.doc.docstatus !== 1 || ["Rejected", "Cancelled"].includes(frm.doc.status)) {
		return;
	}
	if (frm.doc.applicant_email) {
		frm.add_custom_button(__("Send Offer by Email"), () => {
			new frappe.views.CommunicationComposer({
				doc: frm.doc,
				frm: frm,
				recipients: frm.doc.applicant_email,
				subject: __("Job Offer: {0}", [frm.doc.designation]),
				attach_document_print: true,
			});
		});
	}
	frappe.db.get_value("Appointment Letter", { custom_job_offer: frm.doc.name }, "name").then((r) => {
		const letter = r.message && r.message.name;
		if (letter) {
			frm.add_custom_button(
				__("Appointment Letter"),
				() => frappe.set_route("Form", "Appointment Letter", letter),
				__("View")
			);
		} else if (frappe.model.can_create("Appointment Letter")) {
			// a new document's values are copied onto it as they are, with no
			// fetch, so the name is passed too
			frm.add_custom_button(
				__("Appointment Letter"),
				() =>
					frappe.new_doc("Appointment Letter", {
						job_applicant: frm.doc.job_applicant,
						applicant_name: frm.doc.applicant_name,
						company: frm.doc.company,
						appointment_date: frappe.datetime.get_today(),
						custom_job_offer: frm.doc.name,
					}),
				__("Create")
			);
		}
	});
}
