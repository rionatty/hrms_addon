// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Data Change Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Pending HR" && frm.has_perm("submit")) {
			frm.add_custom_button(__("Approve"), () =>
				frappe.confirm(
					__("Write these details to {0}'s record?", [frm.doc.employee_name || frm.doc.employee]),
					() =>
						frappe
							.xcall("hrms_addon.hrms_addon.employee_data.approve", { name: frm.doc.name })
							.then(() => frm.reload_doc())
				)
			);
			frm.add_custom_button(__("Reject"), () =>
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.employee_data.reject", {
								name: frm.doc.name,
								reason: values.reason,
							})
							.then(() => frm.reload_doc()),
					__("Reject the request"),
					__("Reject")
				)
			);
		}
		if (frm.doc.status === "Approved") {
			frm.set_intro(__("Approved and written to the employee's record."), "green");
		} else if (frm.doc.status === "Rejected") {
			frm.set_intro(__("Not approved."), "red");
		}
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.employee) {
			frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then((r) => {
				if (r.message && r.message.name) frm.set_value("employee", r.message.name);
			});
		}
		if (frm.is_new() && !frm.doc.request_date) {
			frm.set_value("request_date", frappe.datetime.get_today());
		}
	},
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
	},
});
