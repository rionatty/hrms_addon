// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Gradar band on Frappe HR's own Employee Grade: set the two ends and
// the ten steps are laid out between them.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Employee Grade", {
	refresh(frm) {
		frm.trigger("say_the_band");
		if (frm.is_new()) return;
		if (frm.doc.custom_min_salary && frm.doc.custom_max_salary) {
			frm.add_custom_button(__("Lay Out the Steps"), () =>
				frappe.confirm(
					__("The steps on this grade are replaced with {0} laid out evenly across the band. Continue?", [
						frm.doc.custom_step_count || 10,
					]),
					() =>
						frappe
							.xcall("hrms_addon.hrms_addon.grades.generate_steps", {
								grade: frm.doc.name,
								steps: frm.doc.custom_step_count,
							})
							.then((made) => {
								frappe.show_alert({
									message: __("{0} step(s).", [made]),
									indicator: "green",
								});
								frm.reload_doc();
							})
				)
			);
		}
	},
	say_the_band(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.custom_min_salary) return;
		frm.dashboard.set_headline(
			`<span>${frappe.utils.escape_html(frm.doc.custom_grade_code || frm.doc.name)}: ` +
				`<b>${format_currency(frm.doc.custom_min_salary)}</b> – ` +
				`<b>${format_currency(frm.doc.custom_max_salary)}</b></span>` +
				` <span class="indicator-pill blue">${__("{0} step(s)", [
					(frm.doc.custom_steps || []).length,
				])}</span>` +
				(frm.doc.custom_second_approval
					? ` <span class="indicator-pill orange">${__("Second approval")}</span>`
					: "")
		);
	},
	custom_max_salary(frm) {
		if (
			frm.doc.custom_min_salary &&
			frm.doc.custom_max_salary &&
			frm.doc.custom_max_salary <= frm.doc.custom_min_salary
		) {
			frappe.show_alert({
				message: __("The top of the band must be above the bottom of it."),
				indicator: "red",
			});
		}
	},
});
