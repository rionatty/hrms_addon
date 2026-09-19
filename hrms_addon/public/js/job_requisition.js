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
// Picking the Job Title fills the Job Description tab from that Job Title's
// JD (job_requisition.get_job_description): Responsibilities, Reporting Line
// and Subordinates. What someone has written there is only replaced when
// they say so.

const HA_JD_FIELDS = ["description", "custom_reporting_line", "custom_subordinates"];

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
	},
	designation(frm) {
		if (frm.doc.designation) {
			ha_fill_job_description(frm);
		}
	},
});

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
