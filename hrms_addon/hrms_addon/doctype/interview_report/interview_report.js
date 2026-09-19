// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Interview Report — the panel's report on one day's interviews for a Job
// Opening, laid out like Luuka's interview report. Get Interview Results fills
// the panel and the candidates from that day's Interviews and score sheets
// (hrms_addon/hrms_addon/interviews.py); the approval runs through the HR
// Manager to the Executive Director (the Workflow's buttons). Approval closes
// the interviews and moves the applicants on; Create Job Offers then makes a
// draft offer for each candidate the panel offered the job.

frappe.ui.form.on("Interview Report", {
	setup(frm) {
		frm.set_query("job_opening", () => ({ filters: { status: ["!=", "Cancelled"] } }));
		frm.set_query("job_applicant", "candidates", () => ({
			filters: { job_title: frm.doc.job_opening || "" },
		}));
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
	},
});

function ha_create_job_offers(frm) {
	frappe.xcall("hrms_addon.hrms_addon.interviews.create_job_offers", { report: frm.doc.name }).then((result) => {
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

function ha_get_interview_results(frm) {
	const refill = () =>
		frappe
			.xcall("hrms_addon.hrms_addon.interviews.get_interview_results", {
				job_opening: frm.doc.job_opening,
				interview_date: frm.doc.interview_date,
			})
			.then((results) => {
				if (!results.candidates.length) {
					frappe.msgprint(__("No interviews for this opening on {0}.", [frappe.datetime.str_to_user(frm.doc.interview_date)]));
					return;
				}
				frm.clear_table("panel");
				results.panel.forEach((row) => frm.add_child("panel", row));
				frm.clear_table("candidates");
				results.candidates.forEach((row) => frm.add_child("candidates", row));
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
		frappe.confirm(__("Replace the panel and candidates with the day's results? Remarks typed here are lost."), refill);
	} else {
		refill();
	}
}
