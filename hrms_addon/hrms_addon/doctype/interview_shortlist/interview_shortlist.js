// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Interview Shortlist — the applicants for one Job Opening invited to
// interview, laid out like Luuka's shortlist sheet. The server writes each
// applicant out from their Bio-Data (hrms_addon/hrms_addon/interviews.py):
// education, work experience, and certifications and licences.
//
// HR screens it and shares it with the HOD, who does the second and final
// screening (the Workflow's buttons, interview_shortlist_approval.py). HR
// builds the list; while it is with the HOD they only remove candidates and
// add remarks, so Get Applicants is HR's alone, and each screener writes
// only their own remarks.

const HA_SHORTLIST_METHODS = "hrms_addon.hrms_addon.interviews.";
const HA_HR_STATES = ["Draft", "Returned to HR"];
const HA_HOD_STATE = "Pending HOD Screening";

frappe.ui.form.on("Interview Shortlist", {
	setup(frm) {
		frm.set_query("job_opening", () => ({ filters: { status: "Open" } }));
		frm.set_query("job_applicant", "candidates", () => ({
			filters: { job_title: frm.doc.job_opening || "" },
		}));
	},
	refresh(frm) {
		const with_hr = !frm.doc.workflow_state || HA_HR_STATES.includes(frm.doc.workflow_state);
		const with_hod = frm.doc.workflow_state === HA_HOD_STATE;
		frm.toggle_enable("hod_comments", with_hod);
		frm.fields_dict.candidates.grid.toggle_enable("hr_remarks", with_hr);
		frm.fields_dict.candidates.grid.toggle_enable("hod_remarks", with_hod);
		if (frm.doc.docstatus === 0 && frm.doc.job_opening && with_hr) {
			frm.add_custom_button(__("Get Applicants"), () => ha_get_applicants(frm));
			if ((frm.doc.candidates || []).length) {
				frm.add_custom_button(__("Refresh Details"), () => ha_refresh_details(frm));
			}
		}
		const unscheduled = (frm.doc.candidates || []).filter((row) => !row.interview);
		if (frm.doc.docstatus === 1 && unscheduled.length && frappe.model.can_create("Interview")) {
			frm.add_custom_button(__("Schedule Interviews"), () => ha_schedule_interviews(frm, unscheduled.length));
		}
	},
});

frappe.ui.form.on("Interview Shortlist Candidate", {
	job_applicant(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.job_applicant) {
			return;
		}
		frappe
			.xcall(HA_SHORTLIST_METHODS + "get_candidate_details", { job_applicants: [row.job_applicant] })
			.then((details) => ha_fill_row(row, details[row.job_applicant]))
			.then(() => frm.refresh_field("candidates"));
	},
});

function ha_get_applicants(frm) {
	const listed = (frm.doc.candidates || []).map((row) => row.job_applicant);
	frappe
		.xcall(HA_SHORTLIST_METHODS + "get_shortlist_candidates", {
			job_opening: frm.doc.job_opening,
			exclude: listed,
		})
		.then((candidates) => {
			if (!candidates.length) {
				frappe.msgprint(__("No other applicant for this opening can be shortlisted."));
				return;
			}
			candidates.forEach((details) => ha_fill_row(frm.add_child("candidates"), details));
			frm.refresh_field("candidates");
			frappe.show_alert({
				message: __("{0} applicants added. Remove the ones not invited, then save.", [candidates.length]),
				indicator: "green",
			});
		});
}

function ha_refresh_details(frm) {
	const applicants = (frm.doc.candidates || []).map((row) => row.job_applicant).filter(Boolean);
	frappe
		.xcall(HA_SHORTLIST_METHODS + "get_candidate_details", { job_applicants: applicants })
		.then((details) => {
			(frm.doc.candidates || []).forEach((row) => ha_fill_row(row, details[row.job_applicant]));
			frm.refresh_field("candidates");
			frm.dirty();
		});
}

function ha_fill_row(row, details) {
	if (!details) {
		return;
	}
	["job_applicant", "applicant_name", "phone_number", "email_id", "education", "work_experience", "certifications"]
		.forEach((field) => (row[field] = details[field] || ""));
}

function ha_schedule_interviews(frm, count) {
	const dialog = new frappe.ui.Dialog({
		title: __("Schedule {0} Interviews", [count]),
		fields: [
			{
				fieldname: "interview_type",
				fieldtype: "Link",
				options: "Interview Type",
				label: __("Interview Type"),
				reqd: 1,
				description: __("Its Interviewers are the panel for every interview."),
			},
			{ fieldname: "scheduled_on", fieldtype: "Date", label: __("Date"), reqd: 1 },
			{ fieldname: "column_break_1", fieldtype: "Column Break" },
			{ fieldname: "from_time", fieldtype: "Time", label: __("First Interview At"), reqd: 1 },
			{
				fieldname: "minutes",
				fieldtype: "Int",
				label: __("Minutes Each"),
				reqd: 1,
				default: 30,
				description: __("Back to back, in the shortlist's order."),
			},
		],
		primary_action_label: __("Schedule"),
		primary_action(values) {
			frappe
				.xcall(HA_SHORTLIST_METHODS + "schedule_interviews", {
					shortlist: frm.doc.name,
					interview_type: values.interview_type,
					scheduled_on: values.scheduled_on,
					from_time: values.from_time,
					minutes: values.minutes,
				})
				.then((result) => {
					dialog.hide();
					const lines = [__("{0} interviews scheduled.", [result.booked.length])];
					if (result.refused.length) {
						lines.push(__("Not scheduled:"), ...result.refused.map((reason) => frappe.utils.escape_html(reason)));
					}
					frappe.msgprint(lines.join("<br>"), __("Interviews"));
					frm.reload_doc();
				});
		},
	});
	dialog.show();
}
