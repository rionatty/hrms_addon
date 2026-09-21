// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Succession Position", {
	refresh(frm) {
		frm.trigger("say_coverage");
		// test case 12: successors are nominated from the finalised talent
		// pool, so the picker offers finalised placements only
		frm.fields_dict.candidates.grid.get_field("placement").get_query = () => ({
			filters: { docstatus: 1, status: "Finalised" },
		});
		if (frm.doc.job_opening) {
			frm.add_custom_button(__("Job Opening"), () =>
				frappe.set_route("Form", "Job Opening", frm.doc.job_opening)
			);
		}
		if (frm.doc.docstatus === 0 && frm.doc.gap && !frm.doc.gap_confirmed) {
			frm.dashboard.add_comment(
				__(
					"There is nobody ready now. Confirming the gap raises a job opening in recruitment when this is submitted."
				),
				"orange",
				true
			);
		}
	},
	say_coverage(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.coverage) return;
		const colour =
			frm.doc.coverage === "Gap" ? "red" : frm.doc.coverage === "At Risk" ? "orange" : "green";
		frm.dashboard.set_headline(
			`<span class="indicator-pill ${colour}">${__(frm.doc.coverage)}</span>` +
				` <span>${__("Ready now")}: <b>${frm.doc.ready_now || 0}</b>,` +
				` ${__("in 1-2 years")}: <b>${frm.doc.ready_soon || 0}</b>,` +
				` ${__("emerging")}: <b>${frm.doc.emerging || 0}</b></span>`
		);
	},
});

frappe.ui.form.on("Succession Candidate", {
	placement(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.placement) return;
		frappe.db.get_value("Talent Placement", row.placement, ["employee", "box_name"]).then((result) => {
			const found = (result && result.message) || {};
			if (found.employee && !row.employee) {
				frappe.model.set_value(cdt, cdn, "employee", found.employee);
			}
			if (found.box_name) {
				frappe.model.set_value(cdt, cdn, "box_name", found.box_name);
			}
		});
	},
});
