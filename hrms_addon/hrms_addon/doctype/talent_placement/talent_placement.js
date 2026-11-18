// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The grid is the point of the form, so the form draws it: three by three,
// the employee's own cell lit, each cell named as HR keep the Nine Box
// records. Everything on it is read from the document; nothing here decides
// a band. Potential is rated on Potential Assessments, one a rater, and
// flight risk on Flight Risk Assessments, each kept as it was made.

const HRA_BOXES = [
	[3, 6, 9],
	[2, 5, 8],
	[1, 4, 7],
];
const HRA_BOX_COLOURS = {
	Red: "#c0392b",
	Orange: "#e08a3c",
	Yellow: "#d4a72c",
	Blue: "#2c6fbb",
	Green: "#2e8b57",
};

frappe.ui.form.on("Talent Placement", {
	refresh(frm) {
		frm.trigger("draw_grid");
		if (frm.doc.development_plan) {
			frm.add_custom_button(__("Development Plan"), () =>
				frappe.set_route("Form", "Talent Program", frm.doc.development_plan)
			);
		}
		if (frm.doc.appraisal) {
			frm.add_custom_button(__("Appraisal"), () =>
				frappe.set_route("Form", "Appraisal", frm.doc.appraisal)
			);
		}
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Assess Potential"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.potential.new_assessment", { placement: frm.doc.name })
					.then((name) => frappe.set_route("Form", "Potential Assessment", name)),
				__("Talent")
			);
		}
		frm.add_custom_button(__("Potential Assessments"), () =>
			frappe.set_route("List", "Potential Assessment", { placement: frm.doc.name }), __("Talent"));
		frm.add_custom_button(__("Assess Flight Risk"), () =>
			frappe.new_doc("Flight Risk Assessment", { employee: frm.doc.employee, placement: frm.doc.name }), __("Talent"));
		frm.add_custom_button(__("Flight Risk History"), () =>
			frappe.set_route("List", "Flight Risk Assessment", { employee: frm.doc.employee }), __("Talent"));
		frm.add_custom_button(__("Calibration Log"), () =>
			frappe.set_route("List", "Talent Calibration Log", { placement: frm.doc.name }), __("Talent"));
		if (frm.doc.raters_disagree) {
			frm.dashboard.add_comment(__("The raters are {0} apart on potential. Settle it in calibration.", [
				format_number(frm.doc.rater_spread || 0, null, 1)]), "orange", true);
		}
	},
	draw_grid(frm) {
		const wrapper = frm.get_field("box_section") && frm.fields_dict.box_section;
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		const colour = HRA_BOX_COLOURS[frm.doc.box_colour] || "#888";
		if (frm.doc.box) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill" style="background:${colour};color:#fff">${frm.doc.box}. ${frappe.utils.escape_html(
					frm.doc.box_name || ""
				)}</span> <span>${frappe.utils.escape_html(frm.doc.default_action || "")}</span>`
			);
		} else if (!frm.doc.performance_score) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill orange">${__(
					"No appraisal in this cycle yet, so there is no performance band to place against."
				)}</span>`
			);
		} else if (!frm.doc.raters) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill orange">${__("Potential is not rated yet. Assess Potential from the Talent menu.")}</span>`
			);
		}
		if (!wrapper || !wrapper.$wrapper || !frm.doc.box) return;
		frappe.db.get_list("Nine Box", { fields: ["box", "box_name", "colour"], limit: 9 }).then((boxes) => {
			const named = {};
			(boxes || []).forEach((row) => (named[row.box] = row));
			wrapper.$wrapper.find(".hra-nine-box").remove();
			const rows = HRA_BOXES.map((line) => `<tr>${line.map((box) => {
				const here = box === frm.doc.box;
				const fill = HRA_BOX_COLOURS[(named[box] || {}).colour] || "#888";
				return `<td style="border:1px solid var(--border-color);padding:8px;text-align:center;${
					here ? `background:${fill};color:#fff;font-weight:600` : "opacity:.55"
				}"><div style="font-size:11px">${box}</div><div>${frappe.utils.escape_html(__((named[box] || {}).box_name || ""))}</div></td>`;
			}).join("")}</tr>`).join("");
			wrapper.$wrapper.append(
				`<div class="hra-nine-box" style="margin:8px 0 12px">
					<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">${rows}</table>
					<div class="text-muted" style="font-size:11px;margin-top:4px">${__(
						"Potential rises up the page; performance rises to the right."
					)}</div>
				</div>`
			);
		});
	},
});
