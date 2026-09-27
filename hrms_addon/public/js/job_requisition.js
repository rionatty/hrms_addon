// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Job Requisition form, loaded through hooks.py doctype_js (read from
// disk at runtime, so no `bench build` is needed after changing it).
// HRMS ships its own job_requisition.js; both run, this one adds to it.
//
// Connections is the standard Connections tab, placed straight after Job
// Description by the field_order property setter; nothing here touches it.
//
// Picking the Job Title fills the Department from that Job Title's JD
// (job_requisition.get_jd_department), and the Responsibilities, Reporting
// Line and Subordinates (job_requisition.get_job_description). What someone
// has written in those three is only replaced when they say so.
//
// The Headcount section is the gap analysis: the job title's staffing plan,
// the people it has, the positions already being filled and the room left
// (job_requisition.get_headcount, drawn again on every save until it is
// decided). Asking for more than the plan leaves shows a notice.

const HA_JD_FIELDS = ["description", "custom_reporting_line", "custom_subordinates"];
const HA_HEADCOUNT_FIELDS = [
	"custom_staffing_plan",
	"custom_planned_positions",
	"custom_current_headcount",
	"custom_positions_filling",
	"custom_headcount_gap",
	"custom_against_plan",
];
const HA_DECIDED = ["Approved", "Rejected"];

frappe.ui.form.on("Job Requisition", {
	onload(frm) {
		// Requested By = the logged-in user's employee. The server applies
		// the same default in before_validate for anything that is not
		// this form (API, import).
		if (frm.is_new() && !frm.doc.requested_by) {
			frappe
				.xcall("hrms_addon.hrms_addon.job_requisition.get_session_employee")
				.then((employee) => {
					if (employee && !frm.doc.requested_by) {
						frm.set_value("requested_by", employee);
					}
				});
		}
	},
	refresh(frm) {
		// A new requisition that arrives with its Job Title already set
		if (frm.is_new() && frm.doc.designation && ha_jd_blank(frm)) {
			ha_fill_job_description(frm);
		}
		if (frm.is_new() && frm.doc.designation && !frm.doc.department) {
			ha_fill_department(frm);
		}
		ha_headcount_notice(frm);
	},
	designation(frm) {
		if (frm.doc.designation) {
			ha_fill_job_description(frm);
			ha_fill_department(frm);
		}
		ha_fill_headcount(frm);
	},
	company(frm) {
		ha_fill_headcount(frm);
	},
	no_of_positions(frm) {
		ha_fill_headcount(frm);
	},
});

// The gap analysis, as the job title, the company or the number changes;
// a requisition already decided keeps the figures its approvers saw
function ha_fill_headcount(frm) {
	if (HA_DECIDED.includes(frm.doc.workflow_state)) {
		return;
	}
	const asked = [frm.doc.designation, frm.doc.company, frm.doc.no_of_positions];
	if (!frm.doc.designation || !frm.doc.company) {
		return;
	}
	frappe
		.xcall("hrms_addon.hrms_addon.job_requisition.get_headcount", {
			designation: frm.doc.designation,
			company: frm.doc.company,
			no_of_positions: frm.doc.no_of_positions || 0,
			posting_date: frm.doc.posting_date || null,
			requisition: frm.is_new() ? null : frm.doc.name,
		})
		.then((values) => {
			if ([frm.doc.designation, frm.doc.company, frm.doc.no_of_positions].join("|") !== asked.join("|")) {
				return; // changed again while this was on its way
			}
			HA_HEADCOUNT_FIELDS.forEach((field) => (frm.doc[field] = values[field] ?? null));
			frm.refresh_fields(HA_HEADCOUNT_FIELDS);
			ha_headcount_notice(frm, values.over_by || 0);
		});
}

// the notice is this script's own: another one on the form is left alone
function ha_headcount_notice(frm, over_by) {
	const above =
		over_by === undefined ? String(frm.doc.custom_against_plan || "").includes("above the plan") : over_by > 0;
	if (above) {
		frm.set_intro(
			__("This requisition asks for more than the staffing plan allows: {0}.", [frm.doc.custom_against_plan]),
			"orange"
		);
		frm.ha_headcount_intro = true;
	} else if (frm.ha_headcount_intro) {
		frm.set_intro("");
		frm.ha_headcount_intro = false;
	}
}

// The Department comes with the Job Title, from its JD
function ha_fill_department(frm) {
	const designation = frm.doc.designation;
	frappe
		.xcall("hrms_addon.hrms_addon.job_requisition.get_jd_department", { designation })
		.then((department) => {
			if (department && frm.doc.designation === designation && frm.doc.department !== department) {
				frm.set_value("department", department);
			}
		});
}

function ha_fill_job_description(frm) {
	const designation = frm.doc.designation;
	frappe
		.xcall("hrms_addon.hrms_addon.job_requisition.get_job_description", { designation })
		.then((jd) => {
			if (frm.doc.designation !== designation) {
				return; // the Job Title changed again while this was on its way
			}
			if (!HA_JD_FIELDS.some((field) => ha_plain(jd[field]))) {
				frappe.show_alert({ message: __("{0} has no Job Description yet.", [designation]), indicator: "orange" });
				return;
			}
			const fill = () =>
				frm.set_value(jd).then(() => {
					frm.__ha_jd_filled = Object.assign({}, jd);
					frappe.show_alert({ message: __("Job Description filled in from {0}.", [designation]), indicator: "green" });
				});
			if (ha_jd_blank(frm) || ha_jd_as_filled(frm)) {
				fill();
			} else {
				frappe.confirm(
					__("Replace the Job Description tab with the Job Description of {0}? What is written there now will be lost.", [
						designation,
					]),
					fill
				);
			}
		});
}

function ha_jd_blank(frm) {
	return !HA_JD_FIELDS.some((field) => ha_plain(frm.doc[field]));
}

// Still just what was filled in last time, so nothing anyone wrote is lost
function ha_jd_as_filled(frm) {
	const filled = frm.__ha_jd_filled;
	return !!filled && HA_JD_FIELDS.every((field) => ha_plain(frm.doc[field]) === ha_plain(filled[field]));
}

// What a value says, tags and spacing aside; a pasted image counts too.
// DOMParser, not jQuery: its documents run no scripts and load no images,
// whatever the HTML holds.
function ha_plain(value) {
	const body = new DOMParser().parseFromString(String(value || ""), "text/html").body;
	const media = body.querySelectorAll("img, video, iframe, object, embed").length;
	return ((body.textContent || "") + (media ? " [" + media + " media]" : "")).replace(/\s+/g, " ").trim();
}
