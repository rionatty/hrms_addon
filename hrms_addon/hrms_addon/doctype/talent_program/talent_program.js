// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The development plan (test cases 1 to 3, and 9): how far it has got —
// the actions done out of all of them, and those past their date — and
// the date each action was done, a column of this plan's actions. The
// appraisal keeps the same actions table, and its own grid is left as it
// is. The links go to whatever the plan came from or went to.

frappe.ui.form.on("Talent Program", {
	setup(frm) {
		// the succession plan, the placement and the promotion that point at
		// a plan are cancelled on their own (talent.program_on_cancel)
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([...(frm.ignore_doctypes_on_cancel_all || []),
				"Succession Position", "Employee Position Change", "Talent Placement", "Training Requisition"]),
		];
	},
	refresh(frm) {
		const grid = frm.fields_dict.actions && frm.fields_dict.actions.grid;
		const done = frappe.meta.get_docfield("Development Action", "completed_on", frm.doc.name);
		if (grid && done && !done.in_list_view) {
			done.in_list_view = 1;
			done.columns = 2;
			grid.reset_grid();
		}
		ha_plan_progress(frm);
		const go = (label, doctype, name) => {
			if (name) frm.add_custom_button(__(label), () => frappe.set_route("Form", doctype, name), __("Open"));
		};
		go("Employee", "Employee", frm.doc.employee);
		go("Succession Plan", "Succession Position", frm.doc.succession_position);
		go("Nine-Box Placement", "Talent Placement", frm.doc.placement);
		go("Training Requisition", "Training Requisition", frm.doc.training_requisition);
	},
});

frappe.ui.form.on("Development Action", {
	completed_on(frm) {
		ha_plan_progress(frm);
	},
	actions_remove(frm) {
		ha_plan_progress(frm);
	},
});

// The plan's progress, in the form's headline: its actions, and the
// trainings L&D booked for it (the Training table, filled from L&D).
function ha_plan_progress(frm) {
	frm.dashboard.clear_headline();
	const rows = frm.doc.actions || [];
	if (frm.is_new() || !rows.length) return;
	const done = rows.filter((row) => row.completed_on).length;
	const today = frappe.datetime.get_today();
	const late = rows.filter((row) => !row.completed_on && row.by_when && row.by_when < today).length;
	const share = Math.round((100 * done) / rows.length);
	const trainings = frm.doc.trainings || [];
	const attended = trainings.filter((row) => row.attendance === "Present").length;
	frm.dashboard.set_headline(
		`<span>${__("{0} of {1} actions done", [done, rows.length])}</span>
		<span style="display:inline-block;width:120px;height:6px;border-radius:3px;background:var(--border-color);
			margin:0 10px;vertical-align:middle;overflow:hidden"><span style="display:block;height:100%;width:${share}%;
			background:#E8A317"></span></span>` +
			(late ? `<span class="indicator-pill red">${__("{0} past their date", [late])}</span>` : "") +
			(trainings.length
				? `<span style="margin-left:12px">${__("{0} of {1} trainings attended", [attended, trainings.length])}</span>`
				: "")
	);
}
