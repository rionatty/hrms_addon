// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Job Opening form, loaded through hooks.py doctype_js. HRMS ships its own
// job_opening.js; both run, this one adds to it.
//
// A new opening fills what it leaves blank from its Job Requisition (the
// description among them) and starts with its JD's screening questions, as
// the server does on save (job_openings.before_validate).

const HA_OPENINGS = "hrms_addon.hrms_addon.job_openings.";

frappe.ui.form.on("Job Opening", {
	refresh(frm) {
		if (!frm.is_new()) {
			return;
		}
		if (frm.doc.job_requisition) {
			ha_fill_from_requisition(frm);
		}
		if (frm.doc.designation && !(frm.doc.custom_screening_questions || []).length) {
			ha_fill_jd_questions(frm);
		}
	},
	designation(frm) {
		if (frm.doc.designation && !(frm.doc.custom_screening_questions || []).length) {
			ha_fill_jd_questions(frm);
		}
	},
});

function ha_fill_from_requisition(frm) {
	frappe.xcall(HA_OPENINGS + "get_requisition_values", { doc: frm.doc }).then((values) => {
		if (values && Object.keys(values).length) {
			frm.set_value(values);
		}
	});
}

function ha_fill_jd_questions(frm) {
	const designation = frm.doc.designation;
	frappe.xcall(HA_OPENINGS + "get_jd_questions", { designation }).then((rows) => {
		if (frm.doc.designation !== designation || (frm.doc.custom_screening_questions || []).length) {
			return;
		}
		(rows || []).forEach((row) => frm.add_child("custom_screening_questions", row));
		frm.refresh_field("custom_screening_questions");
	});
}
