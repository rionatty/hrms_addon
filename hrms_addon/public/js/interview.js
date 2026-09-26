// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Interview — "Submit Feedback" opens Luuka's Candidate Interview Evaluation /
// Score Form (LPL/HR/17), an Interview Feedback, instead of HRMS's star-rating
// dialog (hrms/hr/doctype/interview/interview.js show_feedback_dialog), which has
// no N/A, no criteria groups and only Cleared / Rejected.
//
// HRMS still decides who gets the button (the Interview's interviewers, until
// they have given feedback) and the button still triggers "submit_feedback";
// only what that event does changes. frappe.ui.form.off is Frappe's way to drop
// a form's standard handlers. Loaded through hooks.py doctype_js, after HRMS's
// own form script.
//
// The Candidate tab shows the panel what the candidate applied with and opens
// their CV (interview_access.py): a panel member has no access to the Job
// Applicant itself.

const HA_ACCESS_METHODS = "hrms_addon.hrms_addon.interview_access.";
const HA_INTERVIEW_METHODS = "hrms_addon.hrms_addon.interviews.";
// who sends invitations: interview_access_rules.HR_ROLES
const HA_HR_ROLES = ["HR User", "HR Manager", "System Manager"];

frappe.ui.form.off("Interview", "submit_feedback");

frappe.ui.form.on("Interview", {
	refresh(frm) {
		ha_candidate_pack(frm);
		ha_invitation_button(frm);
	},
	submit_feedback(frm) {
		// A new document's values are copied onto it as they are, with no
		// fetch, so pass what the sheet would otherwise fetch from the Interview.
		frappe.new_doc("Interview Feedback", {
			interview: frm.doc.name,
			interviewer: frappe.session.user,
			interview_type: frm.doc.interview_type,
			job_applicant: frm.doc.job_applicant,
		});
	},
});

// HR invites the candidate (again), by email and, where HR Settings says so, by SMS
function ha_invitation_button(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0 || frm.doc.status === "Cancelled" || !frappe.user.has_role(HA_HR_ROLES)) {
		return;
	}
	frm.add_custom_button(
		frm.doc.custom_invited_on ? __("Invite Again") : __("Send Invitation"),
		() =>
			frappe.xcall(HA_INTERVIEW_METHODS + "send_invitation", { interview: frm.doc.name }).then((sent) => {
				const to = (sent || []).map((where) => frappe.utils.escape_html(where)).join(", ");
				frappe.show_alert({ message: __("Invitation sent to {0}", [to]), indicator: "green" });
				frm.reload_doc();
			}),
		__("Actions")
	);
}

// what the candidate applied with, for the panel
function ha_candidate_pack(frm) {
	const field = frm.fields_dict.custom_candidate_html;
	if (!field) {
		return;
	}
	if (frm.is_new() || !frm.doc.job_applicant) {
		field.$wrapper.empty();
		return;
	}
	frappe
		.xcall(HA_ACCESS_METHODS + "get_candidate_pack", { interview: frm.doc.name })
		.then((pack) => field.$wrapper.html(ha_pack_html(frm, pack || {})));
}

function ha_pack_html(frm, pack) {
	const newline = String.fromCharCode(10);
	const esc = (text) => frappe.utils.escape_html(text || "");
	const lines = (text) => esc(text).split(newline).join("<br>");
	const block = (label, body) =>
		body ? `<div class="mb-4"><div class="text-muted small mb-1">${esc(label)}</div><div>${body}</div></div>` : "";

	let cv = "";
	if (pack.has_cv) {
		const url = "/api/method/" + HA_ACCESS_METHODS + "download_cv?interview=" + encodeURIComponent(frm.doc.name);
		cv = `<a class="btn btn-default btn-sm" href="${url}" target="_blank" rel="noopener">${__("Open CV")}</a>`;
	} else if (/^https?:/i.test(pack.cv_link || "")) {
		cv = `<a href="${esc(pack.cv_link)}" target="_blank" rel="noopener noreferrer">${esc(pack.cv_link)}</a>`;
	}
	const answers = (pack.answers || [])
		.map((row) => `<tr><td>${esc(row.question)}</td><td>${esc(row.answer)}</td></tr>`)
		.join("");

	const html = [
		block(__("CV"), cv),
		block(__("Applied For"), esc(pack.designation)),
		block(__("Education"), lines(pack.education)),
		block(__("Work Experience"), lines(pack.work_experience)),
		block(__("Certifications and Licences"), lines(pack.certifications)),
		block(__("Skills"), esc((pack.skills || []).join(", "))),
		block(__("Languages"), esc((pack.languages || []).join(", "))),
		block(
			__("Screening Answers"),
			answers ? `<table class="table table-bordered table-sm mb-0"><tbody>${answers}</tbody></table>` : ""
		),
		block(__("Cover Letter"), lines(pack.cover_letter)),
	].join("");
	return html || `<div class="text-muted">${__("Nothing on the application yet.")}</div>`;
}
