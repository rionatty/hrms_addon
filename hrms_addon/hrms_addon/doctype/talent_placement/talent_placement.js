// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The grid is the point of the form, so the form draws it: three by three,
// the employee's own cell lit. Everything on it is read from the document —
// nothing here decides a band.

const HRA_BOXES = [
	[3, 6, 9],
	[2, 5, 8],
	[1, 4, 7],
];
const HRA_BOX_NAMES = {
	1: "Risk",
	2: "Inconsistent Player",
	3: "Potential Gem",
	4: "Average Performer",
	5: "Core Player",
	6: "High Potential",
	7: "Trusted Professional",
	8: "High Performer",
	9: "Star",
};
const HRA_BOX_COLOURS = {
	1: "#c0392b",
	2: "#e08a3c",
	3: "#d4a72c",
	4: "#e08a3c",
	5: "#d4a72c",
	6: "#2c6fbb",
	7: "#d4a72c",
	8: "#2c6fbb",
	9: "#2e8b57",
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
	},
	ability(frm) {
		frm.trigger("say_potential");
	},
	aspiration(frm) {
		frm.trigger("say_potential");
	},
	engagement(frm) {
		frm.trigger("say_potential");
	},
	// the three are each out of ten, so say so as they are typed rather
	// than at save
	say_potential(frm) {
		const over = ["ability", "aspiration", "engagement"].filter(
			(field) => frm.doc[field] && frm.doc[field] > 10
		);
		if (over.length) {
			frappe.show_alert({
				message: __("{0} is rated out of ten.", [over.join(", ")]),
				indicator: "red",
			});
		}
	},
	draw_grid(frm) {
		const wrapper = frm.get_field("box_section") && frm.fields_dict.box_section;
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		if (frm.doc.box) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill" style="background:${
					HRA_BOX_COLOURS[frm.doc.box] || "#888"
				};color:#fff">${frm.doc.box}. ${frappe.utils.escape_html(
					frm.doc.box_name || ""
				)}</span> <span>${frappe.utils.escape_html(frm.doc.default_action || "")}</span>`
			);
		} else if (!frm.doc.performance_score) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill orange">${__(
					"No appraisal in this cycle yet, so there is no performance band to place against."
				)}</span>`
			);
		}
		if (!wrapper || !wrapper.$wrapper) return;
		wrapper.$wrapper.find(".hra-nine-box").remove();
		if (!frm.doc.box) return;
		const rows = HRA_BOXES.map((line) => {
			const cells = line
				.map((box) => {
					const here = box === frm.doc.box;
					const colour = HRA_BOX_COLOURS[box] || "#888";
					return `<td style="border:1px solid var(--border-color);padding:8px;text-align:center;${
						here ? `background:${colour};color:#fff;font-weight:600` : "opacity:.55"
					}"><div style="font-size:11px">${box}</div><div>${__(
						HRA_BOX_NAMES[box]
					)}</div></td>`;
				})
				.join("");
			return `<tr>${cells}</tr>`;
		}).join("");
		wrapper.$wrapper.append(
			`<div class="hra-nine-box" style="margin:8px 0 12px">
				<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">${rows}</table>
				<div class="text-muted" style="font-size:11px;margin-top:4px">${__(
					"Potential rises up the page; performance rises to the right."
				)}</div>
			</div>`
		);
	},
});
