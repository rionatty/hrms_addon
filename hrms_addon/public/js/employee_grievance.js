// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The non-disciplinary grievance on Frappe HR's own Employee Grievance
// (grievances.py): its due date while someone has it, and what the next
// button needs filled in first.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

// in someone's hands against the due date (grievance_approval.TIMED), and
// how near the date it is at risk (grievance_rules.AT_RISK_DAYS)
const HA_GRIEVANCE_TIMED = ["Under Review", "Appealed"];
const HA_GRIEVANCE_AT_RISK_DAYS = 2;

frappe.ui.form.on("Employee Grievance", {
	setup(frm) {
		const holders = (roles) => () => ({
			query: "hrms_addon.hrms_addon.grievances.holders_of",
			filters: { roles: roles },
		});
		frm.set_query("custom_assigned_hod", holders(["Head of Department", "HR User", "HR Manager"]));
		frm.set_query("custom_appeals_authority", holders(["General Manager", "HR Manager", "Executive Director"]));
	},
	refresh(frm) {
		ha_grievance_due(frm);
		ha_grievance_intro(frm);
	},
});

function ha_grievance_due(frm) {
	frm.dashboard.clear_headline();
	const due = frm.doc.custom_due_on;
	if (frm.is_new() || !due || !HA_GRIEVANCE_TIMED.includes(frm.doc.workflow_state)) return;
	const left = frappe.datetime.get_day_diff(due, frappe.datetime.get_today());
	const colour = left < 0 ? "red" : left <= HA_GRIEVANCE_AT_RISK_DAYS ? "orange" : "blue";
	const text =
		left < 0
			? __("{0} day(s) overdue", [-left])
			: left === 0
			? __("Due today")
			: __("{0} day(s) left", [left]);
	frm.dashboard.set_headline(
		`<span>${__("Due")} <b>${frappe.datetime.str_to_user(due)}</b></span>` +
			` <span class="indicator-pill ${colour}">${text}</span>`
	);
}

function ha_grievance_intro(frm) {
	frm.set_intro("");
	if (frm.is_new()) return;
	const doc = frm.doc;
	const remarks = frappe.utils.escape_html(doc.custom_return_remarks || "");
	if (doc.workflow_state === "Open" && remarks) {
		frm.set_intro(__("Returned: {0}", [remarks]), "orange");
	} else if (doc.workflow_state === "Under Review" && remarks) {
		frm.set_intro(__("Reopened: {0}", [remarks]), "orange");
	} else if (doc.workflow_state === "Resolved") {
		frm.set_intro(__("Accept, Appeal with its grounds, or Reopen with remarks."), "blue");
	} else if (doc.workflow_state === "Appealed" && doc.custom_appeals_authority) {
		frm.set_intro(__("Heard by {0}.", [frappe.user.full_name(doc.custom_appeals_authority)]), "orange");
	} else if (doc.workflow_state === "Closed") {
		frm.set_intro(__("The outcome is accepted."), "green");
	}
}
