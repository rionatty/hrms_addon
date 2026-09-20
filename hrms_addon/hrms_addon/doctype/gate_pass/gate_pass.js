// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Gate Pass", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && ["Issued", "Not Returned"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Record Return"), () =>
				frappe.prompt(
					{
						fieldname: "came_back",
						fieldtype: "Datetime",
						label: __("Came back at"),
						reqd: 1,
						default: frappe.datetime.now_datetime(),
					},
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.attendance.record_return", {
								name: frm.doc.name,
								came_back: values.came_back,
							})
							.then(() => frm.reload_doc()),
					__("Record the return"),
					__("Record")
				)
			);
		}
		if (frm.doc.status === "Not Returned") {
			frm.set_intro(__("The day has passed and no return was recorded."), "red");
		} else if (frm.doc.status === "Returned") {
			frm.set_intro(__("Back after {0} hour(s).", [frm.doc.hours_away || 0]), "green");
		}
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.pass_date) {
			frm.set_value("pass_date", frappe.datetime.get_today());
		}
	},
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
	},
});
