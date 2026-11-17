// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A month's figures by plant for the HR board pack (board_pack.py): built from the site again on demand.
frappe.ui.form.on("HR Monthly Snapshot", {
	build(frm) {
		frappe
			.xcall("hrms_addon.hrms_addon.board_pack.rebuild_snapshot", { name: frm.doc.name })
			.then(() => frm.reload_doc());
	},
});
