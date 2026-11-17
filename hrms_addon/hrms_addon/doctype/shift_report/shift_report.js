// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A section's shift (excellence.py): the section fills the target, machines,
// crew and the supervisor who leads the shift; the score is worked out on save.
frappe.ui.form.on("Shift Report", {
	setup(frm) {
		frm.set_query("work_section", () => ({ filters: { is_active: 1, shift_reports: 1 } }));
		for (const field of ["supervisor", "production_officer"]) {
			frm.set_query(field, () => ({
				filters: Object.assign({ status: "Active" }, frm.doc.branch ? { branch: frm.doc.branch } : {}),
			}));
		}
	},
	refresh(frm) {
		if (frm.doc.status) {
			const colour = { "On Target": "green", Attention: "orange", Critical: "red" }[frm.doc.status];
			frm.dashboard.set_headline(
				__("Score {0}: {1}. Weakest area: {2}.", [frm.doc.score, __(frm.doc.status), __(frm.doc.weakest_area)]),
				colour
			);
		}
	},
	work_section(frm) {
		ha_shift_defaults(frm, true);
	},
	shift(frm) {
		ha_shift_defaults(frm, false);
	},
});

function ha_shift_defaults(frm, whole) {
	if (!frm.doc.work_section || frm.doc.docstatus !== 0) return;
	frappe
		.xcall("hrms_addon.hrms_addon.excellence.section_defaults", {
			section: frm.doc.work_section,
			shift: frm.doc.shift,
		})
		.then((found) => {
			if (whole) {
				frm.set_value("target", found.target);
				frm.set_value("machines", found.machines);
				frm.set_value("machines_running", found.machines);
				frm.set_value("staff_planned", found.staff_planned);
			}
			if (found.supervisor) frm.set_value("supervisor", found.supervisor);
		});
}
