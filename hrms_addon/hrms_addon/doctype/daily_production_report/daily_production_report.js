// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The day's work, Per Meter or Per Piece (minutes 4.6, Luuka's PER METER
// sheet): each person's Work Done on each size. The Work Unit and the
// Total are worked out on save, from the size's Work Unit on the report's
// date, so nothing here prices anything; it keeps the choices to the
// section the report is for. Looms OT is typed in for the Per Meter section.

frappe.ui.form.on("Daily Production Report", {
	setup(frm) {
		frm.set_query("size", "lines", () => ({
			filters: { section: frm.doc.section, enabled: 1 },
		}));
		const people = () => {
			const filters = { status: "Active", custom_pay_category: frm.doc.section };
			if (frm.doc.branch) filters.branch = frm.doc.branch;
			return { filters: filters };
		};
		frm.set_query("employee", "lines", people);
		frm.set_query("employee", "looms_ot", people);
		frm.set_query("supervisor", () => ({ filters: { status: "Active" } }));
	},

	refresh(frm) {
		ha_size_label(frm);
	},

	section(frm) {
		ha_size_label(frm);
		if ((frm.doc.lines || []).length || (frm.doc.looms_ot || []).length) {
			frappe.show_alert({
				message: __("Check the lines: a size or a person from the other section will be refused."),
				indicator: "orange",
			});
		}
	},
});

// Per Piece prices by piece category, which is what the size column holds there
function ha_size_label(frm) {
	const grid = frm.fields_dict.lines && frm.fields_dict.lines.grid;
	if (!grid) return;
	grid.update_docfield_property("size", "label", frm.doc.section === "Per Piece" ? __("Piece Category") : __("Size"));
	grid.refresh();
}
