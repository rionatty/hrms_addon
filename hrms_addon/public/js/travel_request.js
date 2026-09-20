// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Employee Travel Allowance form (LPL.HR.31) on Frappe HR's own
// Travel Request: a line per kind of expense with its days and rate, a
// total, less any advance already taken, and the balance due.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Travel Request", {
	refresh(frm) {
		frm.trigger("show_totals");
		frm.set_query("custom_advance", () => ({
			filters: { employee: frm.doc.employee, docstatus: 1 },
		}));
		if (frm.is_new() && !(frm.doc.costings || []).length) {
			frm.add_custom_button(__("Add LPL.HR.31 Lines"), () => frm.trigger("add_standard_lines"));
		}
	},
	// The five lines the paper prints, added in one go so nobody retypes
	// them. They are Expense Claim Types, shared with the claim form.
	add_standard_lines(frm) {
		frappe
			.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Expense Claim Type",
					filters: { custom_is_allowance_line: 1 },
					fields: ["name"],
					limit_page_length: 20,
				},
			})
			.then((result) => {
				(result.message || []).forEach((row) => {
					const line = frm.add_child("costings");
					line.expense_type = row.name;
				});
				frm.refresh_field("costings");
			});
	},
	show_totals(frm) {
		frm.dashboard.clear_headline();
		if (!frm.doc.custom_total) return;
		const balance = frm.doc.custom_balance_due || 0;
		const money = (value) => frappe.format(value || 0, { fieldtype: "Currency" });
		frm.dashboard.set_headline(
			`<span>${__("Total")} <b>${money(frm.doc.custom_total)}</b>` +
				` &nbsp;|&nbsp; ${__("Less advance")} <b>${money(frm.doc.custom_less_advance)}</b>` +
				` &nbsp;|&nbsp; ${__("Balance")} <b>${money(balance)}</b></span>` +
				` <span class="indicator-pill ${balance < 0 ? "orange" : "green"}">${
					balance < 0 ? __("Refundable by the employee") : __("Due to the employee")
				}</span>`
		);
	},
	custom_start_date(frm) {
		if (frm.doc.custom_start_date && !frm.doc.custom_end_date) {
			frm.set_value("custom_end_date", frm.doc.custom_start_date);
		}
	},
});

frappe.ui.form.on("Travel Request Costing", {
	custom_days(frm, cdt, cdn) {
		frm.script_manager.trigger("cost_line", cdt, cdn);
	},
	custom_rate(frm, cdt, cdn) {
		frm.script_manager.trigger("cost_line", cdt, cdn);
	},
	cost_line(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const amount = (row.custom_days || 0) * (row.custom_rate || 0);
		frappe.model.set_value(cdt, cdn, "total_amount", amount);
		frappe.model.set_value(cdt, cdn, "funded_amount", amount);
	},
});
