// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Overtime Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Requested" && frm.has_perm("submit")) {
			frm.add_custom_button(__("Authorise"), () =>
				frappe.prompt(
					{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.attendance.authorise_overtime", {
								name: frm.doc.name,
								remarks: values.remarks,
							})
							.then(() => frm.reload_doc()),
					__("Authorise the overtime"),
					__("Authorise")
				)
			);
			frm.add_custom_button(__("Reject"), () =>
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.attendance.reject_overtime", {
								name: frm.doc.name,
								reason: values.reason,
							})
							.then(() => frm.reload_doc()),
					__("Reject the overtime"),
					__("Reject")
				)
			);
		}
		if (frm.doc.status === "Authorised" && !frm.doc.coupons_issued) {
			frm.add_custom_button(__("Issue Food Coupons"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.attendance.issue_coupons", { name: frm.doc.name })
					.then((found) => {
						frappe.show_alert({
							message: __("{0} permanent and {1} casual coupon(s).", [
								found.permanent,
								found.casual,
							]),
							indicator: "green",
						});
						frm.reload_doc();
					})
			);
		}
		if (frm.doc.status === "Authorised") {
			frm.set_intro(__("Authorised. HR issues the food coupons."), "green");
		} else if (frm.doc.status === "Rejected") {
			frm.set_intro(__("Not authorised."), "red");
		}
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.overtime_date) {
			frm.set_value("overtime_date", frappe.datetime.get_today());
		}
	},
	setup(frm) {
		frm.set_query("employee", "employees", () => ({ filters: { status: "Active" } }));
	},
});
