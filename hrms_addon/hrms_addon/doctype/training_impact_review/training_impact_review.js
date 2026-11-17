// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A training's effect on a KPI (learning_delivery.py).
frappe.ui.form.on("Training Impact Review", {
	from_shift_reports(frm) {
		const measure = () =>
			frappe
				.xcall("hrms_addon.hrms_addon.learning_delivery.impact_from_shift_reports", { name: frm.doc.name })
				.then(() => frm.reload_doc());
		if (frm.is_new() || frm.is_dirty()) {
			frm.save().then(measure);
		} else {
			measure();
		}
	},
});
