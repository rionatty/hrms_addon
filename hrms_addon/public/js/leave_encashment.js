// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Luuka's leave encashment (minutes §4.5) on Frappe HR's own Leave
// Encashment: the leave the employee was required to work through, why,
// and what a day of it is worth.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Leave Encashment", {
	setup(frm) {
		frm.set_query("custom_leave_application", () => ({
			filters: {
				employee: frm.doc.employee || "",
				docstatus: 1,
				status: "Approved",
			},
		}));
	},
	refresh(frm) {
		frm.trigger("show_encashment");
	},
	// what is being paid, said before anyone signs
	show_encashment(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.encashment_days) return;
		const money = (value) => frappe.format(value || 0, { fieldtype: "Currency" });
		const parts = [
			`${__("Days")} <b>${frm.doc.encashment_days}</b>`,
			`${__("Per day")} <b>${money(frm.doc.custom_per_day)}</b>`,
			`${__("Amount")} <b>${money(frm.doc.encashment_amount)}</b>`,
		];
		if (
			frm.doc.custom_days_requested &&
			frm.doc.custom_days_requested !== frm.doc.encashment_days
		) {
			parts.push(`${__("Asked for")} ${frm.doc.custom_days_requested}`);
		}
		frm.dashboard.set_headline(`<span>${parts.join(" &nbsp;|&nbsp; ")}</span>`);
	},
});
