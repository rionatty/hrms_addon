// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Appraisal Cycle: the flowchart's other branch, where the
// supervisor appraises away from the system on Luuka's own form, and the
// appraisals Frappe HR creates here sent on like the plan's. doctype_js,
// read from disk when the form loads, so a change to it needs no
// `bench build`.

frappe.ui.form.on("Appraisal Cycle", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Download Sheet"),
			() =>
				frappe.prompt(
					[
						{
							fieldname: "supervisor",
							fieldtype: "Link",
							options: "Employee",
							label: __("Supervisor"),
							description: __("Empty for every appraisal in the cycle."),
						},
					],
					(values) => {
						// asked first: a download that is refused opens as a bare
						// error page, so the reason is said here instead
						const args = { appraisal_cycle: frm.doc.name };
						if (values.supervisor) args.supervisor = values.supervisor;
						frappe
							.xcall("hrms_addon.hrms_addon.appraisals.sheet_count", args)
							.then((found) => {
								if (!found.count) {
									frappe.msgprint({
										title: __("Nothing to download"),
										indicator: "orange",
										message: frappe.utils.escape_html(found.reason || ""),
									});
									return;
								}
								window.open(
									frappe.urllib.get_full_url(
										"/api/method/hrms_addon.hrms_addon.appraisals.download_sheet?appraisal_cycle=" +
											encodeURIComponent(frm.doc.name) +
											(values.supervisor
												? "&supervisor=" + encodeURIComponent(values.supervisor)
												: "")
									)
								);
							});
					},
					__("Download the appraisal sheet"),
					__("Download")
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
							.then((found) => ha_cycle_sheet_summary(found)),
				});
			},
			__("Appraise Offline")
		);
		if (frappe.user.has_role(["HR User", "HR Manager"])) {
			frm.add_custom_button(__("Send Drafts On"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.appraisals.send_drafts", { appraisal_cycle: frm.doc.name })
					.then((sent) =>
						frappe.show_alert({
							message: __("{0} appraisal(s) sent on.", [sent]),
							indicator: "green",
						})
					)
			);
		}
		if (frm.doc.custom_hard_deadline) {
			frm.set_intro(
				__("Appraisals are due by {0}.", [frappe.datetime.str_to_user(frm.doc.custom_hard_deadline)]),
				"blue"
			);
		}
	},
});

// What an upload took and what it did not, and why
function ha_cycle_sheet_summary(found) {
	const esc = frappe.utils.escape_html;
	const list = (rows, text) =>
		rows.length ? "<ul>" + rows.map((row) => "<li>" + text(row) + "</li>").join("") + "</ul>" : "";
	const updated = found.updated || [];
	const skipped = found.skipped || [];
	const problems = found.problems || [];
	frappe.msgprint({
		title: __("Appraisal sheet"),
		indicator: skipped.length || problems.length ? "orange" : "green",
		message: [
			__("{0} appraisal(s) updated.", [updated.length]),
			list(updated, (row) => esc(row.employee_name || row.appraisal) + ": " + esc((row.fields || []).join(", "))),
			skipped.length ? __("Not taken:") : "",
			list(skipped, (row) => esc(row.sheet) + ": " + esc(row.reason)),
			problems.length ? __("Left as they were:") : "",
			list(problems, (row) => esc(row.sheet) + ": " + esc(row.problem)),
		]
			.filter(Boolean)
			.join(""),
	});
}
