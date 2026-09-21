// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shift Allowance", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		if (frm.doc.total) {
			frm.dashboard.set_headline(
				`<span>${__("{0} shift(s)", [frm.doc.shifts_worked || 0])} — <b>${format_currency(
					frm.doc.total
				)}</b></span>` +
					(frm.doc.additional_salary
						? ` <span class="indicator-pill green">${__("With payroll")}</span>`
						: "")
			);
		}
		if (frm.doc.additional_salary) {
			frm.add_custom_button(__("Additional Salary"), () =>
				frappe.set_route("Form", "Additional Salary", frm.doc.additional_salary)
			);
		}
		if (frm.doc.docstatus === 0) {
			frm.set_intro(
				__("Counted from the attendance, not from the roster. A shift planned and not worked is not paid."),
				"blue"
			);
		}
	},
	onload(frm) {
		if (!frm.is_new() || frm.doc.from_date) return;
		// the attendance cycle runs the 26th to the 25th
		const day = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		const opens = new Date(day.getFullYear(), day.getMonth() - 1, 26);
		frm.set_value("from_date", frappe.datetime.obj_to_str(opens));
		frm.set_value("to_date", frappe.datetime.obj_to_str(new Date(day.getFullYear(), day.getMonth(), 25)));
	},
});

frappe.ui.form.on("Shift Allowance Line", {
	shift_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.shift_type || row.rate) return;
		frappe.db
			.get_value("Shift Type", row.shift_type, ["custom_shift_allowance", "custom_allowance_component"])
			.then((result) => {
				const found = (result && result.message) || {};
				if (found.custom_shift_allowance) {
					frappe.model.set_value(cdt, cdn, "rate", found.custom_shift_allowance);
				}
				if (found.custom_allowance_component && !frm.doc.salary_component) {
					frm.set_value("salary_component", found.custom_allowance_component);
				}
			});
	},
});
