// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's stock Appraisal Template — a title, KRAs and rating criteria
// — is neither of Luuka's two appraisal forms. Their own sidebar lists it
// under Setup above ours, so it is the natural click; this says so on the
// form itself and offers the right one, rather than leaving someone to
// fill in a template nothing reads.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Appraisal Template", {
	refresh(frm) {
		frm.set_intro(
			__(
				"This is Frappe HR's own template. Luuka's appraisal templates are one per role and live in <b>Appraisal Template (LPL PMS)</b> — the balanced scorecard, with the four perspectives weighted to 80 and the competencies to 20. Neither of Luuka's forms reads this one."
			),
			"orange"
		);
		frm.add_custom_button(__("Open the LPL PMS Template"), () =>
			frappe.set_route("List", "BSC Appraisal Template")
		);
	},
});
