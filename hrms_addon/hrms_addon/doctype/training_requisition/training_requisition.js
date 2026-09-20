// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Requisition", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
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
						const have = new Set((frm.doc.target_employees || []).map((r) => r.employee));
						for (const row of rows) {
							if (have.has(row.employee)) continue;
							frm.add_child("target_employees", row);
						}
						frm.refresh_field("target_employees");
						if (!frm.doc.required_skills) {
							frm.set_value("required_skills", rows.map((r) => r.skill_areas).filter(Boolean).join("
"));
						}
					})
			);
		}
	},
	setup(frm) {
		frm.set_query("employee", "target_employees", () => ({
			filters: { status: "Active", ...(frm.doc.department ? { department: frm.doc.department } : {}) },
		}));
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
