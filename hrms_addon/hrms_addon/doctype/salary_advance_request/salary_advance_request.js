// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Salary Advance Request", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.first_month) {
			frm.set_value("first_month", frappe.datetime.get_today());
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status !== "Active") return;
		frm.add_custom_button(__("Stop"), () => {
			frappe.prompt(
				{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				(values) =>
					frappe
						.xcall("hrms_addon.hrms_addon.salary_advances.stop_request", {
							name: frm.doc.name,
							reason: values.reason,
						})
						.then(() => frm.reload_doc()),
				__("Stop this request"),
				__("Stop")
			);
		});
	},
});
