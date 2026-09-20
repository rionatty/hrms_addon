// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Performance Review", {
	refresh(frm) {
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
