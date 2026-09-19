// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Employee Contract: renew one coming to its end, or record that it will not
// be renewed (hrms_addon/hrms_addon/contracts.py). A contract marked Not
// Renewed can still be renewed until it is, should HR change its mind.

frappe.ui.form.on("Employee Contract", {
	refresh(frm) {
		const running = ["Active", "Expiring Soon", "Expired", "Not Renewed"].includes(frm.doc.status);
		if (frm.doc.docstatus !== 1 || !running || !frm.doc.end_date || !frm.has_perm("write")) {
			return;
		}
		frm.add_custom_button(
			__("Renew"),
			() =>
				frappe
					.xcall("hrms_addon.hrms_addon.contracts.make_renewal", { contract: frm.doc.name })
					.then((name) => frappe.set_route("Form", "Employee Contract", name)),
			__("Actions")
		);
		if (frm.doc.status === "Not Renewed") {
			return;
		}
		frm.add_custom_button(
			__("Do Not Renew"),
			() =>
				frappe.prompt(
					{ fieldname: "remarks", fieldtype: "Small Text", label: __("Why it is not renewed"), reqd: 1 },
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.contracts.mark_not_renewed", {
								contract: frm.doc.name,
								remarks: values.remarks,
							})
							.then(() => frm.reload_doc()),
					__("Do Not Renew"),
					__("Record")
				),
			__("Actions")
		);
	},
});
