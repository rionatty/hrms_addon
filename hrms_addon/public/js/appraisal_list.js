// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Appraisal list: an employee on an improvement plan (Improvement Plan
// column) and a score below the pass mark (Final Score), in red (Luuka,
// 4 Oct 2026). doctype_list_js, read from disk when the list loads, so a
// change to it needs no `bench build`.

const HA_PASS_MARK = 60; // appraisal_rules.PIP_BELOW

frappe.listview_settings["Appraisal"] = Object.assign(frappe.listview_settings["Appraisal"] || {}, {
	add_fields: [
		...((frappe.listview_settings["Appraisal"] || {}).add_fields || []),
		"custom_on_pip",
		"custom_improvement_plan",
		"custom_band",
	],
	formatters: Object.assign((frappe.listview_settings["Appraisal"] || {}).formatters || {}, {
		custom_on_pip(value, df, doc) {
			if (!value) return "";
			return `<span class="indicator-pill red" title="${frappe.utils.escape_html(
				doc.custom_improvement_plan || __("On an improvement plan")
			)}">${__("PIP")}</span>`;
		},
		final_score(value, df, doc) {
			const shown = frappe.format(value, Object.assign({}, df, { formatter: null }));
			// a score not given is kept as 0: only a rated appraisal is below the mark
			return doc.custom_band && Number(value) < HA_PASS_MARK
				? `<span class="text-danger" style="font-weight:600">${shown}</span>`
				: shown;
		},
	}),
});
