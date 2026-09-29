// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Allowance Request: LPL.HR.31's lines and the other allowances, the
// four signatures, and Accounts' payment (allowances.py). The server works
// every figure out again on save; this keeps the form's figures current as
// they are typed.

frappe.ui.form.on("Allowance Request", {
	setup(frm) {
		frm.set_query("allowance_type", "lines", () => ({ filters: { disabled: 0 } }));
		frm.set_query("advance", () => ({ filters: { employee: frm.doc.employee, docstatus: 1 } }));
		frm.set_query("payment_account", () => ({
			filters: { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 },
		}));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("acting_for", () => ({
			filters: { status: "Active", name: ["!=", frm.doc.employee || ""] },
		}));
		frm.set_query("leave_application", () => ({
			filters: { employee: frm.doc.acting_for, docstatus: 1 },
		}));
		frm.set_query("travel_request", () => ({ filters: { employee: frm.doc.employee } }));
	},

	refresh(frm) {
		ha_allowance_headline(frm);
		if (frm.is_new() && !(frm.doc.lines || []).length) {
			frm.add_custom_button(__("Add Field Allowances"), () => ha_add_field_lines(frm));
		}
	},

	start_date(frm) {
		if (frm.doc.start_date && !frm.doc.end_date) frm.set_value("end_date", frm.doc.start_date);
	},

	less_advance(frm) {
		ha_allowance_totals(frm);
	},
});

frappe.ui.form.on("Allowance Request Line", {
	allowance_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.allowance_type) return;
		frappe.db
			.get_value("Allowance Type", row.allowance_type, [
				"needs_trip",
				"needs_acting_for",
				"paid_through",
				"standard_rate",
			])
			.then((r) => {
				const kind = r.message || {};
				frappe.model.set_value(cdt, cdn, "needs_trip", kind.needs_trip || 0);
				frappe.model.set_value(cdt, cdn, "needs_acting_for", kind.needs_acting_for || 0);
				frappe.model.set_value(cdt, cdn, "paid_through", kind.paid_through || "Accounts");
				if (!row.rate && kind.standard_rate) frappe.model.set_value(cdt, cdn, "rate", kind.standard_rate);
				ha_allowance_sections(frm);
			});
	},
	days(frm, cdt, cdn) {
		ha_cost_line(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		// a rate typed here is the employee's own, not the scale's
		const row = locals[cdt][cdn];
		if (row.from_scale) frappe.model.set_value(cdt, cdn, "from_scale", 0);
		ha_cost_line(frm, cdt, cdn);
	},
	lines_remove(frm) {
		ha_allowance_sections(frm);
		ha_allowance_totals(frm);
	},
});

function ha_cost_line(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const days = flt(row.days);
	const amount = days > 0 ? days * flt(row.rate) : flt(row.rate);
	frappe.model.set_value(cdt, cdn, "amount", amount);
	ha_allowance_totals(frm);
}

// The trip and the standing-in sections show when a line asks for them.
function ha_allowance_sections(frm) {
	const lines = frm.doc.lines || [];
	const trip = lines.some((row) => row.needs_trip) ? 1 : 0;
	const acting = lines.some((row) => row.needs_acting_for) ? 1 : 0;
	if (cint(frm.doc.needs_trip) !== trip) frm.set_value("needs_trip", trip);
	if (cint(frm.doc.needs_acting_for) !== acting) frm.set_value("needs_acting_for", acting);
}

function ha_allowance_totals(frm) {
	let total = 0;
	let payroll = 0;
	(frm.doc.lines || []).forEach((row) => {
		total += flt(row.amount);
		if (row.paid_through === "Payroll") payroll += flt(row.amount);
	});
	frm.doc.total = total;
	frm.doc.through_payroll = payroll;
	frm.doc.balance_due = total - payroll - flt(frm.doc.less_advance);
	frm.refresh_fields(["total", "through_payroll", "balance_due"]);
	ha_allowance_headline(frm);
}

// The five lines LPL.HR.31 prints, added in one go.
function ha_add_field_lines(frm) {
	frappe.db
		.get_list("Allowance Type", {
			filters: { needs_trip: 1, disabled: 0 },
			fields: ["name", "paid_through", "standard_rate"],
			order_by: "creation asc",
			limit: 20,
		})
		.then((rows) => {
			rows.forEach((kind) => {
				frm.add_child("lines", {
					allowance_type: kind.name,
					needs_trip: 1,
					paid_through: kind.paid_through || "Accounts",
					rate: kind.standard_rate || 0,
				});
			});
			frm.refresh_field("lines");
			ha_allowance_sections(frm);
		});
}

function ha_allowance_headline(frm) {
	frm.dashboard.clear_headline();
	if (!flt(frm.doc.total)) return;
	const money = (value) => format_currency(value || 0, frm.doc.currency);
	const balance = flt(frm.doc.balance_due);
	let text =
		`<span>${__("Total")} <b>${money(frm.doc.total)}</b>` +
		` &nbsp;|&nbsp; ${__("Less advance")} <b>${money(frm.doc.less_advance)}</b>` +
		` &nbsp;|&nbsp; ${__("Balance")} <b>${money(balance)}</b>`;
	if (flt(frm.doc.through_payroll)) {
		text += ` &nbsp;|&nbsp; ${__("Through payroll")} <b>${money(frm.doc.through_payroll)}</b>`;
	}
	text +=
		`</span> <span class="indicator-pill ${balance < 0 ? "orange" : "green"}">` +
		`${balance < 0 ? __("Refundable by the employee") : __("Due to the employee")}</span>`;
	frm.dashboard.set_headline(text);
}
