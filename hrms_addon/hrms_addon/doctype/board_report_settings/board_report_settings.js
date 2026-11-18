// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// How the HR board pack counts, and the months before it built from the site (board_pack.py, board_facts.py).
frappe.ui.form.on("Board Report Settings", {
	build_months(frm) {
		const build = () =>
			frappe.xcall("hrms_addon.hrms_addon.board_pack.build_from_settings").then((queued) => {
				frappe.show_alert({ message: __("{0} month(s) queued", [queued]), indicator: queued ? "green" : "orange" });
			});
		if (frm.is_dirty()) {
			frm.save().then(build);
		} else {
			build();
		}
	},
});
