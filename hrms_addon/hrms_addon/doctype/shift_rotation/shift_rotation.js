// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shift Rotation", {
	refresh(frm) {
		frm.trigger("say_the_period");
		if (frm.is_new()) return;
		if (frm.doc.status === "Active") {
			frm.add_custom_button(__("Roll Now"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.shifts.roll", { rotation: frm.doc.name })
					.then((made) => {
						frappe.show_alert({
							message: made
								? __("{0} shift assignment(s) made.", [made])
								: __("Everybody already has this period's assignment."),
							indicator: "green",
						});
						frm.reload_doc();
					})
			);
		}
		frm.add_custom_button(__("Shift Assignments"), () =>
			frappe.set_route("List", "Shift Assignment", { department: frm.doc.department })
		);
	},
	say_the_period(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.this_period_from) return;
		const held = (frm.doc.members || []).filter((row) => row.hold_until).length;
		frm.dashboard.set_headline(
			`<span>${__("This period")} <b>${frappe.datetime.str_to_user(
				frm.doc.this_period_from
			)}</b> – <b>${frappe.datetime.str_to_user(frm.doc.this_period_to)}</b></span>` +
				` <span class="indicator-pill blue">${__("{0} position(s)", [frm.doc.cycle_length || 0])}</span>` +
				(held ? ` <span class="indicator-pill orange">${__("{0} held", [held])}</span>` : "")
		);
	},
});

frappe.ui.form.on("Shift Rotation Member", {
	// somebody held off the rotation is held on a named shift, or the hold
	// means nothing
	hold_until(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.hold_until && !row.held_shift && row.current_shift) {
			frappe.model.set_value(cdt, cdn, "held_shift", row.current_shift);
		}
	},
});
