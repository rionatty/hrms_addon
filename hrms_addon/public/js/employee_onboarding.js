// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Employee Onboarding form, loaded through hooks.py doctype_js (read from
// disk at runtime, so no `bench build` is needed after changing it). HRMS
// ships its own employee_onboarding.js; both run, this one adds to it.
//
// Choosing the Job Applicant fills the rest from the candidate
// (onboarding.get_onboarding_defaults): the accepted Job Offer, the company,
// department and Job Title, the Branch with its HR Officer and Head of
// Department, the holiday list, then the template, whose activities HRMS's
// script loads. Only blank fields are filled; the server applies the same
// defaults on save.

const HA_ONBOARDING_FIELDS = [
	"job_offer",
	"company",
	"department",
	"designation",
	"custom_branch",
	"custom_hr_officer",
	"custom_head_of_department",
	"holiday_list",
];

frappe.ui.form.on("Employee Onboarding", {
	refresh(frm) {
		// arrived with the candidate set (Create > Employee Onboarding on a Job Offer)
		if (frm.is_new() && frm.doc.job_applicant) {
			ha_onboarding_defaults(frm);
		}
	},
	job_applicant(frm) {
		ha_onboarding_defaults(frm);
	},
	employee_onboarding_template(frm) {
		// The template's company, department and Job Title are fetched over
		// ours, blank ones included: fill the blanks again once that lands
		ha_onboarding_defaults(frm, true);
	},
	date_of_joining(frm) {
		if (frm.doc.date_of_joining && !frm.doc.boarding_begins_on) {
			frm.set_value("boarding_begins_on", frm.doc.date_of_joining);
		}
	},
});

function ha_onboarding_defaults(frm, template_chosen) {
	const job_applicant = frm.doc.job_applicant;
	if (!job_applicant || frm.doc.docstatus !== 0) {
		return;
	}
	// after the link fetches already on their way (HRMS's and Frappe's)
	frappe.after_ajax(() =>
		frappe
			.xcall("hrms_addon.hrms_addon.onboarding.get_onboarding_defaults", {
				job_applicant,
				job_offer: frm.doc.job_offer || null,
			})
			.then((values) => {
				if (frm.doc.job_applicant !== job_applicant) {
					return; // the candidate changed again while this was on its way
				}
				const blanks = {};
				for (const field of HA_ONBOARDING_FIELDS) {
					if (values[field] && !frm.doc[field]) {
						blanks[field] = values[field];
					}
				}
				return frm.set_value(blanks).then(() => {
					// last: choosing the template loads its activities (HRMS)
					const template = values.employee_onboarding_template;
					if (!template_chosen && template && !frm.doc.employee_onboarding_template) {
						return frm.set_value("employee_onboarding_template", template);
					}
				});
			})
	);
}
