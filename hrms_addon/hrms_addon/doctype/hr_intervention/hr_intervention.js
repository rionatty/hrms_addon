// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A workforce issue and what HR did about it (excellence.py): the KPI's
// readings give its baseline, latest and change; days open and overdue are
// worked out on save.
frappe.ui.form.on("HR Intervention", {
	setup(frm) {
		frm.set_query("supervisor", () => ({ filters: { status: "Active" } }));
		frm.set_query("work_section", () => ({ filters: { is_active: 1 } }));
		frm.set_query("section_week", () => ({
			filters: frm.doc.work_section ? { work_section: frm.doc.work_section } : {},
		}));
	},
	refresh(frm) {
		if (frm.doc.overdue) {
			frm.dashboard.set_headline(__("Past its target date."), "red");
		} else if (frm.doc.result) {
			const colour = { Improved: "green", Worse: "red" }[frm.doc.result] || "blue";
			frm.dashboard.set_headline(__("{0}: {1}", [__(frm.doc.kpi), __(frm.doc.result)]), colour);
		}
	},
});
