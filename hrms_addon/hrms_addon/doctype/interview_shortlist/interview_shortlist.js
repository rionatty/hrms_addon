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
//
// Remove by Result takes off, in one go, the applicants of a result or below
// a match (interviews.pick_removals). Where HR Settings says so, the names,
// phones and emails stay hidden while HR screens (interviews.hide_names).

const HA_SHORTLIST_METHODS = "hrms_addon.hrms_addon.interviews.";
const HA_HR_STATES = ["Draft", "Returned to HR"];
const HA_HOD_STATE = "Pending HOD Screening";
// who books interviews: interview_access_rules.HR_ROLES
const HA_BOOKERS = ["HR User", "HR Manager", "System Manager"];
// what a blind first screening hides
const HA_NAME_FIELDS = ["applicant_name", "phone_number", "email_id"];

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
		ha_hide_names(frm, !!(frm.doc.__onload && frm.doc.__onload.hide_names) && with_hr && frm.doc.docstatus === 0);
		if (frm.doc.docstatus === 0 && frm.doc.job_opening && with_hr) {
			frm.add_custom_button(__("Get Applicants"), () => ha_get_applicants(frm));
			if ((frm.doc.candidates || []).length) {
				frm.add_custom_button(__("Refresh Details"), () => ha_refresh_details(frm));
				frm.add_custom_button(__("Sort by Match"), () => ha_sort_by_match(frm));
				frm.add_custom_button(__("Remove by Result"), () => ha_remove_by_result(frm));
			}
		}
		// a round at a time, for the candidates ticked (a batch) or everyone; HR
		// books, a panel member only reads (interview_access.py). The button is
		// on every shortlist with candidates, so HR finds it where they review;
		// the interviews are booked once the HOD has screened it.
		if (!frm.is_new() && frm.doc.docstatus !== 2 && (frm.doc.candidates || []).length
			&& frappe.model.can_create("Interview") && frappe.user.has_role(HA_BOOKERS)) {
			frm.add_custom_button(__("Schedule Interviews"), () =>
				frm.doc.docstatus === 1
					? ha_schedule_interviews(frm)
					: frappe.msgprint({
							title: __("Schedule Interviews"),
							indicator: "blue",
							message: __("Interviews are scheduled once the Head of Department has screened the shortlist and it is submitted."),
					  })
			);
		}
		ha_cv_links(frm);
	},
});

// Each candidate's CV, opened from the shortlist (interviews.shortlist_cv):
// HR may open it before the list is saved; a Head of Department screening
// it, who cannot open Job Applicant where the private file is attached, once
// it is saved. The link keeps the click to itself, or the grid takes it to
// edit the row and the link is never followed. A PDF opens in the browser;
// a Word file downloads, as a browser cannot show one.
function ha_cv_links(frm) {
	const grid = frm.fields_dict.candidates && frm.fields_dict.candidates.grid;
	if (!grid) return;
	const formatter = (value, field, options, row) => {
		if (!value || !row || !row.job_applicant) return "";
		const url =
			"/api/method/" + HA_SHORTLIST_METHODS + "shortlist_cv?shortlist=" + encodeURIComponent(frm.doc.name) +
			"&job_applicant=" + encodeURIComponent(row.job_applicant);
		const file = String(value).split("/").pop();
		const label = file.toLowerCase().endsWith(".pdf") ? __("View CV") : __("Download CV");
		return `<a href="${url}" target="_blank" rel="noopener" onclick="event.stopPropagation()" title="${frappe.utils.escape_html(
			file
		)}">${label}</a>`;
	};
	// rows drawn later take it from the grid's fields, those drawn already here
	const df = (grid.docfields || []).find((d) => d.fieldname === "cv");
	if (df) df.formatter = formatter;
	grid.update_docfield_property("cv", "formatter", formatter);
}

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
	["application_id", "job_applicant", "applicant_name", "phone_number", "email_id", "cv", "education", "work_experience",
		"certifications", "screening_result", "matched", "missing", "to_check", "flags"]
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

// The applicants of the results ticked, or below the match given, off the
// list in one go; HR saves to keep the change
function ha_remove_by_result(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Remove by Result"),
		fields: [
			{
				fieldname: "results",
				fieldtype: "MultiCheck",
				label: __("Result"),
				columns: 2,
				options: [
					{ label: __("Does Not Meet"), value: "Does Not Meet", checked: 1 },
					{ label: __("Below Pass Mark"), value: "Below Pass Mark", checked: 0 },
					{ label: __("Not Checked"), value: "Not Checked", checked: 0 },
				],
			},
			{
				fieldname: "below",
				fieldtype: "Percent",
				label: __("Match Below"),
				description: __("Empty to go by the result alone."),
			},
		],
		primary_action_label: __("Remove"),
		primary_action(values) {
			const rows = (frm.doc.candidates || []).map((row) => ({
				job_applicant: row.job_applicant,
				screening_result: row.screening_result,
				match_score: row.match_score,
			}));
			const args = { rows: rows, results: values.results || [] };
			// left out when empty: sent as null it arrives as "", which a typed
			// parameter refuses with nothing shown
			if (values.below !== undefined && values.below !== null && values.below !== "") {
				args.below = values.below;
			}
			frappe
				.xcall(HA_SHORTLIST_METHODS + "pick_removals", args)
				.then((names) => {
					if (!names.length) {
						frappe.msgprint(__("No applicant on the list matches."));
						return;
					}
					frappe.confirm(__("Remove {0} applicants from the list?", [names.length]), () => {
						const gone = new Set(names);
						(frm.doc.candidates || [])
							.filter((row) => gone.has(row.job_applicant))
							.forEach((row) => frappe.model.clear_doc(row.doctype, row.name));
						frm.refresh_field("candidates");
						frm.dirty();
						dialog.hide();
						frappe.show_alert({
							message: __("{0} removed. Save to keep the change.", [names.length]),
							indicator: "green",
						});
					});
				});
		},
	});
	dialog.show();
}

