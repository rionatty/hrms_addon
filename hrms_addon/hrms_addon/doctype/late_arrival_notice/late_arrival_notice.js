// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Late Arrival Notice", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (!frm.doc.notified_on) return;
		// the minutes' recommendation: notified before the shift starts, a full day
		frm.dashboard.set_headline(
			frm.doc.in_advance
				? `<span class="indicator-pill green">${__(
						"Notified in advance: once acknowledged, the day counts in full"
				  )}</span>`
				: `<span class="indicator-pill orange">${__(
						"Notified after the shift started: the day counts as punched"
				  )}</span>`
		);
	},
});
