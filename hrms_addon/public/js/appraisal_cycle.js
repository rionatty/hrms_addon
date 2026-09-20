// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Appraisal Cycle: the flowchart's other branch, where the
// supervisor appraises away from the system. doctype_js, read from disk
// when the form loads, so a change to it needs no `bench build`.

frappe.ui.form.on("Appraisal Cycle", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Download Sheet"),
			() =>
				window.open(
					frappe.urllib.get_full_url(
						"/api/method/hrms_addon.hrms_addon.appraisals.download_sheet?appraisal_cycle=" +
							encodeURIComponent(frm.doc.name)
					)
				),
			__("Appraise Offline")
		);
		frm.add_custom_button(
			__("Upload Filled Sheet"),
			() => {
				new frappe.ui.FileUploader({
					restrictions: { allowed_file_types: [".xlsx"] },
					on_success: (file) =>
						frappe
							.xcall("hrms_addon.hrms_addon.appraisals.upload_sheet", {
								file_url: file.file_url,
								appraisal_cycle: frm.doc.name,
							})
							.then((updated) =>
								frappe.show_alert({
									message: __("{0} appraisal(s) updated from the sheet.", [updated]),
									indicator: "green",
								})
							),
				});
			},
			__("Appraise Offline")
		);
		if (frm.doc.custom_hard_deadline) {
			frm.set_intro(
				__("Appraisals are due by {0}.", [frappe.datetime.str_to_user(frm.doc.custom_hard_deadline)]),
				"blue"
			);
		}
	},
});