// A blind first screening: the names, phones and emails hidden on the list
// and in each row while HR screens (HR Settings, Hide Names While HR Screens)
function ha_hide_names(frm, hide) {
	const grid = frm.fields_dict.candidates.grid;
	let changed = false;
	HA_NAME_FIELDS.forEach((field) => {
		const df = frappe.meta.get_docfield("Interview Shortlist Candidate", field, frm.doc.name);
		if (df && !!df.hidden !== hide) {
			df.hidden = hide ? 1 : 0;
			changed = true;
		}
	});
	if (changed) {
		grid.reset_grid();
	}
}

function ha_schedule_interviews(frm) {
	const ticked = frm.fields_dict.candidates.grid.get_selected_children().map((row) => row.job_applicant);
	const dialog = new frappe.ui.Dialog({
		title: ticked.length ? __("Schedule Interviews for {0} Ticked", [ticked.length]) : __("Schedule Interviews"),
		fields: [
			{
				fieldname: "interview_type",
				fieldtype: "Link",
				options: "Interview Type",
				label: __("Interview Type"),
				reqd: 1,
				description: __("The round. Its interviewers are the panel; its questions come with it."),
				get_query: () => ({ filters: { designation: frm.doc.designation } }),
				onchange() {
					const type = dialog.get_value("interview_type");
					if (type) {
						frappe.db.get_value("Interview Type", type, "custom_venue").then((r) => {
							if (r.message && r.message.custom_venue && !dialog.get_value("venue")) {
								dialog.set_value("venue", r.message.custom_venue);
							}
						});
					}
				},
			},
			{ fieldname: "scheduled_on", fieldtype: "Date", label: __("Date"), reqd: 1, default: frappe.datetime.get_today() },
			{ fieldname: "from_time", fieldtype: "Time", label: __("First Interview At"), reqd: 1, default: "09:00:00" },
			{ fieldname: "minutes", fieldtype: "Int", label: __("Minutes Each"), reqd: 1, default: 30 },
			{
				fieldname: "gap",
				fieldtype: "Int",
				label: __("Minutes Between"),
				description: __("Empty for HR Settings."),
			},
			{ fieldname: "column_break_1", fieldtype: "Column Break" },
			{
				fieldname: "mode",
				fieldtype: "Select",
				label: __("Mode"),
				options: ["In Person", "Video Call", "Phone Call"],
				default: "In Person",
			},
			{ fieldname: "venue", fieldtype: "Data", label: __("Venue"), depends_on: "eval:doc.mode=='In Person'" },
			{
				fieldname: "meeting_link",
				fieldtype: "Data",
				options: "URL",
				label: __("Meeting Link"),
				depends_on: "eval:doc.mode=='Video Call'",
			},
			{ fieldname: "send_invitations", fieldtype: "Check", label: __("Send Invitations"), default: 1 },
		],
		primary_action_label: __("Schedule"),
		primary_action(values) {
			const args = {
				shortlist: frm.doc.name,
				interview_type: values.interview_type,
				scheduled_on: values.scheduled_on,
				from_time: values.from_time,
				minutes: values.minutes,
				mode: values.mode,
				send_invitations: values.send_invitations ? 1 : 0,
			};
			// what is empty is left out: sent as null it arrives as "", which a
			// typed parameter refuses with nothing shown (the method's defaults
			// stand instead: everyone listed, HR Settings' gap, the type's venue)
			if (ticked.length) {
				args.applicants = ticked;
			}
			["gap", "venue", "meeting_link"].forEach((key) => {
				if (values[key] !== undefined && values[key] !== null && values[key] !== "") {
					args[key] = values[key];
				}
			});
			frappe
				.xcall(HA_SHORTLIST_METHODS + "schedule_interviews", args, "POST", {
					freeze: true,
					freeze_message: __("Scheduling interviews"),
				})
				.then((result) => {
					dialog.hide();
					const esc = (text) => frappe.utils.escape_html(text);
					const lines = [__("{0} interviews scheduled.", [result.booked.length])];
					if (result.days.length) {
						lines.push(__("On {0}.", [result.days.map(esc).join(", ")]));
					}
					const add = (heading, names) => names.length && lines.push("", heading, ...names.map(esc));
					add(__("Already have this round:"), result.already);
					add(__("No longer in the running:"), result.out);
					add(__("Have not cleared the round before:"), result.not_cleared);
					add(__("Not scheduled:"), result.refused);
					frappe.msgprint(lines.join("<br>"), __("Interviews"));
					frm.reload_doc();
				});
		},
	});
	dialog.show();
}
