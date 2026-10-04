// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// below the pass mark the recommendation is an improvement plan
// (appraisal_rules.PIP_BELOW)
const HA_REVIEW_PASS_MARK = 60;

// employees on an improvement plan, and scores below the pass mark, red
// (hrms_addon_pip.js)
function ha_review_marks(frm) {
	const grid = frm.fields_dict.employees && frm.fields_dict.employees.grid;
	if (!grid) return;
	// a score not given is kept as 0: only a rated appraisal (its band) is below the mark
	grid.update_docfield_property("total_score", "formatter", (value, df, options, row) =>
		hrms_addon.pip.score_html(
			hrms_addon.pip.plain(value, df, options, row),
			!!(row && row.band) && Number(value) < HA_REVIEW_PASS_MARK
		)
	);
	hrms_addon.pip.mark_rows(frm, "employees");
}

frappe.ui.form.on("Performance Review", {
	refresh(frm) {
		ha_review_marks(frm);
		if (frm.doc.docstatus === 0 && frm.doc.appraisal_cycle) {
			frm.add_custom_button(__("Get Appraisals"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.appraisals.get_appraisals", {
						appraisal_cycle: frm.doc.appraisal_cycle,
					})
					.then((rows) => {
						if (!rows.length) {
							frappe.show_alert({
								message: __("No appraisals on that cycle yet."),
								indicator: "blue",
							});
							return;
						}
						const have = new Set((frm.doc.employees || []).map((r) => r.appraisal));
						for (const row of rows) {
							if (have.has(row.appraisal)) continue;
							frm.add_child("employees", row);
						}
						frm.refresh_field("employees");
						ha_review_marks(frm);
					})
			);
			frm.add_custom_button(__("Share with Management"), () =>
				frappe.prompt(
					{
						fieldname: "shared_with",
						fieldtype: "Small Text",
						label: __("Top management team"),
						reqd: 1,
						default: frm.doc.shared_with,
						description: __("Their user names or email addresses, separated by commas."),
					},
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.appraisals.share_with_management", {
								name: frm.doc.name,
								shared_with: values.shared_with,
							})
							.then(() => frm.reload_doc()),
					__("Share the appraisal report"),
					__("Share")
				)
			);
		}
		if (frm.doc.status === "Decided") {
			frm.set_intro(__("Decided. Promotions and salary increases are raised as Position Changes; anyone below the pass mark has an Improvement Plan."), "green");
		} else if (frm.doc.status === "Shared") {
			frm.set_intro(__("Shared with management. Record a decision against every employee, then submit."), "blue");
		}
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.review_date) {
			frm.set_value("review_date", frappe.datetime.get_today());
		}
	},
});
