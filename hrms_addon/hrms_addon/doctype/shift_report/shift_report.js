// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A section's shift (excellence.py): the standard in force and the roster on
// its date fill the target, machines, crew and who led it; the crew comes from
// the clock; the downtime events and output lines total themselves; the score
// is worked out on save.
frappe.ui.form.on("Shift Report", {
	setup(frm) {
		frm.set_query("work_section", () => ({ filters: { is_active: 1, shift_reports: 1 } }));
		for (const field of ["supervisor", "production_officer"]) {
			frm.set_query(field, () => ({
				filters: Object.assign({ status: "Active" }, frm.doc.branch ? { branch: frm.doc.branch } : {}),
			}));
		}
		frm.set_query("downtime_reason", () => ({ filters: { is_active: 1 } }));
		frm.set_query("downtime_reason", "downtime", () => ({ filters: { is_active: 1 } }));
		const machines = () => ({
			filters: Object.assign({ is_active: 1 }, frm.doc.work_section ? { work_section: frm.doc.work_section } : {}),
		});
		frm.set_query("machine", "downtime", machines);
		frm.set_query("machine", "outputs", machines);
		frm.set_query("plant_order", "outputs", () => ({ filters: { status: ["in", ["Open", "Running"]] } }));
	},
	refresh(frm) {
		if (frm.doc.status) {
			const colour = { "On Target": "green", Attention: "orange", Critical: "red" }[frm.doc.status];
			frm.dashboard.set_headline(
				__("Score {0}: {1}. Weakest area: {2}.", [frm.doc.score, __(frm.doc.status), __(frm.doc.weakest_area)]),
				colour
			);
		}
		if (frm.doc.not_marked && frm.doc.docstatus === 0) {
			frm.dashboard.add_comment(
				__("{0} of the crew are not marked on the clock yet. Fetch again once attendance is in.", [frm.doc.not_marked]),
				"orange",
				true
			);
		}
	},
	work_section(frm) {
		me_shift_defaults(frm, true);
	},
	shift(frm) {
		me_shift_defaults(frm, false);
	},
	report_date(frm) {
		me_shift_defaults(frm, true);
	},
	fetch_crew(frm) {
		const work = () =>
			frappe.xcall("hrms_addon.hrms_addon.excellence.fetch_crew", { name: frm.doc.name }).then((found) => {
				frappe.show_alert({
					message: __("{0} rostered, {1} on shift", [found.planned, found.on_shift]),
					indicator: "green",
				});
				frm.reload_doc();
			});
		if (frm.is_new() || frm.is_dirty()) {
			frm.save().then(work);
		} else {
			work();
		}
	},
});

function me_shift_defaults(frm, whole) {
	if (!frm.doc.work_section || frm.doc.docstatus !== 0) return;
	frappe
		.xcall("hrms_addon.hrms_addon.excellence.section_defaults", {
			section: frm.doc.work_section,
			shift: frm.doc.shift,
			report_date: frm.doc.report_date,
		})
		.then((found) => {
			if (whole) {
				frm.set_value("target", found.target);
				frm.set_value("machines", found.machines);
				frm.set_value("machines_running", found.machines);
				if (!(frm.doc.crew || []).length) frm.set_value("staff_planned", found.staff_planned);
			}
			if (found.supervisor) frm.set_value("supervisor", found.supervisor);
			if (found.production_officer) frm.set_value("production_officer", found.production_officer);
		});
}
