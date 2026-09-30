// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A size of material (Per Meter) or a piece category (Per Piece) and its
// Work Unit from each day it starts (output_pay.size_validate).

frappe.ui.form.on("Output Rate", {
	refresh(frm) {
		ha_output_rate_label(frm);
	},
	section(frm) {
		ha_output_rate_label(frm);
	},
});

function ha_output_rate_label(frm) {
	frm.set_df_property("size", "label", frm.doc.section === "Per Piece" ? __("Piece Category") : __("Size"));
}
