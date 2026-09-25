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
				frm.add_custom_button(__("Sort by Match"), () => ha_sort_by_match(frm));
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

// Which applicants to bring in: by result, match, years and words in the
// bio-data or CV, the best first. The last filter is kept while the form is open.
function ha_get_applicants(frm) {
	const last = frm.ha_filters || { results: ["Meets", "Below Pass Mark", "Not Checked"] };
	const result = (value, label) => ({ label: label, value: value, checked: last.results.includes(value) ? 1 : 0 });
	const dialog = new frappe.ui.Dialog({
		title: __("Get Applicants"),
		fields: [
			{
				fieldname: "results",
				fieldtype: "MultiCheck",
				label: __("Result"),
				columns: 2,
				options: [
					result("Meets", __("Meets")),
					result("Below Pass Mark", __("Below Pass Mark")),
					result("Does Not Meet", __("Does Not Meet")),
					result("Not Checked", __("Not Checked")),
				],
			},
			{ fieldname: "min_score", fieldtype: "Percent", label: __("Match at Least"), default: last.min_score },
			{
				fieldname: "min_years",
				fieldtype: "Float",
				label: __("Years of Experience at Least"),
				default: last.min_years,
			},
			{ fieldname: "column_break_1", fieldtype: "Column Break" },
			{
				fieldname: "look_for",
				fieldtype: "Small Text",
				label: __("Look For"),
				description: __("Words or phrases in the bio-data or CV, one per line."),
				default: last.look_for,
			},
			{ fieldname: "match_all", fieldtype: "Check", label: __("All of Them"), default: last.match_all },
			{
				fieldname: "limit",
				fieldtype: "Int",
				label: __("At Most"),
				description: __("The best matches first. Empty for all."),
				default: last.limit,
			},
		],
		primary_action_label: __("Get Applicants"),
		primary_action(values) {
			frm.ha_filters = values;
			dialog.hide();
			ha_fetch_applicants(frm, values);
		},
	});
	dialog.show();
}

function ha_fetch_applicants(frm, filters) {
	const listed = (frm.doc.candidates || []).map((row) => row.job_applicant);
	frappe
		.xcall(HA_SHORTLIST_METHODS + "get_shortlist_candidates", {
			job_opening: frm.doc.job_opening,
			exclude: listed,
			filters: filters,
		})
		.then((found) => {
			const candidates = found.candidates || [];
			if (!candidates.length) {
				frappe.msgprint(
					found.left_out
						? __("No applicant passes the filter. {0} left out.", [found.left_out])
						: __("No other applicant for this opening can be shortlisted.")
				);
				return;
			}
			candidates.forEach((details) => ha_fill_row(frm.add_child("candidates"), details));
			frm.refresh_field("candidates");
			frappe.show_alert({
				message: found.left_out
					? __("{0} applicants added, {1} left out by the filter.", [candidates.length, found.left_out])
					: __("{0} applicants added. Remove the ones not invited, then save.", [candidates.length]),
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
	["job_applicant", "applicant_name", "phone_number", "email_id", "education", "work_experience", "certifications",
		"screening_result", "matched", "missing", "to_check", "flags"]
		.forEach((field) => (row[field] = details[field] || ""));
	["match_score", "experience_years"].forEach((field) => (row[field] = details[field] ?? null));
}

// Meets first, then Below Pass Mark, then Does Not Meet, then the ones
// nothing could be checked for; the highest match first within each.
function ha_sort_by_match(frm) {
	const order = { Meets: 0, "Below Pass Mark": 1, "Does Not Meet": 2 };
	const rank = (row) => (row.screening_result in order ? order[row.screening_result] : 3);
	frm.doc.candidates.sort(
		(a, b) => rank(a) - rank(b) || flt(b.match_score) - flt(a.match_score) || a.idx - b.idx
	);
	frm.doc.candidates.forEach((row, index) => (row.idx = index + 1));
	frm.refresh_field("candidates");
	frm.dirty();
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
