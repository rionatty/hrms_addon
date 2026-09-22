// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The Daily Loom Production Report and the Per Piece Production File
// (minutes 4.6). The rate on each line is worked out on save from the
// machine's own rates, for the width or piece category, on the report's
// date — so nothing here prices anything; it only keeps the choices to
// the section the report is for.

frappe.ui.form.on("Daily Production Report", {
	setup(frm) {
		frm.set_query("machine", "lines", () => ({
			filters: { section: frm.doc.section, enabled: 1 },
		}));
		frm.set_query("employee", "lines", () => {
			const filters = { status: "Active", custom_pay_category: frm.doc.section };
			if (frm.doc.branch) filters.branch = frm.doc.branch;
			return { filters: filters };
		});
		frm.set_query("supervisor", () => ({ filters: { status: "Active" } }));
	},

	section(frm) {
		if ((frm.doc.lines || []).length) {
			frappe.show_alert({
				message: __("Check the lines: a machine or a person from the other section will be refused."),
				indicator: "orange",
			});
		}
	},
});
