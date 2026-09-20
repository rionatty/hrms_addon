// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Annual Leave Plan", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Tell the Employees"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.leave.inform_employees", { plan: frm.doc.name })
					.then((told) => {
						frappe.show_alert({
							message: __("{0} employee(s) told their leave dates.", [told]),
							indicator: "green",
						});
						frm.reload_doc();
					})
			);
		}
		frm.trigger("show_totals");
	},
	// The plan is only useful if it fits inside what people are owed, so
	// say at a glance how it stands.
	show_totals(frm) {
		frm.dashboard.clear_headline();
		const rows = frm.doc.employees || [];
		if (!rows.length) return;
		const over = rows.filter(
			(row) => row.entitlement_days && (row.planned_days || 0) > row.entitlement_days
		).length;
		frm.dashboard.set_headline(
			`<span>${__("Employees")} <b>${rows.length}</b> &nbsp;|&nbsp; ${__("Days planned")} <b>${
				frm.doc.total_days || 0
			}</b></span>` +
				` <span class="indicator-pill ${over ? "orange" : "green"}">${
					over
						? __("{0} planned for more than they are entitled to", [over])
						: __("Within entitlement")
				}</span>`
		);
	},
	year(frm) {
		if (frm.doc.year && !frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}
	},
});

frappe.ui.form.on("Annual Leave Plan Employee", {
	planned_from(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.planned_from && row.planned_days && !row.planned_to) {
			frappe.model.set_value(
				cdt,
				cdn,
				"planned_to",
				frappe.datetime.add_days(row.planned_from, row.planned_days - 1)
			);
		}
	},
	planned_to(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.planned_from && row.planned_to) {
			frappe.model.set_value(
				cdt,
				cdn,
				"planned_days",
				frappe.datetime.get_day_diff(row.planned_to, row.planned_from) + 1
			);
		}
	},
});
