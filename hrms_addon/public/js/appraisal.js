// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Appraisal, carrying Luuka's Supervisory Skills Evaluation
// Form (LPL/HR/18). doctype_js, read from disk when the form loads, so a
// change to it needs no `bench build`.

frappe.ui.form.on("Appraisal", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Download Sheet"), () =>
				window.open(
					frappe.urllib.get_full_url(
						"/api/method/hrms_addon.hrms_addon.appraisals.download_sheet?appraisal=" +
							encodeURIComponent(frm.doc.name)
					)
				)
			);
		}
		frm.trigger("show_score");
	},
	show_score(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.custom_total_score === undefined || frm.doc.custom_total_score === null) return;
		const colours = {
			Excellent: "green",
			"Very Good": "green",
			Good: "blue",
			Average: "orange",
			"Below Average": "red",
		};
		const parts = [
			__("Ratable Factors {0}/60", [frappe.format(frm.doc.custom_factors_score || 0, { fieldtype: "Float" })]),
			__("Objectives {0}/40", [frappe.format(frm.doc.custom_objectives_score || 0, { fieldtype: "Float" })]),
			__("Total {0}%", [frappe.format(frm.doc.custom_total_score || 0, { fieldtype: "Float" })]),
		];
		frm.dashboard.set_headline(
			`<span>${parts.map((p) => frappe.utils.escape_html(p)).join(" &nbsp;|&nbsp; ")}</span>` +
				(frm.doc.custom_band
					? ` <span class="indicator-pill ${colours[frm.doc.custom_band] || "gray"}">${frappe.utils.escape_html(
							__(frm.doc.custom_band)
					  )}</span>`
					: "")
		);
	},
	employee(frm) {
		if (!frm.doc.employee || frm.doc.custom_supervisor) return;
		frappe.db.get_value("Employee", frm.doc.employee, "reports_to").then((r) => {
			if (r.message && r.message.reports_to) frm.set_value("custom_supervisor", r.message.reports_to);
		});
	},
});

frappe.ui.form.on("Appraisal Factor Rating", {
	supervisor_rating(frm) {
		frm.trigger("show_score");
	},
});

frappe.ui.form.on("Appraisal Objective Rating", {
	supervisor_rating(frm) {
		frm.trigger("show_score");
	},
});
