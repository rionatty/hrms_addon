// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Requisition", {
	refresh(frm) {
		const grid = frm.fields_dict.target_employees.grid;
		if (frm.doc.docstatus !== 0) {
			grid.clear_custom_buttons();
			return;
		}
		grid.add_custom_button(__("Add Employees"), () =>
			hrms_addon.pick_employees({
				department: frm.doc.department,
				skip: listed(frm),
				action: (rows) => add_employees(frm, rows),
			})
		);
		frm.add_custom_button(__("Get Needs Forms"), () =>
			frappe
				.xcall("hrms_addon.hrms_addon.training.get_needs_forms", {
					department: frm.doc.department, year: frm.doc.preferred_year,
				})
				.then((rows) => {
					if (!rows.length) {
						frappe.show_alert({ message: __("No Training Needs Forms waiting for a requisition."), indicator: "blue" });
						return;
					}
					add_employees(frm, rows);
				})
		);
	},
	setup(frm) {
		frm.set_query("employee", "target_employees", () => {
			const filters = { status: "Active" };
			if (frm.doc.department) filters.department = frm.doc.department;
			if (listed(frm).length) filters.name = ["not in", listed(frm)];
			return { filters: filters };
		});
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.department) {
			frappe.db.get_value("Employee", { user_id: frappe.session.user }, ["department", "branch"]).then((r) => {
				if (r.message) {
					if (r.message.department) frm.set_value("department", r.message.department);
					if (r.message.branch) frm.set_value("branch", r.message.branch);
				}
			});
		}
	},
});

function listed(frm) {
	return (frm.doc.target_employees || []).map((r) => r.employee).filter(Boolean);
}

// each employee once: one already listed is left as it is
function add_employees(frm, rows) {
	const have = new Set(listed(frm));
	let added = 0;
	for (const row of rows) {
		if (!row.employee || have.has(row.employee)) continue;
		have.add(row.employee);
		frm.add_child("target_employees", row);
		added += 1;
	}
	frm.refresh_field("target_employees");
	if (added) frm.dirty();
}
