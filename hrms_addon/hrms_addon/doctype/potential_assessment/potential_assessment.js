// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// One rater's view of a placement's potential: every criterion 1 to 5, the
// evidence L&D and the appraisal hold read in, and the score it suggests
// kept beside the rater's own (potential.py).

frappe.ui.form.on("Potential Assessment", {
	refresh(frm) {
		if (frm.doc.placement) {
			frm.add_custom_button(__("Placement"), () => frappe.set_route("Form", "Talent Placement", frm.doc.placement));
		}
	},
	read_evidence(frm) {
		if (!frm.doc.placement) {
			frappe.msgprint(__("Pick the placement first."));
			return;
		}
		frappe.xcall("hrms_addon.hrms_addon.potential.read_evidence", { placement: frm.doc.placement }).then((rows) => {
			const kept = {};
			(frm.doc.ratings || []).forEach((row) => (kept[row.criterion] = row));
			(rows || []).forEach((found) => {
				const row = kept[found.criterion] || frm.add_child("ratings", { criterion: found.criterion });
				row.evidence = found.evidence || row.evidence;
				row.suggested_score = found.suggested_score;
				if (!row.score && found.suggested_score) {
					row.score = found.suggested_score;
					row.source = found.source;
				}
			});
			frm.refresh_field("ratings");
			frm.dirty();
		});
	},
});
