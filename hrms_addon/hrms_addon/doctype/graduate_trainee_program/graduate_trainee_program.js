// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Graduate Trainee Program", {
	refresh(frm) {
		frm.trigger("say_where");
		if (frm.doc.employee) {
			frm.add_custom_button(__("Employee"), () =>
				frappe.set_route("Form", "Employee", frm.doc.employee)
			);
		}
		if (frm.doc.placement) {
			frm.add_custom_button(__("Nine-Box Placement"), () =>
				frappe.set_route("Form", "Talent Placement", frm.doc.placement)
			);
		}
	},
	say_where(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		const parts = [`<span>${__("Cohort")} <b>${frappe.utils.escape_html(frm.doc.cohort || "")}</b></span>`];
		const rotations = (frm.doc.rotations || []).length;
		if (rotations) {
			const done = (frm.doc.rotations || []).filter((row) => row.completed).length;
			parts.push(`<span>${__("Rotations")}: <b>${done}/${rotations}</b></span>`);
		}
		const milestones = (frm.doc.milestones || []).length;
		if (milestones) {
			parts.push(
				`<span>${__("Milestones passed")}: <b>${frm.doc.milestones_passed || 0}/${milestones}</b></span>`
			);
		}
		if (frm.doc.average_score) {
			const colour = frm.doc.average_score < 60 ? "red" : "green";
			parts.push(
				`<span class="indicator-pill ${colour}">${__("Average")} ${frm.doc.average_score}</span>`
			);
		}
		frm.dashboard.set_headline(parts.join(" &nbsp;|&nbsp; "));
	},
});

frappe.ui.form.on("Trainee Rotation", {
	// a trainee is in one place at a time, so the next stint starts after
	// the last one ends
	rotations_add(frm, cdt, cdn) {
		const rows = frm.doc.rotations || [];
		const previous = rows[rows.length - 2];
		if (previous && previous.to_date) {
			frappe.model.set_value(cdt, cdn, "from_date", frappe.datetime.add_days(previous.to_date, 1));
		}
	},
});

frappe.ui.form.on("Trainee Milestone", {
	score(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.score === undefined || row.score === null || row.result) return;
		const rows = frm.doc.milestones || [];
		const last = rows.length && rows[rows.length - 1].name === cdn;
		frappe.model.set_value(cdt, cdn, "result", row.score < 60 ? "Fail" : last ? "Final Pass" : "Pass");
	},
});
