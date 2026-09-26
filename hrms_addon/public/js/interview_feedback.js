// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Interview Feedback — the Candidate Interview Evaluation / Score Form
// (LPL/HR/17). Loaded through hooks.py doctype_js, after HRMS's own script.
//
// A new sheet starts with the round's own criteria and their weights, or,
// for a round with no list, every criterion that is not disabled, in order
// (Interview Criterion). The panel member scores each 1 to 5 (N/A only on the
// general list), and the running total, percentage and rating show under the
// grid as they go. The server works the same totals out again on save
// (hrms_addon/hrms_addon/interviews.py), so these are only for the eye.
// HA_SCORE_BANDS must match interview_rules.BANDS; scripts/verify_interviews.py
// checks that they do.

const HA_SCORE_TABLE = "custom_scores";
// the interview's questions, each with what to look for, the candidate's
// answer and its score
const HA_ANSWER_TABLE = "custom_answers";
const HA_SCORE_BANDS = [
	[90, "Excellent"],
	[70, "Very Good"],
	[50, "Good"],
	[30, "Average"],
	[0, "Below Average"],
];
const HA_RESULTS = { Offer: "Cleared", Shortlist: "Cleared", Reject: "Rejected" };
// a round's own list has already said what applies: no N/A there
const HA_ROUND_SCALE = ["", "1", "2", "3", "4", "5"];

frappe.ui.form.on("Interview Feedback", {
	refresh(frm) {
		// the criteria come from the round or the Interview Criterion list, not from here
		frm.set_df_property(HA_SCORE_TABLE, "cannot_add_rows", true);
		frm.set_df_property(HA_SCORE_TABLE, "cannot_delete_rows", true);
		if (frm.is_new() && !(frm.doc[HA_SCORE_TABLE] || []).length) {
			frappe
				.xcall("hrms_addon.hrms_addon.interviews.get_score_criteria", { interview: frm.doc.interview || null })
				.then((start) => {
					(start.rows || []).forEach((row) => frm.add_child(HA_SCORE_TABLE, row));
					frm.doc.custom_round_criteria = start.round_criteria ? 1 : 0;
					frm.refresh_field(HA_SCORE_TABLE);
					ha_score_options(frm);
					ha_show_score_total(frm);
				});
		}
		// the questions come from the interview, not from here
		frm.set_df_property(HA_ANSWER_TABLE, "cannot_add_rows", true);
		frm.set_df_property(HA_ANSWER_TABLE, "cannot_delete_rows", true);
		if (frm.is_new() && frm.doc.interview && !(frm.doc[HA_ANSWER_TABLE] || []).length) {
			frappe
				.xcall("hrms_addon.hrms_addon.interviews.get_interview_questions", { interview: frm.doc.interview })
				.then((rows) => {
					(rows || []).forEach((row) => frm.add_child(HA_ANSWER_TABLE, row));
					frm.refresh_field(HA_ANSWER_TABLE);
				});
		}
		ha_score_options(frm);
		ha_show_score_total(frm);
	},
	custom_recommendation(frm) {
		frm.set_value("result", HA_RESULTS[frm.doc.custom_recommendation] || "");
	},
});

frappe.ui.form.on("Interview Feedback Score", {
	score(frm) {
		ha_show_score_total(frm);
	},
});

function ha_score_options(frm) {
	const field = frm.fields_dict[HA_SCORE_TABLE];
	if (field && field.grid && frm.doc.custom_round_criteria) {
		field.grid.update_docfield_property("score", "options", HA_ROUND_SCALE.join(String.fromCharCode(10)));
	}
}

function ha_show_score_total(frm) {
	const field = frm.fields_dict[HA_SCORE_TABLE];
	if (!field || !field.grid) {
		return;
	}
	let total = 0;
	let maximum = 0;
	let blank = 0;
	(frm.doc[HA_SCORE_TABLE] || []).forEach((row) => {
		const score = cint(row.score);
		const weight = Math.min(Math.max(cint(row.weight) || 1, 1), 5);
		if (score >= 1 && score <= 5) {
			total += score * weight;
			maximum += 5 * weight;
		} else if (row.score !== "N/A") {
			blank += 1;
		}
	});

	let html = "";
	if (maximum) {
		const percent = Math.round((total * 10000) / maximum) / 100;
		// whole numbers, like interview_rules.band_for: 27 of 30 is exactly 90%
		const band = HA_SCORE_BANDS.find(([floor]) => total * 100 >= floor * maximum)[1];
		html =
			`${__("Total")} <b>${total}</b> ${__("of")} ${maximum} &nbsp;·&nbsp; <b>${percent}%</b>` +
			` &nbsp;·&nbsp; ${__(band)}` +
			(blank
				? ` &nbsp;·&nbsp; <span style="color: var(--red-600, #dc3545)">${__("{0} not scored yet", [blank])}</span>`
				: "");
	}
	// kept on the df too, so Frappe's own grid refresh shows the same text
	field.grid.df.description = html;
	$(field.grid.parent).find(".grid-description").html(html).toggle(Boolean(html));
}
