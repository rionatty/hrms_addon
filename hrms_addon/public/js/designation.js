// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Designation (Job Title) — Job Description tab. Loaded through hooks.py
// doctype_js, read from disk at runtime, so no `bench build` is needed.

// Order and wording as printed in Luuka's JDs. Source of truth is
// hrms_addon/hrms_addon/jd_rules.py PERSPECTIVES — keep them in step
// (scripts/verify_job_description.py checks that they are).
const HA_BSC_PERSPECTIVES = [
	"Financial",
	"Customer / Stakeholder",
	"Internal Business Processes",
	"Learning & Growth",
];

frappe.ui.form.on("Designation", {
	onload(frm) {
		// A new Job Title starts with the four scorecard rows ready to fill.
		if (frm.is_new() && !ha_kra_rows(frm).length) {
			ha_add_perspectives(frm);
		}
	},

	refresh(frm) {
		// Job Titles that existed before the template get a one-click start
		// instead of a silently dirtied form.
		if (!frm.is_new() && frm.has_perm("write") && !ha_kra_rows(frm).length) {
			frm.add_custom_button(__("Add Balanced Scorecard Perspectives"), () => {
				ha_add_perspectives(frm);
			});
		}
	},
});

function ha_kra_rows(frm) {
	return frm.doc.custom_jd_key_result_areas || [];
}

function ha_add_perspectives(frm) {
	HA_BSC_PERSPECTIVES.forEach((perspective) => {
		frm.add_child("custom_jd_key_result_areas", { perspective });
	});
	frm.refresh_field("custom_jd_key_result_areas");
}
