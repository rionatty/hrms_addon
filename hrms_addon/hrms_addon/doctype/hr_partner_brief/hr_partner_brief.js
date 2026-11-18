// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The week for the Monday production meeting (excellence_brief.py): built
// from the week's figures, sent to the Plant Manager and HR.
frappe.ui.form.on("HR Partner Brief", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Build from the Figures"), () => {
			const work = () =>
				frappe.xcall("hrms_addon.hrms_addon.excellence_brief.build", { name: frm.doc.name }).then(() => frm.reload_doc());
			if (frm.is_dirty()) {
				frm.save().then(work);
			} else {
				work();
			}
		});
		frm.add_custom_button(__("Send"), () => {
			frappe.confirm(__("E-mail this brief to the Plant Manager and HR?"), () =>
				frappe.xcall("hrms_addon.hrms_addon.excellence_brief.send", { name: frm.doc.name }).then((users) => {
					frappe.show_alert({ message: __("Sent to {0}", [users.length]), indicator: "green" });
					frm.reload_doc();
				})
			);
		});
	},
});
