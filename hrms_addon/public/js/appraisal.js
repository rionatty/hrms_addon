// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Appraisal, carrying both of Luuka's forms: the Supervisory
// Skills Evaluation Form (LPL/HR/18) and the balanced scorecard (LPL PMS).
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

const HA_BSC = "Balanced Scorecard";

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
			if (frm.doc.custom_form_type === HA_BSC) {
				frm.add_custom_button(__("Get Scorecard"), () =>
					frappe
						.xcall("hrms_addon.hrms_addon.bsc.get_scorecard", {
							appraisal: frm.doc.name,
							template: frm.doc.custom_bsc_template,
						})
						.then((added) => {
							frappe.show_alert({
								message: __("{0} row(s) brought in from the scorecard.", [added]),
								indicator: "green",
							});
							frm.reload_doc();
						})
				);
			}
		}
		frm.trigger("show_score");
	},
	show_score(frm) {
		frm.dashboard.clear_headline();
		const colours = {
			Excellent: "green",
			"Very Good": "green",
			Good: "blue",
			Fair: "orange",
			Average: "orange",
			Poor: "red",
			"Below Average": "red",
		};
		const bsc = frm.doc.custom_form_type === HA_BSC;
		const total = bsc ? frm.doc.custom_bsc_overall : frm.doc.custom_total_score;
		if (total === undefined || total === null) return;
		const band = bsc ? frm.doc.custom_bsc_band : frm.doc.custom_band;
		const number = (value) => frappe.format(value || 0, { fieldtype: "Float" });
		const parts = bsc
			? [
					__("Section A {0}/80", [number(frm.doc.custom_bsc_section_a_score)]),
					__("Section B {0}/20", [number(frm.doc.custom_bsc_section_b_score)]),
					__("{0} {1}%", [frm.doc.custom_period || __("Overall"), number(total)]),
			  ]
			: [
					__("Ratable Factors {0}/60", [number(frm.doc.custom_factors_score)]),
					__("Objectives {0}/40", [number(frm.doc.custom_objectives_score)]),
					__("Total {0}%", [number(total)]),
			  ];
		frm.dashboard.set_headline(
			`<span>${parts.map((p) => frappe.utils.escape_html(p)).join(" &nbsp;|&nbsp; ")}</span>` +
				(band
					? ` <span class="indicator-pill ${colours[band] || "gray"}">${frappe.utils.escape_html(
							__(band)
					  )}</span>`
					: "")
		);
	},
	custom_form_type(frm) {
		frm.trigger("show_score");
	},
	custom_period(frm) {
		frm.trigger("show_score");
	},
	employee(frm) {
		if (!frm.doc.employee || frm.doc.custom_supervisor) return;
		frappe.db.get_value("Employee", frm.doc.employee, "reports_to").then((r) => {
			if (r.message && r.message.reports_to) frm.set_value("custom_supervisor", r.message.reports_to);
		});
	},
});

for (const table of ["Appraisal Factor Rating", "Appraisal Objective Rating"]) {
	frappe.ui.form.on(table, {
		supervisor_rating(frm) {
			frm.trigger("show_score");
		},
	});
}

frappe.ui.form.on("BSC Appraisal Perspective", {
	q1_percent(frm) {
		frm.trigger("show_score");
	},
	q2_percent(frm) {
		frm.trigger("show_score");
	},
	q3_percent(frm) {
		frm.trigger("show_score");
	},
	annual_score(frm) {
		frm.trigger("show_score");
	},
});

frappe.ui.form.on("BSC Appraisal Competency", {
	score(frm) {
		frm.trigger("show_score");
	},
});
