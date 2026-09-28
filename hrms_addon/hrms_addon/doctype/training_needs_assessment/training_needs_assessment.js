// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Training Needs Assessment", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Requisitions"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.training.get_requisitions", { branch: frm.doc.branch, year: frm.doc.year })
					.then((rows) => {
						const have = new Set((frm.doc.requisitions || []).map((r) => r.requisition));
						const fresh = rows.filter((row) => !have.has(row.requisition));
						if (!fresh.length) {
							frappe.show_alert({ message: __("No requisitions waiting for assessment."), indicator: "blue" });
							return;
						}
						// the blank rows a new assessment opens with go first
						for (const row of (frm.doc.requisitions || []).filter((r) => !r.requisition)) {
							frappe.model.clear_doc(row.doctype, row.name);
						}
						for (const row of (frm.doc.needs || []).filter((r) => !r.topic)) {
							frappe.model.clear_doc(row.doctype, row.name);
						}
						// each requisition once, each of its topics a need naming it
						for (const row of fresh) {
							frm.add_child("requisitions", {
								requisition: row.requisition, department: row.department, requester_name: row.requester_name,
							});
							for (const need of row.needs || []) frm.add_child("needs", need);
						}
						frm.refresh_field("requisitions");
						frm.refresh_field("needs");
						frm.dirty();
					})
			);
		}
	},
});
