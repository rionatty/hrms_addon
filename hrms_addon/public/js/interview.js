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

frappe.ui.form.off("Interview", "submit_feedback");

frappe.ui.form.on("Interview", {
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
