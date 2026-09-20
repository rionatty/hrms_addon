// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Needs Assessment", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Requisitions"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.training.get_requisitions", { branch: frm.doc.branch, year: frm.doc.year })
					.then((rows) => {
						if (!rows.length) {
							frappe.show_alert({ message: __("No requisitions waiting for assessment."), indicator: "blue" });
							return;
						}
						const have = new Set((frm.doc.requisitions || []).map((r) => r.requisition));
						for (const row of rows) {
							if (have.has(row.requisition)) continue;
							frm.add_child("requisitions", { requisition: row.requisition });
							frm.add_child("needs", {
								topic: row.training_topic, section: row.department, method: row.proposed_method,
								trainer: row.proposed_trainer, budget: row.estimated_budget, duration: row.duration,
								month: row.preferred_month, target_group: row.target_group, objectives: row.required_skills,
								requisition: row.requisition,
							});
						}
						frm.refresh_field("requisitions");
						frm.refresh_field("needs");
					})
			);
		}
	},
});
