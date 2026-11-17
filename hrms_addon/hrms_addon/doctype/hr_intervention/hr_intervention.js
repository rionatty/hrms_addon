// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A workforce issue and what HR did about it (excellence.py): the KPI's change,
// days open and whether it is overdue are worked out on save.
frappe.ui.form.on("HR Intervention", {
	setup(frm) {
		frm.set_query("supervisor", () => ({ filters: { status: "Active" } }));
		frm.set_query("work_section", () => ({ filters: { is_active: 1 } }));
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
