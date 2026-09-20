// HRMS Addon — the training session (Frappe HR's Training Event) in Luuka's
// process: a draft while scheduled (the HOD confirms the participants, HR
// marks attendance on the day and attaches the signed sheet), submitted once
// the training was held, then the evaluations keyed in.
// See hrms_addon/hrms_addon/training.py.

frappe.ui.form.on("Training Event", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(
				__("Mark each participant Present or Absent, attach the signed attendance sheet, then Submit: the training was held.")
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Create Evaluations"),
				() =>
					frappe
						.xcall("hrms_addon.hrms_addon.training.create_evaluations", { training_event: frm.doc.name })
						.then((made) => {
							frappe.show_alert({
								message: made
									? __("{0} evaluation form(s) drafted: open each and key in the paper form.", [made])
									: __("Every participant marked Present already has an evaluation."),
								indicator: made ? "green" : "blue",
							});
							frm.reload_doc();
						}),
				__("Actions")
			);
			frm.add_custom_button(
				__("Evaluations"),
				() => frappe.set_route("List", "Training Feedback", { training_event: frm.doc.name }),
				__("View")
			);
		}
	},
});
