// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// below the pass mark the recommendation is an improvement plan
// (appraisal_rules.PIP_BELOW)
const HA_REVIEW_PASS_MARK = 60;
const HA_REVIEW = "hrms_addon.hrms_addon.appraisals.";

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

// the quarter's completed appraisals on no review yet, of the review's
// plant, each decided as its score suggests (appraisals.get_appraisals)
function ha_review_get(frm) {
	const args = { appraisal_cycle: frm.doc.appraisal_cycle };
	if (frm.doc.branch) args.branch = frm.doc.branch;
	frappe.xcall(HA_REVIEW + "get_appraisals", args).then((rows) => {
		const have = new Set((frm.doc.employees || []).map((r) => r.appraisal));
		const fresh = rows.filter((row) => !have.has(row.appraisal));
		if (!fresh.length) {
			frappe.show_alert({ message: __("No completed appraisals left to add."), indicator: "blue" });
			return;
		}
		for (const row of fresh) frm.add_child("employees", row);
		frm.refresh_field("employees");
		ha_review_marks(frm);
	});
}

// a copy for anyone else in management to read
function ha_review_share(frm) {
	frappe.prompt(
		{
			fieldname: "shared_with",
			fieldtype: "Small Text",
			label: __("Users"),
			reqd: 1,
			description: __("User names or email addresses, separated by commas."),
		},
		(values) =>
			frappe
				.xcall(HA_REVIEW + "share_with_management", { name: frm.doc.name, shared_with: values.shared_with })
				.then(() => frm.reload_doc()),
		__("Share a Copy"),
		__("Share")
	);
}

frappe.ui.form.on("Performance Review", {
	refresh(frm) {
		ha_review_marks(frm);
		const preparing = frm.doc.docstatus === 0 && (frm.doc.workflow_state || "Draft") === "Draft";
		if (preparing && frm.doc.appraisal_cycle && frappe.user.has_role(["HR User", "HR Manager"])) {
			frm.add_custom_button(__("Get Appraisals"), () => ha_review_get(frm));
		}
		if (!frm.is_new() && frm.doc.docstatus < 2 && frm.perm[0] && frm.perm[0].share) {
			frm.add_custom_button(__("Share a Copy"), () => ha_review_share(frm));
		}
		if (preparing && frm.doc.return_remarks) {
			frm.set_intro(__("Returned: {0}", [frappe.utils.escape_html(frm.doc.return_remarks)]), "orange");
		} else if (frm.doc.docstatus === 1) {
			frm.set_intro(
				__("Approved. Promotions and salary increases are raised as Position Changes; anyone on a PIP has an Improvement Plan."),
				"green"
			);
		}
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.review_date) {
			frm.set_value("review_date", frappe.datetime.get_today());
		}
	},
});
