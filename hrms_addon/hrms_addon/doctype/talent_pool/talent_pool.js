// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// A talent pool: its members drawn from the review's finalised placements
// in the boxes it takes, confirmed by the council, exited rather than taken
// off (talent_pools.py).

frappe.ui.form.on("Talent Pool", {
	refresh(frm) {
		if (frm.is_new()) return;
		if ((frm.doc.members || []).some((row) => row.status === "Proposed")
			&& frappe.user.has_role(["Talent Council", "HR Manager", "System Manager"])) {
			frm.add_custom_button(__("Confirm Members"), () =>
				frappe.xcall("hrms_addon.hrms_addon.talent_pools.confirm_members", { pool: frm.doc.name })
					.then((count) => {
						frappe.show_alert({ message: __("{0} members confirmed", [count || 0]), indicator: "green" });
						frm.reload_doc();
					}));
		}
	},
	get_members(frm) {
		const go = () => frappe
			.xcall("hrms_addon.hrms_addon.talent_pools.get_members", { pool: frm.doc.name })
			.then((added) => {
				frappe.show_alert({ message: __("{0} members proposed", [added || 0]), indicator: "green" });
				frm.reload_doc();
			});
		if (frm.is_dirty() || frm.is_new()) frm.save().then(go);
		else go();
	},
});
