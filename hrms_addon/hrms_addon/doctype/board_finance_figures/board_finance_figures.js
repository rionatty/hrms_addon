// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A quarter's revenue, output and staff cost by plant and month, typed by Finance (board_pack.py).
frappe.ui.form.on("Board Finance Figures", {
	add_lines(frm) {
		const add = () =>
			frappe.xcall("hrms_addon.hrms_addon.board_pack.add_finance_lines", { name: frm.doc.name }).then((added) => {
				frappe.show_alert({ message: __("{0} line(s) added", [added]), indicator: added ? "green" : "orange" });
				frm.reload_doc();
			});
		if (frm.is_new() || frm.is_dirty()) {
			frm.save().then(add);
		} else {
			add();
		}
	},
});
