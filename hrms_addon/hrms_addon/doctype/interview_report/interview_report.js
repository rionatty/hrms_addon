// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Interview Report — the panel's report on a Job Opening's interviews, a day
// or a range of days, one round or all, laid out like Luuka's interview
// report. Get Interview Results fills the panel and the candidates from those
// Interviews and score sheets (hrms_addon/hrms_addon/interviews.py); while HR
// has it, each save reads the panel's figures again. The approval runs through
// the HR Manager to the Executive Director (the Workflow's buttons). Approval
// closes the interviews and moves the applicants on; Create Job Offers then
// makes a draft offer for each candidate offered the job, and Offer a Reserve
// one for a candidate kept in reserve once a position is open.

const HA_REPORT_METHODS = "hrms_addon.hrms_addon.interviews.";

frappe.ui.form.on("Interview Report", {
	setup(frm) {
		frm.set_query("job_opening", () => ({ filters: { status: ["!=", "Cancelled"] } }));
		frm.set_query("job_applicant", "candidates", () => ({
			filters: { job_title: frm.doc.job_opening || "" },
		}));
		// the rounds of this opening's job
		frm.set_query("interview_type", () => ({ filters: { designation: frm.doc.designation || "" } }));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.prepared_by) {
			frappe
				.xcall("hrms_addon.hrms_addon.job_requisition.get_session_employee")
				.then((employee) => employee && frm.set_value("prepared_by", employee));
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.job_opening && frm.doc.interview_date && frm.doc.status !== "Pending Executive Director") {
			frm.add_custom_button(__("Get Interview Results"), () => ha_get_interview_results(frm));
		}
		const unoffered = (frm.doc.candidates || []).filter((row) => row.decision === "Offer" && !row.job_offer);
		if (frm.doc.docstatus === 1 && unoffered.length && frappe.model.can_create("Job Offer")) {
			frm.add_custom_button(__("Create Job Offers"), () => ha_create_job_offers(frm));
		}
		const reserve = (frm.doc.candidates || []).filter((row) => row.decision === "Reserve" && !row.job_offer);
		if (frm.doc.docstatus === 1 && reserve.length && frappe.model.can_create("Job Offer")) {
			frm.add_custom_button(__("Offer a Reserve"), () => ha_offer_reserve(frm, reserve));
		}
	},
});

function ha_create_job_offers(frm) {
	frappe.xcall(HA_REPORT_METHODS + "create_job_offers", { report: frm.doc.name }).then((result) => {
		const lines = [];
		if (result.created.length) {
			lines.push(__("Draft Job Offers made: {0}. Open each one to add the terms, then send it.", [result.created.length]));
		}
		if (result.linked.length) {
			lines.push(__("Candidates who already had a Job Offer, now linked to it: {0}.", [result.linked.length]));
		}
		if (result.refused.length) {
			lines.push(__("Not made:"), ...result.refused.map((reason) => frappe.utils.escape_html(reason)));
		}
		if (!lines.length) {
			lines.push(__("Every candidate offered the job already has a Job Offer."));
		}
		frappe.msgprint(lines.join("<br>"), __("Job Offers"));
		frm.reload_doc();
	});
}

// a candidate kept in reserve, offered the job once a position is open
function ha_offer_reserve(frm, reserve) {
	const dialog = new frappe.ui.Dialog({
		title: __("Offer a Reserve"),
		fields: [
			{
				fieldname: "applicant",
				fieldtype: "Select",
				label: __("Candidate"),
				reqd: 1,
				options: reserve.map((row) => ({ label: row.applicant_name || row.job_applicant, value: row.job_applicant })),
			},
		],
		primary_action_label: __("Make the Job Offer"),
		primary_action(values) {
			frappe
				.xcall(HA_REPORT_METHODS + "offer_reserve", { report: frm.doc.name, applicant: values.applicant })
				.then((offer) => {
					dialog.hide();
					frappe.show_alert({ message: __("Draft Job Offer {0} made.", [frappe.utils.escape_html(offer)]), indicator: "green" });
					frm.reload_doc();
				});
		},
	});
	dialog.show();
}

function ha_get_interview_results(frm) {
	const refill = () =>
		frappe
			.xcall(HA_REPORT_METHODS + "get_interview_results", {
				job_opening: frm.doc.job_opening,
				interview_date: frm.doc.interview_date,
				to_date: frm.doc.to_date || null,
				interview_type: frm.doc.interview_type || null,
			})
			.then((results) => {
				if (!results.candidates.length && !results.absentees) {
					frappe.msgprint(__("No interviews for this opening from {0}.", [frappe.datetime.str_to_user(frm.doc.interview_date)]));
					return;
				}
				frm.clear_table("panel");
				results.panel.forEach((row) => frm.add_child("panel", row));
				frm.clear_table("candidates");
				results.candidates.forEach((row) => frm.add_child("candidates", row));
				frm.set_value("absentees", results.absentees || "");
				frm.refresh_fields();
				frappe.show_alert({
					message: __("{0} candidates and {1} panel members filled in. Add the remarks and recommendations.", [
						results.candidates.length,
						results.panel.length,
					]),
					indicator: "green",
				});
			});
	// Remarks and decisions are HR's writing: ask before replacing them
	if ((frm.doc.candidates || []).length) {
		frappe.confirm(__("Replace the panel and candidates with the results? Remarks typed here are lost."), refill);
	} else {
		refill();
	}
}
