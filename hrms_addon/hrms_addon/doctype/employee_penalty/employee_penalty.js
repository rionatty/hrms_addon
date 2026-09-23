// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Penalty", {
	setup(frm) {
		frm.set_query("recovery_component", () => ({ filters: { type: "Deduction" } }));
		frm.set_query("disciplinary_case", () => ({
			filters: frm.doc.employee ? { employee: frm.doc.employee } : {},
		}));
	},
	refresh(frm) {
		frm.trigger("show_penalty");
		if (frm.doc.docstatus === 1 && frm.doc.outstanding > 0) {
			frm.add_custom_button(__("Mark Recovered"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.recoveries.catch_up_for", {
						doctype: frm.doctype,
						name: frm.doc.name,
					})
					.then(() => frm.reload_doc())
			);
		}
	},
	// what the employee is being asked to agree to, said before anyone signs
	show_penalty(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || frm.doc.finding !== "Liable" || !frm.doc.amount) return;
		const money = (value) => frappe.format(value || 0, { fieldtype: "Currency" });
		const parts = [`${__("Liable for")} <b>${money(frm.doc.amount)}</b>`];
		if (frm.doc.extent_of_deduction) {
			parts.push(frappe.utils.escape_html(frm.doc.extent_of_deduction));
		}
		if (frm.doc.docstatus === 1) {
			parts.push(`${__("Outstanding")} <b>${money(frm.doc.outstanding)}</b>`);
		}
		frm.dashboard.set_headline(`<span>${parts.join(" &nbsp;|&nbsp; ")}</span>`);
	},
	finding(frm) {
		// LPL/HR/39's Liability and Reason start from the supervisor's report
		if (frm.doc.finding !== "Liable") return;
		if (!frm.doc.liability && frm.doc.details) {
			frm.set_value("liability", frm.doc.details);
		}
		if (!frm.doc.reason && frm.doc.kind) {
			frm.set_value("reason", frm.doc.kind);
		}
		if (!frm.doc.amount && frm.doc.estimated_value) {
			frm.set_value("amount", frm.doc.estimated_value);
		}
	},
});
